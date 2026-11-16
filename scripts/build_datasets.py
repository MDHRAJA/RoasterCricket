"""Normalize IPL records and derive descriptive inputs. No predictive claims here."""
import csv
import hashlib
import json
import sqlite3
import zipfile
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
import pandas as pd
from fetch_data import DATA, RAW, TEAMS
from prepare_players import normalize

OUT=DATA/'processed'
TABLES={}
TEAM_NAMES={
    'Chennai Super Kings':'CSK','Delhi Capitals':'DC','Delhi Daredevils':'DC',
    'Gujarat Titans':'GT','Kolkata Knight Riders':'KKR','Lucknow Super Giants':'LSG',
    'Mumbai Indians':'MI','Punjab Kings':'PBKS','Kings XI Punjab':'PBKS',
    'Rajasthan Royals':'RR','Royal Challengers Bangalore':'RCB','Royal Challengers Bengaluru':'RCB',
    'Sunrisers Hyderabad':'SRH','Deccan Chargers':'DCH','Kochi Tuskers Kerala':'KTK',
    'Pune Warriors':'PW','Rising Pune Supergiants':'RPS','Rising Pune Supergiant':'RPS','Gujarat Lions':'GL',
}
BOWLER_WICKETS={'bowled','caught','caught and bowled','lbw','stumped','hit wicket'}
NON_TEAM_WICKETS={'retired hurt','retired not out'}

def team_id(name):
    if not name: return ''
    if name not in TEAM_NAMES: raise ValueError(f'Unknown franchise {name}')
    return TEAM_NAMES[name]

def save(name,frame,columns=None):
    if not isinstance(frame,pd.DataFrame): frame=pd.DataFrame(frame,columns=columns)
    frame.to_csv(OUT/f'{name}.csv',index=False)
    TABLES[name]=frame
    print(f'{name}: {len(frame):,} rows',flush=True)
    return frame

def ratio(n,d,m=1):
    return (n/d.where(d!=0)*m).round(6)

def aggregate_deliveries(d,keys):
    g=d.groupby(keys,dropna=False).agg(
        deliveries=('delivery_id','size'),matches=('match_id','nunique'),
        legal_balls=('legal_ball','sum'),balls_faced=('ball_faced','sum'),
        batter_runs=('batter_runs','sum'),team_runs=('total_runs','sum'),
        bowler_runs_conceded=('bowler_runs_conceded','sum'),
        bowler_wickets=('bowler_wicket','sum'),striker_dismissals=('striker_dismissed','sum'),
        fours=('four','sum'),sixes=('six','sum'),batting_dots=('batting_dot','sum'),
        bowling_dots=('bowling_dot','sum'),first_date=('match_date','min'),last_date=('match_date','max')).reset_index()
    g['strike_rate']=ratio(g.batter_runs,g.balls_faced,100)
    g['economy']=ratio(g.bowler_runs_conceded,g.legal_balls,6)
    g['boundary_ball_rate']=ratio(g.fours+g.sixes,g.balls_faced)
    g['bowling_dot_rate']=ratio(g.bowling_dots,g.legal_balls)
    return g

def recent_form(stats):
    rows=[]
    for pid,group in stats.groupby('player_id',sort=True):
        batting=deque(maxlen=10); bowling=deque(maxlen=10)
        for row in group.sort_values(['match_date','match_id']).to_dict('records'):
            # DNB and did-not-bowl appearances never become zero-performance innings.
            if row['batted']: batting.append(row)
            if row['bowling_deliveries']>0: bowling.append(row)
            output={'player_id':pid,'as_of_after_match_id':row['match_id'],'as_of_after_date':row['match_date']}
            for n in (5,10):
                bs=list(batting)[-n:]; ws=list(bowling)[-n:]
                output[f'batting_innings_last{n}']=len(bs)
                output[f'bowling_innings_last{n}']=len(ws)
                output[f'runs_trend_per_innings_last{n}']=float(np.polyfit(range(len(bs)),[x['batting_runs'] for x in bs],1)[0]) if len(bs)>=3 else None
                for side,window in [('batting',bs),('bowling',ws)]:
                    if side=='batting':
                        runs=sum(x['batting_runs'] for x in window); balls=sum(x['balls_faced'] for x in window)
                        output[f'runs_last{n}']=runs if window else None
                        output[f'balls_faced_last{n}']=balls if window else None
                        output[f'runs_per_innings_last{n}']=runs/len(window) if window else None
                        output[f'strike_rate_last{n}']=100*runs/balls if balls else None
                        output[f'dismissals_last{n}']=sum(x['dismissals'] for x in window) if window else None
                        weights=np.array([.85**(len(window)-1-i) for i in range(len(window))])
                        output[f'recency_weighted_runs_last{n}']=float(np.average([x['batting_runs'] for x in window],weights=weights)) if window else None
                    else:
                        balls=sum(x['legal_balls_bowled'] for x in window); runs=sum(x['runs_conceded'] for x in window)
                        output[f'wickets_last{n}']=sum(x['bowler_wickets'] for x in window) if window else None
                        output[f'legal_balls_bowled_last{n}']=balls if window else None
                        output[f'economy_last{n}']=6*runs/balls if balls else None
            rows.append(output)
    return pd.DataFrame(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    players=pd.read_csv(OUT/'players.csv',dtype={'player_id':str,'cricinfo_id':str},keep_default_na=False)
    TABLES['players']=players
    for name in ['squads_current','squads_historical_observed','player_attributes','player_aliases','metadata_conflicts']:
        TABLES[name]=pd.read_csv(OUT/f'{name}.csv',keep_default_na=False)
    pmap=players.set_index('player_id').to_dict('index')
    match_rows=[]; innings_rows=[]; delivery_rows=[]; wicket_rows=[]; replacement_rows=[]; lineup_rows=[]
    penalty_rows=[]; source_totals={}; venue_aliases={}; player_teams={}
    with zipfile.ZipFile(RAW/'cricsheet/ipl_json.zip') as z:
        (RAW/'cricsheet/README.txt').write_bytes(z.read('README.txt'))
        files=[n for n in z.namelist() if n.endswith('.json')]
        docs=[(Path(n).stem,json.loads(z.read(n))) for n in files]
    alias_path=Path(__file__).resolve().parents[1]/'config/venue_aliases.json'
    alias_map=json.loads(alias_path.read_text(encoding='utf-8')) if alias_path.exists() else {}
    for mid,doc in sorted(docs,key=lambda x:(x[1]['info']['dates'][0],x[0])):
        info=doc['info']; reg=info['registry']['people']; date=info['dates'][0]; season=str(date)[:4]
        venue=info.get('venue',''); venue_key=normalize(venue)
        # Explicitly reviewed stadium aliases keep distinct grounds separate.
        venue_key=alias_map.get(venue,venue_key)
        vid='venue_'+hashlib.sha256(venue_key.encode()).hexdigest()[:10]
        venue_aliases[venue]={'venue_name_raw':venue,'venue_id':vid,'city':info.get('city',''),'canonical_key':venue_key}
        event=info.get('event',{}); outcome=info.get('outcome',{})
        match_rows.append({'match_id':mid,'match_date':date,'season':season,'season_raw':str(info['season']),'team1_id':team_id(info['teams'][0]),'team2_id':team_id(info['teams'][1]),'team1_name_raw':info['teams'][0],'team2_name_raw':info['teams'][1],'venue_id':vid,'venue_name_raw':venue,'city':info.get('city',''),'match_number':event.get('match_number',''),'stage':event.get('stage',''),'winner_id':team_id(outcome.get('winner')),'result':outcome.get('result','win' if outcome.get('winner') else ''),'win_by_runs':outcome.get('by',{}).get('runs'),'win_by_wickets':outcome.get('by',{}).get('wickets'),'result_method':outcome.get('method',''),'toss_winner_id':team_id(info['toss']['winner']),'toss_decision':info['toss']['decision'],'scheduled_overs':info.get('overs',20),'balls_per_over':info['balls_per_over'],'source_file':f'{mid}.json','data_revision':doc['meta']['revision'],'missing_metadata':json.dumps(info.get('missing',[]))})
        incoming=set()
        for inning in doc['innings']:
            for over in inning.get('overs',[]):
                for ball in over['deliveries']:
                    for rtype,replacements in ball.get('replacements',{}).items():
                        for r in replacements:
                            if rtype=='match': incoming.add(reg[r['in']])
        for team,names in info['players'].items():
            for name in names:
                pid=reg[name]; player_teams[(mid,pid)]=team_id(team)
                lineup_rows.append({'match_id':mid,'player_id':pid,'team_id':team_id(team),'name_in_match':name,'listed_in_match':1,'is_incoming_match_replacement':int(pid in incoming),'starting_status':'incoming_replacement' if pid in incoming else 'listed_original_or_unresolved','source':'Cricsheet players and replacement events'})
        for ino,inning in enumerate(doc['innings'],start=1):
            superover=int(inning.get('super_over',False)); bat_team=team_id(inning['team'])
            bowl_team=next(team_id(x) for x in info['teams'] if x!=inning['team'])
            pre=inning.get('penalty_runs',{}).get('pre',0); post=inning.get('penalty_runs',{}).get('post',0)
            for when,value in inning.get('penalty_runs',{}).items():
                penalty_rows.append({'match_id':mid,'innings':ino,'timing':when,'runs':value})
            cumulative_runs=pre; cumulative_wickets=0; sequence=0; legal_count=0
            for over in inning.get('overs',[]):
                for oball,ball in enumerate(over['deliveries'],start=1):
                    sequence+=1; did=f'{mid}:{ino}:{sequence}'
                    ext=ball.get('extras',{}); runs=ball['runs']
                    legal=int(not ext.get('wides',0) and not ext.get('noballs',0))
                    faced=int(not ext.get('wides',0))
                    wickets=ball.get('wickets',[])
                    team_wickets=sum(w['kind'] not in NON_TEAM_WICKETS for w in wickets)
                    bowler_wickets=sum(w['kind'] in BOWLER_WICKETS for w in wickets)
                    striker_dismissed=sum(w['player_out']==ball['batter'] and w['kind'] not in NON_TEAM_WICKETS for w in wickets)
                    row={'delivery_id':did,'match_id':mid,'match_date':date,'season':season,'venue_id':vid,'innings':ino,'is_super_over':superover,'batting_team_id':bat_team,'bowling_team_id':bowl_team,'over_index':over['over'],'delivery_in_over':oball,'sequence_in_innings':sequence,'actual_delivery':ball.get('actual_delivery',''),'phase':'powerplay' if over['over']<6 else 'middle' if over['over']<16 else 'death','batter_id':reg[ball['batter']],'bowler_id':reg[ball['bowler']],'non_striker_id':reg[ball['non_striker']],'batter_runs':runs['batter'],'extras_runs':runs['extras'],'total_runs':runs['total'],'wides':ext.get('wides',0),'noballs':ext.get('noballs',0),'byes':ext.get('byes',0),'legbyes':ext.get('legbyes',0),'penalty_extras':ext.get('penalty',0),'legal_ball':legal,'ball_faced':faced,'bowler_runs_conceded':runs['total']-ext.get('byes',0)-ext.get('legbyes',0)-ext.get('penalty',0),'team_wickets':team_wickets,'bowler_wicket':bowler_wickets,'striker_dismissed':striker_dismissed,'four':int(runs['batter']==4 and not ball.get('non_boundary',False)),'six':int(runs['batter']==6 and not ball.get('non_boundary',False)),'batting_dot':int(faced and runs['batter']==0),'bowling_dot':int(legal and runs['total']==0),'score_before':cumulative_runs,'wickets_before':cumulative_wickets,'legal_balls_before':legal_count,'target_runs':inning.get('target',{}).get('runs')}
                    # Cricsheet nests the non-boundary flag inside runs, not the delivery.
                    row['four']=int(runs['batter']==4 and not runs.get('non_boundary',False))
                    row['six']=int(runs['batter']==6 and not runs.get('non_boundary',False))
                    row['non_boundary']=int(runs.get('non_boundary',False))
                    bp=pmap.get(row['batter_id'],{}); wp=pmap.get(row['bowler_id'],{})
                    row['batting_hand']=bp.get('batting_hand','') or 'unknown'
                    row['bowling_style']=wp.get('bowling_style','') or 'unknown'
                    row['bowling_category']=wp.get('bowling_category','') or 'unknown'
                    row['bowling_arm']=wp.get('bowling_arm','') or 'unknown'
                    row['bowling_metadata_conflict']=int(bool(wp.get('metadata_conflict','')))
                    delivery_rows.append(row)
                    for wi,w in enumerate(wickets):
                        wicket_rows.append({'delivery_id':did,'wicket_index':wi,'match_id':mid,'innings':ino,'player_out_id':reg[w['player_out']],'kind':w['kind'],'credited_to_bowler':int(w['kind'] in BOWLER_WICKETS),'counts_as_team_wicket':int(w['kind'] not in NON_TEAM_WICKETS),'fielder_ids':json.dumps([reg[f['name']] for f in w.get('fielders',[]) if f.get('name')])})
                    for rtype,replacements in ball.get('replacements',{}).items():
                        for ri,r in enumerate(replacements):
                            replacement_rows.append({'delivery_id':did,'replacement_type':rtype,'replacement_index':ri,'match_id':mid,'player_in_id':reg[r['in']],'player_out_id':reg.get(r.get('out',''),''),'team_id':team_id(r.get('team',inning['team'])),'reason':r.get('reason',''),'role':r.get('role','')})
                    cumulative_runs+=runs['total']; cumulative_wickets+=team_wickets; legal_count+=legal
            innings_rows.append({'match_id':mid,'innings':ino,'match_date':date,'season':season,'venue_id':vid,'batting_team_id':bat_team,'bowling_team_id':bowl_team,'is_super_over':superover,'runs_from_deliveries':cumulative_runs-pre,'penalty_runs_pre':pre,'penalty_runs_post':post,'total_runs':cumulative_runs+post,'wickets':cumulative_wickets,'legal_balls':legal_count,'delivery_count':sequence,'target_runs':inning.get('target',{}).get('runs'),'target_overs':inning.get('target',{}).get('overs'),'powerplays_json':json.dumps(inning.get('powerplays',[]))})
            source_totals[(mid,ino)]=sum(b['runs']['total'] for o in inning.get('overs',[]) for b in o['deliveries'])
    matches=save('matches',match_rows); innings=save('innings',innings_rows); deliveries=save('deliveries',delivery_rows)
    wickets=save('wickets',wicket_rows,columns=['delivery_id','wicket_index','match_id','innings','player_out_id','kind','credited_to_bowler','counts_as_team_wicket','fielder_ids'])
    save('replacements',replacement_rows,columns=['delivery_id','replacement_type','replacement_index','match_id','player_in_id','player_out_id','team_id','reason','role'])
    lineups=save('match_players',lineup_rows)
    save('innings_penalties',penalty_rows,columns=['match_id','innings','timing','runs'])
    save('teams',[{'team_id':code,'display_name':name,'is_current':int(code in TEAMS)} for code,name in {v:k for k,v in TEAM_NAMES.items()}.items()])
    save('team_aliases',[{'team_name_raw':name,'team_id':code} for name,code in TEAM_NAMES.items()])
    save('venue_aliases',list(venue_aliases.values()))
    regular=deliveries[deliveries.is_super_over==0].copy()
    regular_innings=innings[innings.is_super_over==0]
    venues=regular.groupby('venue_id').agg(matches=('match_id','nunique'),legal_balls=('legal_ball','sum'),runs=('total_runs','sum'),wickets=('team_wickets','sum'),first_date=('match_date','min'),last_date=('match_date','max')).reset_index()
    venues['runs_per_over']=ratio(venues.runs,venues.legal_balls,6)
    venue_names=pd.DataFrame(venue_aliases.values()).groupby('venue_id').agg(display_name=('venue_name_raw','first'),city=('city','first')).reset_index()
    save('venues',venue_names)
    firsts=regular_innings[regular_innings.innings==1].groupby('venue_id').agg(first_innings_count=('match_id','size'),mean_first_innings_runs=('total_runs','mean'),median_first_innings_runs=('total_runs','median')).reset_index()
    save('venue_profiles',venues.merge(firsts,on='venue_id',how='left'))
    save('venue_phase_profiles',aggregate_deliveries(regular,['venue_id','season','phase','bowling_category']))
    batting=regular.groupby(['match_id','batter_id']).agg(batting_deliveries=('delivery_id','size'),batting_runs=('batter_runs','sum'),balls_faced=('ball_faced','sum'),fours=('four','sum'),sixes=('six','sum'),batting_dots=('batting_dot','sum')).reset_index().rename(columns={'batter_id':'player_id'})
    bowling=regular.groupby(['match_id','bowler_id']).agg(bowling_deliveries=('delivery_id','size'),legal_balls_bowled=('legal_ball','sum'),runs_conceded=('bowler_runs_conceded','sum'),bowler_wickets=('bowler_wicket','sum'),bowling_dots=('bowling_dot','sum')).reset_index().rename(columns={'bowler_id':'player_id'})
    dismissed=wickets[wickets.counts_as_team_wicket==1].merge(innings[['match_id','innings','is_super_over']],on=['match_id','innings'])
    dismissed=dismissed[dismissed.is_super_over==0].groupby(['match_id','player_out_id']).size().reset_index(name='dismissals').rename(columns={'player_out_id':'player_id'})
    stats=lineups[['match_id','player_id','team_id']].merge(matches[['match_id','match_date','season','venue_id']],on='match_id').merge(batting,on=['match_id','player_id'],how='outer').merge(bowling,on=['match_id','player_id'],how='outer').merge(dismissed,on=['match_id','player_id'],how='left')
    numeric=['batting_deliveries','batting_runs','balls_faced','fours','sixes','batting_dots','bowling_deliveries','legal_balls_bowled','runs_conceded','bowler_wickets','bowling_dots','dismissals']
    stats[numeric]=stats[numeric].fillna(0).astype(int)
    # A non-striker who enters the crease has batted even if they face no ball.
    crease=pd.concat([regular[['match_id','batter_id']].rename(columns={'batter_id':'player_id'}),regular[['match_id','non_striker_id']].rename(columns={'non_striker_id':'player_id'})]).drop_duplicates()
    crease['batted']=1
    stats=stats.merge(crease,on=['match_id','player_id'],how='left')
    stats['batted']=stats.batted.fillna(0).astype(int)
    stats['bowled']=(stats.bowling_deliveries>0).astype(int)
    stats['strike_rate']=ratio(stats.batting_runs,stats.balls_faced,100)
    stats['economy']=ratio(stats.runs_conceded,stats.legal_balls_bowled,6)
    stats=stats.sort_values(['match_date','match_id','player_id'])
    save('player_match_stats',stats)
    totals=stats.groupby(['player_id','season','team_id']).agg(matches_involved=('match_id','nunique'),batting_innings=('batted','sum'),bowling_innings=('bowled','sum'),runs=('batting_runs','sum'),balls_faced=('balls_faced','sum'),dismissals=('dismissals','sum'),fours=('fours','sum'),sixes=('sixes','sum'),wickets=('bowler_wickets','sum'),legal_balls_bowled=('legal_balls_bowled','sum'),runs_conceded=('runs_conceded','sum')).reset_index()
    totals['batting_average']=ratio(totals.runs,totals.dismissals)
    totals['strike_rate']=ratio(totals.runs,totals.balls_faced,100)
    totals['economy']=ratio(totals.runs_conceded,totals.legal_balls_bowled,6)
    totals['bowling_average']=ratio(totals.runs_conceded,totals.wickets)
    save('player_season_stats',totals)
    save('recent_form',recent_form(stats))
    save('player_phase_batting',aggregate_deliveries(regular,['batter_id','season','phase']))
    save('player_phase_bowling',aggregate_deliveries(regular,['bowler_id','season','phase']))
    save('matchups',aggregate_deliveries(regular,['batter_id','bowler_id','season','phase']))
    save('bowler_type_matchups',aggregate_deliveries(regular,['batter_id','season','phase','bowling_category','bowling_arm','bowling_style']))
    save('batter_hand_matchups',aggregate_deliveries(regular,['bowler_id','season','phase','batting_hand']))
    save('player_venue_batting',aggregate_deliveries(regular,['batter_id','venue_id','season','phase']))
    save('player_venue_bowling',aggregate_deliveries(regular,['bowler_id','venue_id','season','phase']))
    save('outcome_counts',regular.groupby(['batter_id','bowler_id','season','phase','batter_runs','striker_dismissed'],dropna=False).agg(deliveries=('delivery_id','size'),legal_balls=('legal_ball','sum'),balls_faced=('ball_faced','sum')).reset_index())
    save('season_coverage',matches.groupby('season').agg(matches=('match_id','size'),first_date=('match_date','min'),last_date=('match_date','max')).reset_index())
    observed=TABLES['squads_historical_observed']; observed['team_id']=observed.team_name_raw.map(team_id)
    save('squads_historical_observed',observed)
    current=TABLES['squads_current']
    availability=current[['season','team_id','player_id','ipl_player_id','display_name']].copy()
    availability['availability']='unknown'; availability['effective_on']=''; availability['source_url']=''; availability['notes']='Manual match-specific input required'
    # Availability is an editable input: preserve the user's existing entries on rebuild.
    manual=DATA/'manual'; manual.mkdir(exist_ok=True)
    if (manual/'availability.csv').exists():
        previous=pd.read_csv(manual/'availability.csv',keep_default_na=False)
        keys=['season','team_id','display_name']
        fields=['availability','effective_on','source_url','notes']
        if previous.duplicated(keys).any(): raise ValueError('Duplicate manual availability keys; resolve without overwriting user inputs')
        previous['season']=previous.season.astype(str); availability['season']=availability.season.astype(str)
        lookup=previous.set_index(keys).to_dict('index')
        for i,row in availability.iterrows():
            old=lookup.get(tuple(row[k] for k in keys))
            if old:
                for field in fields: availability.at[i,field]=old[field]
        # Never silently discard manual rows for people absent from the current snapshot.
        new_keys=set(tuple(row[k] for k in keys) for row in availability.to_dict('records'))
        leftovers=previous[[tuple(row[k] for k in keys) not in new_keys for row in previous.to_dict('records')]]
        availability=pd.concat([availability,leftovers],ignore_index=True)
    availability.to_csv(manual/'availability.csv',index=False)
    conditions=manual/'match_conditions.csv'
    if not conditions.exists():
        pd.DataFrame(columns=['scenario_id','match_date','season','team_id','opponent_team_id','venue_id','pitch_assumption','dew_assumption','weather_source_url','confirmed_toss_winner_id','confirmed_toss_decision','notes']).to_csv(conditions,index=False)
    checks=[]
    def check(name,condition,detail):
        checks.append({'check':name,'passed':bool(condition),'detail':detail})
    check('archive_match_count',len(matches)==len(files),len(files))
    check('match_ids_unique',not matches.match_id.duplicated().any(),len(matches))
    check('delivery_ids_unique',not deliveries.delivery_id.duplicated().any(),len(deliveries))
    check('run_arithmetic',(deliveries.batter_runs+deliveries.extras_runs==deliveries.total_runs).all(),'batter + extras = total')
    check('innings_runs_reconciled',all(source_totals[(r['match_id'],r['innings'])]==r['runs_from_deliveries'] for r in innings_rows),'every source innings independently summed')
    check('legal_ball_flags',((deliveries.legal_ball==1)==((deliveries.wides==0)&(deliveries.noballs==0))).all(),'wide/no-ball excluded')
    known=set(players.player_id)
    check('delivery_player_foreign_keys',set(deliveries.batter_id)|set(deliveries.bowler_id)|set(deliveries.non_striker_id)<=known,'all striker, non-striker and bowler IDs')
    check('current_squads_all_ten',set(current.team_id)==set(TEAMS),current.groupby('team_id').size().to_dict())
    check('current_squad_ids_unique',not current.duplicated(['team_id','player_id']).any(),len(current))
    current_players=players[players.player_id.isin(current.player_id)]
    check('current_player_hands_and_roles',((current_players.batting_hand!='')&(current_players.primary_role!='')).all(),'reported hand and selection role for all official snapshot members')
    check('statistics_identity_and_dates',not stats[['player_id','match_date','team_id']].isna().any().any(),'player match stats fully linked')
    check('batting_total_reconciled',stats.batting_runs.sum()==regular.batter_runs.sum(),int(stats.batting_runs.sum()))
    check('bowling_total_reconciled',stats.runs_conceded.sum()==regular.bowler_runs_conceded.sum(),int(stats.runs_conceded.sum()))
    check('bowling_wickets_reconciled',stats.bowler_wickets.sum()==regular.bowler_wicket.sum(),int(stats.bowler_wickets.sum()))
    recent=TABLES['recent_form']
    check('recent_form_window_limits',(recent.batting_innings_last10<=10).all() and (recent.bowling_innings_last5<=5).all(),'last 5/10 actual batting/bowling innings')
    check('canonical_season_year',(matches.season==matches.match_date.str[:4]).all(),'calendar IPL year; original season labels retained')
    check('wicket_player_foreign_keys',set(wickets.player_out_id)<=known,'including non-striker run outs')
    check('lineup_player_foreign_keys',set(lineups.player_id)<=known,'listed match participants')
    (DATA/'validation_report.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    # SQL mirror supports a frontend/API without scanning CSV files per request.
    db=DATA/'ipl.sqlite'
    with sqlite3.connect(db) as connection:
        for name,frame in TABLES.items():
            frame.to_sql(name,connection,if_exists='replace',index=False,chunksize=5000)
        for name,col in [('matches','match_id'),('players','player_id'),('deliveries','delivery_id')]:
            connection.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{name}_{col} ON {name}({col})')
        for name,cols in [('deliveries','match_id'),('deliveries','batter_id, bowler_id'),('deliveries','match_date'),('player_match_stats','player_id, match_date'),('recent_form','player_id, as_of_after_date'),('matchups','batter_id, bowler_id, season'),('squads_current','team_id, season')]:
            connection.execute(f'CREATE INDEX IF NOT EXISTS ix_{name}_{cols.replace(", ","_")} ON {name}({cols})')
        connection.execute('PRAGMA optimize')
        assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    catalog=[]
    for name,frame in TABLES.items():
        path=OUT/f'{name}.csv'
        catalog.append({'dataset':name,'path':f'processed/{name}.csv','rows':len(frame),'columns':list(frame.columns),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'type':'source_normalized' if name in ['matches','innings','deliveries','wickets','replacements','match_players','players','squads_current'] else 'descriptive_derived','as_of':'2026-10-02'})
    (DATA/'dataset_catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    missing=players[(players.batting_hand=='')|(players.primary_role=='')|(players.country=='')|(players.bowling_category=='')].copy()
    missing.to_csv(DATA/'metadata_review.csv',index=False)
    summary={'matches':len(matches),'deliveries':len(deliveries),'players':len(players),'historical_players':int(players.has_ipl_history.sum()),'current_squad_rows':len(current),'squad_counts':current.groupby('team_id').size().to_dict(),'first_match':matches.match_date.min(),'latest_match':matches.match_date.max(),'seasons':sorted(matches.season.unique().tolist()),'venues':len(venue_names),'datasets':len(TABLES),'current_only_local_ids':int(current.player_id.str.startswith('ipl:').sum()),'missing_batting_hand':int((players.batting_hand=='').sum()),'missing_primary_role':int((players.primary_role=='').sum()),'current_missing_primary_role':int((current_players.primary_role=='').sum()),'current_missing_bowling_style':int((current_players.bowling_style=='').sum()),'metadata_conflicts':len(TABLES['metadata_conflicts']),'historical_delivery_bowling_category_coverage':float((regular.bowling_category!='unknown').mean()),'passed_checks':sum(c['passed'] for c in checks),'total_checks':len(checks),'sqlite_bytes':db.stat().st_size}
    (DATA/'coverage_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)
    if not all(c['passed'] for c in checks): raise SystemExit('Validation failed; see validation_report.json')

if __name__=='__main__': main()
