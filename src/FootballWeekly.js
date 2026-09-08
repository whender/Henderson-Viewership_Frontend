import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getTeamLogoUrl } from './teamLogos';
import { defaultWeek, gradePrediction, predictionStats, weekKey, weekLabel } from './footballPredictionStats';

const percent = p => `${(p * 100).toFixed(1)}%`;
const points = p => p == null ? '—' : p.toFixed(1);
const dateLabel = value => new Date(value).toLocaleDateString('en-US', {
  month: 'short', day: 'numeric', timeZone: 'UTC',
});

function TeamName({ name, logo, teams }) {
  const content = <><img src={logo || getTeamLogoUrl(name)} alt="" loading="lazy"
    onError={event => { event.currentTarget.style.visibility = 'hidden'; }} /><span>{name}</span></>;
  return teams.has(name)
    ? <Link className="cfb-team" to={`/football-model/teams/${encodeURIComponent(name)}`}>{content}</Link>
    : <span className="cfb-team">{content}</span>;
}

function Stats({ games, label }) {
  const stats = predictionStats(games);
  return <section className="cfb-week-stats" aria-label={label}>
    <div className="cfb-week-stats-heading"><h4>{label}</h4><span>{stats.graded} graded games</span></div>
    <div className="cfb-week-metrics">
      <div><span>Winner record</span><strong>{stats.correct}–{stats.incorrect}</strong>
        <small>{stats.accuracy == null ? 'No graded winner picks' : `${percent(stats.accuracy)} correct`}</small></div>
      <div><span>Average spread error</span><strong>{points(stats.mae)}</strong><small>Points · lower is better</small></div>
      <div><span>Root mean square error</span><strong>{points(stats.rmse)}</strong><small>Points · emphasizes larger misses</small></div>
      <div><span>Brier score</span><strong>{stats.brier == null ? '—' : stats.brier.toFixed(3)}</strong><small>Win-probability error · lower is better</small></div>
    </div>
    <p className="cfb-week-provenance">{stats.archived} archived · {stats.reconstructed} reconstructed forecasts</p>
  </section>;
}

function PredictionRow({ game, teams }) {
  const p = game.prediction;
  const grade = gradePrediction(game);
  const final = game.completed && Number.isFinite(game.homePoints) && Number.isFinite(game.awayPoints);
  const hasMargin = p && Number.isFinite(p.predicted_margin);
  const margin = hasMargin ? p.predicted_margin : null;
  const line = !hasMargin ? 'Unavailable' : Math.abs(margin) < 0.05 ? 'Pick’em'
    : `${margin > 0 ? game.home : game.away} -${Math.abs(margin).toFixed(1)}`;
  const hasProbability = p && Number.isFinite(p.home_win_probability);
  const pick = !hasProbability || p.home_win_probability === 0.5 ? null
    : p.home_win_probability > 0.5 ? game.home : game.away;
  const probability = hasProbability ? Math.max(p.home_win_probability, 1 - p.home_win_probability) : null;
  const source = game.predictionSource === 'reconstructed' ? 'Reconstructed pregame'
    : game.predictionSource === 'archived' ? 'Archived pregame' : 'Current forecast';
  return <tr>
    <td data-label="Date">{dateLabel(game.date)}</td>
    <td data-label="Matchup" className="cfb-week-matchup">
      <TeamName name={game.away} logo={game.awayLogo} teams={teams} />
      <span className="cfb-week-site">{game.neutral ? 'vs · neutral site' : 'at'}</span>
      <TeamName name={game.home} logo={game.homeLogo} teams={teams} />
    </td>
    <td data-label="Model spread"><strong className="cfb-number">{line}</strong>
      {p && <small title={game.predictionAsOf ? `Forecast cutoff: ${game.predictionAsOf}` : undefined}>{source}</small>}
    </td>
    <td data-label="Winner pick">{hasProbability ? <><strong>{pick || 'Even matchup'}</strong><small>{percent(probability)}</small></> : 'Unavailable'}</td>
    <td data-label="Result">{final ? <><strong>{game.awayPoints}–{game.homePoints}</strong>
      <small>{game.awayPoints === game.homePoints ? 'Final · Tie'
        : `Final · ${game.homePoints > game.awayPoints ? game.home : game.away} wins`}</small></>
      : game.completed ? 'Final unavailable' : 'Upcoming'}</td>
    <td data-label="Pick / error">{grade ? <><strong className={grade.correct === false ? 'cfb-pick-miss' : ''}>
      {grade.correct == null ? 'No winner grade' : grade.correct ? 'Correct' : 'Miss'}</strong>
      <small>{grade.absoluteError.toFixed(1)} pt error</small></> : game.completed ? 'Not graded' : '—'}</td>
  </tr>;
}

export default function FootballWeekly({ data }) {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [basis, setBasis] = useState('all');
  const ordered = [...data.games].sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id);
  const weeks = [...new Set(ordered.map(weekKey))];
  const requested = params.get('week');
  const selected = weeks.includes(requested) ? requested : defaultWeek(ordered);
  const index = weeks.indexOf(selected);
  function selectWeek(value) {
    const next = new URLSearchParams(params);
    next.set('week', value);
    setParams(next);
  }
  const seasonGames = basis === 'archived'
    ? ordered.filter(g => g.predictionSource === 'archived') : ordered;
  const weeklyGames = seasonGames.filter(g => weekKey(g) === selected);
  const visible = weeklyGames.filter(g => {
    const matchesTeam = `${g.home} ${g.away}`.toLowerCase().includes(search.toLowerCase());
    const grade = gradePrediction(g);
    const matchesStatus = status === 'all' || (status === 'completed' && g.completed)
      || (status === 'upcoming' && !g.completed) || (status === 'misses' && grade?.correct === false);
    return matchesTeam && matchesStatus;
  });
  const teams = new Set(data.teams.map(t => t.team));
  return <section className="home-panel cfb-weekly">
    <div className="home-panel-header"><div><p className="home-kicker">{data.season} Football</p><h3>Weekly Predictions</h3></div>
      <label className="cfb-week-basis">Forecasts<select value={basis} onChange={e => setBasis(e.target.value)}>
        <option value="all">All forecasts</option><option value="archived">Archived pregame only</option>
      </select></label>
    </div>
    <Stats games={seasonGames} label="Season overall" />
    <div className="cfb-controls cfb-week-controls">
      <button className="btn-secondary" disabled={index <= 0} onClick={() => selectWeek(weeks[index - 1])}>Previous week</button>
      <label>Prediction week<select value={selected} onChange={e => selectWeek(e.target.value)}>
        {!weeks.length && <option value="">No weeks available</option>}
        {weeks.map(key => <option value={key} key={key}>{weekLabel(key)}</option>)}
      </select></label>
      <button className="btn-secondary" disabled={index < 0 || index >= weeks.length - 1} onClick={() => selectWeek(weeks[index + 1])}>Next week</button>
    </div>
    {selected && <Stats games={weeklyGames} label={`${weekLabel(selected)} summary`} />}
    <div className="cfb-controls">
      <label>Find a matchup<input type="search" placeholder="Search teams" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Game status<select value={status} onChange={e => setStatus(e.target.value)}>
        <option value="all">All games</option><option value="upcoming">Upcoming</option>
        <option value="completed">Completed</option><option value="misses">Missed winner picks</option>
      </select></label>
    </div>
    <p className="cfb-week-list-caption">{visible.length} games shown · Scores list away team first. Search and status filter the game list; summary stats cover the selected forecast group.</p>
    {visible.length ? <div className="overflow-x-auto"><table className="cfb-table cfb-week-table">
      <thead><tr><th scope="col">Date</th><th scope="col">Matchup</th><th scope="col">Model spread</th>
        <th scope="col">Winner pick</th><th scope="col">Final score</th><th scope="col">Pick / error</th></tr></thead>
      <tbody>{visible.map(game => <PredictionRow key={game.id} game={game} teams={teams} />)}</tbody>
    </table></div> : <p role="status" className="cfb-notice">No games match this week and these filters.</p>}
    <p className="cfb-footnote">Only completed games with final scores and a pregame forecast are graded. Winner picks use win probability; even picks and tied results are excluded from winner accuracy. Spread error compares predicted margin with actual margin, not a sportsbook line. Brier score measures squared probability error on a 0–1 scale; lower is better.</p>
    <p className="cfb-footnote">Archived forecasts were published before kickoff. Reconstructed forecasts refit ratings using earlier results but retain the saved annual priors and calibration; their results are retrospective, not a live betting record. Select Archived pregame only to isolate the published record.</p>
  </section>;
}
