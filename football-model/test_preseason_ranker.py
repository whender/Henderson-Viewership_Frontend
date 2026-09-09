import copy,json,unittest
from pathlib import Path
import numpy as np
from ap_preseason_ranker import history_features,fit_pairwise,predict_pairwise,selection_then_pairwise
from ap_preseason import preseason_forecast,preseason_scores

class PreseasonRankerTests(unittest.TestCase):
    def test_future_polls_excluded(self):
        def poll(y,r):return {'season':y,'kind':'preseason','size':25,'ranks':[{'teamId':1,'rank':r}]}
        teams=[{'teamId':1}];past=[poll(2023,8)]
        np.testing.assert_array_equal(history_features(teams,2024,past),history_features(teams,2024,past+[poll(2024,1),poll(2025,2)]))

    def test_membership_preserved(self):
        scores=selection_then_pairwise(np.array([5.,4.,3.,2.,1.]),np.array([1.,2.,3.,100.,200.]),3)
        np.testing.assert_array_equal(np.argsort(-scores),[2,1,0,3,4])

    def test_future_training_excluded_and_serialization(self):
        o={'season':2020,'x':np.array([[0.,1.],[1.,0.],[.5,.5]]),'actual':{1:1,2:2}}
        future={**o,'season':2021,'x':np.full((3,2),1e6),'actual':{0:1,2:2}}
        m=fit_pairwise([o],'x',2020)
        self.assertEqual(m,fit_pairwise([o,future],'x',2020))
        np.testing.assert_array_equal(predict_pairwise(m,o['x']),predict_pairwise(json.loads(json.dumps(m)),o['x']))

    def test_current_forecast_uses_immutable_snapshot(self):
        a=preseason_forecast(2026,[],[],[])
        b=preseason_forecast(2026,[{'season':2026,'ranks':[{'teamId':1,'rank':1}]}],[{'season':2026,'homePoints':1000}],[])
        self.assertEqual(a,b)
        self.assertIn('pairwise',a['basis'])
        self.assertAlmostEqual(a['overallEvaluation']['rankError'],3.337142857142857)

    def test_invalid_snapshot_and_cutoff_rejected(self):
        a=json.loads((Path(__file__).parent/'ap/preseason_model.json').read_text())
        with self.assertRaises(ValueError):preseason_scores(a['model'],a['snapshot']['x'])
        m=copy.deepcopy(a['model']);m['reranker']['trainedThrough']=2026
        with self.assertRaises(ValueError):preseason_scores(m,a['snapshot']['x'],a['snapshot']['extended'])

if __name__=='__main__':unittest.main()
