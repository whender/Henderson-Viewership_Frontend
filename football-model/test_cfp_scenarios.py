"""Cross-language parity for editable next-release resumes and power ratings."""
import gzip,json,subprocess,unittest
from pathlib import Path
from dataclasses import replace
from datetime import datetime
from cfbpredict.games import Game
from cfbpredict.committee import CommitteeModel
from cfbpredict.committee_history import build_resume_state
from export_cfp import rankings,identities
from cfp_scenarios import scenario_payload
ROOT=Path(__file__).parent

class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT.parent/'public/football/cfp.json').read_text())
        cls.engine=cls.data['next']['scenarioEngine']
        cls.games=[Game.from_cfbd(g) for g in json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes())) if g['season']==cls.data['season']]
        cls.model=CommitteeModel.load(ROOT/'cfp/model.json')
        cls.cutoff=datetime.fromisoformat(cls.engine['cutoff'])

    def browser(self,index,overrides=None):
        script="const fs=require('fs');const p=JSON.parse(fs.readFileSync(0,'utf8'));import('./src/cfpScenario.mjs').then(({projectScenario})=>process.stdout.write(JSON.stringify(projectScenario(p.engine,p.index,p.overrides,p.eligible))));"
        return json.loads(subprocess.run(['node','-e',script],cwd=ROOT.parent,input=json.dumps({'engine':self.engine,'index':index,'overrides':overrides or {},'eligible':self.data['next']['eligibleTeams']}),capture_output=True,text=True,check=True).stdout)

    def assert_python_parity(self,result):
        choices={r['id']:r for r in result['assumptions']}
        games=[replace(g,completed=True,home_points=choices[g.id]['margin'] if choices[g.id]['homeWin'] else 0,away_points=0 if choices[g.id]['homeWin'] else choices[g.id]['margin']) if g.id in choices else g for g in self.games]
        expected=rankings(self.model,games,self.cutoff,identities(self.games));resumes,_=build_resume_state(games,self.cutoff)
        self.assertEqual([r['key'] for r in expected],[r['key'] for r in result['rows'][:40]])
        for r in result['rows']:
            p=resumes[r['key']]
            self.assertAlmostEqual(r['power'],p.power_rating,places=8)
            self.assertAlmostEqual(r['recordStrength'],p.record_strength,places=8)
            self.assertAlmostEqual(r['scheduleStrength'],p.schedule_strength,places=8)
            self.assertEqual((r['wins'],r['losses'],r['qualityWins']),(p.wins,p.losses,p.top_25_wins))
        for actual,expected_row in zip(result['rows'],expected):
            self.assertEqual(actual['bestWins'],expected_row['bestWins']);self.assertEqual(actual['worstLosses'],expected_row['worstLosses'])

    def test_main_and_simulated_rankings_match_python(self):
        for i in (0,1,25):
            with self.subTest(projection=i):self.assert_python_parity(self.browser(i))
        self.assertTrue(all(g['homeWin']==(g['probability']>=.5) for g in self.browser(0)['assumptions']))

    def test_forced_upset_updates_entire_resume_and_rankings(self):
        keys={t['key'] for t in self.data['next']['eligibleTeams']}
        g=next(g for g in self.engine['games'] if g['projected'] and (g['homeKey'] in keys or g['awayKey'] in keys))
        winner=g['awayKey'] if g['probability']>=.5 else g['homeKey']
        result=self.browser(0,{str(g['id']):winner})
        assumption=next(a for a in result['assumptions'] if a['id']==g['id'])
        self.assertTrue(assumption['forced']);self.assertEqual(assumption['homeWin'],winner==g['homeKey'])
        self.assert_python_parity(result)

    def test_export_has_25_projections_and_fixed_eligibility(self):
        self.assertEqual(len(self.data['next']['alternatives']),25)
        self.assertEqual(len(self.data['next']['eligibleTeams']),25)
        ps=[t['probability'] for t in self.data['next']['eligibleTeams']]
        self.assertEqual(ps,sorted(ps,reverse=True))
        self.assertTrue(all(0<=p<=1 for p in ps))

    def test_future_scores_do_not_enter_payload(self):
        football=json.loads((ROOT.parent/'public/football/model.json').read_text());predictions={g['id']:g for g in football['games']}
        changed=[replace(g,home_points=99,away_points=0) if not g.completed else g for g in self.games]
        # Compare two fits on the same runtime; saved Linux and local BLAS
        # builds can differ at machine precision even for identical inputs.
        baseline=scenario_payload(self.games,predictions,self.cutoff,self.model)
        self.assertEqual(scenario_payload(changed,predictions,self.cutoff,self.model),baseline)
