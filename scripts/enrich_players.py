"""Download public ESPN athlete profiles for IPL players, with bounded concurrency."""
import csv
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from fetch_data import DATA, RAW, fetch

def main():
    register=list(csv.DictReader((RAW/'cricsheet/people.csv').open(encoding='utf-8')))
    reg={r['identifier']:r for r in register}
    ids=set()
    with zipfile.ZipFile(RAW/'cricsheet/ipl_json.zip') as z:
        for file in z.namelist():
            if not file.endswith('.json'): continue
            info=json.loads(z.read(file))['info']
            for names in info['players'].values():
                ids.update(info['registry']['people'][n] for n in names)
    current=list(csv.DictReader((DATA/'processed/players.csv').open(encoding='utf-8')))
    cricinfo_ids={reg[pid]['key_cricinfo'] for pid in ids if reg.get(pid,{}).get('key_cricinfo')}
    cricinfo_ids.update(r['cricinfo_id'] for r in current if r.get('ipl_player_id') and r.get('cricinfo_id'))
    items=[(f'espn/athletes/{pid}.json', f'http://core.espnuk.org/v2/sports/cricket/athletes/{pid}', 'ESPN public athlete facts; ESPN terms separately apply') for pid in sorted(cricinfo_ids)]
    records=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(fetch,item) for item in items]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records)%100==0: print(f'Profiles saved/checked: {len(records)}/{len(items)}',flush=True)
    countries=set()
    for path in (RAW/'espn/athletes').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'))
        if d.get('country'): countries.add(str(d['country']))
    items=[(f'espn/countries/{c}.json',f'http://core.espnuk.org/v2/sports/cricket/teams/{c}','ESPN country lookup; website terms apply') for c in countries]
    with ThreadPoolExecutor(max_workers=4) as pool: records.extend(pool.map(fetch,items))
    (DATA/'enrichment_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps({'downloaded_or_cached':sum(r['status']!='failed' for r in records),'failed':[r for r in records if r['status']=='failed']}),flush=True)

if __name__=='__main__': main()
