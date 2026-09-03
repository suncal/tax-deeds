#!/usr/bin/env python3
"""Run every scraper, merge, and write ../data.json for the dashboard.

Repeated strings (program blurbs, price labels, source names/URLs, jurisdiction
names) are interned into lookup tables and referenced by index — without that the
payload is ~20 MB of duplicated prose for ~22k rows.

A source that fails does NOT fail the build, and it does not vanish either. Its
rows are carried forward from the previous data.json and flagged stale, so one
agency's outage cannot silently delete a state's worth of inventory or block the
other three sources from refreshing. Staleness is surfaced on the page.
"""
import json, os, sys, datetime, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_alabama, fetch_texas, fetch_pennsylvania, fetch_mississippi
import fetch_missouri, fetch_newyork

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data.json')

SOURCES = [
    ('Mississippi Secretary of State — statewide tax-forfeited inventory', fetch_mississippi),
    ('Alabama Dept. of Revenue — 68 county transcripts', fetch_alabama),
    ('Texas struck-off resale lists (Perdue Brandon)', fetch_texas),
    ('Pennsylvania repository lists', fetch_pennsylvania),
    ('Missouri — Land Bank of Kansas City', fetch_missouri),
    ('New York — Albany County Land Bank', fetch_newyork),
]

# Programs where the published number IS the price you can actually pay today.
# Mississippi publishes only the accumulated tax/fee floor; the SoS sets the
# final price and can require an appraisal, so MS discounts are indicative.
DEFAULT_QUOTED = {'TX': True, 'PA': True, 'MO': True, 'NY': True,
                  'AL': False, 'MS': False}


def load_previous():
    """Return {state: (rows, as_of)} rebuilt from the last published data.json."""
    try:
        d = json.load(open(OUT))
    except Exception:
        return {}
    tb, prev = d.get('tables', {}), {}
    def un(field, idx):
        try:
            return tb[field][idx]
        except Exception:
            return ''
    for r in d.get('rows', []):
        st = r['s']
        prev.setdefault(st, []).append({
            'state': st, 'state_name': r.get('sname', ''),
            'program': un('program', r['pg']),
            'jurisdiction': un('jurisdiction', r['j']),
            'price': r['p'], 'price_label': un('price_label', r['pl']),
            'market_value': r.get('mv'), 'value_label': un('value_label', r['vl']),
            'value_is_published': r.get('mv') is not None,
            'discount_pct': r.get('d'), 'price_is_quoted': bool(r.get('q')),
            'parcel': r.get('pa', ''), 'legal': r.get('l', ''), 'address': r.get('a', ''),
            'acres': r.get('ac'), 'cls': un('cls', r['cl']),
            'ptype': r['pt'], 'repair': r['rp'],
            'bucket_why': un('bucket_why', r['w']), 'bucket_conf': r['c'],
            'list_updated': r.get('u', ''),
            'source_name': un('source_name', r['sn']),
            'source_url': un('source_url', r['su']), 'source_page': r.get('sp'),
            'stale_since': r.get('ss') or d.get('meta', {}).get('generated', '')[:10],
        })
    return prev


# Which state each source owns, so a failure can be back-filled from the last run.
OWNS = {'Mississippi': 'MS', 'Alabama': 'AL', 'Texas': 'TX', 'Pennsylvania': 'PA',
        'Missouri': 'MO', 'New York': 'NY'}


def main():
    rows, status = [], []
    prev = load_previous()
    for name, mod in SOURCES:
        t0 = datetime.datetime.now()
        try:
            got, err = mod.run()
        except Exception:
            got, err = [], traceback.format_exc(limit=2).strip().splitlines()[-1]
        secs = (datetime.datetime.now() - t0).total_seconds()
        st = {'name': name, 'rows': len(got), 'error': err, 'seconds': round(secs, 1),
              'stale': False}

        if not got:
            key = next((k for k in OWNS if name.startswith(k)), None)
            carried = prev.get(OWNS.get(key, ''), []) if key else []
            if carried:
                for r in carried:
                    r.setdefault('stale_since', '')
                got = carried
                st.update(rows=len(got), stale=True,
                          stale_since=carried[0].get('stale_since', ''))
                print(f'{name}: SOURCE DOWN ({err}) — carrying forward '
                      f'{len(got)} rows from {st["stale_since"]}')
            else:
                print(f'{name}: FAILED with no previous data to carry — {err}')
        else:
            print(f'{name}: {len(got)} rows in {secs:.1f}s')
        status.append(st)
        rows.extend(got)

    if not rows:
        print('FATAL: every source failed; refusing to overwrite data.json')
        return 1

    # Mississippi lists a parcel once per outstanding tax certificate, so ~11% of
    # its rows were exact repeats of the same property at the same price. Collapse
    # them; a buyer cares about the parcel, not how many certificates are attached.
    seen, deduped, dropped = set(), [], 0
    for r in rows:
        key = (r['state'], r.get('parcel', ''), r['price'], r.get('market_value'),
               (r.get('address') or r.get('legal') or '')[:60])
        if r.get('parcel') and key in seen:
            dropped += 1
            continue
        seen.add(key)
        deduped.append(r)
    if dropped:
        print(f'deduped {dropped:,} repeated parcels')
    rows = deduped

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
            'ss': r.get('stale_since') or None,
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
        'stale_sources': [s['name'] for s in status if s.get('stale')],
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
