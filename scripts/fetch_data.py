"""Download attributable IPL sources. Run from the project root; cached by default."""
import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'outputs' / 'ipl-data'
# The portable pack keeps scripts/config in pipeline/ beside ipl-data/.
if ROOT.name == 'pipeline' and (ROOT.parent / 'ipl-data').is_dir():
    DATA = ROOT.parent / 'ipl-data'
RAW = DATA / 'raw'
TEAMS = {
    'CSK': 'chennai-super-kings', 'DC': 'delhi-capitals',
    'GT': 'gujarat-titans', 'KKR': 'kolkata-knight-riders',
    'LSG': 'lucknow-super-giants', 'MI': 'mumbai-indians',
    'PBKS': 'punjab-kings', 'RR': 'rajasthan-royals',
    'RCB': 'royal-challengers-bengaluru', 'SRH': 'sunrisers-hyderabad',
}
SOURCES = [
    ('cricsheet/ipl_json.zip', 'https://cricsheet.org/downloads/ipl_json.zip', 'Cricsheet match archive; retain bundled license notice'),
    ('cricsheet/people.csv', 'https://cricsheet.org/register/people.csv', 'Open Data Commons Attribution 1.0'),
    ('cricsheet/names.csv', 'https://cricsheet.org/register/names.csv', 'Open Data Commons Attribution 1.0'),
    ('cricsheet/downloads.html', 'https://cricsheet.org/downloads/', 'Reference snapshot'),
    ('cricsheet/register.html', 'https://cricsheet.org/register/', 'Reference snapshot'),
    ('cricsheet/format.json.html', 'https://cricsheet.org/format/json/', 'Reference snapshot'),
    ('cricketdata/player_meta.rda', 'https://raw.githubusercontent.com/robjhyndman/cricketdata/master/data/player_meta.rda', 'cricketdata package GPL-3; upstream ESPN data terms separately apply'),
    ('cricketdata/DESCRIPTION', 'https://raw.githubusercontent.com/robjhyndman/cricketdata/master/DESCRIPTION', 'Package source/license record'),
    ('cricketdata/data.R', 'https://raw.githubusercontent.com/robjhyndman/cricketdata/master/R/data.R', 'Metadata snapshot date documentation'),
    ('ipl/playing-conditions.html', 'https://www.iplt20.com/playing-conditions', 'Official IPL reference; website terms apply'),
    ('ipl/TATA_IPL_2026_Match_Playing_Conditions_current.pdf', 'https://www.iplt20.com/cms/files/jot2qw8s50z1/7DScv8UxUc6AJcrXDon2yW/bdc93c1c438bfafad464f2a334862d59/1775736835406_TATA_IPL_2026_Match_Playing_Conditions.pdf', 'Official 2026 playing conditions linked in the public IPL page; source terms apply'),
    ('ipl/terms.html', 'https://www.iplt20.com/terms-and-conditions', 'Official website terms'),
]
SOURCES += [(f'ipl/squads/{code}.html', f'https://www.iplt20.com/teams/{slug}/squad', 'Official IPL squad snapshot; website terms apply') for code, slug in TEAMS.items()]
SOURCES += [(f'ipl/squads/{code}.json', f'https://www.iplt20.com/api/bff/cms/teams/{slug}?tab=squad', 'Official IPL complete squad snapshot; website terms apply') for code, slug in TEAMS.items()]

def fetch(item, refresh=False):
    relative, url, license_note = item
    target = RAW / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {'file': f'raw/{relative}', 'source_url': url, 'license_note': license_note}
    if target.exists() and not refresh:
        record['status'] = 'cached'
        record['retrieved_at_utc'] = datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat()
    else:
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'IPLResearchDataset/0.1'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                    record['http_status'] = response.status
                    record['content_type'] = response.headers.get('Content-Type')
                    record['last_modified'] = response.headers.get('Last-Modified')
                # Archive / structured sources must never contain error HTML.
                if relative.endswith('.zip') and not body.startswith(b'PK'):
                    raise ValueError('Source did not return a ZIP archive')
                if relative.endswith('.rda') and body.lstrip().startswith(b'<'):
                    raise ValueError('Source did not return R data')
                if relative.endswith('.pdf') and not body.startswith(b'%PDF-'):
                    raise ValueError('Source did not return a PDF')
                target.write_bytes(body)
                record.update(status='downloaded', retrieved_at_utc=datetime.now(timezone.utc).isoformat())
                break
            except Exception as error:
                if attempt == 2 or '403' in str(error):
                    record.update(status='failed', error=str(error))
                    return record
                time.sleep(attempt + 1)
    record['bytes'] = target.stat().st_size
    record['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    return record

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda x: fetch(x, args.refresh), SOURCES))
    (DATA / 'source_manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    for r in records:
        print(r['status'], r['file'], r.get('bytes', r.get('error')), flush=True)
    if any(r['status'] == 'failed' for r in records):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
