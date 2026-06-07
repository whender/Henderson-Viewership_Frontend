import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl, getTeamTheme } from "./teamLogos";

const BASKETBALL_TABS = [
  ["predictor", "PREDICTOR"],
  ["effects", "TEAM EFFECTS"],
  ["rankings", "VIEWERSHIP RANKINGS"],
  ["comparison", "COMPARISON"],
  ["model", "MODEL"],
];

const DEFAULT_FILTERS = {
  network: "all",
  time_slot: "all",
  stage: "all",
  season: "all",
  conference: "all",
  team: "all",
  rank_bucket: "all",
  include_tournament: true,
};

function formatViewers(value) {
  if (value == null) return "N/A";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${Math.round(value / 1000)}K`;
  return `${Math.round(value)}`;
}

function formatSignedViewers(value) {
  if (value == null) return "N/A";
  const prefix = value >= 0 ? "+" : "-";
  return `${prefix}${formatViewers(Math.abs(value))}`;
}

function formatPercent(value) {
  if (value == null) return "N/A";
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

function rankLabel(rank) {
  return Number(rank || 0) > 0 ? `#${rank}` : "UR";
}

function hexToRgb(hex) {
  if (!hex || typeof hex !== "string" || !hex.startsWith("#")) {
    return "17, 17, 17";
  }
  const normalized = hex.replace("#", "");
  const expanded =
    normalized.length === 3
      ? normalized.split("").map((char) => `${char}${char}`).join("")
      : normalized;
  const int = Number.parseInt(expanded, 16);
  if (Number.isNaN(int)) {
    return "17, 17, 17";
  }
  return `${(int >> 16) & 255}, ${(int >> 8) & 255}, ${int & 255}`;
}

function buildPanelStyle(team) {
  const theme = getTeamTheme(team);
  const primaryRgb = hexToRgb(theme.primary);
  return {
    "--team-primary": theme.primary,
    "--team-primary-rgb": primaryRgb,
    "--team-secondary": theme.secondary,
    borderColor: `rgba(${primaryRgb}, 0.22)`,
  };
}

function getNiceAxisMax(value) {
  if (!value || value <= 0) return 1_000_000;
  const targetMillions = value / 1_000_000;
  if (targetMillions <= 1) return 1_000_000;
  if (targetMillions <= 2) return 2_000_000;
  if (targetMillions <= 3) return 3_000_000;
  if (targetMillions <= 4) return 4_000_000;
  if (targetMillions <= 5) return 5_000_000;
  return Math.ceil(targetMillions / 2) * 2_000_000;
}

function buildSeasonRows(games) {
  const bySeason = new Map();
  for (const game of games) {
    if (!bySeason.has(game.season)) bySeason.set(game.season, []);
    bySeason.get(game.season).push(game);
  }

  return Array.from(bySeason.entries())
    .sort((a, b) => String(b[0]).localeCompare(String(a[0])))
    .map(([season, seasonGames]) => {
      const sortedGames = seasonGames
        .slice()
        .sort((a, b) => b.viewers - a.viewers || String(b.date).localeCompare(String(a.date)));
      const peakGame = sortedGames[0];
      const lowGame = sortedGames[sortedGames.length - 1];
      const viewers = seasonGames.map((game) => game.viewers).sort((a, b) => a - b);
      const mid = Math.floor(viewers.length / 2);
      const median =
        viewers.length % 2 === 0 ? (viewers[mid - 1] + viewers[mid]) / 2 : viewers[mid];
      const actualSum = seasonGames.reduce((sum, game) => sum + (game.viewers || 0), 0);
      const expectedGames = seasonGames.filter((game) => game.expected_viewers != null);
      const expectedSum = expectedGames.reduce((sum, game) => sum + (game.expected_viewers || 0), 0);
      const expectedActualSum = expectedGames.reduce((sum, game) => sum + (game.viewers || 0), 0);
      const deltas = seasonGames
        .map((game) => game.actual_minus_expected)
        .filter((value) => value != null);

      return {
        season,
        games: seasonGames.length,
        average_viewers: actualSum / seasonGames.length,
        median_viewers: median,
        expected_average_viewers: expectedGames.length ? expectedSum / expectedGames.length : null,
        average_minus_expected: deltas.length ? average(seasonGames, "actual_minus_expected") : null,
        overperformance_pct: expectedSum > 0 ? ((expectedActualSum / expectedSum) - 1) * 100 : null,
        games_above_expected: deltas.filter((value) => value > 0).length,
        peak_viewers: peakGame?.viewers,
        peak_matchup: peakGame?.matchup,
        peak_network: peakGame?.network,
        low_viewers: lowGame?.viewers,
        low_matchup: lowGame?.matchup,
      };
    });
}

function buildBasketballSummary(team, games, seasonRows) {
  if (!games.length) return null;
  const sortedByViewers = games
    .slice()
    .sort((a, b) => b.viewers - a.viewers || String(b.date).localeCompare(String(a.date)));
  const viewers = games.map((game) => game.viewers).sort((a, b) => a - b);
  const mid = Math.floor(viewers.length / 2);
  const median =
    viewers.length % 2 === 0 ? (viewers[mid - 1] + viewers[mid]) / 2 : viewers[mid];
  const actualSum = games.reduce((sum, game) => sum + (game.viewers || 0), 0);
  const expectedGames = games.filter((game) => game.expected_viewers != null);
  const expectedSum = expectedGames.reduce((sum, game) => sum + (game.expected_viewers || 0), 0);
  const expectedActualSum = expectedGames.reduce((sum, game) => sum + (game.viewers || 0), 0);
  const deltas = games.map((game) => game.actual_minus_expected).filter((value) => value != null);

  return {
    team,
    games: games.length,
    seasons_available: seasonRows.map((row) => row.season).sort(),
    average_viewers: actualSum / games.length,
    median_viewers: median,
    expected_average_viewers: expectedGames.length ? expectedSum / expectedGames.length : null,
    average_minus_expected: deltas.length ? average(games, "actual_minus_expected") : null,
    overperformance_pct: expectedSum > 0 ? ((expectedActualSum / expectedSum) - 1) * 100 : null,
    games_above_expected: deltas.filter((value) => value > 0).length,
    peak_viewers: sortedByViewers[0]?.viewers,
    peak_matchup: sortedByViewers[0]?.matchup,
  };
}

function uniqueOptions(games, key) {
  return ["all", ...new Set(games.map((game) => game[key]).filter(Boolean))];
}

function average(games, key) {
  const values = games
    .map((game) => game[key])
    .filter((value) => value != null && !Number.isNaN(Number(value)));
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

function actualVsExpectedPct(games) {
  const expectedGames = games.filter((game) => game.expected_viewers != null);
  if (!expectedGames.length) return null;
  const actualSum = expectedGames.reduce((sum, game) => sum + (game.viewers || 0), 0);
  const expectedSum = expectedGames.reduce((sum, game) => sum + (game.expected_viewers || 0), 0);
  return expectedSum > 0 ? ((actualSum / expectedSum) - 1) * 100 : null;
}

function BasketballYearlyTrend({ rows, team }) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const theme = getTeamTheme(team);
  const primaryRgb = hexToRgb(theme.primary);
  const maxAudience = rows.reduce((maxValue, row) => {
    const values = [row.average_viewers, row.expected_average_viewers].filter((value) => value != null);
    return values.length ? Math.max(maxValue, ...values) : maxValue;
  }, 0);
  const axisMax = getNiceAxisMax(maxAudience);
  const axisTicks = Array.from({ length: 5 }, (_, index) => {
    const value = (axisMax / 4) * index;
    return { value, label: formatViewers(value), left: `${(index / 4) * 100}%` };
  });

  return (
    <div className="profile-yearly-trend">
      <div className="profile-yearly-trend-legend" aria-hidden="true">
        <span className="profile-yearly-trend-legend-item">
          <span className="profile-yearly-trend-legend-swatch profile-yearly-trend-legend-swatch-expected" />
          Expected
        </span>
        <span className="profile-yearly-trend-legend-item">
          <span
            className="profile-yearly-trend-legend-swatch profile-yearly-trend-legend-swatch-actual"
            style={{ backgroundColor: `rgba(${primaryRgb}, 0.72)`, boxShadow: `0 0 0 1px rgba(${primaryRgb}, 0.28)` }}
          />
          Actual
        </span>
      </div>
      <div className="profile-yearly-trend-axis" aria-hidden="true">
        {axisTicks.map((tick) => (
          <span key={`${team}-axis-${tick.value}`} className="profile-yearly-trend-axis-tick" style={{ left: tick.left }}>
            {tick.label}
          </span>
        ))}
      </div>
      <div className="profile-yearly-trend-grid">
        {rows.map((row) => (
          <div className="profile-yearly-trend-item" key={`${team}-${row.season}`}>
            <div className="profile-yearly-trend-top">
              <span className="profile-yearly-trend-year">{row.season}</span>
              <span
                className={`profile-yearly-trend-badge ${
                  row.average_minus_expected > 0
                    ? "profile-yearly-trend-badge-positive"
                    : row.average_minus_expected < 0
                      ? "profile-yearly-trend-badge-negative"
                      : "profile-yearly-trend-badge-neutral"
                }`}
              >
                {formatPercent(row.overperformance_pct)}
              </span>
            </div>
            <div className="profile-yearly-trend-bar-shell" aria-hidden="true">
              <div
                className="profile-yearly-trend-bar profile-yearly-trend-bar-expected"
                style={{ width: `${(row.expected_average_viewers / axisMax) * 100}%` }}
              />
              <div
                className="profile-yearly-trend-bar profile-yearly-trend-bar-actual profile-yearly-trend-bar-top"
                style={{
                  width: `${(row.average_viewers / axisMax) * 100}%`,
                  backgroundColor: `rgba(${primaryRgb}, 0.72)`,
                  boxShadow: `0 0 0 1px rgba(${primaryRgb}, 0.28)`,
                }}
              />
            </div>
            <div className="profile-yearly-trend-stats">
              <span>Actual {formatViewers(row.average_viewers)}</span>
              <span>Expected {formatViewers(row.expected_average_viewers)}</span>
              <span>{formatSignedViewers(row.average_minus_expected)}</span>
              <span>{row.games_above_expected}/{row.games} above</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TeamPill({ team, compact = false }) {
  const logoUrl = getTeamLogoUrl(team);
  return (
    <span className={`team-pill ${compact ? "team-pill-compact" : ""}`}>
      {logoUrl && <img src={logoUrl} alt={`${team} logo`} className="team-logo" />}
      <span>{team}</span>
    </span>
  );
}

export function SelectBlock({ label, value, onChange, options }) {
  return (
    <div className="scenario-select-block">
      <label className="scenario-select-label">{label}</label>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "all" ? "All" : option}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function BasketballDashboard() {
  const [activeTab, setActiveTab] = useState("predictor");
  const [metadata, setMetadata] = useState(null);
  const [teams, setTeams] = useState([]);
  const [filters, setFilters] = useState(null);

  useEffect(() => {
    fetch(`${BACKEND_BASE}/cbb/metadata`)
      .then((res) => res.json())
      .then(setMetadata);
    fetch(`${BACKEND_BASE}/cbb/teams`)
      .then((res) => res.json())
      .then((data) => setTeams(data.teams || []));
    fetch(`${BACKEND_BASE}/cbb/filters`)
      .then((res) => res.json())
      .then(setFilters);
  }, []);

  return (
    <div>
      <div className="basketball-header">
        <div>
          <h2 className="text-3xl font-semibold mb-3">College Basketball Viewership</h2>
          <p className="text-gray-600 max-w-4xl">
            A basketball version of the Henderson Viewership model using TV Media Blog
            and On3 college basketball ratings data, filtered to men’s games.
          </p>
        </div>
        {metadata && (
          <div className="basketball-metrics">
            <Metric label="Games" value={metadata.games?.toLocaleString()} />
            <Metric label="Brand Teams" value={metadata.display_team_fixed_effects ?? metadata.team_fixed_effects} />
            <Metric
              label="Model MAE"
              value={`${formatViewers(metadata.model_mae_viewers)} / ${metadata.model_mae_pct ?? "N/A"}%`}
            />
          </div>
        )}
      </div>

      <div className="basketball-tab-row">
        {BASKETBALL_TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={`basketball-tab ${activeTab === key ? "basketball-tab-active" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "predictor" && <BasketballPredictor teams={teams} filters={filters} />}
      {activeTab === "effects" && <BasketballTeamEffects />}
      {activeTab === "rankings" && <BasketballViewershipRankings filters={filters} />}
      {activeTab === "comparison" && <BasketballProfiles teams={teams} comparisonOnly />}
      {activeTab === "model" && <BasketballModelExplanation metadata={metadata} />}
    </div>
  );
}

export function Metric({ label, value }) {
  return (
    <div className="basketball-metric">
      <span>{label}</span>
      <strong>{value ?? "N/A"}</strong>
    </div>
  );
}

export function BasketballPredictor({ teams, filters }) {
  const [form, setForm] = useState({
    team1: "",
    team2: "",
    network: "ESPN",
    time_slot: "Prime",
    day_of_week: "Saturday",
    month: 3,
    team1_rank: "",
    team2_rank: "",
  });
  const [prediction, setPrediction] = useState(null);
  const networkOptions = filters?.networks?.filter((option) => option !== "all") || ["ESPN"];
  const timeOptions = filters?.time_slots?.filter((option) => option !== "all") || ["Prime"];

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setPrediction(null);
  }

  async function handlePredict() {
    const res = await fetch(`${BACKEND_BASE}/cbb/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        stage: "Regular Season",
        is_tournament: 0,
        month: Number(form.month),
        team1_rank: Number(form.team1_rank || 0),
        team2_rank: Number(form.team2_rank || 0),
      }),
    });
    const data = await res.json();
    setPrediction(data);
  }

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Game Predictor</h2>

      <div className="grid grid-cols-2 gap-8 mb-8">
        <div>
          <label>Team 1</label>
          <select value={form.team1} onChange={(event) => updateField("team1", event.target.value)}>
            <option value="">Select a team</option>
            {teams.map((team) => (
              <option key={team.value} value={team.value}>{team.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label>Team 2</label>
          <select value={form.team2} onChange={(event) => updateField("team2", event.target.value)}>
            <option value="">Select a team</option>
            {teams.map((team) => (
              <option key={team.value} value={team.value}>{team.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 mb-8">
        <div>
          <label>Team 1 AP Rank</label>
          <input
            type="number"
            min="1"
            max="25"
            placeholder="Unranked"
            value={form.team1_rank}
            onChange={(event) => updateField("team1_rank", event.target.value)}
          />
        </div>
        <div>
          <label>Team 2 AP Rank</label>
          <input
            type="number"
            min="1"
            max="25"
            placeholder="Unranked"
            value={form.team2_rank}
            onChange={(event) => updateField("team2_rank", event.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 mb-8">
        <div>
          <label>Network</label>
          <select value={form.network} onChange={(event) => updateField("network", event.target.value)}>
            {networkOptions.map((option) => <option key={option}>{option}</option>)}
          </select>
        </div>
        <div>
          <label>Time Slot</label>
          <select value={form.time_slot} onChange={(event) => updateField("time_slot", event.target.value)}>
            {timeOptions.map((option) => <option key={option}>{option}</option>)}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 mb-8">
        <div>
          <label>Day</label>
          <select value={form.day_of_week} onChange={(event) => updateField("day_of_week", event.target.value)}>
            {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </div>
        <div>
          <label>Month</label>
          <select value={form.month} onChange={(event) => updateField("month", event.target.value)}>
            {[10, 11, 12, 1, 2, 3, 4].map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
      </div>

      <button onClick={handlePredict} className="btn-primary">
        Predict Viewership
      </button>

      {prediction && (
        <div className="text-center mt-12">
          <h3 className="text-3xl font-bold mb-2">
            Predicted Viewers: {prediction.prediction_formatted}
          </h3>
          <div className="team-pill-row">
            {[form.team1, form.team2].filter(Boolean).map((team) => (
              <TeamPill key={team} team={team} />
            ))}
          </div>
          <p className="text-gray-600 text-lg">
            {form.team1 && form.team2 ? `${form.team1} vs ${form.team2}` : ""}
            {form.network ? ` | ${form.network}` : ""}
            {" | Regular Season"}
          </p>
          <p className="text-gray-500 text-sm mt-2">
            {form.team1_rank ? `${form.team1 || "Team 1"} AP #${form.team1_rank}` : `${form.team1 || "Team 1"} unranked`}
            {" | "}
            {form.team2_rank ? `${form.team2 || "Team 2"} AP #${form.team2_rank}` : `${form.team2 || "Team 2"} unranked`}
          </p>
          <p className="text-gray-500 text-sm mt-3">
            Holdout MAE: {formatViewers(prediction.model_mae_viewers)} / {prediction.model_mae_pct ?? "N/A"}%
          </p>
        </div>
      )}
    </div>
  );
}

export function BasketballTeamEffects() {
  const [rows, setRows] = useState([]);
  const [metadata, setMetadata] = useState(null);
  const [availableFilters, setAvailableFilters] = useState({});
  const [conference, setConference] = useState("all");

  useEffect(() => {
    const params = new URLSearchParams({ conference });
    fetch(`${BACKEND_BASE}/cbb/team-effects?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        setRows(data.rows || []);
        setMetadata(data.metadata || null);
        setAvailableFilters(data.available_filters || {});
      });
  }, [conference]);

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Brand Pull Rankings</h2>
      <p className="text-gray-600 mb-6 max-w-4xl">
        These rankings use men’s college basketball TV viewership data from the
        2024-25 and 2025-26 seasons. Multiplier shows estimated viewership lift
        relative to the model baseline after controlling for network, slot, day,
        month, and stage.
      </p>
      {metadata && (
        <p className="text-gray-500 text-sm mb-6">
          {metadata.team_fixed_effects} teams with 5+ appearances after team-name cleanup.
          {" "}Model MAE: {formatViewers(metadata.model_mae_viewers)} / {metadata.model_mae_pct ?? "N/A"}%.
        </p>
      )}
      <div className="scenario-controls mb-6">
        <SelectBlock
          label="Conference"
          value={conference}
          onChange={setConference}
          options={availableFilters.conferences || ["all"]}
        />
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-max w-full">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Team</th>
              <th>Conference</th>
              <th>Lift (%)</th>
              <th>Games Used</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.team}>
                <td>{row.rank}</td>
                <td><TeamPill team={row.team} compact /></td>
                <td>{row.conference}</td>
                <td>{((row.viewer_multiplier - 1) * 100).toFixed(1)}</td>
                <td>{row.appearances}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function BasketballViewershipRankings({ filters }) {
  const [rankingFilters, setRankingFilters] = useState(DEFAULT_FILTERS);
  const [rows, setRows] = useState([]);
  const [availableFilters, setAvailableFilters] = useState(filters || {});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadRows() {
      setLoading(true);
      const params = new URLSearchParams({
        ...rankingFilters,
        include_tournament: String(rankingFilters.include_tournament),
      });
      const res = await fetch(`${BACKEND_BASE}/cbb/game-viewership-rankings?${params.toString()}`);
      const data = await res.json();
      setRows(data.rows || []);
      setAvailableFilters(data.available_filters || filters || {});
      setLoading(false);
    }
    loadRows();
  }, [rankingFilters, filters]);

  const optionSets = useMemo(() => availableFilters || filters || {}, [availableFilters, filters]);

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Viewership Rankings</h2>
      <p className="text-gray-600 mb-6 max-w-4xl">
        Rank every rated men&apos;s college basketball game by viewership, then filter
        by season, network, team, rankings, stage, and TV window.
      </p>

      <div className="scenario-controls mb-6">
        <SelectBlock label="Network" value={rankingFilters.network} onChange={(value) => setRankingFilters((prev) => ({ ...prev, network: value }))} options={optionSets.networks || ["all"]} />
        <SelectBlock label="Time Slot" value={rankingFilters.time_slot} onChange={(value) => setRankingFilters((prev) => ({ ...prev, time_slot: value }))} options={optionSets.time_slots || ["all"]} />
        <SelectBlock label="Stage" value={rankingFilters.stage} onChange={(value) => setRankingFilters((prev) => ({ ...prev, stage: value }))} options={optionSets.stages || ["all"]} />
        <SelectBlock label="Season" value={rankingFilters.season} onChange={(value) => setRankingFilters((prev) => ({ ...prev, season: value }))} options={optionSets.seasons || ["all"]} />
        <SelectBlock label="Conference" value={rankingFilters.conference} onChange={(value) => setRankingFilters((prev) => ({ ...prev, conference: value }))} options={optionSets.conferences || ["all"]} />
        <SelectBlock label="Team" value={rankingFilters.team} onChange={(value) => setRankingFilters((prev) => ({ ...prev, team: value }))} options={optionSets.teams || optionSets.opponents || ["all"]} />
        <SelectBlock label="Rankings" value={rankingFilters.rank_bucket} onChange={(value) => setRankingFilters((prev) => ({ ...prev, rank_bucket: value }))} options={optionSets.rank_buckets || ["all"]} />
      </div>
      <label className="team-profile-toggle">
        <input
          type="checkbox"
          checked={rankingFilters.include_tournament}
          onChange={(event) => setRankingFilters((prev) => ({ ...prev, include_tournament: event.target.checked }))}
        />
        Include tournament and postseason games
      </label>

      {loading && <p>Loading…</p>}
      {!loading && (
        <div className="overflow-x-auto">
          <table className="min-w-max w-full">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Date</th>
                <th>Season</th>
                <th>Matchup</th>
                <th>Network</th>
                <th>Time Slot</th>
                <th>Stage</th>
                <th>Rankings</th>
                <th>Viewership</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.rank}-${row.season}-${row.date}-${row.matchup}`}>
                  <td>{row.rank}</td>
                  <td>{row.date}</td>
                  <td>{row.season}</td>
                  <td>
                    <span className="matchup-cell">
                      <span className="matchup-logos">
                        <TeamPill team={row.team1} compact />
                        <TeamPill team={row.team2} compact />
                      </span>
                    </span>
                  </td>
                  <td>{row.network}</td>
                  <td>{row.time_slot || "N/A"}</td>
                  <td>{row.stage || "N/A"}</td>
                  <td>{rankLabel(row.team1_rank)} / {rankLabel(row.team2_rank)}</td>
                  <td>{formatViewers(row.viewers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function resolveBasketballTeamValue(rawTeam, teams) {
  if (!rawTeam) return "";
  const decodedTeam = rawTeam.trim();
  const match = teams.find((option) => option.value === decodedTeam || option.label === decodedTeam);
  return match ? match.value : decodedTeam;
}

export function BasketballProfiles({ teams, comparisonOnly = false, initialTeam = "", profileOnly = false }) {
  const location = useLocation();
  const [team, setTeam] = useState("");
  const [compareTeam, setCompareTeam] = useState("");
  const [profile, setProfile] = useState(null);
  const [compareProfile, setCompareProfile] = useState(null);
  const [selectedSeason, setSelectedSeason] = useState("all");
  const [gameTableFilters, setGameTableFilters] = useState({
    network: "all",
    time_slot: "all",
    stage: "all",
  });
  const [scenarioFilters, setScenarioFilters] = useState({
    season: "all",
    network: "all",
    time_slot: "all",
    stage: "all",
  });

  useEffect(() => {
    const requestedInitialTeam = resolveBasketballTeamValue(initialTeam, teams);
    if (requestedInitialTeam && requestedInitialTeam !== team) {
      setTeam(requestedInitialTeam);
      return;
    }

    const params = new URLSearchParams(location.search);
    const requestedTeam = resolveBasketballTeamValue(params.get("team") || "", teams);
    if (requestedTeam && requestedTeam !== team) {
      setTeam(requestedTeam);
    }
  }, [initialTeam, location.search, teams, team]);

  useEffect(() => {
    if (!team && !profileOnly && teams.length > 0) setTeam(teams[0].value);
    if (!compareTeam && teams.length > 1) setCompareTeam(teams[1].value);
  }, [teams, team, compareTeam, profileOnly]);

  useEffect(() => {
    if (!team) return;
    fetch(`${BACKEND_BASE}/cbb/team-profile?team=${encodeURIComponent(team)}`)
      .then((res) => res.json())
      .then((data) => {
        setProfile(data);
        setSelectedSeason("all");
        setGameTableFilters({ network: "all", time_slot: "all", stage: "all" });
        setScenarioFilters({ season: "all", network: "all", time_slot: "all", stage: "all" });
      });
  }, [team]);

  useEffect(() => {
    if (!compareTeam || compareTeam === team) {
      setCompareProfile(null);
      return;
    }
    fetch(`${BACKEND_BASE}/cbb/team-profile?team=${encodeURIComponent(compareTeam)}`)
      .then((res) => res.json())
      .then((data) => setCompareProfile(data?.error ? null : data))
      .catch(() => setCompareProfile(null));
  }, [compareTeam, team]);

  const games = useMemo(() => {
    const rows = Array.isArray(profile?.games) ? profile.games : [];
    return rows.filter((game) => Number(game.is_tournament) !== 1);
  }, [profile]);
  const allProfileGames = Array.isArray(profile?.games) ? profile.games : [];
  const seasonRows = useMemo(() => buildSeasonRows(games), [games]);
  const summary = useMemo(() => buildBasketballSummary(profile?.team, games, seasonRows), [profile, games, seasonRows]);
  const logoUrl = getTeamLogoUrl(profile?.team || team);
  const compareLogoUrl = getTeamLogoUrl(compareTeam);
  const theme = buildPanelStyle(profile?.team || team);
  const seasonOptions = summary ? ["all", ...summary.seasons_available.slice().sort().reverse()] : ["all"];
  const gameTableOptions = {
    networks: uniqueOptions(games, "network"),
    timeSlots: uniqueOptions(games, "time_slot"),
    stages: uniqueOptions(games, "stage"),
  };
  const filteredGames = games.filter((game) => {
    if (selectedSeason !== "all" && game.season !== selectedSeason) return false;
    if (gameTableFilters.network !== "all" && game.network !== gameTableFilters.network) return false;
    if (gameTableFilters.time_slot !== "all" && game.time_slot !== gameTableFilters.time_slot) return false;
    if (gameTableFilters.stage !== "all" && game.stage !== gameTableFilters.stage) return false;
    return true;
  });
  const topGames = games
    .slice()
    .sort((a, b) => b.viewers - a.viewers || String(b.date).localeCompare(String(a.date)))
    .slice(0, 10)
    .map((game, index) => ({ ...game, rank: index + 1 }));
  const tournamentGames = allProfileGames
    .filter((game) => Number(game.is_tournament) === 1)
    .sort((a, b) => b.viewers - a.viewers || String(b.date).localeCompare(String(a.date)));
  const compareGames = Array.isArray(compareProfile?.games)
    ? compareProfile.games.filter((game) => Number(game.is_tournament) !== 1)
    : [];
  const scenarioTeamGames = games.filter((game) => {
    if (scenarioFilters.season !== "all" && game.season !== scenarioFilters.season) return false;
    if (scenarioFilters.network !== "all" && game.network !== scenarioFilters.network) return false;
    if (scenarioFilters.time_slot !== "all" && game.time_slot !== scenarioFilters.time_slot) return false;
    if (scenarioFilters.stage !== "all" && game.stage !== scenarioFilters.stage) return false;
    return true;
  });
  const scenarioCompareGames = compareGames.filter((game) => {
    if (scenarioFilters.season !== "all" && game.season !== scenarioFilters.season) return false;
    if (scenarioFilters.network !== "all" && game.network !== scenarioFilters.network) return false;
    if (scenarioFilters.time_slot !== "all" && game.time_slot !== scenarioFilters.time_slot) return false;
    if (scenarioFilters.stage !== "all" && game.stage !== scenarioFilters.stage) return false;
    return true;
  });
  const teamAverage = average(scenarioTeamGames, "viewers");
  const compareAverage = average(scenarioCompareGames, "viewers");
  const difference = teamAverage != null && compareAverage != null ? teamAverage - compareAverage : null;
  const differencePct = compareAverage ? ((teamAverage / compareAverage) - 1) * 100 : null;
  const sharedOpponents = useMemo(() => {
    const rows = [];
    const opponents = new Set(scenarioTeamGames.map((game) => game.opponent));
    for (const opponent of opponents) {
      const teamRows = scenarioTeamGames.filter((game) => game.opponent === opponent);
      const compareRows = scenarioCompareGames.filter((game) => game.opponent === opponent);
      if (!compareRows.length) continue;
      rows.push({
        opponent,
        team_average_viewers: average(teamRows, "viewers"),
        compare_average_viewers: average(compareRows, "viewers"),
        team_games: teamRows.length,
        compare_games: compareRows.length,
      });
    }
    return rows
      .map((row) => ({
        ...row,
        difference_viewers: row.team_average_viewers - row.compare_average_viewers,
      }))
      .sort((a, b) => Math.abs(b.difference_viewers) - Math.abs(a.difference_viewers));
  }, [scenarioTeamGames, scenarioCompareGames]);
  const headToHeadGames = scenarioTeamGames
    .filter((game) => game.opponent === compareTeam)
    .sort((a, b) => b.viewers - a.viewers);

  return (
    <div className={comparisonOnly ? "comparison-page" : ""}>
      <h2 className="text-3xl font-semibold mb-4">
        {comparisonOnly ? "Team Comparison" : profile?.team ? `${profile.team} Profile` : "Team Profile"}
      </h2>
      <p className="text-gray-600 mb-3 max-w-4xl">
        {comparisonOnly
          ? "Compare two basketball programs under the same conditions."
          : "A dedicated basketball team page for viewership history and actual-versus-expected performance."}
      </p>
      <p className="text-gray-500 text-sm mb-6 max-w-4xl">
        Data is filtered to men’s college basketball games.
      </p>

      {!comparisonOnly && !profileOnly && (
      <div className="mb-6">
        <label className="mr-2">Select Team</label>
        <select value={team} onChange={(event) => setTeam(event.target.value)}>
          <option value="">Select a team</option>
          {teams.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      )}

      {profile?.error && <p className="text-red-600">{profile.error}</p>}

      {profile?.summary && summary && (
        <>
          <div className="profile-hero-shell mb-8" style={theme}>
            <div className="profile-hero">
              {logoUrl && <img src={logoUrl} alt={`${profile.team} logo`} className="profile-hero-logo" />}
              <div>
                <div className="profile-hero-kicker">{comparisonOnly ? "Primary Team" : "Team Profile"}</div>
                <h3 className="profile-hero-title">{profile.team}</h3>
                <p className="profile-hero-subtitle">
                  {summary.games} regular-season tracked games across {summary.seasons_available.length} seasons
                </p>
              </div>
            </div>

            <div className="profile-metrics">
              <ProfileMetric label="All-Time Average" value={formatViewers(summary.average_viewers)} />
              <ProfileMetric label="All-Time Median" value={formatViewers(summary.median_viewers)} />
              <ProfileMetric label="Typical Expected" value={formatViewers(summary.expected_average_viewers)} />
              <ProfileMetric label="Above / Below Expected" value={formatSignedViewers(summary.average_minus_expected)} />
            </div>

            <div className="profile-metrics">
              <ProfileMetric label="Over / Under Expected" value={formatPercent(summary.overperformance_pct)} />
              <ProfileMetric label="Games Above Expected" value={`${summary.games_above_expected}/${summary.games}`} />
              <ProfileMetric label="Peak Audience" value={formatViewers(summary.peak_viewers)} />
              <ProfileMetric label="Games Used" value={summary.games} />
            </div>

            <div className="profile-yearly-trend-section">
              <div className="profile-yearly-trend-header">
                <div>
                  <div className="profile-hero-kicker">Season Actual Vs Expected</div>
                  <p className="profile-yearly-trend-copy">
                    For each season, this compares actual average basketball viewership to
                    the regular-season audience expected for those same TV conditions without team effects.
                  </p>
                  <p className="profile-yearly-trend-note">
                    Positive values mean the team drew more viewers than the basketball model
                    expected from the game context alone.
                  </p>
                </div>
              </div>
              <BasketballYearlyTrend rows={seasonRows} team={profile.team} />
            </div>
          </div>

          <div className="card mb-8">
            <p className="text-gray-600 mb-2">Largest audience on record</p>
            <p className="text-xl font-semibold">
              {summary.peak_matchup || "N/A"} · {formatViewers(summary.peak_viewers)}
            </p>
          </div>

          {comparisonOnly && (
          <div className="scenario-shell scenario-shell-premium mb-8">
            <div className="scenario-header">
              <div className="comparison-select-card scenario-corner-select">
                <label className="comparison-select-label">Team 1</label>
                <select value={team} onChange={(event) => setTeam(event.target.value)}>
                  <option value="">Select a team</option>
                  {teams
                    .filter((option) => option.value !== compareTeam)
                    .map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                </select>
              </div>
              <div className="scenario-title-block">
                <div className="profile-hero-kicker">Comparison</div>
                <h3 className="text-2xl font-semibold mb-1">Scenario Simulator</h3>
              </div>
              <div className="comparison-select-card scenario-corner-select">
                <label className="comparison-select-label">Team 2</label>
                <select value={compareTeam} onChange={(event) => setCompareTeam(event.target.value)}>
                  <option value="">Select a team</option>
                  {teams
                    .filter((option) => option.value !== team)
                    .map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                </select>
              </div>
            </div>

            <div className="simulator-showcase">
              <div className="simulator-team-display">
                <div className="simulator-team-identity">
                  {logoUrl && <img src={logoUrl} alt={`${profile.team} logo`} className="simulator-showcase-logo" />}
                  <div className="simulator-showcase-name">{profile.team}</div>
                  <div className="simulator-showcase-meta">{scenarioTeamGames.length} games</div>
                </div>
              </div>
              <div className="simulator-versus-badge">vs</div>
              <div className="simulator-team-display">
                <div className="simulator-team-identity">
                  {compareLogoUrl && <img src={compareLogoUrl} alt={`${compareTeam} logo`} className="simulator-showcase-logo" />}
                  <div className="simulator-showcase-name">{compareTeam || "Select team"}</div>
                  <div className="simulator-showcase-meta">{scenarioCompareGames.length} games</div>
                </div>
              </div>
            </div>

            <div className="scenario-controls">
              <SelectBlock label="Season" value={scenarioFilters.season} onChange={(value) => setScenarioFilters((prev) => ({ ...prev, season: value }))} options={seasonOptions} />
              <SelectBlock label="Network" value={scenarioFilters.network} onChange={(value) => setScenarioFilters((prev) => ({ ...prev, network: value }))} options={gameTableOptions.networks} />
              <SelectBlock label="Time Slot" value={scenarioFilters.time_slot} onChange={(value) => setScenarioFilters((prev) => ({ ...prev, time_slot: value }))} options={gameTableOptions.timeSlots} />
              <SelectBlock label="Stage" value={scenarioFilters.stage} onChange={(value) => setScenarioFilters((prev) => ({ ...prev, stage: value }))} options={gameTableOptions.stages} />
            </div>

            <div className="scenario-stat-grid">
              <ProfileMetric label={`${profile.team} Average`} value={formatViewers(teamAverage)} />
              <ProfileMetric label={`${compareTeam || "Compare"} Average`} value={formatViewers(compareAverage)} />
              <ProfileMetric label="Difference" value={formatSignedViewers(difference)} />
              <ProfileMetric label={`Lift Vs ${compareTeam || "Compare"}`} value={formatPercent(differencePct)} />
            </div>

            <div className="scenario-summary-card">
              <p className="text-gray-600 mb-2">Actual vs Typical D-I Expectation</p>
              <div className="scenario-expected-grid">
                <div>
                  <p className="text-sm text-gray-600 mb-1">{profile.team}</p>
                  <p className="text-lg font-semibold">
                    {formatSignedViewers(average(scenarioTeamGames, "actual_minus_expected"))}
                  </p>
                  <p className="text-gray-600 text-sm">
                    Expected {formatViewers(average(scenarioTeamGames, "expected_viewers"))}
                    {" · "}
                    {formatPercent(actualVsExpectedPct(scenarioTeamGames))}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">{compareTeam}</p>
                  <p className="text-lg font-semibold">
                    {formatSignedViewers(average(scenarioCompareGames, "actual_minus_expected"))}
                  </p>
                  <p className="text-gray-600 text-sm">
                    Expected {formatViewers(average(scenarioCompareGames, "expected_viewers"))}
                    {" · "}
                    {formatPercent(actualVsExpectedPct(scenarioCompareGames))}
                  </p>
                </div>
              </div>
              <p className="text-gray-500 text-sm mt-3">
                Positive numbers mean the team drew more viewers than a typical men’s D-I team would
                have been expected to draw in the same conditions. Negative numbers mean it drew less.
              </p>
            </div>

            <div className="scenario-subsection">
              <h4 className="text-xl font-semibold">Shared Opponents</h4>
              {sharedOpponents.length ? (
                <div className="overflow-x-auto scenario-table-wrap">
                  <table className="min-w-max w-full">
                    <thead>
                      <tr>
                        <th>Opponent</th>
                        <th>{profile.team}</th>
                        <th>{compareTeam}</th>
                        <th>Difference</th>
                        <th>Games</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sharedOpponents.map((row) => (
                        <tr key={row.opponent}>
                          <td><TeamPill team={row.opponent} compact /></td>
                          <td>{formatViewers(row.team_average_viewers)}</td>
                          <td>{formatViewers(row.compare_average_viewers)}</td>
                          <td>{formatSignedViewers(row.difference_viewers)}</td>
                          <td>{row.team_games}-{row.compare_games}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-600">No shared opponents match the current scenario filters.</p>
              )}
            </div>

            <div className="scenario-subsection">
              <h4 className="text-xl font-semibold">Head-to-Head Games</h4>
              {headToHeadGames.length ? (
                <div className="overflow-x-auto scenario-table-wrap">
                  <table className="min-w-max w-full">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Season</th>
                        <th>Matchup</th>
                        <th>Network</th>
                        <th>Stage</th>
                        <th>Audience</th>
                      </tr>
                    </thead>
                    <tbody>
                      {headToHeadGames.map((game) => (
                        <tr key={`${game.date}-${game.matchup}`}>
                          <td>{game.date}</td>
                          <td>{game.season}</td>
                          <td>{game.matchup}</td>
                          <td>{game.network}</td>
                          <td>{game.stage}</td>
                          <td>{formatViewers(game.viewers)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-600">No head-to-head games match the current scenario filters.</p>
              )}
            </div>
          </div>
          )}

          <div className="team-profile-sections">
            <div className="team-profile-section">
              <h3 className="text-2xl font-semibold mb-4">Yearly Summary</h3>
              <div className="overflow-x-auto">
                <table className="min-w-max w-full">
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>Games</th>
                      <th>Average</th>
                      <th>Median</th>
                      <th>Peak Game</th>
                      <th>Peak Audience</th>
                      <th>Peak Network</th>
                      <th>Low Game</th>
                      <th>Low Audience</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seasonRows.map((row) => (
                      <tr key={row.season}>
                        <td>{row.season}</td>
                        <td>{row.games}</td>
                        <td>{formatViewers(row.average_viewers)}</td>
                        <td>{formatViewers(row.median_viewers)}</td>
                        <td>{row.peak_matchup}</td>
                        <td>{formatViewers(row.peak_viewers)}</td>
                        <td>{row.peak_network || "N/A"}</td>
                        <td>{row.low_matchup}</td>
                        <td>{formatViewers(row.low_viewers)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="team-profile-section">
              <h3 className="text-2xl font-semibold mb-4">Top 10 Most Viewed Games</h3>
              <div className="card">
                <div className="overflow-x-auto">
                  <table className="min-w-max w-full">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Season</th>
                        <th>Date</th>
                        <th>Matchup</th>
                        <th>Network</th>
                        <th>Stage</th>
                        <th>Audience</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topGames.map((game) => (
                        <tr key={`${game.rank}-${game.date}-${game.matchup}`}>
                          <td>{game.rank}</td>
                          <td>{game.season}</td>
                          <td>{game.date}</td>
                          <td>{game.matchup}</td>
                          <td>{game.network}</td>
                          <td>{game.stage}</td>
                          <td>{formatViewers(game.viewers)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {tournamentGames.length > 0 && (
              <div className="team-profile-section">
                <h3 className="text-2xl font-semibold mb-4">Tournament & Postseason Games</h3>
                <p className="text-gray-600 mb-4">
                  These games are shown as actual audience results only. Brand pull and expected-viewership
                  comparisons are based on the regular-season model.
                </p>
                <div className="overflow-x-auto">
                  <table className="min-w-max w-full">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Season</th>
                        <th>Matchup</th>
                        <th>Network</th>
                        <th>Stage</th>
                        <th>Audience</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tournamentGames.map((game) => (
                        <tr key={`tournament-${game.date}-${game.matchup}`}>
                          <td>{game.date}</td>
                          <td>{game.season}</td>
                          <td>{game.matchup}</td>
                          <td>{game.network}</td>
                          <td>{game.stage}</td>
                          <td>{formatViewers(game.viewers)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="team-profile-section">
              <div className="team-profile-filter-row">
                <h3 className="text-2xl font-semibold">Games By Season</h3>
                <div className="team-profile-year-filter">
                  <label className="mr-2">Season</label>
                  <select value={selectedSeason} onChange={(event) => setSelectedSeason(event.target.value)}>
                    <option value="all">All Seasons</option>
                    {summary.seasons_available.slice().sort().reverse().map((season) => (
                      <option key={season} value={season}>{season}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="scenario-controls mb-4">
                <SelectBlock label="Network" value={gameTableFilters.network} onChange={(value) => setGameTableFilters((prev) => ({ ...prev, network: value }))} options={gameTableOptions.networks} />
                <SelectBlock label="Time Slot" value={gameTableFilters.time_slot} onChange={(value) => setGameTableFilters((prev) => ({ ...prev, time_slot: value }))} options={gameTableOptions.timeSlots} />
                <SelectBlock label="Stage" value={gameTableFilters.stage} onChange={(value) => setGameTableFilters((prev) => ({ ...prev, stage: value }))} options={gameTableOptions.stages} />
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-max w-full">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Season</th>
                      <th>Matchup</th>
                      <th>Opponent</th>
                      <th>Network</th>
                      <th>Time Slot</th>
                      <th>Stage</th>
                      <th>Audience</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredGames.map((game) => (
                      <tr key={`${game.date}-${game.matchup}-${game.season}`}>
                        <td>{game.date}</td>
                        <td>{game.season}</td>
                        <td>{game.matchup}</td>
                        <td>{game.opponent}</td>
                        <td>{game.network}</td>
                        <td>{game.time_slot || "N/A"}</td>
                        <td>{game.stage || "N/A"}</td>
                        <td>{formatViewers(game.viewers)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredGames.length === 0 && <p className="text-gray-600">No games match the current filter.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ProfileMetric({ label, value }) {
  return (
    <div className="metric-card-modern">
      <div className="text-sm text-gray-600 metric-card-label">{label}</div>
      <p className="text-2xl font-semibold mt-1 metric-card-value">{value}</p>
    </div>
  );
}

export function BasketballModelExplanation({ metadata }) {
  return (
    <div className="card basketball-model-card">
      <h2 className="text-3xl font-semibold mb-4">Model Explanation</h2>
      <p className="text-gray-600 mb-4">
        The basketball model follows the same basic philosophy as the college football
        model: estimate national TV audience from structural TV variables and team
        drawing power. The current basketball version uses a regularized log-viewership
        regression trained on men’s regular-season college basketball games from the
        2024-25 and 2025-26 seasons.
      </p>
      <p className="text-gray-600 mb-4">
        Inputs include network, time slot, day of week, categorical month controls,
        AP ranking controls, and symmetric team fixed effects. Symmetric means Duke
        receives the same team effect whether listed first or second in the matchup.
        Tournament and postseason games are displayed separately because March Madness
        is a different viewing environment.
      </p>
      <p className="text-gray-600 mb-4">
        Team effects are only created for teams with at least five appearances. Less frequent
        teams are treated as baseline teams so the model does not overfit tiny samples.
      </p>
      <p className="text-gray-600 mb-4">
        Team-name aliases such as FAU/Florida Atlantic and USF/South Florida are
        canonicalized before training, so each program has one team effect in the model.
      </p>
      <p className="text-gray-600 mb-4">
        Basketball Brand Rankings also apply the same explicit sample-size shrinkage used
        by the football dashboard: teams with 25 or fewer appearances have their team-effect
        coefficient multiplied by games / (games + 25) before lift percentage is shown.
      </p>
      {metadata && (
        <p className="text-gray-600">
          Current trained rows: {metadata.trained_rows?.toLocaleString()}. Team effects:
          {" "}{metadata.team_fixed_effects}. Holdout MAE: {formatViewers(metadata.model_mae_viewers)}
          {" "} / {metadata.model_mae_pct ?? "N/A"}%. Baseline MAE without team effects:
          {" "}{formatViewers(metadata.baseline_mae_viewers)} / {metadata.baseline_mae_pct ?? "N/A"}%.
        </p>
      )}
    </div>
  );
}
