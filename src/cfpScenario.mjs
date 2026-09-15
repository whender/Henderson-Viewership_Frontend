/* Shared browser/exporter engine. Power responses reproduce the Python ridge fit. */
const mean = xs => xs.length ? xs.reduce((a, b) => a + Number(b), 0) / xs.length : 0;
const sigmoid = x => 1 / (1 + Math.exp(-x));
const compareNames = (a, b) => a.team.toLowerCase() < b.team.toLowerCase() ? -1 : a.team.toLowerCase() > b.team.toLowerCase() ? 1 : 0;
function random(seed) {
  let state = seed >>> 0;
  return () => { state += 0x6D2B79F5; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function eligibleGames(engine, eligibleTeams) {
  const keys = new Set(eligibleTeams.map(t => t.key));
  return engine.games.filter(g => g.projected && (keys.has(g.homeKey) || keys.has(g.awayKey)));
}
function projectScenario(engine, index = 0, overrides = {}, eligibleTeams = []) {
  if (!engine || engine.version !== 1) throw new Error('CFP scenario data needs an update.');
  const allowed = new Set(eligibleGames(engine, eligibleTeams).map(g => String(g.id)));
  const rng = random(2026 + index * 7919);
  const powers = engine.teams.map(t => t.power);
  const games = engine.games.map(g => {
    if (!g.projected) return g;
    const draw = rng();
    const forced = allowed.has(String(g.id)) && [g.homeKey, g.awayKey].includes(overrides[g.id]) ? overrides[g.id] : null;
    const homeWin = forced ? forced === g.homeKey : index === 0 ? g.probability >= .5 : draw < g.probability;
    if (!homeWin && g.powerChange) g.powerChange.forEach((v, i) => { powers[i] += v; });
    return {...g, homeWin, forced: Boolean(forced)};
  });
  const teams = engine.teams.map((t, i) => ({...t, power: powers[i]}));
  const byKey = Object.fromEntries(teams.map(t => [t.key, t]));
  const ordered = [...teams].sort((a, b) => b.power - a.power || compareNames(a, b));
  const powerRank = Object.fromEntries(ordered.map((t, i) => [t.key, i + 1]));
  const minimum = ordered[ordered.length - 1].power;
  const median = (ordered[Math.floor((ordered.length - 1) / 2)].power + ordered[Math.floor(ordered.length / 2)].power) / 2;
  const reference = ordered[Math.min(24, ordered.length - 1)].power;
  const records = Object.fromEntries(teams.map(t => [t.key, []]));
  const opponents = {};
  games.forEach(g => {
    [[g.homeKey, g.awayKey, g.homeWin, g.awayClassification, g.away, g.awayId], [g.awayKey, g.homeKey, !g.homeWin, g.homeClassification, g.home, g.homeId]].forEach(([key, opponent, won, classification, name, id]) => {
      if (!opponents[key]) opponents[key] = {};
      if (!opponents[key][opponent]) opponents[key][opponent] = [];
      opponents[key][opponent].push(won);
      if (records[key]) records[key].push({g, opponent, won, classification, name, id});
    });
  });
  const wins = Object.fromEntries(teams.map(t => [t.key, records[t.key].filter(r => r.won).length]));
  const owp = r => records[r.opponent] ? records[r.opponent].length > 1 ? (wins[r.opponent] - Number(!r.won)) / (records[r.opponent].length - 1) : .5 : .35;
  const baseOwp = Object.fromEntries(teams.map(t => [t.key, mean(records[t.key].map(owp))]));
  const model = engine.model;
  const rows = teams.map(t => {
    const rs = records[t.key], w = wins[t.key], losses = rs.length - w;
    const qualities = [], winQualities = [], bestWins = [], worstLosses = [];
    let strength = 0, top10 = 0, top25 = 0, road = 0, bad = 0, fcs = 0, champion = false, runnerUp = false;
    rs.forEach(r => {
      const power = byKey[r.opponent]?.power ?? minimum - (r.classification === 'fcs' ? 8 : 15);
      const quality = sigmoid((power - median) / 7), site = r.g.neutral ? 0 : r.g.homeKey === t.key ? 2 : -2;
      const probability = Math.max(.03, Math.min(.97, sigmoid((reference - power + site) / 8.5)));
      qualities.push(quality); strength += r.won ? -Math.log(probability) : Math.log(1 - probability);
      if (r.classification === 'fcs') fcs++;
      if (r.g.championship) { if (r.won) champion = true; else runnerUp = true; }
      const highlight = {gameId: r.g.id, team: r.name, teamId: r.id, power};
      if (r.won) {
        winQualities.push(quality); top10 += Number(powerRank[r.opponent] <= 10); top25 += Number(powerRank[r.opponent] <= 25);
        if (site <= 0) road += quality;
        bestWins.push(highlight);
      } else { bad += Number((powerRank[r.opponent] ?? teams.length + 1) > 50 || r.classification !== 'fbs'); worstLosses.push(highlight); }
    });
    winQualities.sort((a, b) => b - a);
    const schedule = (2 * mean(rs.map(owp)) + mean(rs.map(r => baseOwp[r.opponent] ?? .30))) / 3;
    const values = {wins: w, losses, win_percentage: rs.length ? w / rs.length : 0, record_strength: strength, schedule_strength: schedule, average_opponent_quality: mean(qualities), strong_schedule_rate: mean(qualities.map(v => v >= .70)), best_win_quality: winQualities[0] || 0, second_best_win_quality: winQualities[1] || 0, top_10_wins: top10, top_25_wins: top25, road_quality_wins: road, bad_losses: bad, fcs_games: fcs, conference_champion: Number(champion), conference_runner_up: Number(runnerUp), power_rating: t.power, undefeated: Number(rs.length > 0 && losses === 0), one_loss: Number(losses === 1)};
    const base = model.feature_schema.reduce((sum, k) => sum + model.coefficients[k] * values[k] / model.feature_scales[k], 0);
    const highlights = (rs, sign) => rs.sort((a, b) => sign * (a.power - b.power) || compareNames(a, b) || a.gameId - b.gameId).slice(0, 3).map(({power, ...r}) => r);
    return {...t, wins: w, losses, qualityWins: top25, badLosses: bad, recordStrength: strength, scheduleStrength: schedule, bestWins: highlights(bestWins, -1), worstLosses: highlights(worstLosses, 1), base, score: 0};
  }).sort(compareNames);
  rows.forEach((a, i) => rows.slice(i + 1).forEach(b => {
    let logit = a.base - b.base;
    if (Math.abs(logit) <= model.comparable_window) {
      const ar = opponents[a.key] || {}, br = opponents[b.key] || {};
      const direct = ar[b.key] ? 2 * mean(ar[b.key]) - 1 : 0;
      const common = Object.keys(ar).filter(k => k !== a.key && k !== b.key && br[k]);
      logit += model.head_to_head_coefficient * direct + model.common_opponent_coefficient * mean(common.map(k => mean(ar[k]) - mean(br[k])));
    }
    const p = sigmoid(logit); a.score += p; b.score += 1 - p;
  }));
  rows.sort((a, b) => b.score - a.score || b.base - a.base || compareNames(a, b));
  return {rows: rows.map((r, i) => ({...r, rank: i + 1})), assumptions: games.filter(g => g.projected).map(g => ({id:g.id, home:g.home, away:g.away, homeWin:g.homeWin, probability:g.probability, margin:g.margin, forced:g.forced, winner: g.homeWin ? g.home : g.away, winnerProbability: g.homeWin ? g.probability : 1 - g.probability}))};
}
function contenderPool(engine, count = 1000) {
  const stats = Object.fromEntries(engine.teams.map(t => [t.key, {...t, top25: 0, rankSum: 0}]));
  for (let i = 1; i <= count; i++) projectScenario(engine, i).rows.forEach(r => { stats[r.key].top25 += Number(r.rank <= 25); stats[r.key].rankSum += r.rank; });
  return Object.values(stats).sort((a, b) => b.top25 - a.top25 || a.rankSum - b.rankSum || compareNames(a, b)).slice(0, 25).map(({power, top25, rankSum, ...t}) => ({...t, probability: top25 / count}));
}
export {projectScenario, contenderPool, eligibleGames};
