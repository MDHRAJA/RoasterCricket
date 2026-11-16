"""Independent, read-only checks of the saved tables against the raw archive."""
import csv
import json
import sqlite3
import unittest
import zipfile
from collections import defaultdict
from fetch_data import DATA, RAW


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=sqlite3.connect(f'file:{(DATA/"ipl.sqlite").as_posix()}?mode=ro',uri=True)
        cls.db.row_factory=sqlite3.Row
        cls.archive=zipfile.ZipFile(RAW/'cricsheet/ipl_json.zip')
        cls.documents=[(name,json.loads(cls.archive.read(name))) for name in cls.archive.namelist() if name.endswith('.json')]

    @classmethod
    def tearDownClass(cls):
        cls.db.close(); cls.archive.close()

    def scalar(self,sql): return self.db.execute(sql).fetchone()[0]

    def test_01_archive_membership(self):
        saved={str(r[0])+'.json' for r in self.db.execute('SELECT match_id FROM matches')}
        self.assertEqual(saved,{name for name,_ in self.documents})

    def test_02_first_match_reference(self):
        match=self.db.execute("SELECT match_id FROM matches WHERE match_date='2008-04-18'").fetchone()[0]
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT total_runs,wickets FROM innings WHERE match_id=? AND is_super_over=0 ORDER BY innings',(match,))],[(222,3),(82,10)])
        self.assertEqual(self.db.execute("SELECT SUM(batter_runs) FROM deliveries d JOIN players p ON p.player_id=d.batter_id WHERE match_id=? AND p.cricsheet_name='BB McCullum'",(match,)).fetchone()[0],158)

    def test_03_non_boundary_flags(self):
        ids=[]
        for name,doc in self.documents:
            for ino,innings in enumerate(doc['innings'],1):
                seq=0
                for over in innings.get('overs',[]):
                    for ball in over['deliveries']:
                        seq+=1
                        if ball['runs'].get('non_boundary'):
                            ids.append(f'{name[:-5]}:{ino}:{seq}')
        self.assertGreater(len(ids),0)
        for did in ids:
            self.assertEqual(tuple(self.db.execute('SELECT four,six,non_boundary FROM deliveries WHERE delivery_id=?',(did,)).fetchone()),(0,0,1))

    def test_04_ball_denominators(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM deliveries WHERE ball_faced != (wides=0) OR legal_ball != (wides=0 AND noballs=0)'),0)

    def test_05_bowler_concessions(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM deliveries WHERE bowler_runs_conceded != total_runs-byes-legbyes-penalty_extras'),0)

    def test_06_non_striker_runouts(self):
        cases=list(self.db.execute("SELECT w.delivery_id,d.striker_dismissed,w.credited_to_bowler FROM wickets w JOIN deliveries d USING(delivery_id) WHERE kind='run out' AND player_out_id=non_striker_id"))
        self.assertGreater(len(cases),0)
        self.assertTrue(all(r['striker_dismissed']==0 and r['credited_to_bowler']==0 for r in cases))

    def test_07_super_over_exclusion(self):
        self.assertGreater(self.scalar('SELECT COUNT(*) FROM deliveries WHERE is_super_over=1'),0)
        self.assertEqual(self.scalar('SELECT SUM(batter_runs) FROM deliveries WHERE is_super_over=0'),self.scalar('SELECT SUM(runs) FROM player_season_stats'))

    def test_08_cumulative_state(self):
        sql='''SELECT COUNT(*) FROM (
          SELECT score_before,legal_balls_before,wickets_before,
           COALESCE(SUM(d.total_runs) OVER w,0)+i.penalty_runs_pre AS expected_score,
           COALESCE(SUM(legal_ball) OVER w,0) AS expected_balls,
           COALESCE(SUM(team_wickets) OVER w,0) AS expected_wickets
          FROM deliveries d JOIN innings i USING(match_id,innings)
          WINDOW w AS (PARTITION BY d.match_id,d.innings ORDER BY sequence_in_innings ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
         ) WHERE score_before!=expected_score OR legal_balls_before!=expected_balls OR wickets_before!=expected_wickets'''
        self.assertEqual(self.scalar(sql),0)

    def test_09_recent_form_recomputed(self):
        saved={(r['player_id'],str(r['as_of_after_match_id'])):r for r in self.db.execute('SELECT * FROM recent_form')}
        history=defaultdict(list); bowling=defaultdict(list)
        for r in self.db.execute('SELECT * FROM player_match_stats ORDER BY player_id,match_date,CAST(match_id AS TEXT)'):
            pid=r['player_id']
            if r['batted']: history[pid].append(r)
            if r['bowled']: bowling[pid].append(r)
            out=saved[(pid,str(r['match_id']))]
            b=history[pid][-5:]; w=bowling[pid][-5:]
            self.assertEqual(out['batting_innings_last5'],len(b))
            self.assertEqual(out['bowling_innings_last5'],len(w))
            self.assertEqual(out['runs_last5'],sum(x['batting_runs'] for x in b) if b else None)
            self.assertEqual(out['wickets_last5'],sum(x['bowler_wickets'] for x in w) if w else None)

    def test_10_zero_faced_batted_not_dnb(self):
        self.assertGreater(self.scalar('SELECT COUNT(*) FROM player_match_stats WHERE batted=1 AND batting_deliveries=0'),0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM player_match_stats WHERE batting_deliveries>0 AND batted=0'),0)

    def test_11_current_attributes(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM squads_current s JOIN players p USING(player_id) WHERE batting_hand='' OR primary_role=''"),0)
        self.assertEqual(self.scalar('SELECT COUNT(DISTINCT team_id) FROM squads_current'),10)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM metadata_conflicts WHERE display_name='Daksh Kamra'"),1)

    def test_12_database_integrity(self):
        self.assertEqual(self.scalar('PRAGMA integrity_check'),'ok')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DatasetTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests_run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors),'failures':[{'test':str(t),'traceback':text} for t,text in result.failures+result.errors]}
    (DATA/'independent_tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
