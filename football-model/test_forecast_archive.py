import unittest
from copy import deepcopy
from datetime import datetime,timezone
from forecast_archive import records
from export import saved_pregame
from cfbpredict.games import Game

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.game={'id':1,'date':'2026-09-12T16:00:00+00:00','home':'Home','away':'Away','neutral':False,'completed':False,'prediction':{'predicted_margin':7},'predictionAsOf':'2026-09-12T15:00:00+00:00','predictionSource':'current'}
        self.snapshot={'asOf':self.game['predictionAsOf'],'generatedAt':'2026-09-12T15:01:00+00:00','season':2026,'games':[self.game]}
    def test_only_verified_pregame_current_forecasts_are_archived(self):
        args=(self.snapshot,'2026-09-12T15:02:00+00:00',{'type':'test'})
        self.assertEqual(records(*args),records(*args))
        self.assertEqual(len(records(*args)),1)
        self.assertEqual(records(self.snapshot,self.game['date'],{}),[])
        self.game['predictionSource']='reconstructed';self.assertEqual(records(*args),[])
        self.game['predictionSource']='current';self.game['completed']=True;self.assertEqual(records(*args),[])
    def test_generation_after_kickoff_is_rejected_even_with_early_model(self):
        self.snapshot['generatedAt']='2026-09-12T16:01:00+00:00'
        self.assertEqual(records(self.snapshot,'2026-09-12T15:02:00+00:00',{}),[])
    def test_frozen_pregame_pick_survives_live_partial_scores(self):
        import gzip,json
        from pathlib import Path
        from dataclasses import replace
        raw=json.loads(gzip.decompress((Path(__file__).parent/'games.json.gz').read_bytes()))
        g=Game.from_cfbd(raw[0]);g=replace(g,start_date=datetime(2026,9,12,16,tzinfo=timezone.utc),home_team='Home',away_team='Away',neutral_site=False,completed=False,home_points=0,away_points=35)
        entry=records(self.snapshot,'2026-09-12T15:02:00+00:00',{})[0]
        self.assertEqual(saved_pregame(entry,g,None)[0]['predicted_margin'],7)
        entry['observedAt']='2026-09-12T16:02:00+00:00';self.assertIsNone(saved_pregame(entry,g,None))
