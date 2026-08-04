"""Texas struck-off / tax-resale lists published by Perdue Brandon Fielder
Collins & Mott, county tax counsel for much of the state.

This is the only source in the project where BOTH numbers are published by the
government: the court-appraised value at time of judgment and the minimum bid.
So the discount is a fact, not an estimate.

Two parsers, because the lists are not consistently formatted:
  1. ruled tables  -> PyMuPDF find_tables()
  2. whitespace-aligned tables -> positional pass anchored on the header words
"""
import re, os, time
from concurrent.futures import ThreadPoolExecutor
import fitz
from common import get, get_pdf, classify

INDEX = 'https://www.pbfcm.com/taxresale.html'
MONEY = re.compile(r'\$\s?([\d,]+(?:\.\d{1,2})?)')
MONEY_TOK = re.compile(r'^\$[\d,]+(?:\.\d{1,2})?$')
ACCT_TOK = re.compile(r'^[A-Z]?\d[\dA-Z\-./]{3,}$')

# Chambers' list interleaves multi-tract sub-lists that break row pairing.
SKIP = {'chamberscountytaxresale.pdf'}

NAMES = {
    'austintaxresale.pdf': 'Austin County', 'dimmittaxresale.pdf': 'Dimmit County',
    'fortbendisdtaxresale.pdf': 'Fort Bend ISD (Fort Bend County)',
    'mavericktaxresale.pdf': 'Maverick County',
    'nacogdochescountytaxresale.pdf': 'Nacogdoches County',
    'needvilleisdtaxresale.pdf': 'Needville ISD (Fort Bend County)',
    'sanjacintocountytaxresale.pdf': 'San Jacinto County',
    'smithcountytaxresale.pdf': 'Smith County', 'uvaldecountytaxresale.pdf': 'Uvalde County',
    'walkercountytaxresale.pdf': 'Walker County', 'wallercountytaxresale.pdf': 'Waller County',
    'washingtoncountytaxresale.pdf': 'Washington County', 'woodtaxresale.pdf': 'Wood County',
    'zavalalapryorisd.pdf': 'Zavala County — La Pryor ISD',
    'zavalauvaldecisd.pdf': 'Zavala County — Uvalde CISD',
    'dickinsonisdtaxresale.pdf': 'Dickinson ISD (Galveston County)',
    'magnoliaisdtaxresale.pdf': 'Magnolia ISD (Montgomery County)',
    'matagordacountytaxresale.pdf': 'Matagorda County',
    'montgomerycountyutilitytaxresale.pdf': 'Montgomery County utility districts',
    'santafeisdtaxresale.pdf': 'Santa Fe ISD (Galveston County)',
}


def money(s):
    vals = [float(v.replace(',', '')) for v in MONEY.findall((s or '').replace('\n', ' '))]
    return max(vals) if vals else None


def norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def pretty(fn):
    if fn in NAMES:
        return NAMES[fn]
    b = fn.replace('.pdf', '').replace('taxresale', '').replace('resale', '')
    b = b.replace('cityof', 'City of ').replace('isd', ' ISD').replace('county', ' County')
    return norm(b.title()) or fn


def header_map(rows):
    ncol = max(len(r) for r in rows)
    joined = [''] * ncol
    for r in rows[:4]:
        for i, c in enumerate(r):
            if c:
                joined[i] += ' ' + c.lower().replace('\n', ' ')
    m = {}
    for i, h in enumerate(joined):
        if 'appraised' in h or 'adjudged' in h or ('value' in h and 'judgment' in h):
            m.setdefault('value', i)
        elif 'minimum bid' in h or 'min bid' in h or 'opening bid' in h:
            m.setdefault('bid', i)
        elif any(k in h for k in ('account', 'property id', 'parcel', 'cad', 'geo')):
            m.setdefault('acct', i)
        elif 'legal' in h or 'description' in h:
            m.setdefault('legal', i)
    return m


def parse_tables(doc, fn):
    out, hmap, updated = [], None, ''
    for pno in range(len(doc)):
        try:
            page = doc[pno]
            txt = page.get_text()
        except Exception:
            continue
        if not updated:
            mu = re.search(r'(?:as of|updated:?)\s*([A-Za-z0-9,/ -]{4,20}\d{4})', txt, re.I)
            if mu:
                updated = norm(mu.group(1))
        try:
            tabs = page.find_tables()
        except Exception:
            continue
        for t in tabs.tables:
            try:
                rows = t.extract()
            except Exception:
                continue
            if not rows or len(rows[0]) < 3:
                continue
            hm = header_map(rows)
            if 'value' in hm and 'bid' in hm:
                hmap = hm
            hm = hmap or hm
            if 'value' not in hm or 'bid' not in hm:
                continue
            for r in rows:
                cells = [norm(c) for c in r]
                blob = ' '.join(cells).lower()
                if 'appraised' in blob and 'bid' in blob:
                    continue
                val = money(cells[hm['value']]) if hm['value'] < len(cells) else None
                bid = money(cells[hm['bid']]) if hm['bid'] < len(cells) else None
                if not val or not bid:
                    continue
                legal = cells[hm['legal']] if hm.get('legal') is not None and hm['legal'] < len(cells) else ''
                acct = cells[hm['acct']] if hm.get('acct') is not None and hm['acct'] < len(cells) else ''
                if len(legal) < 8 and len(acct) < 3:
                    continue
                out.append((val, bid, legal[:400], acct[:40], pno + 1))
    return out, updated


def parse_positional(doc, fn):
    out, updated = [], ''
    col_val = col_bid = None
    for pno in range(len(doc)):
        try:
            page = doc[pno]
            words = page.get_text('words')
        except Exception:
            continue
        if not words:
            continue
        if not updated:
            mu = re.search(r'(?:as of|updated:?)\s*([A-Za-z0-9,/ -]{4,20}\d{4})', page.get_text(), re.I)
            if mu:
                updated = norm(mu.group(1))
        for w in words:
            t = w[4].upper().strip(':')
            cx = (w[0] + w[2]) / 2
            if t in ('APPRAISED', 'ADJUDGED'):
                col_val = cx
            elif t in ('MIN', 'MINIMUM'):
                col_bid = cx
        if col_val is None or col_bid is None or abs(col_val - col_bid) < 20:
            continue
        recs = {}
        for w in words:
            if not MONEY_TOK.match(w[4]):
                continue
            try:
                v = float(w[4].replace('$', '').replace(',', ''))
            except ValueError:
                continue
            if v <= 0:
                continue
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            dv, db = abs(cx - col_val), abs(cx - col_bid)
            if min(dv, db) > 75:
                continue
            key = 'value' if dv < db else 'price'
            slot = next((y for y in recs if abs(y - cy) < 12), None)
            if slot is None:
                recs[cy] = {}
                slot = cy
            recs[slot].setdefault(key, v)
        rows = sorted((y, d) for y, d in recs.items() if 'value' in d and 'price' in d)
        left_x = min(col_val, col_bid) - 15
        right_x = max(col_val, col_bid) + 30
        prev_y = 0
        for i, (y, d) in enumerate(rows):
            nxt = rows[i + 1][0] if i + 1 < len(rows) else 1e9
            band = [w for w in words if w[2] < left_x
                    and prev_y - 8 <= (w[1] + w[3]) / 2 < min(y + 40, nxt - 4)]
            band.sort(key=lambda w: ((w[1] + w[3]) / 2 // 6, w[0]))
            legal = norm(' '.join(w[4] for w in band))
            acct = next((w[4] for w in words
                         if w[0] > right_x and abs((w[1] + w[3]) / 2 - y) < 12
                         and ACCT_TOK.match(w[4])), '')
            prev_y = y
            if len(legal) < 15 and not acct:
                continue
            out.append((d['value'], d['price'], legal[:400], acct[:40], pno + 1))
    return out, updated


def one(path):
    fn = os.path.basename(path)
    if fn in SKIP:
        return []
    # pbfcm throttles: a concurrent burst returns empty bodies, which silently
    # costs whole counties. Retry the file itself, not just the HTTP request.
    blob = None
    for _ in range(3):
        blob = get_pdf(f'https://www.pbfcm.com/{path}', referer=INDEX)
        if blob and blob[:4] == b'%PDF':
            break
        time.sleep(3)
    if not blob or blob[:4] != b'%PDF':
        print(f'    ! gave up on {fn}')
        return []
    try:
        doc = fitz.open(stream=blob, filetype='pdf')
    except Exception:
        return []
    recs, updated = parse_tables(doc, fn)
    if not recs:
        recs, updated = parse_positional(doc, fn)
    rows = []
    for val, bid, legal, acct, page in recs:
        if val < 500 or bid <= 0:
            continue
        ptype, repair, why, conf = classify(legal, infer_land=True)
        rows.append({
            'state': 'TX', 'state_name': 'Texas',
            'program': 'Struck-off / tax resale — private sale by bid form, any time',
            'jurisdiction': pretty(fn),
            'price': round(bid, 2),
            'price_label': 'Minimum bid at the original tax sale',
            'market_value': round(val, 2),
            'value_label': 'Court-appraised value at time of judgment, published by the county',
            'value_is_published': True,
            'discount_pct': round((val - bid) / val * 100, 1),
            'price_is_quoted': True,
            'parcel': acct, 'legal': legal, 'address': '',
            'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
            'list_updated': updated,
            'source_name': 'Perdue Brandon Fielder Collins & Mott (county tax counsel)',
            'source_url': f'https://www.pbfcm.com/{path}', 'source_page': page,
        })
    return rows


def run():
    html = get(INDEX, binary=False)
    if not html:
        return [], 'Texas / pbfcm.com: index page unreachable'
    paths = sorted(set(re.sub(r'^/', '', p) for p in
                       re.findall(r'[a-zA-Z0-9./_-]*taxdocs/resales/[a-zA-Z0-9._-]+\.pdf', html)))
    if not paths:
        return [], 'Texas / pbfcm.com: no resale PDFs linked on the index'
    rows = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        for r in ex.map(one, paths):
            rows.extend(r)
    seen, ded = set(), []
    for r in rows:
        k = (r['jurisdiction'], r['parcel'], r['market_value'], r['price'], r['legal'][:80])
        if k in seen:
            continue
        seen.add(k)
        ded.append(r)
    return ded, None if ded else 'Texas / pbfcm.com: PDFs fetched but nothing parsed'


if __name__ == '__main__':
    r, e = run()
    print(len(r), 'rows', e or '')
