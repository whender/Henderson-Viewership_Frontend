import unittest,json,gzip
from pathlib import Path
import numpy as np
import ap_movement as m
ROOT=Path(__file__).parent
class MovementTests(unittest.TestCase):
    def test_serialized_model_and_target_rank_immunity(self):
        polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()));target=next(p for p in reversed(polls) if p['season']==2026 and p['kind']=='regular');prior=polls[:polls.index(target)]
        games=json.loads(gzip.decompress((ROOT/'ap/games.json.gz').read_bytes()));games=[g for g in games if g['season'] in [2025,2026]]
        market={r['id']:m.e.closing_consensus(r) for r in json.loads(gzip.decompress((ROOT/'ap/lines.json.gz').read_bytes()))}
        votes=json.loads(gzip.decompress((ROOT/'ap/receiving_votes.json.gz').read_bytes()))
        x,teams=m.matrix(target,prior[-1],prior,games,market,votes=votes)
        altered={**target,'ranks':[{'rank':1,'teamId':999}]}
        y,_=m.matrix(altered,prior[-1],prior,games,market,votes=votes);np.testing.assert_array_equal(x,y)
        model=json.loads((ROOT/'ap/movement_model.json').read_text());a=m.predict(model,x);b=m.predict(json.loads(json.dumps(model)),x);np.testing.assert_array_equal(a,b)
        self.assertEqual(model['trainedThrough'],2025);self.assertTrue(np.isfinite(a).all())
        order=np.argsort(-a,kind='stable');oregon=next(i for i,t in enumerate(teams) if str(t['teamId'])=='2483')
        if target['label']=='September 8':self.assertEqual(list(order).index(oregon)+1,5)
    def test_provider_aliases_and_missing_lines(self):
        self.assertEqual(m.e.closing_consensus({'lines':[{'provider':'DraftKings','spread':-24.5},{'provider':'Draft Kings','spread':-24.5},{'provider':'Bovada','spread':-25}]})['homeExpected'],24.75)
        self.assertIsNone(m.e.closing_consensus({'lines':[]}))
