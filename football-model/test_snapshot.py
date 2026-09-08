import json
import unittest
from pathlib import Path
from cfbpredict.v2 import CollegeFootballV2Model

ROOT = Path(__file__).resolve().parent

class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT.parent / 'public/football/model.json').read_text())
        cls.model = CollegeFootballV2Model.load(ROOT / 'model.json')

    def test_rankings_match_actual_model(self):
        actual = self.model.rankings(limit=25)
        for expected, row in zip(actual, self.data['teams'][:25]):
            self.assertEqual(expected.team, row['team'])
            self.assertAlmostEqual(expected.rating, row['rating'])

    def test_matchups_match_model_at_both_venues(self):
        for home, away in [('BYU', 'Notre Dame'), ('Notre Dame', 'BYU'), ('Ohio State', 'Miami')]:
            h = next(t for t in self.data['teams'] if t['team'] == home)
            a = next(t for t in self.data['teams'] if t['team'] == away)
            for neutral in [False, True]:
                p = self.model.predict(home, away, neutral_site=neutral)
                result = self.data['matchups'][f"{h['team_id']}:{a['team_id']}:{int(neutral)}"]
                self.assertAlmostEqual(result[0], p.predicted_margin, places=5)
                self.assertAlmostEqual(result[1], p.home_win_probability, places=7)

    def test_complete_consistent_snapshot(self):
        teams = self.data['teams']
        self.assertEqual(self.data['asOf'], self.model.as_of.isoformat())
        self.assertEqual(len(self.data['matchups']), len(teams) * (len(teams) - 1) * 2)
        self.assertEqual(len({g['id'] for g in self.data['games']}), len(self.data['games']))
        for game in self.data['games']:
            if game['completed']:
                self.assertIsNone(game['prediction'])
            elif game['prediction']:
                p = game['prediction']
                self.assertAlmostEqual(p['home_win_probability'] + p['away_win_probability'], 1)
                self.assertTrue(0 <= p['home_win_probability'] <= 1)

if __name__ == '__main__':
    unittest.main()

class PredictionConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT.parent / 'public/football/model.json').read_text())
        cls.model = CollegeFootballV2Model.load(ROOT / 'model.json')

    def test_every_neutral_matchup_is_order_independent(self):
        for key, (margin, probability) in self.data['matchups'].items():
            home, away, neutral = key.split(':')
            if neutral != '1':
                continue
            reverse = self.data['matchups'][f'{away}:{home}:1']
            self.assertAlmostEqual(margin, -reverse[0], places=5)
            self.assertAlmostEqual(probability, 1 - reverse[1], places=7)

    def test_scheduled_predictor_matches_every_upcoming_fbs_game(self):
        teams = {t['team']: t['team_id'] for t in self.data['teams']}
        checked = set()
        for game in sorted(self.data['games'], key=lambda g: (g['date'], g['id'])):
            if game['completed'] or game['home'] not in teams or game['away'] not in teams:
                continue
            key = f"{teams[game['home']]}:{teams[game['away']]}:{int(game['neutral'])}"
            if key in checked:
                continue
            checked.add(key)
            scheduled = self.data['scheduledMatchups'][key]
            self.assertEqual(scheduled['gameId'], game['id'])
            self.assertAlmostEqual(scheduled['margin'], game['prediction']['predicted_margin'])
            self.assertAlmostEqual(scheduled['probability'], game['prediction']['home_win_probability'])

    def test_scheduled_neutral_matchups_are_symmetric_with_rest(self):
        for key, p in self.data['scheduledMatchups'].items():
            home, away, neutral = key.split(':')
            if neutral != '1':
                continue
            reverse = self.data['scheduledMatchups'][f'{away}:{home}:1']
            self.assertAlmostEqual(p['margin'], -reverse['margin'])
            self.assertAlmostEqual(p['probability'], 1 - reverse['probability'])
