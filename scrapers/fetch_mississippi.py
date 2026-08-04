"""Mississippi Secretary of State — statewide tax-forfeited inventory.

The public map at tflgis.sos.ms.gov is an ArcGIS JS app that talks to an
enterprise portal using a short-lived token embedded in the page as
<input id="tk" value="...">. So: scrape the token, resolve the web map to its
FeatureServer, then page through the layer.

This is the richest source in the project — it publishes market value, the
accumulated tax/fee total, a street address, acreage and a blighted flag.
"""
import re, json
from common import get, get_json, classify

HOME = 'https://tflgis.sos.ms.gov/'
PORTAL = 'https://gisportal.its.ms.gov/portal/sharing/rest'
FIELDS = ('county,parcel_number,ppin_number,legal_description,subdivision,'
          'propertyaddress,city,zip,acres,square_feet,market_value,sumoftaxfees,'
          'blighted,tidelands,parcel_status_description,certificatetaxyear,'
          'municipality_name,sosparno')
PAGE = 3000

LOT_NOTE = re.compile(r'\((?:[^)]*\b(lot|vacant|empty|undeveloped|no house|no access)\b[^)]*)\)', re.I)
HAS_STREET_NO = re.compile(r'^\s*\d+[-\w]*\s+\w')


def classify_ms(r):
    addr = r.get('propertyaddress') or ''
    legal = r.get('legal_description') or ''
    if str(r.get('blighted') or '') == '1':
        return ('building', 'needed',
                'Mississippi SoS flags this parcel as BLIGHTED — a deteriorated structure', 'stated')
    if LOT_NOTE.search(addr):
        return ('land', 'none',
                'the state annotates the address as a vacant / empty lot', 'stated')
    p, rep, why, conf = classify(legal)
    if p != 'unknown':
        return p, rep, why, conf
    mv = r.get('market_value') or 0
    if HAS_STREET_NO.match(addr):
        # A street number alone proves nothing — vacant lots get numbers too. But a
        # number plus a county value well above bare-lot money points to a structure.
        if mv >= 20000:
            return ('building', 'unknown',
                    f'street number plus a ${mv:,.0f} county value — high for a bare lot here', 'inferred')
        return 'unknown', 'unknown', 'has a street number but too low a value to call it', 'unknown'
    if re.search(r'[A-Za-z]{3}', addr):
        # Street named, no street number. Municipalities assign numbers to
        # structures, so this asymmetric case is a reliable read for vacant land.
        return ('land', 'none',
                'the state lists a street but no street number — numbers are assigned to structures', 'inferred')
    return 'unknown', 'unknown', 'the state list does not say whether a structure exists', 'unknown'


def run():
    html = get(HOME, binary=False)
    if not html:
        return [], 'Mississippi SoS: home page unreachable'
    tk = re.search(r'id="tk"[^>]*value="([^"]+)"', html)
    mapid = re.search(r'id="mapid"[^>]*value="([^"]+)"', html)
    if not (tk and mapid):
        return [], 'Mississippi SoS: could not read map token from the page'
    tk, mapid = tk.group(1), mapid.group(1)

    wm = get_json(f'{PORTAL}/content/items/{mapid}/data?f=json&token={tk}')
    layer = None
    for l in (wm or {}).get('operationalLayers', []):
        if l.get('url'):
            layer = l['url']
            break
    if not layer:
        return [], 'Mississippi SoS: web map exposed no feature layer'

    feats, off = [], 0
    while True:
        q = (f'{layer}/query?where=1%3D1&outFields={FIELDS}&returnGeometry=false'
             f'&resultOffset={off}&resultRecordCount={PAGE}&f=json&token={tk}')
        d = get_json(q)
        got = (d or {}).get('features', [])
        feats += got
        if len(got) < PAGE:
            break
        off += PAGE
        if off > 60000:
            break

    rows = []
    for f in feats:
        a = f.get('attributes', {})
        mv = a.get('market_value')
        price = a.get('sumoftaxfees')
        if not price or price <= 0:
            continue
        mv = mv if (mv and mv > 0) else None
        ptype, repair, why, conf = classify_ms(a)
        addr = re.sub(r'\s+', ' ', (a.get('propertyaddress') or '')).strip()
        county = (a.get('county') or '').strip()
        rows.append({
            'state': 'MS', 'state_name': 'Mississippi',
            'program': 'Tax-forfeited inventory — apply to purchase online, any time',
            'jurisdiction': f'{county} County' if county else 'Mississippi',
            'price': round(price, 2),
            'price_label': 'Accumulated taxes + fees (the statutory floor — the SoS sets the final price '
                           'and may require an appraisal on higher-value parcels)',
            'market_value': round(mv, 2) if mv else None,
            'value_label': "County market value, published by the state in its own parcel record",
            'value_is_published': mv is not None,
            'discount_pct': round((mv - price) / mv * 100, 1) if mv else None,
            'parcel': (a.get('parcel_number') or a.get('sosparno') or '').strip(),
            'legal': re.sub(r'\s+', ' ', (a.get('legal_description') or ''))[:280],
            'address': addr,
            'acres': round(a['acres'], 3) if a.get('acres') else None,
            'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
            'list_updated': 'live query',
            'source_name': 'Mississippi Secretary of State — tax-forfeited inventory',
            'source_url': 'https://tflgis.sos.ms.gov/',
            'source_page': None,
        })
    return rows, None


if __name__ == '__main__':
    r, err = run()
    print(len(r), 'rows', err or '')
    print(json.dumps(r[:2], indent=1))
