"""Regression: a running game's frozen line must not be recalculated in lookup."""
import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from export import export

@dataclass
class Team:
    team: str
    team_id: int
    rating: float = 0

@dataclass
class Prediction:
    predicted_margin: float = 99
    home_win_probability: float = .99
    away_win_probability: float = .01

class ExportLiveConsistencyTests(unittest.TestCase):
    def test_archived_running_game_and_neutral_reverse_use_identical_line(self):
        now=datetime.now(UTC);kickoff=now-timedelta(minutes=20)
        for neutral in [False,True]:
            with self.subTest(neutral=neutral), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'model.json'
                game={'id':1,'season':2026,'week':3,'seasonType':'regular','startDate':kickoff.isoformat(),'completed':False,'neutralSite':neutral,'homeId':1,'homeTeam':'A','awayId':2,'awayTeam':'B','homeClassification':'fbs','awayClassification':'fbs','homePoints':0,'awayPoints':7}
                saved={'id':1,'home':'A','away':'B','neutral':neutral,'date':kickoff.isoformat(),'predictionAsOf':(kickoff-timedelta(minutes=30)).isoformat(),'predictionSource':'archived','prediction':{'predicted_margin':8.496001721347698,'home_win_probability':.72,'away_win_probability':.28}}
                model=SimpleNamespace(season=2026,as_of=now,rankings=lambda:[Team('A',1),Team('B',2)],predict=lambda *a,**kw:Prediction(),predict_game=lambda *a,**kw:Prediction())
                with patch('export.reconstruct_pregame',side_effect=AssertionError('Must retain the archived forecast')):
                    export(model,[game],output,[],archive={1:saved})
                data=json.loads(output.read_text());actual=data['games'][0]['prediction'];lookup=data['scheduledMatchups'][f'1:2:{int(neutral)}']
                self.assertEqual(lookup['margin'],actual['predicted_margin'])
                self.assertEqual(lookup['probability'],actual['home_win_probability'])
                self.assertEqual(data['games'][0]['predictionSource'],'archived')
                if neutral:
                    reverse=data['scheduledMatchups']['2:1:1']
                    self.assertEqual(reverse['margin'],-actual['predicted_margin'])
                    self.assertAlmostEqual(reverse['probability'],1-actual['home_win_probability'])
                else:
                    self.assertEqual(data['scheduledMatchups']['2:1:0']['margin'],99)
