import unittest
import numpy as np
from ap_movement import histogram_edges, BoostedMovement

class HistogramTests(unittest.TestCase):
    def test_rare_binary_values_stay_separate(self):
        for rare,common in [(1.,0.),(0.,1.),(-1.,0.)]:
            x=np.array([rare]*25+[common]*975)
            edges=histogram_edges(x)
            self.assertNotEqual(np.searchsorted(edges,rare,side='right'),np.searchsorted(edges,common,side='right'))
            self.assertLessEqual(len(edges),23)
    def test_constant_and_sparse_continuous(self):
        self.assertEqual(len(histogram_edges(np.zeros(100))),0)
        x=np.r_[np.zeros(980),np.arange(1,21)]
        bins=np.searchsorted(histogram_edges(x),x,side='right')
        self.assertTrue(np.all(bins[-20:]>bins[0]))
    def test_model_can_learn_rare_flag(self):
        x=np.r_[np.zeros(975),np.ones(25)][:,None]
        model=BoostedMovement(trees=30,depth=1,min_leaf=20,rate=.1).fit(x,x[:,0],np.ones(1000))
        pred=model.predict(np.array([[0.],[1.]]))
        self.assertGreater(pred[1]-pred[0],.9)
