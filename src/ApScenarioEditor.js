import { useEffect, useState } from 'react';
import { predictScenario, validateScores } from './apScenario';

function Team({ id, name }) {
  return <span className="cfb-team"><img src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${id}.png`} alt="" loading="lazy" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} /><span>{name}</span></span>;
}

export default function ApScenarioEditor({ forecast, onResult, savedDraft, onDraft }) {
  const [payload, setPayload] = useState(null), [error, setError] = useState('');
  const initial = savedDraft?.asOf === forecast.asOf ? savedDraft : null;
  const [edits, setEdits] = useState(initial?.edits || {}), [dirty, setDirty] = useState(initial?.dirty || false), [applied, setApplied] = useState(initial?.applied || 0);
  useEffect(() => { onDraft?.({ asOf: forecast.asOf, edits, dirty, applied }); }, [forecast.asOf, edits, dirty, applied, onDraft]);
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(`${process.env.PUBLIC_URL || ''}${forecast.next.simulator.url}?v=${encodeURIComponent(forecast.asOf)}`, { cache: 'no-cache', signal: controller.signal });
        if (!response.ok) throw new Error('The custom forecast is temporarily unavailable. Try another forecast basis.');
        const next = await response.json();
        if (next.asOf !== forecast.asOf || next.pollId !== forecast.next.previousPollId || next.modelVersion !== forecast.modelVersion) throw new Error('The forecast is updating. Reopen My game picks after the dashboard refreshes.');
        setPayload(next);
      } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
    })();
    return () => controller.abort();
  }, [forecast.asOf, forecast.modelVersion, forecast.next.previousPollId, forecast.next.simulator.url]);
  if (error) return <p className="cfb-notice" role="alert">{error}</p>;
  if (!payload) return <p role="status">Loading custom game predictions…</p>;
  const games = payload.games.filter(g => g.editable);
  const update = (id, values) => { setEdits(old => ({ ...old, [id]: values })); setDirty(true); };
  const resetGame = id => { setEdits(old => { const next = { ...old }; delete next[id]; return next; }); setDirty(true); };
  const pick = (g, side) => {
    const old = edits[g.id];
    const valid = old && !validateScores(old.home, old.away);
    const high = valid ? Math.max(Number(old.home), Number(old.away)) : 27;
    const low = valid ? Math.min(Number(old.home), Number(old.away)) : 20;
    update(g.id, { home: String(side === 'home' ? high : low), away: String(side === 'away' ? high : low) });
  };
  const invalid = Object.values(edits).some(v => validateScores(v.home, v.away));
  const apply = event => {
    event.preventDefault();
    try { const rows = predictScenario(payload, edits); onResult({ rows, count: Object.keys(edits).length, asOf: forecast.asOf }); setApplied(Object.keys(edits).length); setDirty(false); }
    catch (e) { setError(e.message); }
  };
  return <form className="ap-scenario" onSubmit={apply}>
    <div className="ap-scenario-heading"><h4>Your game picks</h4><span>{games.length} upcoming games</span></div>
    <p className="cfb-footnote">Games involving a team in the projected Top 40 before the next poll. Pick a winner to start at 27–20, then edit either score. Unchanged games keep the model’s assumptions. These are hypothetical final scores.</p>
    {games.length ? <div className="ap-scenario-games">{games.map(g => {
      const values = edits[g.id], issue = values ? validateScores(values.home, values.away) : '';
      const winner = values && !issue ? (Number(values.home) > Number(values.away) ? 'home' : 'away') : null;
      const margin = g.homePoints == null ? null : g.homePoints - g.awayPoints;
      return <fieldset className="ap-scenario-game" key={g.id}>
        <legend>{g.awayTeam} {g.neutralSite ? 'vs.' : 'at'} {g.homeTeam}</legend>
        <div className="ap-scenario-date">{new Date(g.startDate).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}{g.neutralSite ? ' · Neutral site' : ''}</div>
        {['away', 'home'].map(side => <div className="ap-scenario-team" key={side}>
          <button type="button" className={winner === side ? 'ap-pick selected' : 'ap-pick'} aria-pressed={winner === side} aria-label={`Pick ${g[`${side}Team`]} to beat ${g[side === 'home' ? 'awayTeam' : 'homeTeam']}`} onClick={() => pick(g, side)}><Team id={g[`${side}Id`]} name={g[`${side}Team`]} />{winner === side && <span className="ap-pick-label">Your winner</span>}</button>
          <label className="ap-score-label"><span>{g[`${side}Team`]} score</span><input aria-label={`${g[`${side}Team`]} score against ${g[side === 'home' ? 'awayTeam' : 'homeTeam']}`} aria-describedby={`game-note-${g.id}`} aria-invalid={Boolean(issue)} type="number" inputMode="numeric" min="0" max="200" step="1" placeholder="—" value={values?.[side] ?? ''} onChange={e => update(g.id, { home: values?.home ?? '', away: values?.away ?? '', [side]: e.target.value })} /></label>
        </div>)}
        <div className="ap-scenario-game-footer"><span id={`game-note-${g.id}`}>{issue || (values ? 'Custom result' : margin == null ? 'No model result assumed' : `Model: ${margin > 0 ? g.homeTeam : g.awayTeam} by ${Math.abs(margin).toFixed(1)}`)}</span>{values && <button type="button" onClick={() => resetGame(g.id)} aria-label={`Use model result for ${g.awayTeam} at ${g.homeTeam}`}>Use model</button>}</div>
      </fieldset>;
    })}</div> : <p>No upcoming games involving the projected Top 40 before this release.</p>}
    <div className="ap-scenario-actions"><button className="ap-apply" type="submit" disabled={invalid || !games.length}>Update prediction</button><button type="button" onClick={() => { setEdits({}); setDirty(false); setApplied(0); onResult(null); }}>Reset all picks</button><span role="status" aria-live="polite">{invalid ? 'Complete each edited game with a valid final score.' : dirty ? 'Changes not yet applied.' : applied ? `${applied} custom ${applied === 1 ? 'result' : 'results'} applied.` : 'Using model assumptions until you apply your picks.'}</span></div>
  </form>;
}
