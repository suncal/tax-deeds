"""Shared helpers for every OTC tax-property scraper.

Every county/state site in this project rejects a bare urllib/requests UA with a
403, so all network access goes through get() which sends browser-shaped headers.
"""
import re, time, json, ssl, shutil, subprocess
import urllib.request, urllib.parse, urllib.error

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36')

CURL = shutil.which('curl')


def _curl(url, referer, timeout):
    """Fallback path. Some county servers (delcopa.gov) reject Python's TLS
    handshake with TLSV1_ALERT_PROTOCOL_VERSION but are fine with curl."""
    if not CURL:
        return None
    cmd = [CURL, '-sSL', '--max-time', str(timeout), '-A', UA, '--compressed']
    if referer:
        cmd += ['-H', f'Referer: {referer}']
    cmd.append(url)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
        return p.stdout if p.returncode == 0 and p.stdout else None
    except Exception:
        return None


def get(url, referer=None, timeout=90, retries=3, binary=True):
    """Fetch a URL with browser headers. Returns bytes, or None after retries."""
    hdrs = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/pdf,application/json,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
    }
    if referer:
        hdrs['Referer'] = referer
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if binary else data.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 410):
                last = e
                break                      # not worth retrying
            last = e
        except Exception as e:
            last = e
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))

    data = _curl(url, referer, timeout)
    if data:
        return data if binary else data.decode('utf-8', 'replace')
    print(f'    ! fetch failed {url} :: {last}')
    return None


def get_pdf(url, referer=None, timeout=120, tries=4):
    """Fetch a PDF and verify it is COMPLETE before handing it back.

    A truncated download still opens in PyMuPDF and silently yields fewer rows —
    which is how a 226-row source quietly became 188. Checking for the trailing
    %%EOF marker turns that into a retry instead of missing inventory.
    """
    best = None
    for i in range(tries):
        blob = get(url, referer, timeout=timeout, retries=2)
        if not blob or blob[:4] != b'%PDF':
            time.sleep(1.5 * (i + 1))
            continue
        if b'%%EOF' in blob[-2048:]:
            return blob
        if best is None or len(blob) > len(best):
            best = blob            # keep the longest partial as a last resort
        print(f'    ~ truncated PDF ({len(blob):,} bytes), retrying {url}')
        time.sleep(1.5 * (i + 1))
    if best:
        print(f'    ! never got a complete PDF, using best partial: {url}')
    return best


def get_json(url, referer=None, timeout=90):
    b = get(url, referer, timeout)
    if not b:
        return None
    try:
        return json.loads(b)
    except Exception as e:
        print(f'    ! bad json from {url} :: {e}')
        return None


# ---------------------------------------------------------------- classifying
STRUCT_WORDS = re.compile(
    r'\b(IMPROVEMENT|IMPROVEMENTS|IMPROVED|DWELLING|HOUSE|RESIDENCE|BUILDING|BLDG|'
    r'MOBILE HOME|MANUFACTURED HOME|DOUBLE-?WIDE|TRAILER|APARTMENT|DUPLEX|STORE|'
    r'WAREHOUSE|CABIN|GARAGE|STRUCTURE)\b', re.I)
LAND_WORDS = re.compile(
    r'\b(VACANT|UNIMPROVED|UNDEVELOPED|EMPTY LOT|GRD|GROUND|LOT ONLY|NO HOUSE|'
    r'RAW LAND|ACREAGE|TIMBER|PASTURE)\b', re.I)
MINERAL_WORDS = re.compile(
    r'\b(WORKING INTEREST|MINERAL|ROYALTY|OIL|GAS|LEASE R\d)\b', re.I)

# ptype:  land | building | mineral | unknown      -> "what am I buying"
# repair: none | needed  | unknown                 -> "will it need work"


def classify(text, infer_land=False):
    """Return (ptype, repair, why, confidence) from free text alone."""
    t = text or ''
    if MINERAL_WORDS.search(t):
        return 'mineral', 'none', 'mineral / non-surface interest — no structure exists', 'stated'
    if STRUCT_WORDS.search(t):
        return 'building', 'unknown', 'the listing text names a structure', 'stated'
    if LAND_WORDS.search(t):
        return 'land', 'none', 'the listing text says vacant / land-only', 'stated'
    if infer_land and re.search(r'\b(LOT|LOTS|BLOCK|BLK|TRACT|ACRES?)\b', t, re.I) and len(t) > 15:
        return 'land', 'none', 'legal description is a bare lot/tract, no improvements named', 'inferred'
    return 'unknown', 'unknown', 'the source list does not say whether a structure exists', 'unknown'
