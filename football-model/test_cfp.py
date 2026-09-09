import gzip,json,unittest
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from cfp_data import parse_rankings
from export_cfp import scenario_games
from cfbpredict.games import Game
from cfbpredict.committee_history import build_resume_state
ROOT=Path(__file__).parent
class CFPTests(unittest.TestCase):
    def test_official_parser_rejects_new_incomplete_but_preserves_known_history(self):
        data=[{'label':'2026','weeks':[{'label':'NOVEMBER 3','sub':'','isSelection':False}], 'teams':[{'name':f'Team {i}','ranks':[str(i)]} for i in range(1,26)]}]
        text='const RANKINGS_DATA = '+json.dumps(data)+'; arbitraryJavaScript();'
        self.assertEqual(len(parse_rankings(text)[(2026,'2026-11-03')]),25)
        data[0]['teams'].pop();text='const RANKINGS_DATA = '+json.dumps(data)
        with self.assertRaises(ValueError):parse_rankings(text)
        self.assertEqual(parse_rankings(text,{(2026,'2026-11-03')}),{})
        self.assertEqual(parse_rankings(text,season_filter=2027),{})
    def test_future_results_and_duplicates_do_not_change_historical_inputs(self):
        raw=json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes()))
        games=[Game.from_cfbd(g) for g in raw if g['season']==2025]
        cutoff=datetime(2025,11,4,12,tzinfo=timezone.utc)
        original=build_resume_state(games,cutoff)
        changed=[replace(g,home_points=99,away_points=0,completed=True) if g.start_date>=cutoff else g for g in games]
        self.assertEqual(original,build_resume_state(changed+changed,cutoff))
    def test_scenario_preserves_actual_results_and_reports_missing_predictions(self):
        raw=json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes()))
        g=Game.from_cfbd(raw[0]);now=g.start_date-timedelta(days=1);cutoff=g.start_date+timedelta(days=1)
        future=replace(g,completed=False,home_points=None,away_points=None,home_classification='fbs')
        result,assumptions,missing=scenario_games([future],{g.id:{'prediction':{'predicted_margin':-7,'home_win_probability':.3}}},now,cutoff)
        self.assertFalse(future.completed);self.assertTrue(result[0].completed);self.assertEqual(assumptions[0]['winner'],g.away_team)
        self.assertEqual(scenario_games([future],{},now,cutoff)[2],[g.id])
        self.assertEqual(scenario_games([replace(g,completed=True)],{},now,cutoff)[0],[replace(g,completed=True)])
    def test_public_snapshot_and_held_out_archive(self):
        data=json.loads((ROOT.parent/'public/football/cfp.json').read_text())
        self.assertEqual(data['trainingThrough'],data['season']-1)
        self.assertEqual(data['overallEvaluation']['polls'],sum(e['historical_poll_count'] for e in data['evaluation']))
        for poll in data['history']:
            self.assertEqual([r['rank'] for r in poll['rows']],list(range(1,26)))
            if 2019<=poll['season']<=data['trainingThrough']:
                self.assertTrue(all(r['predictedRank'] for r in poll['rows']))
