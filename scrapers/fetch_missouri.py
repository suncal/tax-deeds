"""Kansas City, Missouri — Land Bank of Kansas City / Homesteading Authority.

Published on the city's Socrata portal with BOTH an asking price and the county
market value, so the discount is a real published number rather than an estimate.

The Land Bank prices by policy at two-thirds of market value, so nearly every
parcel shows the same ~33% discount. That is not a bug in the data: it is the
programme. It also means the interesting variable here is not the discount but
which parcels are improved (an actual house) and where they are.

Buy-it-now: submit an offer through the Land Bank. No auction.
"""
import json
from common import get_json, classify

SRC = 'https://data.kcmo.org/resource/4257-6mtc.json'
PAGE = 5000


def truthy(v):
    return str(v).strip().lower() in ('true', 'yes', 'y', '1')


def run():
    rows, off = [], 0
    while True:
        d = get_json(f'{SRC}?$limit={PAGE}&$offset={off}')
        if d is None:
            return [], ('Kansas City open-data portal did not respond. This is an '
                        'outage on data.kcmo.org, not a parsing problem.')
        rows += d
        if len(d) < PAGE:
            break
        off += PAGE
        if off > 60000:
            break
    if not rows:
        return [], 'Kansas City Land Bank: dataset returned no records'

    out = []
    for r in rows:
        if not truthy(r.get('available')) or not truthy(r.get('active')):
            continue
        try:
            price = float(r.get('asking_price') or 0)
            mv = float(r.get('market_value') or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        mv = mv if mv > 0 else None

        cls = (r.get('property_class') or '').strip()
        low = cls.lower()
        if 'improv' in low:
            ptype, repair, why, conf = ('building', 'unknown',
                'the Land Bank classes this parcel as improved — a structure stands on it', 'stated')
        elif 'vacant' in low or 'land' in low:
            ptype, repair, why, conf = ('land', 'none',
                'the Land Bank classes this parcel as vacant', 'stated')
        else:
            ptype, repair, why, conf = classify(cls)

        addr = ' '.join(str(r.get(k) or '').strip()
                        for k in ('address', 'street_address')).strip()
        if not addr:
            addr = (r.get('location_1_address') or '').strip()
        city = (r.get('city') or 'Kansas City').strip()
        if addr and city.lower() not in addr.lower():
            addr = f'{addr}, {city} MO'

        sqft = r.get('parcel_square_footage')
        try:
            acres = round(float(sqft) / 43560, 3) if sqft and float(sqft) > 0 else None
        except (TypeError, ValueError):
            acres = None

        out.append({
            'state': 'MO', 'state_name': 'Missouri',
            'program': 'Land Bank of Kansas City — buy-it-now by offer, no auction',
            'jurisdiction': f'Jackson County — {city}',
            'price': round(price, 2),
            'price_label': 'Land Bank asking price (set by policy at two-thirds of market value)',
            'market_value': round(mv, 2) if mv else None,
            'value_label': 'County market value, published by the Land Bank beside its asking price',
            'value_is_published': mv is not None,
            'discount_pct': round((mv - price) / mv * 100, 1) if mv else None,
            'price_is_quoted': True,
            'parcel': (r.get('parcel_number') or '').strip(),
            'legal': cls or 'Land Bank parcel',
            'address': addr,
            'acres': acres,
            'cls': cls,
            'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
            'list_updated': (r.get('property_status_date') or '')[:10],
            'source_name': 'Land Bank of Kansas City (data.kcmo.org)',
            'source_url': 'https://data.kcmo.org/Housing/Land-Bank-and-Homesteading-Authority-Data/4257-6mtc',
            'source_page': None,
        })
    return out, None


if __name__ == '__main__':
    r, e = run()
    print(len(r), 'rows', e or '')
    print(json.dumps(r[:2], indent=1))
