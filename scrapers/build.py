#!/usr/bin/env python3
"""Run every scraper, merge, and write ../data.json for the dashboard.

Repeated strings (program blurbs, price labels, source names/URLs, jurisdiction
names) are interned into lookup tables and referenced by index — without that the
payload is ~20 MB of duplicated prose for ~22k rows.

A source that fails does NOT fail the build: it is recorded in meta.sources with
an error, the page renders the rest, and the failure is shown to the user rather
than silently dropping inventory.
"""
import json, os, sys, datetime, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_alabama, fetch_texas, fetch_pennsylvania, fetch_mississippi

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data.json')

SOURCES = [
    ('Mississippi Secretary of State — statewide tax-forfeited inventory', fetch_mississippi),
    ('Alabama Dept. of Revenue — 68 county transcripts', fetch_alabama),
    ('Texas struck-off resale lists (Perdue Brandon)', fetch_texas),
    ('Pennsylvania repository lists', fetch_pennsylvania),
]

# Programs where the published number IS the price you can actually pay today.
# Mississippi publishes only the accumulated tax/fee floor; the SoS sets the
# final price and can require an appraisal, so MS discounts are indicative.
DEFAULT_QUOTED = {'TX': True, 'PA': True, 'AL': False, 'MS': False}


def main():
    rows, status = [], []
    for name, mod in SOURCES:
        t0 = datetime.datetime.now()
        try:
            got, err = mod.run()
        except Exception:
            got, err = [], traceback.format_exc(limit=2).strip().splitlines()[-1]
        secs = (datetime.datetime.now() - t0).total_seconds()
        status.append({'name': name, 'rows': len(got), 'error': err,
                       'seconds': round(secs, 1)})
        print(f'{name}: {len(got)} rows in {secs:.1f}s {"ERROR: "+err if err else ""}')
        rows.extend(got)

    if not rows:
        print('FATAL: every source failed; refusing to overwrite data.json')
        return 1

    # ---- intern repeated strings -------------------------------------------
    tables = {'program': [], 'price_label': [], 'value_label': [], 'jurisdiction': [],
              'source_name': [], 'source_url': [], 'bucket_why': [], 'cls': []}
    index = {k: {} for k in tables}

    def intern(field, val):
        val = val or ''
        d, t = index[field], tables[field]
        if val not in d:
            d[val] = len(t)
            t.append(val)
        return d[val]

    out = []
    for i, r in enumerate(rows):
        quoted = r.get('price_is_quoted', DEFAULT_QUOTED.get(r['state'], False))
        out.append({
            'i': i,
            's': r['state'],
            'j': intern('jurisdiction', r['jurisdiction']),
            'pg': intern('program', r['program']),
            'p': r['price'],
            'pl': intern('price_label', r['price_label']),
            'mv': r.get('market_value'),
            'vl': intern('value_label', r['value_label']),
            'd': r.get('discount_pct'),
            'q': 1 if quoted else 0,
            'pt': r['ptype'],
            'rp': r['repair'],
            'w': intern('bucket_why', r['bucket_why']),
            'c': r['bucket_conf'],
            'pa': r.get('parcel', ''),
            'a': r.get('address', ''),
            'l': r.get('legal', ''),
            'ac': r.get('acres'),
            'cl': intern('cls', r.get('cls', '')),
            'u': r.get('list_updated', ''),
            'sn': intern('source_name', r['source_name']),
            'su': intern('source_url', r['source_url']),
            'sp': r.get('source_page'),
        })

    pub = [r for r in out if r['mv']]
    meta = {
        'generated': datetime.datetime.now(datetime.timezone.utc)
                        .strftime('%Y-%m-%d %H:%M UTC'),
        'total': len(out),
        'by_state': {},
        'with_value': len(pub),
        'over19': len([r for r in pub if r['d'] and r['d'] >= 19]),
        'over70': len([r for r in pub if r['d'] and r['d'] >= 70]),
        'jurisdictions': len(tables['jurisdiction']),
        'sources': status,
    }
    for r in out:
        meta['by_state'][r['s']] = meta['by_state'].get(r['s'], 0) + 1

    json.dump({'meta': meta, 'tables': tables, 'rows': out},
              open(OUT, 'w'), separators=(',', ':'))
    mb = os.path.getsize(OUT) / 1e6
    print(f'\nwrote {OUT} — {len(out):,} rows, {mb:.1f} MB')
    print(f'  {meta["with_value"]:,} with a published market value; '
          f'{meta["over19"]:,} at 19%+ off; {meta["over70"]:,} at 70%+ off')
    print(f'  {meta["jurisdictions"]} jurisdictions across {len(meta["by_state"])} states')
    return 0


if __name__ == '__main__':
    sys.exit(main())
