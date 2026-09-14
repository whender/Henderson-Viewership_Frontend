import { useEffect, useState } from "react";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl, parseMatchupTeams } from "./teamLogos";
import "./FootballModel.css";
import "./WeeklyPredictions.css";

const weekKey = week => `${week.year}-${week.week}`;
const percent = value => Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";

export default function WeeklyPredictions() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [weeks, setWeeks] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [openWeek, setOpenWeek] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await fetch(`${BACKEND_BASE}/weekly-predictions`);
        if (response.ok === false) throw new Error("Request failed");
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        if (!active) return;
        const ordered = [...(data.weeks || [])].sort((a, b) => Number(b.year || 0) - Number(a.year || 0) || Number(b.week) - Number(a.week));
        setWeeks(ordered);
        setMetrics(data.metrics || null);
        setOpenWeek(ordered.length ? weekKey(ordered[0]) : null);
      } catch {
        if (active) setError("Unable to load weekly predictions. Please refresh to try again.");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  return <section className="cfb-model viewership-weekly">
    <div className="home-panel">
      <header className="home-panel-header"><div><p className="home-kicker">Football viewership</p><h2>Weekly Predictions</h2></div></header>
      {loading ? <p role="status" className="vw-message">Loading weekly predictions…</p> : error ? <p role="alert" className="cfb-notice">{error}</p> : <>
        {metrics && <div className="vw-overall" aria-label="Overall accuracy">
          <MetricGroup title="Pregame Model" stats={metrics.pregame} />
          <MetricGroup title="Postgame Model" stats={metrics.postgame} />
        </div>}
        {!weeks.length && <p role="status" className="vw-message">No weekly predictions available yet.</p>}
        <div className="vw-weeks">{weeks.map(week => {
          const key = weekKey(week), expanded = openWeek === key;
          return <section key={key} className="vw-week">
            <h3><button className="vw-week-toggle" onClick={() => setOpenWeek(expanded ? null : key)} aria-label={`Week ${week.week}${week.year ? ` (${week.year})` : ""}`} aria-describedby={`summary-${key}`} aria-expanded={expanded} aria-controls={`games-${key}`}>
              <span>Week {week.week}{week.year ? ` (${week.year})` : ""}</span>
              <WeekSummary games={week.games} id={`summary-${key}`} />
              <span className="vw-week-meta" aria-hidden="true"><svg viewBox="0 0 20 20" className={expanded ? "vw-chevron expanded" : "vw-chevron"}><path d="m5 7.5 5 5 5-5" /></svg></span>
            </button></h3>
            {expanded && <div id={`games-${key}`} className="overflow-x-auto vw-table-scroll" role="region" aria-label={`Week ${week.week} ${week.year || ""} predictions`} tabIndex={0}>
              <table className="cfb-table vw-table">
                <thead><tr>{["Date / Time", "Matchup", "Spread", "Network", "Pregame", "Postgame", "Actual", "Error (Pre)", "Error (Post)"].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
                <tbody>{week.games.map((game, i) => <tr key={game.cfbd_game_id || i}>
                  <td className="vw-date">{game.date}<small>{game.time_slot}</small></td>
                  <td><MatchupCell matchup={game.matchup} /></td>
                  <td className="vw-spread">{game.spread || "—"}</td>
                  <td><span className="vw-network">{game.network || "—"}</span></td>
                  <td><Forecast value={game.revised_predicted || game.predicted} /></td>
                  <td><Forecast value={game.post_predicted} /></td>
                  <td className="vw-number vw-actual">{game.actual || "—"}</td>
                  <td><ErrorValue value={game.percent_error} /></td>
                  <td><ErrorValue value={game.post_percent_error} /></td>
                </tr>)}</tbody>
              </table>
            </div>}
          </section>;
        })}</div>
      </>}
    </div>
  </section>;
}

function WeekSummary({ games, id }) {
  // The API supplies errors for the latest saved forecasts, as in the table.
  const errors = games.map(game => game.percent_error).filter(Number.isFinite).map(Math.abs).sort((a, b) => a - b);
  const count = errors.length;
  if (!count) return <span id={id} className="vw-week-summary vw-week-pending">{games.length} games · Awaiting ratings</span>;
  const middle = Math.floor(count / 2);
  const median = count % 2 ? errors[middle] : (errors[middle - 1] + errors[middle]) / 2;
  const values = [
    ["Median error", median],
    ["Mean error", errors.reduce((sum, error) => sum + error, 0) / count],
    ["Within 10%", errors.filter(error => error <= 10).length / count * 100],
    ["Within 25%", errors.filter(error => error <= 25).length / count * 100],
  ];
  return <span id={id} className="vw-week-summary">
    <span className="vw-week-sample">Pregame<span>{count}/{games.length} games scored</span></span>
    {values.map(([label, value]) => <span className="vw-week-stat" key={label}><span>{label}</span><strong>{percent(value)}</strong></span>)}
  </span>;
}

function MetricGroup({ title, stats }) {
  return <section className="cfb-week-stats vw-stats">
    <div className="cfb-week-stats-heading"><h3>{title}</h3><span>Overall accuracy</span></div>
    <div className="cfb-week-metrics">{[
      ["Median % Error", percent(stats?.median_error)], ["Mean % Error", percent(stats?.mean_error)],
      ["Within 10%", Number.isFinite(stats?.pct_within_10) ? `${stats.pct_within_10}%` : "—"],
      ["Within 25%", Number.isFinite(stats?.pct_within_25) ? `${stats.pct_within_25}%` : "—"],
    ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
  </section>;
}

function MatchupCell({ matchup }) {
  const teams = parseMatchupTeams(matchup);
  const labels = String(matchup || "").split(/\s+(?:at|vs\.?|v\.)\s+/i);
  return <div className="vw-matchup">{teams.length ? teams.map((team, i) => {
    const logo = getTeamLogoUrl(team);
    return <div key={`${team}-${i}`} className="cfb-team">{logo && <img src={logo} alt={`${team} logo`} loading="lazy" />}<span>{labels[i] || team}</span></div>;
  }) : matchup || "—"}</div>;
}

function Forecast({ value }) {
  if (!value) return <span className="vw-muted">—</span>;
  const parts = String(value).match(/^([^()[]+?)\s*(\([^)]*\))?\s*(\[retrospective\])?$/i);
  if (!parts) return <span className="vw-number">{value}</span>;
  return <div className="vw-forecast"><strong className="vw-number">{parts[1].trim()}</strong>{parts[2] && <small>{parts[2]}</small>}{parts[3] && <small className="vw-timing">Retrospective</small>}</div>;
}

function ErrorValue({ value }) {
  const tone = !Number.isFinite(value) ? "pending" : value >= 35 ? "high" : value >= 25 ? "moderate" : "low";
  return <span className={`vw-error vw-error-${tone}`}>{percent(value)}</span>;
}
