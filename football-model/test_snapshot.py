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
                self.assertIsNotNone(game['prediction'])
                self.assertIn(game['predictionSource'], ('archived', 'reconstructed'))
                self.assertLessEqual(game['predictionAsOf'], game['date'])
            if game['prediction']:
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

class PregameHistoryTests(unittest.TestCase):
    def test_archive_requires_a_forecast_from_before_kickoff(self):
        import gzip
        from export import saved_pregame
        from cfbpredict.games import normalize_games
        with gzip.open(ROOT / 'games.json.gz', 'rt') as f:
            game = next(g for g in normalize_games(json.load(f))
                        if g.season == 2026 and g.completed and g.home_team == 'BYU')
        old = dict(home=game.home_team, away=game.away_team, date=game.start_date.isoformat(),
                   neutral=game.neutral_site, prediction={'predicted_margin': 12.3})
        cutoff = '2026-08-01T00:00:00+00:00'
        self.assertEqual(saved_pregame(old, game, cutoff), (old['prediction'], 'archived', cutoff))
        self.assertIsNone(saved_pregame(old, game, game.start_date.isoformat()))
        self.assertIsNone(saved_pregame(old, game, '2026-12-31T00:00:00+00:00'))
        old['predictionSource'] = 'reconstructed'
        old['predictionAsOf'] = game.start_date.isoformat()
        self.assertEqual(saved_pregame(old, game, cutoff)[1], 'reconstructed')

    def test_reconstructed_spread_excludes_target_and_later_scores(self):
        import gzip
        from dataclasses import replace
        from export import reconstruct_pregame
        from cfbpredict.games import normalize_games
        model = CollegeFootballV2Model.load(ROOT / 'model.json')
        with gzip.open(ROOT / 'games.json.gz', 'rt') as f:
            history = normalize_games(json.load(f))
        with gzip.open(ROOT / 'advanced.json.gz', 'rt') as f:
            advanced = json.load(f)
        game = next(g for g in history if g.season == 2026 and g.completed and g.home_team == 'BYU')
        before = reconstruct_pregame(model, history, advanced, game.start_date)
        changed = [replace(g, home_points=100, away_points=0)
                   if g.start_date >= game.start_date and g.completed else g for g in history]
        after = reconstruct_pregame(model, changed, advanced, game.start_date)
        p1 = before.predict_game(game, history)
        p2 = after.predict_game(game, changed)
        self.assertAlmostEqual(p1.predicted_margin, p2.predicted_margin)
        self.assertAlmostEqual(p1.home_win_probability, p2.home_win_probability)
