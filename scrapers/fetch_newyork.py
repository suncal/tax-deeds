"""Albany County, New York — Albany County Land Bank Corporation inventory.

Published as an open ArcGIS layer with a real asking price and a street address.

IMPORTANT, and the reason this file filters hard: the published export is titled
"All Property" and contains ~1,070 parcels the Land Bank has ALREADY SOLD, still
carrying their old asking price and now owned by private individuals, churches
and LLCs. Listing those would tell a reader that somebody's home is buyable for
$600. Only Inventory_Type 'Land Bank' / 'ACLB Holdings LLC' is actually for sale,
so that is all this scraper emits.
"""
import json, urllib.parse
from common import get_json

LAYER = ('https://services5.arcgis.com/rhmvOR2TDsslEybT/arcgis/rest/services/'
         '2026_02_04_ACLB_All_Property_Export/FeatureServer/0')
FOR_SALE = ("Inventory_Type IN ('Land Bank','ACLB Holdings LLC')")
FIELDS = ('Name,Owner,Inventory_Type,Street_Address,City,Property_Class,General_Zoning,'
          'Zip_Code,Neighborhood,Asking_Price,School_District,Parcel_Acres')


def run():
    q = (f'{LAYER}/query?where={urllib.parse.quote(FOR_SALE)}&outFields={FIELDS}'
         f'&returnGeometry=false&resultRecordCount=4000&f=json')
    d = get_json(q)
    if d is None:
        return [], ('The Albany County Land Bank ArcGIS layer did not respond. '
                    'Outage on their side, not a parsing problem.')
    feats = d.get('features')
    if feats is None:
        return [], f"Albany County Land Bank layer returned no features ({str(d)[:120]})"

    out = []
    for f in feats:
        a = f.get('attributes', {})
        try:
            price = float(a.get('Asking_Price') or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue          # unpriced holdings are not on the market yet

        cls = (a.get('Property_Class') or '').strip()
        low = cls.lower()
        if 'vacant' in low or 'lot' in low:
            ptype, repair, why, conf = ('land', 'none',
                f'the Land Bank classes this as "{cls}"', 'stated')
        elif 'building' in low or 'structure' in low:
            ptype, repair, why, conf = ('building', 'unknown',
                f'the Land Bank classes this as "{cls}"', 'stated')
        else:
            ptype, repair, why, conf = ('unknown', 'unknown',
                'the Land Bank does not state whether a structure stands here', 'unknown')

        city = (a.get('City') or 'Albany').strip()
        street = (a.get('Street_Address') or '').strip()
        zipc = a.get('Zip_Code')
        addr = ', '.join(x for x in [street, f'{city} NY {zipc or ""}'.strip()] if x)

        acres = a.get('Parcel_Acres')
        try:
            acres = round(float(acres), 3) if acres else None
        except (TypeError, ValueError):
            acres = None

        out.append({
            'state': 'NY', 'state_name': 'New York',
            'program': 'Albany County Land Bank — buy by application, no auction',
            'jurisdiction': f'Albany County — {city}',
            'price': round(price, 2),
            'price_label': 'Land Bank asking price (a real quote, not a statutory floor)',
            'market_value': None,
            'value_label': 'Not published by the Land Bank — pull assessed value from the county',
            'value_is_published': False, 'discount_pct': None,
            'price_is_quoted': True,
            'parcel': (a.get('Name') or '').strip(),
            'legal': ' · '.join(x for x in [cls, a.get('General_Zoning'),
                                            a.get('Neighborhood')] if x),
            'address': addr,
            'acres': acres,
            'cls': cls,
            'ptype': ptype, 'repair': repair, 'bucket_why': why, 'bucket_conf': conf,
            'list_updated': 'live query',
            'source_name': 'Albany County Land Bank Corporation (open ArcGIS layer)',
            'source_url': 'https://albanycountylandbank.org/properties/',
            'source_page': None,
        })
    return out, None


if __name__ == '__main__':
    r, e = run()
    print(len(r), 'rows', e or '')
    print(json.dumps(r[:2], indent=1))
