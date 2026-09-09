import copy,gzip,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
import numpy as np
import ap_model
import export_ap
from ap_data import normalize_poll
from ap_preseason import FEATURES,HISTORY,load_inputs,preseason_forecast
ROOT=Path(__file__).parent

class PreseasonTests(unittest.TestCase):
    def test_real_dates_and_unknown_date_not_guessed(self):
        raw={'season':2026,'label':'Preseason','ranks':[]}
        p=normalize_poll(raw,{})
        self.assertEqual(p['releaseDate'],'2026-08-17')
        self.assertEqual(p['cutoff'],'2026-08-17T00:00:00+00:00')
        self.assertIsNone(normalize_poll({**raw,'season':2030},{})['cutoff'])

    def test_future_labels_and_features_cannot_change_fit(self):
        inputs=load_inputs(ROOT/'ap/preseason_features.json.gz')['observations']
        first=ap_model.fit(inputs,2025,feature_names=FEATURES)
        poisoned=copy.deepcopy(inputs)
        last=next(o for o in poisoned if o['season']==2026)
        last['x'][:]=1e6;last['y'][:]=1
        second=ap_model.fit(poisoned,2025,feature_names=FEATURES)
        np.testing.assert_array_equal(first['coefficients'],second['coefficients'])

    def test_frozen_forecast_ignores_poll_and_game_changes(self):
        first=preseason_forecast(2026,[],[],[])
        second=preseason_forecast(2026,[{'season':2026,'ranks':[{'rank':1,'teamId':999}]}],[{'season':2026,'homePoints':999}],[])
        self.assertEqual(first['rows'],second['rows'])
        self.assertEqual(len(first['rows']),40)
        self.assertEqual(first['overallEvaluation']['polls'],7)

    def test_missing_roster_uses_explicit_history_fallback(self):
        artifact=json.loads((ROOT/'ap/preseason_model.json').read_text());artifact['snapshot']=None
        candidates=[{'team':f'Team {i}','teamId':i} for i in range(1,31)]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model.json';path.write_text(json.dumps(artifact))
            result=preseason_forecast(2026,[],[],candidates,artifact_path=path)
        self.assertIn('fallback',result['basis']);self.assertEqual(len(result['rows']),30)

    def test_stale_model_refused(self):
        with self.assertRaisesRegex(ValueError,'this season'):
            preseason_forecast(2027,[],[],[])

    def test_export_switches_after_first_poll(self):
        polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()))
        class August(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,8,1,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'football-model';(root/'ap').mkdir(parents=True)
            (Path(d)/'public/football').mkdir(parents=True)
            for name in ['receiving_votes.json.gz','movement_model.json','movement_validation.json','lines.json.gz','identities.json','model.json','preseason_model.json','preseason_dates.json','coverage.json','games.json.gz']:
                (root/'ap'/name).write_bytes((ROOT/'ap'/name).read_bytes())
            (root/'games.json.gz').write_bytes(gzip.compress(b'[]'))
            candidates=json.loads((ROOT/'ap/preseason_model.json').read_text())['snapshot']['teams']
            football={'season':2026,'teams':[{'team':t['team'],'team_id':t['teamId'],'conference':t.get('conference')} for t in candidates],'games':[]}
            (Path(d)/'public/football/model.json').write_text(json.dumps(football))
            for before in [True,False]:
                selected=[p for p in polls if p['season']<2026] if before else polls
                (root/'ap/polls.json.gz').write_bytes(gzip.compress(json.dumps(selected).encode()))
                with patch.object(export_ap,'ROOT',root),patch.object(export_ap,'datetime',August),patch('sys.argv',['export_ap.py']):
                    export_ap.main()
                output=json.loads((Path(d)/'public/football/ap.json').read_text())
                self.assertEqual(output['activeModel'],'preseason' if before else 'in-season')
                if before:
                    self.assertEqual(output['next']['rows'],output['preseason']['rows'])
                    self.assertEqual(output['next']['estimatedReleaseDate'],'2026-08-17')
                    self.assertFalse(output['next']['assumptions'])
                else:self.assertTrue(output['latest']['official'])

if __name__=='__main__':unittest.main()
