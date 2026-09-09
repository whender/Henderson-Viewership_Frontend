// Browser inference for the published AP movement model. Inputs contain no credentials.
const clip = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const mean = xs => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
const marketNames = ['expected', 'residual', 'over', 'under', 'disappointing_win', 'ranked_disappointing_win', 'home_disappointing_win', 'missing'];
const buckets = ['top5', '6to10', '11to25', 'unranked', 'fcs'];
const contextNames = ['early', 'early_previous', 'early_underperformance', 'early_disappointing_win', 'early_home_disappointment', 'top10_disappointment', 'early_top10_disappointment', 'peer_margin', 'peer_surprise', 'peer_ranked_wins', 'peer_margin_gap', 'peer_surprise_gap', 'impressive_peers', 'above_margin', 'above_surprise'];

export function validateScores(home, away) {
  if (String(home).trim() === '' || String(away).trim() === '') return 'Enter both scores.';
  const h = Number(home), a = Number(away);
  if (![h, a].every(v => Number.isInteger(v) && v >= 0 && v <= 200)) return 'Use whole-number scores from 0 to 200.';
  if (h === a) return 'Final scores must have a winner.';
  return '';
}

export function scenarioFeatures(payload, overrides = {}) {
  if (payload.schemaVersion !== 1 || payload.modelVersion !== 'ap-movement-v3') throw new Error('This scenario model needs an update.');
  const { teams, model } = payload, names = model.features;
  const index = Object.fromEntries(names.map((n, i) => [n, i]));
  const x = payload.baseFeatures.map(row => [...row]);
  const ids = new Map(teams.map((t, i) => [String(t.teamId), i]));
  const stats = new Map();
  const stat = id => {
    const key = String(id);
    if (!stats.has(key)) stats.set(key, { wins: 0, losses: 0, ties: 0, margin: 0, recentWins: 0, recentLosses: 0, recentMargin: 0, opponents: [], recentMargins: [] });
    return stats.get(key);
  };
  const dynamic = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20];
  for (const row of x) {
    dynamic.forEach(j => { row[j] = 0; });
    for (const period of ['season', 'recent']) {
      for (const bucket of buckets) for (const metric of ['win', 'loss', 'margin', 'close_home_win']) row[index[`${period}_ap_${bucket}_${metric}`]] = 0;
      marketNames.forEach(n => { row[index[`${period}_${n}`]] = 0; });
    }
    contextNames.forEach(n => { row[index[n]] = 0; });
  }
  for (const id of Object.keys(overrides)) {
    if (!payload.games.some(g => String(g.id) === id && g.editable && !g.completed)) throw new Error('Only listed upcoming games can be changed.');
  }
  for (const game of payload.games) {
    const override = overrides[String(game.id)];
    if (override) {
      const error = validateScores(override.home, override.away);
      if (error) throw new Error(error);
    }
    const home = override ? Number(override.home) : game.homePoints;
    const away = override ? Number(override.away) : game.awayPoints;
    if (home == null || away == null) continue;
    for (const [side, other, margin] of [['home', 'away', home - away], ['away', 'home', away - home]]) {
      const id = game[`${side}Id`], opponent = game[`${other}Id`], s = stat(id);
      const win = Number(margin > 0), loss = Number(margin < 0), bounded = clip(margin, -35, 35);
      s.wins += win; s.losses += loss; s.ties += Number(margin === 0); s.margin += bounded; s.opponents.push(opponent);
      if (game.recent) { s.recentWins += win; s.recentLosses += loss; s.recentMargin += bounded; s.recentMargins.push(margin); }
      const i = ids.get(String(id));
      if (i === undefined) continue;
      const row = x[i];
      if (game[`${side}RankedOpponent`]) { row[10] += win / 5; row[11] += loss / 5; }
      const bucket = game[`${side}Bucket`];
      const ap = { win, loss, margin: bounded / 35, close_home_win: Number(margin > 0 && margin <= 7 && side === 'home' && !game.neutralSite) };
      let market;
      if (game.homeExpected == null) market = { missing: 1 };
      else {
        const expected = game.homeExpected * (side === 'home' ? 1 : -1);
        const residual = clip(margin - expected, -35, 35) / 35;
        const disappointment = win ? Math.min(residual, 0) : 0;
        market = { expected: clip(expected, -49, 49) / 35, residual, over: Math.max(residual, 0), under: Math.min(residual, 0), disappointing_win: disappointment, ranked_disappointing_win: game[`${side}Strength`] * disappointment, home_disappointing_win: disappointment * Number(side === 'home' && !game.neutralSite), missing: 0 };
      }
      for (const period of game.recent ? ['season', 'recent'] : ['season']) {
        const divisor = period === 'season' ? 12 : 1;
        for (const [n, value] of Object.entries(ap)) row[index[`${period}_ap_${bucket}_${n}`]] += value / divisor;
        for (const [n, value] of Object.entries(market)) row[index[`${period}_${n}`]] += value / divisor;
      }
    }
  }
  const margins = [];
  teams.forEach((t, i) => {
    const s = stat(t.teamId), row = x[i], n = s.wins + s.losses + s.ties, rec = s.recentWins + s.recentLosses;
    row[5] = s.wins / 12; row[6] = s.losses / 12; row[7] = n ? (s.wins + .5 * s.ties) / n : 0; row[8] = s.margin / Math.max(n, 1) / 35;
    row[9] = mean(s.opponents.map(id => { const other = stat(id); return (other.wins + .5 * other.ties) / Math.max(other.wins + other.losses + other.ties, 1); }));
    row[12] = s.recentWins; row[13] = s.recentLosses; row[14] = s.recentMargin / Math.max(rec, 1) / 35;
    row[15] = row[0] * s.recentLosses; row[16] = row[0] * s.recentWins; row[17] = row[0] * row[14]; row[20] = Math.min(n / 12, 1);
    margins.push(s.recentMargins.length ? Math.min(...s.recentMargins) : 0);
  });
  const previous = teams.map(t => t.previousRank || 40), margin = x.map(row => row[14]), surprise = x.map(row => row[index.recent_residual]);
  const quality = x.map(row => ['top5', '6to10', '11to25'].reduce((n, b) => n + row[index[`recent_ap_${b}_win`]], 0));
  teams.forEach((t, i) => {
    const row = x[i], p = previous[i], early = Math.max(0, 1 - (row[5] * 12 + row[6] * 12) / 4);
    const below = previous.map((q, j) => q > p && q <= Math.min(p + 5, 25) ? j : -1).filter(j => j >= 0);
    const above = previous.map((q, j) => q < p && q >= Math.max(p - 5, 1) ? j : -1).filter(j => j >= 0);
    const avg = (values, subset) => mean(subset.map(j => values[j]));
    const pm = avg(margin, below), ps = avg(surprise, below), dw = row[index.recent_disappointing_win];
    const values = [early, early * row[0], early * Math.min(surprise[i], 0), early * dw, early * row[index.recent_home_disappointing_win], dw * Number(p <= 10), dw * early * Number(p <= 10), pm, ps, avg(quality, below), pm - margin[i], ps - surprise[i], below.filter(j => quality[j] > 0 || (margin[j] > .6 && surprise[j] > 0)).length / 5, avg(margin, above), avg(surprise, above)];
    contextNames.forEach((name, j) => { row[index[name]] = values[j]; });
  });
  return { x, margins, stats };
}

export function predictScenario(payload, overrides = {}) {
  const { x, margins, stats } = scenarioFeatures(payload, overrides), { model, teams } = payload;
  const scores = x.map((row, i) => {
    const bins = model.edges.map((edges, j) => { let lo = 0, hi = edges.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (row[j] < edges[mid]) hi = mid; else lo = mid + 1; } return lo; });
    let contribution = 0;
    for (const tree of model.trees) { let node = tree; while (Array.isArray(node)) node = bins[node[0]] <= node[1] ? node[2] : node[3]; contribution += model.rate * node; }
    const movement = model.bias + contribution;
    return row[0] + movement + Math.max(-movement, 0) * clip((margins[i] - 14) / 28, 0, 1);
  });
  return teams.map((t, i) => ({ t, i, score: scores[i] })).sort((a, b) => b.score - a.score || a.i - b.i).slice(0, 40).map(({ t, i }, j) => {
    const rank = j + 1, s = stats.get(String(t.teamId));
    return { ...t, wins: s?.wins || 0, losses: s?.losses || 0, ties: s?.ties || 0, rank, movement: t.previousRank ? t.previousRank - rank : null,
      drivers: [{ feature: 'scenario', label: 'Your game assumptions', contribution: null, detail: 'Custom scores plus model projections for unchanged games' }, { feature: 'prior', label: 'Previous AP', contribution: null, detail: String(t.previousRank || 'Unranked') }, { feature: 'vegas', label: 'Versus Vegas expectations', contribution: null, detail: `${(x[i][model.features.indexOf('recent_residual')] * 35).toFixed(1)} points in games with lines` }] };
  });
}
