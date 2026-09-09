import { useEffect, useState } from 'react';

const pct = n => `${(n * 100).toFixed(1)}%`;
function Team({ row }) {
  return <span className="cfb-team">{row.teamId && <img src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${row.teamId}.png`} alt="" loading="lazy" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} />}<span>{row.team}</span></span>;
}
function Comparison({ poll }) {
  return <><p className="cfb-footnote ap-note">{poll.forecastSource}. Reconstructed predictions use only results available before this release.</p><div className="overflow-x-auto"><table className="cfb-table"><thead><tr><th>CFP rank</th><th>Team</th><th>Record</th><th>Predicted rank</th><th>Error</th></tr></thead><tbody>{poll.rows.map(t => <tr key={t.team}><td className="cfb-rank">{t.rank}</td><td><Team row={t} /></td><td>{t.record}</td><td>{t.predictedRank ?? '—'}</td><td>{t.predictedRank == null ? '—' : Math.abs(t.predictedRank - t.rank)}</td></tr>)}</tbody></table></div></>;
}
export default function CfpPollPredictor() {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [view, setView] = useState('outlook'), [basis, setBasis] = useState('today');
  const [search, setSearch] = useState(''), [bubble, setBubble] = useState(false), [year, setYear] = useState(''), [date, setDate] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${process.env.PUBLIC_URL || ''}/football/cfp.json`, { cache: 'no-cache', signal: controller.signal });
        if (!response.ok) throw new Error('CFP predictions are temporarily unavailable.');
        const value = await response.json();
        if (value.schemaVersion !== 1) throw new Error('CFP prediction data needs an update.');
        setData(value); setError('');
      } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
    }
    load(); const timer = setInterval(load, 300000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  if (!data) return <p role={error ? 'alert' : 'status'}>{error || 'Loading CFP predictor…'}</p>;
  const years = [...new Set(data.history.map(p => p.season))].sort((a, b) => b - a);
  const selectedYear = Number(year || years[0]);
  const polls = data.history.filter(p => p.season === selectedYear);
  const poll = polls.find(p => p.releaseDate === date) || polls[0];
  const rows = (basis === 'today' ? data.today : data.next.rows).filter(t => (bubble || t.rank <= 25) && t.team.toLowerCase().includes(search.toLowerCase()));
  const stats = data.overallEvaluation;
  return <section className="home-panel ap-predictor">
    <div className="home-panel-header"><div><p className="home-kicker">Selection committee model</p><h3>CFP Rankings Predictor</h3><p className="ap-subtitle">Predicting the committee’s Top 25.</p></div><div className="ap-timestamp">Updated {new Date(data.asOf).toLocaleString()}</div></div>
    {error && <p role="alert" className="cfb-notice">{error} Showing the last loaded forecast.</p>}
    {Date.now() - Date.parse(data.asOf) > 3 * 86400000 && <p className="cfb-notice">This forecast is more than three days old. Check its update time before using it.</p>}
    <div className="ap-view-controls" role="group" aria-label="CFP predictor views">{[['outlook','Outlook'],['latest','Latest rankings'],['history','Rankings archive'],['model','Model & accuracy']].map(([key, label]) => <button key={key} className={`ap-view${view === key ? ' active' : ''}`} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div>
    {view === 'outlook' && <>
      <div className="ap-outlook-heading"><h4>{basis === 'today' ? 'Resume rankings today' : 'Next release scenario'}</h4><span>{data.next.releaseDate ? `Next CFP release: ${data.next.releaseDate}` : 'Final CFP release complete'}</span></div>
      {!data.latest && <p className="cfb-footnote ap-note">The {data.season} committee rankings have not started. First release: {data.firstRelease}. Early-season estimates have limited results to work with.</p>}
      <div className="cfb-controls"><label>Ranking basis<select value={basis} onChange={e => setBasis(e.target.value)}><option value="today">Completed results only</option><option value="projected">Project to next release</option></select></label><label>Find a team<input type="search" placeholder="Search teams" value={search} onChange={e => setSearch(e.target.value)} /></label><label className="cfb-checkbox"><input type="checkbox" checked={bubble} onChange={e => setBubble(e.target.checked)} />Include bubble teams (26–40)</label></div>
      <p className="cfb-notice">{basis === 'today' ? 'Uses completed games available now, through the final CFP release. Rankings will change as teams build their resumes.' : `One scenario assuming the football model’s favorites win ${data.next.assumptions.length} remaining games before the release. Records include those projected results; this is not a probability forecast.`}</p>
      {basis === 'projected' && data.next.unprojectedGames > 0 && <p role="alert" className="cfb-notice">{data.next.unprojectedGames} scheduled games have no available prediction and are excluded from this scenario.</p>}
      {rows.length ? <div className="overflow-x-auto"><table className="cfb-table ap-table"><thead><tr><th>Predicted</th><th>Team</th><th>Record</th><th>Quality wins</th><th>Model factors</th></tr></thead><tbody>{rows.map(t => <tr key={t.key}><td className="cfb-rank">{t.rank}</td><td><Team row={t} /></td><td className="cfb-number">{t.wins}–{t.losses}</td><td>{t.qualityWins}</td><td><details><summary>Why this rank?</summary><ul className="ap-factor-list">{t.drivers.map(d => <li key={d.feature}>{d.label} <span>{d.contribution >= 0 ? 'Supports' : 'Lowers'} score</span></li>)}</ul></details></td></tr>)}</tbody></table></div> : <p role="status">No rankings available for this selection.</p>}
      <p className="cfb-footnote">Quality wins are wins over model-rated Top 25 opponents. Factors show the largest base-score contributions; head-to-head and common opponents also affect comparisons.</p>
      {basis === 'projected' && <details className="ap-details"><summary>Game assumptions ({data.next.assumptions.length})</summary><div className="ap-assumptions">{data.next.assumptions.map(g => <div key={g.id}><span>{g.away} at {g.home}</span><strong>{g.winner} by {g.margin.toFixed(1)}</strong></div>)}</div></details>}
    </>}
    {view === 'latest' && (data.latest ? <><h4 className="cfb-schedule-title">CFP rankings · {data.latest.releaseDate}</h4><Comparison poll={data.latest} /></> : <p className="cfb-notice">No official {data.season} CFP rankings yet. The first release is {data.firstRelease}.</p>)}
    {view === 'history' && <><div className="cfb-controls"><label>CFP season<select value={selectedYear} onChange={e => { setYear(e.target.value); setDate(''); }}>{years.map(y => <option key={y}>{y}</option>)}</select></label><label>Release date<select value={poll?.releaseDate || ''} onChange={e => setDate(e.target.value)}>{polls.map(p => <option key={p.releaseDate}>{p.releaseDate}</option>)}</select></label></div>{poll && <Comparison poll={poll} />}</>}
    {view === 'model' && <>
      <div className="cfb-week-stats"><div className="cfb-week-stats-heading"><h4>Historical validation · 2019–{data.trainingThrough}</h4><span>{stats.polls} CFP releases</span></div><div className="cfb-week-metrics"><div><span>Average rank error</span><strong>{stats.historical_mean_absolute_rank_error.toFixed(2)}</strong><small>Protocol baseline: {stats.baselineRankError.toFixed(2)}</small></div><div><span>Top 25 membership</span><strong>{pct(stats.historical_top_25_recall)}</strong><small>Actual ranked teams recovered</small></div><div><span>Top 12 membership</span><strong>{pct(stats.historical_top_12_recall)}</strong><small>Ranking overlap, not playoff bids</small></div><div><span>Training polls</span><strong>{data.trainingPolls}</strong><small>2014–{data.trainingThrough} · {data.archivePolls} archived</small></div></div></div>
      <p className="cfb-footnote">Each season is tested using training polls from earlier years only. Error uses full predicted ranks, without the AP model’s cap at 26. The baseline uses fixed committee-protocol weights. These backtests reconstruct information available before release; they are not archived live forecasts.</p>
      <div className="overflow-x-auto ap-validation"><table className="cfb-table"><thead><tr><th>Season</th><th>Polls</th><th>Top 25 overlap</th><th>Rank error</th><th>Baseline error</th></tr></thead><tbody>{data.evaluation.map(e => <tr key={e.season}><td>{e.season}</td><td>{e.historical_poll_count}</td><td>{pct(e.historical_top_25_recall)}</td><td>{e.historical_mean_absolute_rank_error.toFixed(2)}</td><td>{e.baseline.historical_mean_absolute_rank_error.toFixed(2)}</td></tr>)}</tbody></table></div>
      <details className="ap-details"><summary>Methodology and sources</summary><ul>{data.methodology.map(m => <li key={m}>{m}</li>)}</ul><p>{data.sources.map(s => <a key={s.url} href={s.url} target="_blank" rel="noreferrer">{s.title}</a>)}</p></details>
    </>}
    <p className="cfb-footnote">Independent committee-ranking predictions. This is not an official CFP product and does not predict playoff seeds or qualification probabilities. Forecasts update automatically.</p>
  </section>;
}
