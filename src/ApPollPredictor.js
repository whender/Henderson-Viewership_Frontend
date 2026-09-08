import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const pct = x => `${(x * 100).toFixed(1)}%`;
function LogoTeam({ team, id }) {
  const numeric = /^\d+$/.test(String(id));
  return <span className="cfb-team">{numeric && <img src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${id}.png`} alt="" loading="lazy" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} />}<span>{team}</span></span>;
}
function RankingTable({ rows, official = false, showDrivers = false }) {
  return <div className="overflow-x-auto"><table className="cfb-table ap-table"><thead><tr><th scope="col">{official ? 'AP rank' : 'Projected'}</th><th scope="col">Team</th><th scope="col">Record</th>{!official && <><th scope="col">Previous AP</th><th scope="col">Move</th>{showDrivers && <th scope="col">Model factors</th>}</>}</tr></thead>
    <tbody>{rows.map(t => <tr key={t.teamId}><td className="cfb-rank">{t.rank}</td><td><LogoTeam team={t.team || t.school} id={t.teamId} /></td><td className="cfb-number">{official ? t.record || '—' : `${t.wins}–${t.losses}${t.ties ? `–${t.ties}` : ''}`}</td>{!official && <><td>{t.previousRank || 'NR'}</td><td className={t.movement > 0 ? 'ap-rise' : t.movement < 0 ? 'ap-fall' : ''}>{t.movement == null ? 'New' : t.movement > 0 ? `+${t.movement}` : t.movement || '—'}</td>{showDrivers && <td><details><summary>Why this rank?</summary><ul className="ap-factor-list">{t.drivers.map(d => <li key={d.feature}>{d.label} <span>{d.contribution >= 0 ? 'Supports' : 'Lowers'} score</span></li>)}</ul></details></td>}</>}</tr>)}</tbody></table></div>;
}
export default function ApPollPredictor() {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [view, setView] = useState('outlook'), [basis, setBasis] = useState('projected');
  const [year, setYear] = useState(''), [pollId, setPollId] = useState(''), [search, setSearch] = useState(''), [bubble, setBubble] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetch(`${process.env.PUBLIC_URL || ''}/football/ap.json`, { cache: 'no-cache', signal: controller.signal });
        if (!response.ok) throw new Error('AP poll predictions are temporarily unavailable.');
        const next = await response.json();
        if (next.schemaVersion !== 1) throw new Error('AP poll data needs an update.');
        setData(next); setError('');
      } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
    };
    load(); const timer = setInterval(load, 300000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  if (!data) return <p role={error ? 'alert' : 'status'}>{error || 'Loading AP poll predictor…'}</p>;
  const years = [...new Set(data.history.map(p => p.season))];
  const selectedYear = year ? Number(year) : data.season;
  const polls = data.history.filter(p => p.season === selectedYear);
  const historical = polls.find(p => String(p.id) === pollId) || polls[0];
  const ranking = basis === 'projected' ? data.next.rows : data.next.resultsSoFar;
  const visible = ranking.filter(t => (bubble || t.rank <= 25) && t.team.toLowerCase().includes(search.toLowerCase()));
  const stats = data.overallEvaluation;
  return <section className="home-panel ap-predictor">
    <div className="home-panel-header"><div><p className="home-kicker">AP voting model</p><h3>AP Poll Predictor</h3><p className="ap-subtitle">Predicting the voters’ Top 25.</p></div><div className="ap-timestamp">Updated {new Date(data.asOf).toLocaleString()}</div></div>
    {error && <p role="alert" className="cfb-notice">{error} Showing the last loaded forecast.</p>}
    {Date.now() - Date.parse(data.asOf) > 3 * 86400000 && <p className="cfb-notice">This AP forecast is more than three days old. Check its update time before using it.</p>}
    <div className="ap-view-controls" role="group" aria-label="AP predictor views">{[['outlook','Next poll'],['latest','Latest poll check'],['history','Poll archive'],['model','Model & accuracy']].map(([key,label]) => <button key={key} className={view === key ? 'ap-view active' : 'ap-view'} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div>
    {view === 'outlook' && <>
      <div className="ap-outlook-heading"><h4>Next release outlook</h4><span>Estimated release: {data.next.estimatedReleaseDate}</span></div>
      <div className="cfb-controls"><label>Forecast basis<select value={basis} onChange={e => setBasis(e.target.value)}><option value="projected">Project remaining games</option><option value="sofar">Completed results only</option></select></label><label>Find a team<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search teams" /></label><label className="cfb-checkbox"><input type="checkbox" checked={bubble} onChange={e => setBubble(e.target.checked)} />Include bubble teams (26–40)</label></div>
      <p className="cfb-notice">{basis === 'projected' ? `Assumes the football model’s favored teams win ${data.next.assumptions.length} remaining games before the estimated release. Records include those projected results.` : 'Uses completed results available now. Unplayed games are excluded; this outlook will change as results arrive.'} Movement is relative to the {data.latest.label} AP poll.</p>
      {visible.length ? <RankingTable rows={visible} showDrivers /> : <p role="status">No teams match your search.</p>}
      {basis === 'projected' && <details className="ap-details"><summary>Game assumptions ({data.next.assumptions.length})</summary><p>One scenario using the football model’s winner and margin estimates. No game scores are being reported as actual results.</p><div className="ap-assumptions">{data.next.assumptions.map(g => <div key={g.id}><span>{g.away} at {g.home}</span><strong>{g.winner} by {g.margin.toFixed(1)}</strong></div>)}</div></details>}
    </>}
    {view === 'latest' && <>
      <h4 className="cfb-schedule-title">{data.season} · {data.latest.label} AP poll</h4>
      <p className="cfb-footnote ap-note">{data.latest.forecastSource}. The prediction excludes this poll’s rankings. Earlier reconstructions are not forecasts published before release.</p>
      <div className="overflow-x-auto"><table className="cfb-table"><thead><tr><th scope="col">Actual AP</th><th scope="col">Team</th><th scope="col">Predicted</th><th scope="col">Rank error</th></tr></thead><tbody>{data.latest.official.map(t => { const prediction = data.latest.rows.find(r => String(r.teamId) === String(t.teamId)); const rank = prediction?.rank; return <tr key={t.teamId}><td className="cfb-rank">{t.rank}</td><td><LogoTeam team={t.school} id={t.teamId} /></td><td>{rank && rank <= 25 ? rank : 'NR'}</td><td>{Math.abs(Math.min(rank || 26, 26) - t.rank)}</td></tr>; })}</tbody></table></div>
    </>}
    {view === 'history' && <>
      <div className="cfb-controls"><label>AP season<select value={selectedYear} onChange={e => { setYear(e.target.value); setPollId(''); }}>{years.map(y => <option key={y}>{y}</option>)}</select></label><label>AP poll<select value={historical?.id || ''} onChange={e => setPollId(e.target.value)}>{polls.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label></div>
      {historical && <><h4 className="cfb-schedule-title">{selectedYear} · {historical.label} · AP Top {historical.size}</h4><RankingTable rows={historical.ranks} official /></>}
      <p className="cfb-footnote">Official historical rankings, including tied ranks. The AP used Top 10 and Top 20 formats before expanding to 25 teams in 1989.</p>
    </>}
    {view === 'model' && <>
      <div className="cfb-week-stats"><div className="cfb-week-stats-heading"><h4>Historical validation · 2019–2025</h4><span>{stats.polls} in-season polls</span></div><div className="cfb-week-metrics">
        <div><span>Top 25 membership</span><strong>{pct(stats.overlap)}</strong><small>Previous-poll baseline: {pct(stats.baselineOverlap)}</small></div>
        <div><span>Average rank error</span><strong>{stats.rankError.toFixed(2)}</strong><small>Previous-poll baseline: {stats.baselineRankError.toFixed(2)}</small></div>
        <div><span>Historical archive</span><strong>{data.coverage.polls.toLocaleString()}</strong><small>{data.coverage.startYear}–{data.coverage.endYear}</small></div>
        <div><span>Training polls</span><strong>{data.trainingPolls.toLocaleString()}</strong><small>Through {data.trainingThrough}; {data.excludedTrainingPolls.length} targets excluded</small></div>
      </div></div>
      <p className="cfb-footnote">Each validation season was predicted using a model trained only on prior seasons. Top 25 membership is the fraction of actual ranked teams included in the predicted list. Rank error measures actual ranked teams, with unranked predictions counted as 26. The baseline keeps the previous poll order.</p>
      <div className="overflow-x-auto ap-validation"><table className="cfb-table"><thead><tr><th scope="col">Season</th><th scope="col">Polls</th><th scope="col">Top 25 overlap</th><th scope="col">Rank error</th><th scope="col">Baseline error</th></tr></thead><tbody>{data.evaluation.map(e => <tr key={e.season}><td>{e.season}</td><td>{e.polls}</td><td>{pct(e.overlap)}</td><td>{e.rankError.toFixed(2)}</td><td>{e.baselineRankError.toFixed(2)}</td></tr>)}</tbody></table></div>
      <h4 className="cfb-schedule-title">What the model learns</h4><p className="cfb-footnote ap-note">Largest fitted effects per one historical standard deviation. These are associations, not causal explanations; correlated factors can share or offset influence.</p>
      <div className="ap-drivers">{data.drivers.slice(0,10).map(d => <div key={d.feature}><span>{d.label}</span><span className="cfb-number">{d.effect >= 0 ? '+' : ''}{d.effect.toFixed(3)}</span><div className="ap-driver-track"><span style={{ width: `${Math.abs(d.effect) / Math.max(...data.drivers.map(v => Math.abs(v.effect)), .001) * 100}%` }} /></div></div>)}</div>
      <details className="ap-details"><summary>Methodology and data coverage</summary><ul>{data.methodology.map(m => <li key={m}>{m}</li>)}</ul>{data.excludedTrainingPolls.length > 0 && <p>Excluded target polls: {data.excludedTrainingPolls.map(p => `${p.season} #${p.id}`).join(', ')}. These polls remain in the archive and earlier-poll history.</p>}<p>{data.sources.map(s => <a key={s.url} href={s.url} target="_blank" rel="noreferrer">{s.title}</a>)}</p></details>
    </>}
    <p className="cfb-footnote">AP poll projections are separate from <Link to="/football-model">Henderson’s power rankings</Link>. This is an independent prediction model, not an AP product. Forecasts update automatically.</p>
  </section>;
}
