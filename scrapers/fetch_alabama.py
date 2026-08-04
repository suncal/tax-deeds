"""Alabama Dept. of Revenue — statewide transcripts of tax-delinquent land
available for sale (the state's live over-the-counter inventory).

One fixed-column PDF per county, numbered 01-68. Quirk that costs an hour if you
miss it: the dollar amount is printed on the line BELOW the parcel line, and the
legal description wraps onto following lines.
"""
import re, io, json
from concurrent.futures import ThreadPoolExecutor
import fitz
from common import get, get_pdf, classify

BASE = 'https://www.revenue.alabama.gov/wp-content/uploads/property-tax-transcripts/WWW_TRANS_{:02d}.PDF'
REFERER = 'https://www.revenue.alabama.gov/property-tax/tax-delinquent-property-and-land-sales/'

COUNTY = {
    1: 'Jefferson (Birmingham)', 2: 'Mobile', 3: 'Montgomery', 4: 'Autauga', 5: 'Baldwin',
    6: 'Barbour', 7: 'Bibb', 8: 'Blount', 9: 'Bullock', 10: 'Butler', 11: 'Calhoun',
    12: 'Chambers', 13: 'Cherokee', 14: 'Chilton', 15: 'Choctaw', 16: 'Clarke', 17: 'Clay',
    18: 'Cleburne', 19: 'Coffee', 20: 'Colbert', 21: 'Conecuh', 22: 'Coosa', 23: 'Covington',
    24: 'Crenshaw', 25: 'Cullman', 26: 'Dale', 27: 'Dallas', 28: 'DeKalb', 29: 'Elmore',
    30: 'Escambia', 31: 'Etowah', 32: 'Fayette', 33: 'Franklin', 34: 'Geneva', 35: 'Greene',
    36: 'Hale', 37: 'Henry', 38: 'Houston', 39: 'Jackson', 40: 'Lamar', 41: 'Lauderdale',
    42: 'Lawrence', 43: 'Lee', 44: 'Limestone', 45: 'Lowndes', 46: 'Macon', 47: 'Madison',
    48: 'Marengo', 49: 'Marion', 50: 'Marshall', 51: 'Monroe', 52: 'Morgan', 53: 'Perry',
    54: 'Pickens', 55: 'Pike', 56: 'Randolph', 57: 'Russell', 58: 'Shelby', 59: 'St. Clair',
    60: 'Sumter', 61: 'Talladega', 62: 'Tallapoosa', 63: 'Tuscaloosa', 64: 'Walker',
    65: 'Washington', 66: 'Wilcox', 67: 'Winston', 68: 'Jefferson (Bessemer)',
}
CLASS = {'1': 'Utility', '2': 'Commercial / non-owner-occupied',
         '3': 'Ag, forest or owner-occupied residential', '4': 'Vehicles'}

COLS = [('name', 0, 158), ('amt', 158, 242), ('co', 242, 262), ('yr', 262, 282),
        ('cs', 282, 326), ('cls', 326, 355), ('code', 355, 385),
        ('parcel', 385, 470), ('desc', 470, 4000)]


def parse_pdf(blob, code):
    try:
        doc = fitz.open(stream=blob, filetype='pdf')
    except Exception:
        return [], ''
    out, date = [], ''
    for pno in range(len(doc)):
        try:
            words = doc[pno].get_text('words')
        except Exception:
            continue
        if not words:
            continue
        lines = {}
        for w in words:
            y = round(w[1])
            slot = next((k for k in lines if abs(k - y) <= 3), None)
            if slot is None:
                lines[y] = []
                slot = y
            lines[slot].append(w)
        ys = sorted(lines)
        amt_at, desc_at = {}, {}
        for y in ys:
            toks = sorted(lines[y], key=lambda w: w[0])
            money = [w[4] for w in toks if 158 <= w[0] < 242 and re.fullmatch(r'[\d,]+\.\d{2}', w[4])]
            if money:
                amt_at[y] = money[0]
            cont = [w[4] for w in toks if w[0] >= 470]
            if cont:
                desc_at[y] = ' '.join(cont)

        for idx, y in enumerate(ys):
            if y < 100:
                if not date:
                    m = re.search(r'\d{2}/\d{2}/\d{4}', ' '.join(w[4] for w in lines[y]))
                    if m:
                        date = m.group(0)
                continue
            cells = {k: [] for k, _, _ in COLS}
            for w in sorted(lines[y], key=lambda w: w[0]):
                for k, lo, hi in COLS:
                    if lo <= w[0] < hi:
                        cells[k].append(w[4])
                        break
            g = {k: ' '.join(v).strip() for k, v in cells.items()}
            parcel = g['parcel'].replace(' ', '')
            if not re.fullmatch(r'\d{10,26}', parcel):
                continue
            raw = g['amt']
            if not re.fullmatch(r'[\d,]+\.\d{2}', raw):
                raw = ''
                for y2 in ys[idx + 1:]:
                    if y2 - y > 16:
                        break
                    if y2 in amt_at:
                        raw = amt_at[y2]
                        break
            try:
                amt = float(raw.replace(',', ''))
            except ValueError:
                continue
            nxt = next((y2 for y2 in ys[idx + 1:]
                        if any(re.fullmatch(r'\d{10,26}', w[4]) and w[0] >= 385 for w in lines[y2])), None)
            for y2 in ys[idx + 1:]:
                if nxt is not None and y2 >= nxt:
                    break
                if y2 in desc_at:
                    g['desc'] += ' ' + desc_at[y2]
            out.append((amt, parcel, g['cls'], g['yr'], g['cs'],
                        re.sub(r'\s+', ' ', g['desc'])[:200], pno + 1))
    return out, date


def one(code):
    url = BASE.format(code)
    blob = get_pdf(url, referer=REFERER, timeout=180)
    if not blob or not blob[:4] == b'%PDF':
        return []
    parsed, date = parse_pdf(blob, code)
    rows = []
    for amt, parcel, cls, yr, cs, desc, page in parsed:
        # Do NOT infer 'vacant' here: "LOT 11 BLK 4 HOMER HIGHLANDS" is a platted
        # city lot that very often has a house on it. The transcript never says.
        ptype, repair, why, conf = classify(desc, infer_land=False)
        rows.append({
            'state': 'AL', 'state_name': 'Alabama',
            'program': 'State-held tax certificate / tax deed — buy OTC any business day',
            'jurisdiction': COUNTY.get(code, f'County {code}'),
            'price': round(amt, 2),
            'price_label': 'Amount bid at tax sale — the base. Add statutory 12%/yr interest and fees.',
            'market_value': None,
            'value_label': 'Not published on the state transcript — pull it from the county',
            'value_is_published': False, 'discount_pct': None,
            'price_is_quoted': False,
            'parcel': parcel, 'legal': desc, 'address': '',
            'cls': CLASS.get(cls, cls), 'tax_year': yr, 'cert_no': cs,
            'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
            'list_updated': date,
            'source_name': 'Alabama Dept. of Revenue — Property Tax Division transcript',
            'source_url': url, 'source_page': page,
        })
    return rows


def run():
    rows = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for r in ex.map(one, range(1, 69)):
            rows.extend(r)
    if not rows:
        return [], 'Alabama ADOR: no transcripts parsed'
    return rows, None


if __name__ == '__main__':
    r, e = run()
    print(len(r), 'rows', e or '')
