import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { getTeamLogoUrl } from './teamLogos';
import './FootballModel.css';
import FootballWeekly from './FootballWeekly';

const percent = value => `${(value * 100).toFixed(1)}%`;
const signed = value => `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
export function spread(margin, home, away) {
  return Math.abs(margin) < 0.05 ? 'Pick’em' : `${margin > 0 ? home : away} -${Math.abs(margin).toFixed(1)}`;
}
function Team({ name, logo, link = true }) {
  const content = <><img src={logo || getTeamLogoUrl(name)} alt="" loading="lazy" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} /><span>{name}</span></>;
  return link ? <Link className="cfb-team" to={`/football-model/teams/${encodeURIComponent(name)}`}>{content}</Link> : <span className="cfb-team">{content}</span>;
}
export default function FootballModel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${process.env.PUBLIC_URL || ''}/football/model.json`, { cache: 'no-cache', signal: controller.signal });
        if (!response.ok) throw new Error('Model data could not be loaded.');
        const next = await response.json();
        if (next.schemaVersion !== 1 || !Array.isArray(next.teams) || !Array.isArray(next.games) || !next.matchups) throw new Error('Model data is unavailable.');
        setData(next); setError('');
      } catch (err) { if (err.name !== 'AbortError') setError(err.message); }
    }
    load();
    const timer = setInterval(load, 5 * 60 * 1000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  const stale = data && Date.now() - Date.parse(data.asOf) > 3 * 86400000;
  return <main className="cfb-model">
    <header className="cfb-heading"><div><p className="home-kicker">Henderson Football</p><h2>College Football Model</h2><p>Team strength, projected spreads, and win probabilities.</p></div>
      <div className="cfb-update">{data && <><strong>{data.season} season · V2 model</strong><span>Updated {new Date(data.asOf).toLocaleString()}</span></>}</div>
    </header>
    <nav className="cfb-tabs" aria-label="Football model navigation"><NavLink end to="/football-model">Top 25</NavLink><NavLink to="/football-model/predictor">Matchup Predictor</NavLink><NavLink to="/football-model/teams">Teams & Schedules</NavLink><NavLink to="/football-model/weekly">Weekly Predictions</NavLink></nav>
    {error && <p role="alert" className="cfb-notice">{error} {data ? 'Showing the last loaded snapshot.' : 'Please try again later.'}</p>}
    {stale && <p className="cfb-notice">The last model update is more than three days old. Forecasts below use the timestamp shown above.</p>}
    {!data && !error && <p role="status">Loading football model…</p>}
    {data && <Routes><Route index element={<Rankings data={data} />} /><Route path="predictor" element={<Predictor data={data} />} /><Route path="weekly" element={<FootballWeekly data={data} />} /><Route path="teams" element={<Teams data={data} />} /><Route path="teams/:team" element={<TeamPage data={data} />} /><Route path="*" element={<p>Page not found. <Link to="/football-model">View Top 25</Link></p>} /></Routes>}
    <p className="cfb-footnote">Model projections, not sportsbook lines. Rankings measure average symmetric neutral-field margin against the FBS field. Matchup forecasts use additional model components and are not a subtraction of the rankings.</p>
  </main>;
}
function Rankings({ data }) {
  return <section className="home-panel"><div className="home-panel-header"><div><p className="home-kicker">Power Rankings</p><h3>Top 25</h3></div><Link className="home-panel-link" to="/football-model/teams">All {data.teams.length} teams</Link></div>
    <div className="overflow-x-auto"><table className="cfb-table"><thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">Conference</th><th scope="col">Rating</th><th scope="col">Games</th></tr></thead><tbody>{data.teams.slice(0, 25).map(t => <tr key={t.team_id}><td className="cfb-rank">{t.rank}</td><td><Team name={t.team} logo={t.logo} /></td><td>{t.conference || 'Independent'}</td><td className="cfb-number">{signed(t.rating)}</td><td>{t.games}</td></tr>)}</tbody></table></div></section>;
}
function Predictor({ data }) {
  const teams = useMemo(() => [...data.teams].sort((a, b) => a.team.localeCompare(b.team)), [data]);
  const [home, setHome] = useState('BYU');
  const [away, setAway] = useState('Notre Dame');
  const [neutral, setNeutral] = useState(false);
  const [useSchedule, setUseSchedule] = useState(true);
  const h = teams.find(t => t.team === home), a = teams.find(t => t.team === away);
  const key = h && a && home !== away ? `${h.team_id}:${a.team_id}:${Number(neutral)}` : null;
  const scheduled = key ? data.scheduledMatchups?.[key] : null;
  const usingSchedule = useSchedule && Boolean(scheduled);
  const result = usingSchedule ? [scheduled.margin, scheduled.probability] : data.matchups[key];
  const matchesVenue = scheduled && neutral === scheduled.actualNeutral && (neutral || home === scheduled.actualHome);
  return <section className="home-panel"><div className="home-panel-header"><div><p className="home-kicker">Hypothetical Matchup</p><h3>Who has the edge?</h3></div></div>
    <div className="cfb-controls"><label>{neutral ? 'Team 1' : 'Home team'}<select value={home} onChange={e => setHome(e.target.value)}>{teams.map(t => <option key={t.team_id}>{t.team}</option>)}</select></label><button className="btn-secondary" onClick={() => { setHome(away); setAway(home); }}>Swap teams</button><label>{neutral ? 'Team 2' : 'Away team'}<select value={away} onChange={e => setAway(e.target.value)}>{teams.map(t => <option key={t.team_id}>{t.team}</option>)}</select></label><label className="cfb-checkbox"><input type="checkbox" checked={neutral} onChange={e => setNeutral(e.target.checked)} />Neutral site</label></div>
    {scheduled && <div className="cfb-context"><label className="cfb-checkbox"><input type="checkbox" checked={useSchedule} onChange={e => setUseSchedule(e.target.checked)} />Use scheduled game context</label><p>{new Date(scheduled.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}{usingSchedule ? matchesVenue ? ' · Same forecast as the team schedule' : ' · Scheduled date and rest, with your selected venue' : ' · Disabled; using equal rest'}</p></div>}
    {home === away ? <p role="alert" className="cfb-notice">Choose two different teams.</p> : !result ? <p role="alert">This matchup is unavailable.</p> : <div className="cfb-matchup" aria-live="polite"><div className="cfb-versus"><div><Team name={home} logo={h.logo} /><strong>{percent(result[1])}</strong><span>Win probability</span></div><div className="cfb-line"><span>Projected spread</span><strong>{spread(result[0], home, away)}</strong><span>{neutral ? 'Neutral field' : `At ${home}`}</span></div><div><Team name={away} logo={a.logo} /><strong>{percent(1 - result[1])}</strong><span>Win probability</span></div></div><div className="cfb-probability" aria-label={`${home} ${percent(result[1])}, ${away} ${percent(1 - result[1])}`}><span style={{ width: percent(result[1]) }} /></div></div>}
    <p className="cfb-footnote">Home-site predictions include travel to the home team’s venue. For an upcoming scheduled matchup, its date and rest context are used by default. Turn off scheduled context to compare on equal rest. On a neutral field, swapping teams preserves the spread and each team’s win probability.</p></section>;
}
function Teams({ data }) {
  const [search, setSearch] = useState('');
  const [conference, setConference] = useState('');
  const rows = data.teams.filter(t => t.team.toLowerCase().includes(search.toLowerCase()) && (!conference || t.conference === conference));
  return <section className="home-panel"><div className="home-panel-header"><h3>Teams & Schedules</h3><span>{rows.length} teams</span></div><div className="cfb-controls"><label>Find a team<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search teams" /></label><label>Conference<select value={conference} onChange={e => setConference(e.target.value)}><option value="">All conferences</option>{[...new Set(data.teams.map(t => t.conference).filter(Boolean))].sort().map(c => <option key={c}>{c}</option>)}</select></label></div><div className="cfb-team-grid">{rows.map(t => <div className="cfb-team-card" key={t.team_id}><span className="cfb-rank">{t.rank}</span><Team name={t.team} logo={t.logo} /><span className="cfb-number">{signed(t.rating)}</span></div>)}</div>{!rows.length && <p>No teams match these filters.</p>}</section>;
}
function TeamPage({ data }) {
  const { team } = useParams();
  const navigate = useNavigate();
  const info = data.teams.find(t => t.team === team);
  if (!info) return <section className="home-panel"><h3>{team}</h3><p>This team does not have an FBS model profile.</p><Link to="/football-model/teams">Browse teams</Link></section>;
  const games = data.games.filter(g => g.home === team || g.away === team).sort((a, b) => a.date.localeCompare(b.date));
  let wins = 0, losses = 0, expected = 0;
  games.forEach(g => {
    const home = g.home === team;
    if (g.completed && g.homePoints != null && g.awayPoints != null) {
      const margin = (g.homePoints - g.awayPoints) * (home ? 1 : -1);
      if (margin > 0) { wins++; expected++; } else if (margin < 0) losses++;
    } else if (!g.completed && g.prediction) expected += home ? g.prediction.home_win_probability : g.prediction.away_win_probability;
  });
  return <section className="home-panel"><div className="home-panel-header"><div><p className="home-kicker">{info.conference || 'Independent'} · #{info.rank}</p><h3><Team name={team} logo={info.logo} link={false} /></h3></div><label className="cfb-team-picker">Change team<select value={team} onChange={e => navigate(`/football-model/teams/${encodeURIComponent(e.target.value)}`)}>{[...data.teams].sort((a,b) => a.team.localeCompare(b.team)).map(t => <option key={t.team_id}>{t.team}</option>)}</select></label></div>
    <div className="cfb-stats"><div><span>Power rating</span><strong>{signed(info.rating)}</strong></div><div><span>Current record</span><strong>{wins}–{losses}</strong></div><div><span>Expected wins</span><strong>{expected.toFixed(1)} <small>/ {games.length}</small></strong></div></div>
    <h4 className="cfb-schedule-title">{data.season} Schedule</h4><div className="overflow-x-auto"><table className="cfb-table cfb-schedule"><thead><tr><th>Week / Date</th><th>Opponent</th><th>Model spread</th><th>{team} win chance</th><th>Result</th></tr></thead><tbody>{games.map(g => {
      const home = g.home === team, opponent = home ? g.away : g.home;
      const p = g.prediction, probability = p ? (home ? p.home_win_probability : p.away_win_probability) : null;
      const line = p ? -p.predicted_margin * (home ? 1 : -1) : null;
      const actual = g.completed && g.homePoints != null && g.awayPoints != null;
      const ours = home ? g.homePoints : g.awayPoints, theirs = home ? g.awayPoints : g.homePoints;
      return <tr key={g.id}><td><strong>W{g.week}</strong><small>{new Date(g.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })}</small></td><td><div className="cfb-opponent"><span>{g.neutral ? 'N' : home ? 'vs' : 'at'}</span><Team name={opponent} logo={home ? g.awayLogo : g.homeLogo} link={data.teams.some(t => t.team === opponent)} /></div></td><td className="cfb-number">{line == null ? '—' : Math.abs(line) < 0.05 ? 'Pick’em' : `${team} ${signed(line)}`}{g.completed && p && <small title={`Forecast cutoff: ${g.predictionAsOf || 'Unavailable'}`}>{g.predictionSource === 'reconstructed' ? 'Pregame · reconstructed' : 'Pregame · archived'}</small>}</td><td>{probability == null ? '—' : <div className="cfb-chance"><strong>{percent(probability)}</strong><div><span style={{ width: percent(probability) }} /></div></div>}</td><td>{actual ? `${ours > theirs ? 'W' : ours < theirs ? 'L' : 'T'} ${ours}–${theirs}` : g.completed ? 'Final unavailable' : 'Upcoming'}</td></tr>;
    })}</tbody></table></div>{!games.length && <p>No scheduled games available.</p>}<p className="cfb-footnote">Expected wins combine actual wins with remaining-game probabilities. Spreads are from {team}’s perspective: negative means favored. Completed games show pregame spreads alongside final results. Archived forecasts were saved before kickoff; reconstructed forecasts refit ratings using only earlier results while retaining the saved model’s annual priors and calibration. Dates use the schedule’s UTC calendar date; kickoff times may be provisional.</p></section>;
}
