import unittest
import numpy as np
import ap_movement as m

class ComfortableWinTests(unittest.TestCase):
    def test_losses_close_wins_and_byes_unchanged(self):
        s=np.full(5,.7)
        np.testing.assert_array_equal(m.comfortable_win_scores(s,np.full(5,.8),[-10,0,1,7,14]),s)

    def test_taper_is_bounded_and_keeps_positive_movement(self):
        s=m.comfortable_win_scores(np.array([.7,.7,.7,.9]),np.full(4,.8),[14,28,42,42])
        np.testing.assert_allclose(s,[.7,.75,.8,.9])

    def test_future_games_excluded_and_minimum_margin_used(self):
        p={'season':2026,'cutoff':'2026-09-08T16:00:00+00:00'};prev={'cutoff':'2026-08-17T16:00:00+00:00'}
        def game(day,margin):return {'season':2026,'startDate':f'2026-09-{day:02}T12:00:00+00:00','completed':True,'homeId':1,'awayId':2,'homePoints':40,'awayPoints':40-margin}
        np.testing.assert_array_equal(m.win_context(p,prev,[{'teamId':1},{'teamId':2}],[game(1,35),game(5,7),game(9,100)]),[7,-35])

    def test_peer_advancement_can_still_lower_rank(self):
        scores=m.comfortable_win_scores(np.array([.7,.82]),np.array([.8,.76]),[42,7])
        self.assertLess(scores[0],scores[1])

if __name__=='__main__':unittest.main()
