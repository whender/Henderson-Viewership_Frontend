const independent = c => !c || /independent/i.test(c);
export const recordText = (r, projected = false) => `${projected ? r.wins.toFixed(1) : r.wins}–${projected ? r.losses.toFixed(1) : r.losses}${r.ties ? `–${r.ties}` : ''}`;
const empty = () => ({ wins: 0, losses: 0, ties: 0 });
const percentage = r => { const n = r.wins + r.losses + r.ties; return n ? (r.wins + r.ties / 2) / n : 0; };
export function buildStandings(data, projected = false) {
 const teams = new Map(data.teams.map(t => [t.team, { ...t, conference: t.conference || 'FBS Independents', overall: empty(), league: empty(), unprojected: 0 }]));
 const seen = new Set();
 for (const g of data.games) {
  if (seen.has(g.id) || g.seasonType !== 'regular' || /championship/i.test(g.notes || '')) continue;
  seen.add(g.id);
  const home = teams.get(g.home), away = teams.get(g.away);
  // The annual Army–Navy game does not count toward American standings.
  const armyNavy = [g.home,g.away].includes('Army') && [g.home,g.away].includes('Navy');
  const league = g.conferenceGame === true && home && away && home.conference === away.conference && !independent(home.conference) && !armyNavy;
  let result;
  if (g.completed && Number.isFinite(g.homePoints) && Number.isFinite(g.awayPoints)) result = Math.sign(g.homePoints-g.awayPoints);
  else if (projected && !g.completed) {
   const p = g.prediction?.home_win_probability;
   if (Number.isFinite(p) && p >= 0 && p <= 1) {
    for (const [t, wins] of [[home,p],[away,1-p]]) {
     if (!t) continue;
     t.overall.wins += wins; t.overall.losses += 1-wins;
     if (league) { t.league.wins += wins; t.league.losses += 1-wins; }
    }
    continue;
   }
  }
  if (result === undefined) { if (projected) for (const t of [home,away]) if (t) t.unprojected++; continue; }
  for (const [t,sign] of [[home,1],[away,-1]]) {
   if (!t) continue;
   const field = result === 0 ? 'ties' : result*sign > 0 ? 'wins' : 'losses';
   t.overall[field]++; if (league) t.league[field]++;
  }
 }
 return [...new Set([...teams.values()].map(t => t.conference))].sort().map(conference => {
  const isIndependent = independent(conference), rows = [...teams.values()].filter(t => t.conference === conference);
  const pct = t => percentage(isIndependent ? t.overall : t.league);
  rows.sort((a,b) => pct(b)-pct(a) || a.team.localeCompare(b.team));
  rows.forEach((t,i) => { t.position = i && pct(t) === pct(rows[i-1]) ? rows[i-1].position : i+1; });
  return { conference, isIndependent, rows };
 });
}
