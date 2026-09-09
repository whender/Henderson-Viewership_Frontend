"""Cross-language checks: browser scenarios must reproduce production Python inference."""
import copy,gzip,json,subprocess,unittest
from pathlib import Path
import numpy as np
import ap_movement as m
ROOT=Path(__file__).parent

class SimulatorTests(unittest.TestCase):
    def test_browser_matches_python_for_defaults_and_custom_results(self):
        payload=json.loads((ROOT.parent/'public/football/ap-simulator.json').read_text())
        read=lambda name:json.loads(gzip.decompress((ROOT/'ap'/name).read_bytes()))
        polls=[p for p in read('polls.json.gz') if p['id']<=payload['pollId']];year=polls[-1]['season']
        source=[g for g in read('games.json.gz') if g['season'] in [year-1,year]]
        market={a['id']:m.e.closing_consensus(a) for a in read('lines.json.gz')};votes=read('receiving_votes.json.gz')
        target={'season':year,'kind':'regular','cutoff':payload['releaseDate'],'size':25}
        editable=[g for g in payload['games'] if g['editable']]
        cases=[{}]
        if editable:
            cases.extend([{str(editable[0]['id']):{'home':45,'away':10}}, {str(g['id']):{'home':7 if i%2 else 35,'away':42 if i%2 else 0} for i,g in enumerate(editable)}])
        script="""const fs=require('fs');(async()=>{const code=fs.readFileSync(process.argv[1],'utf8');const m=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));const a=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(a.cases.map(c=>({x:m.scenarioFeatures(a.payload,c).x,ranks:m.predictScenario(a.payload,c).map(t=>String(t.teamId))}))));})().catch(e=>{console.error(e);process.exit(1);});"""
        browser=json.loads(subprocess.check_output(['node','-e',script,str(ROOT.parent/'src/apScenario.js')],input=json.dumps({'payload':payload,'cases':cases}).encode(),timeout=30))
        for overrides,actual in zip(cases,browser):
            games=copy.deepcopy(source);defaults={str(g['id']):g for g in payload['games']}
            for g in games:
                d=defaults.get(str(g['id']))
                if d and d['homePoints'] is not None:g.update(completed=True,homePoints=d['homePoints'],awayPoints=d['awayPoints'])
                if str(g['id']) in overrides:g.update(completed=True,homePoints=overrides[str(g['id'])]['home'],awayPoints=overrides[str(g['id'])]['away'])
            x,t=m.matrix(target,polls[-1],polls,games,market,payload['teams'],votes)
            np.testing.assert_allclose(actual['x'],x,rtol=0,atol=1e-12)
            s=m.comfortable_win_scores(m.predict(payload['model'],x),x[:,0],m.win_context(target,polls[-1],t,games))
            self.assertEqual(actual['ranks'],[str(t[i]['teamId']) for i in np.argsort(-s,kind='stable')[:40]])

    def test_editable_games_are_upcoming_and_within_release_window(self):
        p=json.loads((ROOT.parent/'public/football/ap-simulator.json').read_text())
        out=json.loads((ROOT.parent/'public/football/ap.json').read_text());top={str(t['teamId']) for t in out['next']['rows'][:40]}
        for g in p['games']:
            if not g['editable']:continue
            self.assertFalse(g['completed']);self.assertGreater(g['startDate'],p['asOf'])
            self.assertLessEqual(m.ap.timestamp(g['startDate'])+m.ap.timedelta(hours=4),m.ap.timestamp(p['releaseDate']))
            self.assertTrue({str(g['homeId']),str(g['awayId'])}&top)

if __name__=='__main__':unittest.main()
