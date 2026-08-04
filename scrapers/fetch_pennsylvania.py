"""Pennsylvania repository-of-unsold-properties lists.

Repository parcels failed BOTH the upset sale and the judicial sale, so they are
sold free and clear of delinquent taxes and liens — genuinely rare in tax sales.
Bids are a flat county-set minimum and can be submitted any time.

Delaware County is the one with a machine-readable list and, usefully, street
addresses plus a "GRD" (ground only, no structure) flag.
"""
import re
from concurrent.futures import ThreadPoolExecutor
import fitz
from common import get, get_pdf

PARCEL = re.compile(r'^\d{2}-\d{2}-\d{5}-\d{2}$')
GRD = re.compile(r'\bGRD\b|\bGROUND\b|grassy|vacant|empty lot', re.I)
HAS_NO = re.compile(r'^\d+[-\d]*\s+\S')

SOURCES = [{
    'county': 'Delaware County',
    'page': 'https://www.delcopa.gov/treasurer/repositorysale',
    'pattern': r'href="(/sites/default/files/[^"]*Repository[^"]*List[^"]*\.pdf)"',
    'base': 'https://www.delcopa.gov',
    'min_bid': 1000.0,
    'price_label': 'Bid starts at $1,000, plus a $250 demolition/rehab fund fee (from 1 Jan 2026)',
}]


def parse(blob, src):
    try:
        doc = fitz.open(stream=blob, filetype='pdf')
    except Exception:
        return []
    rows, muni, updated, pend = [], '', '', None
    for pno in range(len(doc)):
        for ln in doc[pno].get_text().split('\n'):
            s = ln.strip()
            if not s:
                continue
            m = re.search(r'UPDATED\s+([\d/]+)', s, re.I)
            if m:
                updated = m.group(1)
            if PARCEL.match(s.replace(' ', '')):
                pend = s.replace(' ', '')
                continue
            if pend:
                is_grd = bool(GRD.search(s))
                has_no = bool(HAS_NO.match(s))
                if is_grd:
                    ptype, repair, why, conf = ('land', 'none',
                        'the county marks it GRD — ground only, no structure', 'stated')
                elif has_no:
                    ptype, repair, why, conf = ('building', 'unknown',
                        'a street number is listed and it is not flagged GRD', 'inferred')
                else:
                    ptype, repair, why, conf = ('unknown', 'unknown',
                        'no GRD flag and no street number — verify with the county', 'unknown')
                rows.append({
                    'state': 'PA', 'state_name': 'Pennsylvania',
                    'program': 'Repository of unsold properties — bid form, any time, free and clear',
                    'jurisdiction': f"{src['county']} — {muni.title()}" if muni else src['county'],
                    'price': src['min_bid'], 'price_label': src['price_label'],
                    'market_value': None,
                    'value_label': 'Not on the repository list — pull assessed value from the county',
                    'value_is_published': False, 'discount_pct': None,
                    'price_is_quoted': True,
                    'parcel': pend,
                    'legal': s,
                    'address': re.sub(r'\s*\(.*?\)\s*', ' ', s).strip(),
                    'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
                    'list_updated': updated,
                    'source_name': f"{src['county']} PA Tax Claim Bureau repository list",
                    'source_url': src['url'], 'source_page': pno + 1,
                })
                pend = None
                continue
            if s.isupper() and len(s) < 40 and not any(c.isdigit() for c in s):
                muni = s
    return rows


def one(src):
    html = get(src['page'], binary=False)
    if not html:
        return []
    m = re.search(src['pattern'], html, re.I)
    if not m:
        return []
    url = src['base'] + m.group(1) if m.group(1).startswith('/') else m.group(1)
    blob = get_pdf(url, referer=src['page'])
    if not blob or blob[:4] != b'%PDF':
        return []
    src = dict(src, url=url)
    return parse(blob, src)


def run():
    rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(one, SOURCES):
            rows.extend(r)
    return rows, None if rows else 'Pennsylvania: no repository list parsed'


if __name__ == '__main__':
    r, e = run()
    print(len(r), 'rows', e or '')
