import unittest
from datetime import datetime,timezone
from export_ap import project_games

class ProjectionTests(unittest.TestCase):
    def test_unfinished_games_project_without_using_partial_scores(self):
        game={'id':1,'season':2026,'startDate':'2026-09-12T16:00:00Z','completed':False,'homePoints':0,'awayPoints':28,'homeTeam':'Home','awayTeam':'Away'}
        prediction={1:{'prediction':{'predicted_margin':7,'home_win_probability':.7}}}
        target=datetime(2026,9,13,16,tzinfo=timezone.utc)
        projected,assumptions=project_games([game],prediction,2026,target)
        self.assertEqual((projected[0]['homePoints'],projected[0]['awayPoints']),(7,0))
        self.assertEqual(len(assumptions),1);self.assertFalse(game['completed'])
        final={**game,'completed':True}
        self.assertEqual(project_games([final],prediction,2026,target),([final],[]))
        after={**game,'startDate':'2026-09-14T00:00:00Z'}
        self.assertEqual(project_games([after],prediction,2026,target),([after],[]))
        self.assertEqual(project_games([game],prediction,2026,target,True),([game],[]))
