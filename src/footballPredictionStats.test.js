import { defaultWeek, gradePrediction, predictionStats, weekKey } from './footballPredictionStats';

function game(overrides = {}) {
  return { id: 1, week: 1, date: '2026-09-05T20:00:00Z', completed: true,
    homePoints: 28, awayPoints: 21, predictionSource: 'archived',
    predictionAsOf: '2026-09-04T12:00:00Z',
    prediction: { predicted_margin: 10, home_win_probability: .8 }, ...overrides };
}

test('season stats use winner probabilities and correctly calculate margin and probability errors', () => {
  const stats = predictionStats([game(), game({ id: 2, homePoints: 24, awayPoints: 21,
    predictionSource: 'reconstructed', predictionAsOf: '2026-09-05T20:00:00Z',
    prediction: { predicted_margin: -7, home_win_probability: .25 } }), game({ completed: false })]);
  expect(stats.graded).toBe(2);
  expect(stats.correct).toBe(1);
  expect(stats.incorrect).toBe(1);
  expect(stats.accuracy).toBe(.5);
  expect(stats.mae).toBe(6.5);
  expect(stats.rmse).toBeCloseTo(Math.sqrt(54.5));
  expect(stats.brier).toBeCloseTo(.30125);
  expect(stats.archived).toBe(1);
  expect(stats.reconstructed).toBe(1);
});

test('missing scores, non-pregame predictions and invalid probabilities cannot affect stats', () => {
  const invalid = [game({ homePoints: null }), game({ prediction: null }),
    game({ predictionSource: 'current' }), game({ predictionAsOf: '2026-09-06T00:00:00Z' }),
    game({ prediction: { predicted_margin: 2, home_win_probability: 1.2 } })];
  expect(predictionStats(invalid).graded).toBe(0);
  expect(predictionStats(invalid).accuracy).toBeNull();
  expect(predictionStats(invalid).mae).toBeNull();
});

test('even picks and tied results are not incorrectly marked as missed winners', () => {
  expect(gradePrediction(game({ prediction: { predicted_margin: 0, home_win_probability: .5 } })).correct).toBeNull();
  const tie = gradePrediction(game({ homePoints: 21 }));
  expect(tie.correct).toBeNull();
  expect(tie.brier).toBeNull();
  expect(tie.absoluteError).toBe(10);
});

test('default week selects next upcoming slate and distinguishes postseason', () => {
  const games = [game(), game({ week: 2, date: '2026-09-12T00:00:00Z', completed: false }),
    game({ week: 1, seasonType: 'postseason', date: '2026-12-20T00:00:00Z', completed: false })];
  expect(defaultWeek(games)).toBe('regular:2');
  expect(weekKey(games[2])).toBe('postseason:1');
  expect(defaultWeek(games.map(g => ({ ...g, completed: true })))).toBe('postseason:1');
  expect(defaultWeek([])).toBe('');
});
