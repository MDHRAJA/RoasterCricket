"""Build the IPL identity/attribute layer, retaining field sources and missing values."""
import csv
import difflib
import json
import re
import sys
import unicodedata
import warnings
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work' / 'vendor'))
import pandas as pd
import rdata
from fetch_data import DATA, RAW, TEAMS

def normalize(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value)).encode('ascii','ignore').decode().lower())

def clean(value):
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()

def primary_role(value):
    n=normalize(value)
    if 'wicketkeeper' in n or n == 'wk': return 'wicketkeeper_batter'
    if 'allround' in n: return 'allrounder'
    if 'bowler' in n: return 'bowler'
    if 'batter' in n or 'batsman' in n: return 'batter'
    return ''

def bowling_traits(style):
    n=normalize(style)
    # Mixed styles remain explicit; assigning a single type would lose information.
    spin=any(k in n for k in ['orthodox','offbreak','offspin','legbreak','legspin','wristspin','googly'])
    pace=any(k in n for k in ['fast','medium'])
    category='mixed' if spin and pace else 'spin' if spin else 'pace' if pace else ''
    left='leftarm' in n
    right='rightarm' in n or ('legbreak' in n and not left)
    arm='mixed' if left and right else 'left' if left else 'right' if right else ''
    return category,arm

def main():
    processed=DATA/'processed'; processed.mkdir(parents=True,exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        meta=rdata.read_rda(RAW/'cricketdata/player_meta.rda')['player_meta']
    meta.columns=[str(c) for c in meta.columns]
    meta['dob']=pd.to_datetime(meta['dob'],unit='D',origin='1970-01-01',errors='coerce').dt.strftime('%Y-%m-%d')
    meta.to_csv(RAW/'cricketdata/player_meta.csv',index=False)
    records={str(r['cricsheet_id']):{k:clean(v) for k,v in r.items()} for r in meta.to_dict('records')}
    people=list(csv.DictReader((RAW/'cricsheet/people.csv').open(encoding='utf-8')))
    register={r['identifier']:r for r in people}
    aliases=defaultdict(set); external=defaultdict(set)
    for p in people:
        for field in ['name','unique_name']:
            aliases[normalize(p[field])].add(p['identifier'])
        for field in ['key_bcci','key_bcci_2','key_pulse','key_pulse_2']:
            if p.get(field): external[p[field]].add(p['identifier'])
    for p in csv.DictReader((RAW/'cricsheet/names.csv').open(encoding='utf-8')):
        aliases[normalize(p['name'])].add(p['identifier'])
    for pid,p in records.items():
        for field in ['full_name','name','unique_name']:
            if p.get(field): aliases[normalize(p[field])].add(pid)
        # First/last names are accepted only when unique; full original names remain saved.
        tokens=re.findall(r'[a-z]+',p.get('full_name','').lower())
        if len(tokens)>=2: aliases[normalize(tokens[0]+tokens[-1])].add(pid)
    for reg in people:
        cid=reg.get('key_cricinfo')
        live_path=RAW/f'espn/athletes/{cid}.json'
        if not cid or not live_path.exists(): continue
        live=json.loads(live_path.read_text(encoding='utf-8'))
        for field in ['name','fullName','displayName']:
            if live.get(field): aliases[normalize(live[field])].add(reg['identifier'])
    participated={}
    historical=[]
    team_season_ids=defaultdict(set)
    with zipfile.ZipFile(RAW/'cricsheet/ipl_json.zip') as archive:
        for file in archive.namelist():
            if not file.endswith('.json'): continue
            info=json.loads(archive.read(file))['info']
            reg=info['registry']['people']
            for team,names in info['players'].items():
                for name in names:
                    pid=reg[name]; participated[pid]=name
                    year=str(info['dates'][0])[:4]
                    historical.append((pid,team,year,info['dates'][0]))
                    team_season_ids[(team,year)].add(pid)
    overrides_path=ROOT/'config/player_identity_overrides.json'
    overrides=json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    squad_rows=[]; identity_issues=[]; official_by_id={}
    for code,slug in TEAMS.items():
        wrapper=json.loads((RAW/f'ipl/squads/{code}.json').read_text(encoding='utf-8'))
        if wrapper.get('status')!=200: raise ValueError(f'Bad squad response {code}')
        team=wrapper['data']
        players=team['squad']['players']
        if len(players)<11: raise ValueError(f'Incomplete squad {code}: {len(players)}')
        for p in players:
            candidates=external[str(p['externalId'])]
            method='register_external_id'
            if len(candidates)!=1:
                candidates=aliases[normalize(p['name'])]; method='unique_exact_alias'
            if len(candidates)>1:
                team_candidates=candidates & team_season_ids[(team['title'],'2026')]
                if len(team_candidates)==1:
                    candidates=team_candidates; method='exact_alias_and_2026_team_history'
            if p['name'] in overrides:
                candidates={overrides[p['name']]}; method='reviewed_override'
            pid=next(iter(candidates)) if len(candidates)==1 else f"ipl:{p['externalId']}"
            if len(candidates)!=1:
                nearby=difflib.get_close_matches(normalize(p['name']),aliases.keys(),n=3,cutoff=.68)
                identity_issues.append({'team':code,'name':p['name'],'ipl_id':p['externalId'],'candidates':[(k,sorted(aliases[k])) for k in nearby]})
            source=f'https://www.iplt20.com/api/bff/cms/teams/{slug}?tab=squad'
            snapshot_date='2026-10-02'
            squad_rows.append({'season':2026,'team_id':code,'team_name':team['title'],'player_id':pid,'ipl_player_id':p['externalId'],'display_name':p['name'],'official_role':p.get('role',''),'country':p.get('country',''),'is_overseas':int(p['country']!='India') if p.get('country') else None,'is_wicketkeeper':int(p.get('isWicketKeeper',False)),'is_captain':int(p.get('isCaptain',False)),'identity_method':method,'roster_type':'official_website_snapshot','verified_on':snapshot_date,'source_url':source})
            official_by_id[pid]=p
            official_by_id[pid]['source_url']=source
    rows=[]
    for pid in sorted(set(participated)|set(official_by_id)):
        p=records.get(pid,{})
        reg=register.get(pid,{})
        official=official_by_id.get(pid,{})
        name=p.get('name') or official.get('name') or reg.get('name') or participated[pid]
        batting=p.get('batting_style',''); bowling=p.get('bowling_style','')
        category,arm=bowling_traits(bowling)
        role=primary_role(official.get('role','')) or primary_role(p.get('playing_role',''))
        country=official.get('country') or p.get('country','')
        rows.append({'player_id':pid,'cricsheet_name':participated.get(pid,reg.get('unique_name','')),'display_name':official.get('name') or name,'full_name':p.get('full_name') or name,'cricinfo_id':reg.get('key_cricinfo') or p.get('cricinfo_id',''),'ipl_player_id':official.get('externalId',''),'country':country,'date_of_birth':p.get('dob',''),'primary_role':role,'role_detail':p.get('playing_role',''),'is_wicketkeeper':int('wicketkeeper' in role or official.get('isWicketKeeper',False)) if role else None,'is_overseas':int(country!='India') if country else None,'batting_hand':'left' if 'left' in batting.lower() else 'right' if 'right' in batting.lower() else '', 'batting_style':batting,'bowling_style':bowling,'bowling_category':category,'bowling_arm':arm,'attribute_source':'cricketdata/ESPN snapshot' if p else '', 'attribute_as_of':'2025-03-24' if p else '', 'role_source_url':official.get('source_url') or ('https://pkg.robjhyndman.com/cricketdata/reference/player_meta.html' if p else ''),'country_source_url':official.get('source_url') or ('https://pkg.robjhyndman.com/cricketdata/reference/player_meta.html' if p else ''),'attributes_source_url':'https://pkg.robjhyndman.com/cricketdata/reference/player_meta.html' if p else '', 'downloaded_on':'2026-10-02','has_ipl_history':int(pid in participated)})
    frame=pd.DataFrame(rows)
    for field in ['batting','bowling','dob']:
        frame[field+'_source_url']=frame.attributes_source_url
        frame[field+'_observed_on']=frame.attribute_as_of
    frame['metadata_conflict']=''
    frame['metadata_confidence']='provider_reported'
    attribute_path=ROOT/'config/player_attribute_overrides.json'
    attributes=json.loads(attribute_path.read_text(encoding='utf-8')) if attribute_path.exists() else {}
    for i,row in frame.iterrows():
        if attributes.get(row.display_name,{}).get('cricinfo_id'):
            frame.at[i,'cricinfo_id']=attributes[row.display_name]['cricinfo_id']
    # Live ESPN profiles fill missing fields, never erase existing facts with blanks.
    for i,row in frame.iterrows():
        live_path=RAW/f"espn/athletes/{row.cricinfo_id}.json"
        if not row.cricinfo_id or not live_path.exists(): continue
        live=json.loads(live_path.read_text(encoding='utf-8'))
        live_url=f'http://core.espnuk.org/v2/sports/cricket/athletes/{row.cricinfo_id}'
        frame.at[i,'full_name']=live.get('fullName') or row.full_name
        if live.get('dateOfBirth'):
            frame.at[i,'date_of_birth']=live['dateOfBirth'][:10]
            frame.at[i,'dob_source_url']=live_url; frame.at[i,'dob_observed_on']='2026-10-02'
        styles={s['type']:s['description'] for s in live.get('style',[]) if 'type' in s and 'description' in s}
        if styles.get('batting'):
            b=styles['batting']; frame.at[i,'batting_style']=b
            frame.at[i,'batting_hand']='left' if 'left' in b.lower() else 'right' if 'right' in b.lower() else ''
            frame.at[i,'batting_source_url']=live_url; frame.at[i,'batting_observed_on']='2026-10-02'
        if styles.get('bowling'):
            b=styles['bowling']; frame.at[i,'bowling_style']=b
            category,arm=bowling_traits(b); frame.at[i,'bowling_category']=category; frame.at[i,'bowling_arm']=arm
            frame.at[i,'bowling_source_url']=live_url; frame.at[i,'bowling_observed_on']='2026-10-02'
        live_role=live.get('position',{}).get('name','')
        if live_role:
            frame.at[i,'role_detail']=live_role
            if 'wicketkeeper' in normalize(live_role): frame.at[i,'is_wicketkeeper']=1
            # Historical role is ESPN-sourced. Current squad retains the IPL selection role.
            if row.player_id not in official_by_id:
                frame.at[i,'primary_role']=primary_role(live_role)
                frame.at[i,'is_wicketkeeper']=int('wicketkeeper' in live_role.lower())
                frame.at[i,'role_source_url']=f'http://core.espnuk.org/v2/sports/cricket/athletes/{row.cricinfo_id}'
        frame.at[i,'attribute_source']='ESPN athlete profile'
        frame.at[i,'attribute_as_of']='2026-10-02'
        frame.at[i,'attributes_source_url']=f'http://core.espnuk.org/v2/sports/cricket/athletes/{row.cricinfo_id}'
        country_path=RAW/f"espn/countries/{live.get('country')}.json"
        if not row.country and country_path.exists():
            c=json.loads(country_path.read_text(encoding='utf-8')).get('name','')
            frame.at[i,'country']=c; frame.at[i,'is_overseas']=int(c!='India') if c else None
            frame.at[i,'country_source_url']=f"http://core.espnuk.org/v2/sports/cricket/teams/{live.get('country')}"
    conflicts=[]
    for i,row in frame.iterrows():
        override=attributes.get(row.display_name,{})
        if not override: continue
        for field in ['full_name','batting_style','bowling_style','date_of_birth']:
            if override.get(field): frame.at[i,field]=override[field]
        if override.get('batting_style'):
            b=override['batting_style'].lower(); frame.at[i,'batting_hand']='left' if 'left' in b else 'right' if 'right' in b else ''
            frame.at[i,'batting_source_url']=override['source_url']; frame.at[i,'batting_observed_on']='2026-10-02'
        if override.get('bowling_style'):
            category,arm=bowling_traits(override['bowling_style'])
            frame.at[i,'bowling_category']=category; frame.at[i,'bowling_arm']=override.get('bowling_arm',arm)
            frame.at[i,'bowling_source_url']=override['source_url']; frame.at[i,'bowling_observed_on']='2026-10-02'
        if override.get('date_of_birth'):
            frame.at[i,'dob_source_url']=override['source_url']; frame.at[i,'dob_observed_on']='2026-10-02'
        frame.at[i,'attribute_source']=override['source_class']
        frame.at[i,'attribute_as_of']='2026-10-02'; frame.at[i,'attributes_source_url']=override['source_url']
        frame.at[i,'metadata_confidence']=override.get('confidence','source_reported')
        if override.get('conflict'):
            frame.at[i,'metadata_conflict']=override['conflict']
            conflicts.append({'player_id':row.player_id,'display_name':row.display_name,'field':'bowling_style','chosen_value':override['bowling_style'],'source_url':override['source_url'],'alternative_source_url':override['alternative_source_url'],'note':override['conflict']})
    extracts=RAW/'profile_extracts'; extracts.mkdir(exist_ok=True)
    (extracts/'reviewed_facts.json').write_text(json.dumps({'observed_on':'2026-10-02','acquisition':'Public profile facts retrieved through web search/open; biographies and images excluded','profiles':attributes},indent=2),encoding='utf-8')
    pd.DataFrame(conflicts,columns=['player_id','display_name','field','chosen_value','source_url','alternative_source_url','note']).to_csv(processed/'metadata_conflicts.csv',index=False)
    frame['identity_status']=frame.player_id.map(lambda pid:'current_only_local_id' if pid.startswith('ipl:') else 'cricsheet_register_id')
    attribute_rows=[]
    for row in frame.to_dict('records'):
        for field,prefix in [('batting_style','batting'),('bowling_style','bowling'),('date_of_birth','dob'),('primary_role','role'),('country','country')]:
            if row[field]:
                attribute_rows.append({'player_id':row['player_id'],'field':field,'value':row[field],'source_url':row.get(prefix+'_source_url',''),'source_observed_on':row.get(prefix+'_observed_on') or ('2026-10-02' if row['ipl_player_id'] else ''),'effective_from':'','historical_validity':'not_established'})
    pd.DataFrame(attribute_rows).to_csv(processed/'player_attributes.csv',index=False)
    frame.to_csv(processed/'players.csv',index=False)
    alias_rows=[]
    known_ids=set(frame.player_id)
    for name,identifiers in aliases.items():
        for pid in identifiers & known_ids:
            if name: alias_rows.append({'player_id':pid,'normalized_alias':name,'source':'Cricsheet register / cricketdata / saved ESPN profiles'})
    for row in frame.to_dict('records'):
        for field in ['display_name','full_name','cricsheet_name']:
            if row[field]: alias_rows.append({'player_id':row['player_id'],'normalized_alias':normalize(row[field]),'source':'canonical player record'})
    pd.DataFrame(alias_rows).drop_duplicates(['player_id','normalized_alias']).to_csv(processed/'player_aliases.csv',index=False)
    pd.DataFrame(squad_rows).to_csv(processed/'squads_current.csv',index=False)
    pd.DataFrame(historical,columns=['player_id','team_name_raw','season','match_date']).groupby(['player_id','team_name_raw','season']).agg(first_appearance=('match_date','min'),last_appearance=('match_date','max'),matches_involved=('match_date','size')).reset_index().to_csv(processed/'squads_historical_observed.csv',index=False)
    (DATA/'identity_issues.json').write_text(json.dumps(identity_issues,indent=2),encoding='utf-8')
    print(json.dumps({'players':len(frame),'historical_players':len(participated),'current_squad_rows':len(squad_rows),'unresolved_squad_identities':len(identity_issues),'missing_batting_hand':int((frame.batting_hand=='').sum()),'missing_primary_role':int((frame.primary_role=='').sum())}))
    if identity_issues: print(json.dumps([{'team':x['team'],'name':x['name'],'candidates':x['candidates']} for x in identity_issues]))

if __name__=='__main__': main()
