// Grade only completed games with a pregame forecast and usable final scores.
export function gradePrediction(game) {
  const p = game.prediction;
  const archived = game.predictionSource === 'archived';
  const reconstructed = game.predictionSource === 'reconstructed';
  const cutoff = Date.parse(game.predictionAsOf);
  const kickoff = Date.parse(game.date);
  if (!game.completed || (!archived && !reconstructed) || !p
      || !Number.isFinite(game.homePoints) || !Number.isFinite(game.awayPoints)
      || !Number.isFinite(p.predicted_margin) || !Number.isFinite(p.home_win_probability)
      || p.home_win_probability < 0 || p.home_win_probability > 1
      || !Number.isFinite(cutoff) || !Number.isFinite(kickoff)
      || cutoff > kickoff || (archived && cutoff === kickoff)) return null;
  const actualMargin = game.homePoints - game.awayPoints;
  const error = p.predicted_margin - actualMargin;
  const hasWinner = actualMargin !== 0;
  const hasPick = p.home_win_probability !== 0.5;
  return {
    correct: hasWinner && hasPick
      ? (p.home_win_probability > 0.5) === (actualMargin > 0) : null,
    absoluteError: Math.abs(error),
    squaredError: error * error,
    brier: hasWinner ? (p.home_win_probability - Number(actualMargin > 0)) ** 2 : null,
    source: game.predictionSource,
  };
}

export function predictionStats(games) {
  const grades = games.map(gradePrediction).filter(Boolean);
  const picks = grades.filter(g => g.correct !== null);
  const probabilities = grades.filter(g => g.brier !== null);
  const correct = picks.filter(g => g.correct).length;
  return {
    graded: grades.length,
    correct,
    incorrect: picks.length - correct,
    accuracy: picks.length ? correct / picks.length : null,
    mae: grades.length ? grades.reduce((sum, g) => sum + g.absoluteError, 0) / grades.length : null,
    rmse: grades.length ? Math.sqrt(grades.reduce((sum, g) => sum + g.squaredError, 0) / grades.length) : null,
    brier: probabilities.length ? probabilities.reduce((sum, g) => sum + g.brier, 0) / probabilities.length : null,
    reconstructed: grades.filter(g => g.source === 'reconstructed').length,
    archived: grades.filter(g => g.source === 'archived').length,
  };
}

export function weekKey(game) {
  return `${game.seasonType || 'regular'}:${game.week}`;
}
export function weekLabel(key) {
  const [type, week] = key.split(':');
  return `${type === 'postseason' ? 'Postseason · ' : ''}Week ${week}`;
}
export function defaultWeek(games) {
  const ordered = [...games].sort((a, b) => a.date.localeCompare(b.date));
  const upcoming = ordered.find(g => !g.completed);
  return upcoming ? weekKey(upcoming) : ordered.length ? weekKey(ordered[ordered.length - 1]) : '';
}
