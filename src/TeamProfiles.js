import { useEffect, useState } from "react";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl, getTeamTheme } from "./teamLogos";

function formatMillions(value) {
  if (value == null) {
    return "N/A";
  }

  return `${(value / 1000).toFixed(2)}M`;
}

function formatDifference(value) {
  if (value == null) {
    return "N/A";
  }

  const prefix = value >= 0 ? "+" : "-";
  return `${prefix}${(Math.abs(value) / 1000).toFixed(2)}M`;
}

function formatPercent(value) {
  if (value == null) {
    return "N/A";
  }

  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

function formatRank(value) {
  if (value == null) {
    return "N/A";
  }

  return `#${value}`;
}

function BrandTrendChart({ rows, team }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return null;
  }

  const theme = getTeamTheme(team);
  const sortedRows = rows
    .filter((row) => row?.year != null && row?.brand_rank != null)
    .slice()
    .sort((a, b) => a.year - b.year);

  if (!sortedRows.length) {
    return null;
  }

  const width = 720;
  const height = 156;
  const padding = { top: 14, right: 10, bottom: 34, left: 38 };
  const rankValues = sortedRows.map((row) => row.brand_rank);
  const minRank = Math.min(...rankValues);
  const maxRank = Math.max(...rankValues);
  const rankRange = Math.max(maxRank - minRank, 1);
  const xStep =
    sortedRows.length > 1
      ? (width - padding.left - padding.right) / (sortedRows.length - 1)
      : 0;

  const points = sortedRows.map((row, index) => {
    const x = padding.left + xStep * index;
    const normalized =
      rankRange === 0 ? 0.5 : (row.brand_rank - minRank) / rankRange;
    const y =
      padding.top +
      (height - padding.top - padding.bottom) * normalized;

    return { ...row, x, y };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const yTicks = [
    minRank,
    Math.round((minRank + maxRank) / 2),
    maxRank,
  ].filter((value, index, array) => array.indexOf(value) === index);

  const getY = (rank) => {
    const normalized = rankRange === 0 ? 0.5 : (rank - minRank) / rankRange;
    return padding.top + (height - padding.top - padding.bottom) * normalized;
  };

  return (
    <div className="profile-brand-trend-chart-wrap">
      <div className="profile-brand-trend-chart-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="profile-brand-trend-chart"
          role="img"
          aria-label={`${team} brand rank trend by year`}
        >
          {yTicks.map((tick) => {
            const y = getY(tick);
            return (
              <g key={`${team}-y-${tick}`}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  className="profile-brand-trend-gridline"
                />
                <line
                  x1={padding.left - 3}
                  y1={y}
                  x2={padding.left}
                  y2={y}
                  className="profile-brand-trend-axis"
                />
                <text
                  x={padding.left - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="profile-brand-trend-tick-label"
                >
                  #{tick}
                </text>
              </g>
            );
          })}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={height - padding.bottom}
            className="profile-brand-trend-axis"
          />
          <line
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
            className="profile-brand-trend-axis"
          />
          <path
            d={linePath}
            fill="none"
            stroke={theme.primary}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {points.map((point) => (
            <g key={`${team}-${point.year}`}>
              <line
                x1={point.x}
                y1={height - padding.bottom}
                x2={point.x}
                y2={height - padding.bottom + 3}
                className="profile-brand-trend-axis"
              />
              <circle
                cx={point.x}
                cy={point.y}
                r="3"
                fill="#ffffff"
                stroke={theme.primary}
                strokeWidth="2"
              />
              <text
                x={point.x}
                y={point.y - 7}
                textAnchor="middle"
                className="profile-brand-trend-point-rank"
                fill={theme.secondary}
              >
                {formatRank(point.brand_rank)}
              </text>
              <text
                x={point.x}
                y={height - 16}
                textAnchor="middle"
                className="profile-brand-trend-point-year"
              >
                {point.year}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="profile-brand-trend-legend">
        {sortedRows.map((row) => (
          <div className="profile-brand-trend-legend-item" key={`${team}-legend-${row.year}`}>
            <span className="profile-brand-trend-legend-year">{row.year}</span>
            <span className="profile-brand-trend-legend-rank">{formatRank(row.brand_rank)}</span>
            <span className="profile-brand-trend-legend-lift">{formatPercent(row.viewership_lift_pct)}</span>
          </div>
        ))}
      </div>

      <div className="profile-brand-trend-mobile-list">
        {sortedRows.map((row, index) => (
          <div className="profile-brand-trend-mobile-item" key={`${team}-mobile-${row.year}`}>
            <div className="profile-brand-trend-mobile-year">{row.year}</div>
            <div className="profile-brand-trend-mobile-bar-shell" aria-hidden="true">
              <div
                className="profile-brand-trend-mobile-bar"
                style={{
                  width: `${
                    rankRange === 0
                      ? 100
                      : ((maxRank - row.brand_rank) / rankRange) * 100
                  }%`,
                  backgroundColor: theme.primary,
                }}
              />
            </div>
            <div className="profile-brand-trend-mobile-metrics">
              <span>{formatRank(row.brand_rank)}</span>
              <span>{formatPercent(row.viewership_lift_pct)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function hexToRgb(hex) {
  if (!hex || typeof hex !== "string" || !hex.startsWith("#")) {
    return "17, 17, 17";
  }

  const normalized = hex.replace("#", "");
  const expanded =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => `${char}${char}`)
          .join("")
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
    boxShadow: `0 18px 40px rgba(${primaryRgb}, 0.06)`,
  };
}

function buildYearlyRows(games) {
  const byYear = new Map();

  for (const game of games) {
    if (!byYear.has(game.year)) {
      byYear.set(game.year, []);
    }
    byYear.get(game.year).push(game);
  }

  return Array.from(byYear.entries())
    .sort((a, b) => b[0] - a[0])
    .map(([year, yearGames]) => {
      const sortedGames = yearGames
        .slice()
        .sort((a, b) => b.viewers - a.viewers || String(a.date).localeCompare(String(b.date)));
      const peakGame = sortedGames[0];
      const lowGame = sortedGames[sortedGames.length - 1];
      const viewers = yearGames.map((game) => game.viewers).sort((a, b) => a - b);
      const mid = Math.floor(viewers.length / 2);
      const median =
        viewers.length % 2 === 0
          ? (viewers[mid - 1] + viewers[mid]) / 2
          : viewers[mid];

      return {
        year,
        games: yearGames.length,
        average_viewers: yearGames.reduce((sum, game) => sum + game.viewers, 0) / yearGames.length,
        median_viewers: median,
        peak_viewers: peakGame.viewers,
        peak_matchup: peakGame.matchup,
        peak_network: peakGame.network,
        low_viewers: lowGame.viewers,
        low_matchup: lowGame.matchup,
      };
    });
}

function buildSummary(team, games, yearlyRows) {
  if (!games.length) {
    return {
      team,
      games: 0,
      years_available: [],
      average_viewers: null,
      median_viewers: null,
      peak_viewers: null,
      peak_matchup: null,
      latest_year: null,
      latest_year_average: null,
    };
  }

  const sortedByViewers = games
    .slice()
    .sort((a, b) => b.viewers - a.viewers || b.year - a.year);
  const viewers = games.map((game) => game.viewers).sort((a, b) => a - b);
  const mid = Math.floor(viewers.length / 2);
  const median =
    viewers.length % 2 === 0
      ? (viewers[mid - 1] + viewers[mid]) / 2
      : viewers[mid];
  const latestYear = Math.max(...yearlyRows.map((row) => row.year));
  const latestYearRow = yearlyRows.find((row) => row.year === latestYear);

  return {
    team,
    games: games.length,
    years_available: yearlyRows.map((row) => row.year).sort((a, b) => a - b),
    average_viewers: games.reduce((sum, game) => sum + game.viewers, 0) / games.length,
    median_viewers: median,
    peak_viewers: sortedByViewers[0].viewers,
    peak_matchup: sortedByViewers[0].matchup,
    latest_year: latestYear,
    latest_year_average: latestYearRow?.average_viewers ?? null,
  };
}

function buildProfileView(profile, selectedYear, includeConfChamp) {
  if (!profile) {
    return null;
  }

  const games = Array.isArray(profile.games) ? profile.games : [];
  const includedGames = games.filter((game) => includeConfChamp || !game.conf_champ);
  const filteredGames = includedGames.filter((game) =>
    selectedYear === "all" ? true : String(game.year) === selectedYear
  );
  const yearlyRows = buildYearlyRows(includedGames);
  const summary = buildSummary(profile.team, includedGames, yearlyRows);
  const topGames = includedGames
    .slice()
    .sort((a, b) => b.viewers - a.viewers || b.year - a.year)
    .slice(0, 10)
    .map((game, index) => ({ ...game, rank: index + 1 }));

  return {
    includedGames,
    filteredGames,
    yearlyRows,
    summary,
    topGames,
    hasConfChampGames: games.some((game) => game.conf_champ),
  };
}

function uniqueOptions(games, key) {
  return [
    "all",
    ...new Set(
      games
        .map((game) => game[key])
        .filter(Boolean)
    ),
  ];
}

async function fetchProfile(team) {
  if (!team) {
    return null;
  }

  const response = await fetch(
    `${BACKEND_BASE}/team-profile?team=${encodeURIComponent(team)}`
  );
  if (!response.ok) {
    throw new Error(`Team profile request failed (${response.status})`);
  }
  return response.json();
}

export default function TeamProfiles({ teams }) {
  const [selectedTeam, setSelectedTeam] = useState("");
  const [compareTeam, setCompareTeam] = useState("");
  const [selectedYear, setSelectedYear] = useState("all");
  const [includeConfChamp, setIncludeConfChamp] = useState(true);
  const [profile, setProfile] = useState(null);
  const [compareProfile, setCompareProfile] = useState(null);
  const [gameTableFilters, setGameTableFilters] = useState({
    network: "all",
    time_bucket: "all",
    rank_detail: "all",
  });
  const [scenarioFilters, setScenarioFilters] = useState({
    network: "all",
    time_bucket: "all",
    rank_bucket: "all",
    year_start: "all",
    year_end: "all",
  });
  const [scenarioData, setScenarioData] = useState(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selectedTeam && teams.length > 0) {
      setSelectedTeam(teams[0].value);
    }
    if (!compareTeam && teams.length > 1) {
      setCompareTeam(teams[1].value);
    }
  }, [teams, selectedTeam, compareTeam]);

  useEffect(() => {
    if (!selectedTeam) {
      return;
    }

    async function loadProfile() {
      try {
        setLoading(true);
        setError("");

        const data = await fetchProfile(selectedTeam);
        if (data?.error) {
          throw new Error(data.error);
        }

        setProfile(data);
        setSelectedYear("all");
        setIncludeConfChamp(true);
        setGameTableFilters({
          network: "all",
          time_bucket: "all",
          rank_detail: "all",
        });
        setScenarioFilters({
          network: "all",
          time_bucket: "all",
          rank_bucket: "all",
          year_start: "all",
          year_end: "all",
        });
      } catch (err) {
        console.error("Team profile load error:", err);
        setProfile(null);
        setError(err.message || "Failed to load team profile.");
      } finally {
        setLoading(false);
      }
    }

    loadProfile();
  }, [selectedTeam]);

  useEffect(() => {
    if (!profile || !teams.length) {
      return;
    }

    if (!compareTeam || compareTeam === profile.team) {
      const fallback = teams.find((team) => team.value !== profile.team);
      if (fallback) {
        setCompareTeam(fallback.value);
      }
    }
  }, [profile, teams, compareTeam]);

  useEffect(() => {
    if (!compareTeam || compareTeam === selectedTeam) {
      setCompareProfile(null);
      return;
    }

    async function loadCompareProfile() {
      try {
        const data = await fetchProfile(compareTeam);
        if (data?.error) {
          setCompareProfile(null);
          return;
        }
        setCompareProfile(data);
      } catch (err) {
        console.error("Compare team profile load error:", err);
        setCompareProfile(null);
      }
    }

    loadCompareProfile();
  }, [compareTeam, selectedTeam]);

  useEffect(() => {
    if (!selectedTeam || !compareTeam || selectedTeam === compareTeam) {
      setScenarioData(null);
      return;
    }

    async function loadScenarioCompare() {
      try {
        setScenarioLoading(true);

        const params = new URLSearchParams({
          team: selectedTeam,
          compare_team: compareTeam,
          network: scenarioFilters.network,
          time_bucket: scenarioFilters.time_bucket,
          rank_bucket: scenarioFilters.rank_bucket,
          year_start: scenarioFilters.year_start,
          year_end: scenarioFilters.year_end,
          include_conf_champ: String(includeConfChamp),
        });

        const res = await fetch(
          `${BACKEND_BASE}/team-scenario-compare?${params.toString()}`
        );
        const data = await res.json();
        setScenarioData(data);
      } catch (err) {
        console.error("Scenario compare load error:", err);
        setScenarioData(null);
      } finally {
        setScenarioLoading(false);
      }
    }

    loadScenarioCompare();
  }, [selectedTeam, compareTeam, scenarioFilters, includeConfChamp]);

  const view = buildProfileView(profile, selectedYear, includeConfChamp);
  const scenarioYearOptions = view
    ? ["all", ...view.summary.years_available.map((year) => String(year))]
    : ["all"];
  const logoUrl = getTeamLogoUrl(profile?.team || selectedTeam);
  const compareLogoUrl = getTeamLogoUrl(compareTeam);
  const theme = buildPanelStyle(profile?.team || selectedTeam);
  const hasConfChampGames = Boolean(view?.hasConfChampGames);
  const gameTableOptions = view
      ? {
        networks: uniqueOptions(view.includedGames, "network"),
        timeBuckets: uniqueOptions(view.includedGames, "time_bucket"),
        rankDetails: uniqueOptions(view.includedGames, "rank_detail"),
      }
    : {
        networks: ["all"],
        timeBuckets: ["all"],
        rankDetails: ["all"],
      };
  const filteredGamesByTable = view
    ? view.filteredGames.filter((game) => {
        if (gameTableFilters.network !== "all" && game.network !== gameTableFilters.network) {
          return false;
        }
        if (
          gameTableFilters.time_bucket !== "all" &&
          game.time_bucket !== gameTableFilters.time_bucket
        ) {
          return false;
        }
        if (
          gameTableFilters.rank_detail !== "all" &&
          game.rank_detail !== gameTableFilters.rank_detail
        ) {
          return false;
        }
        return true;
      })
    : [];

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Team Profiles</h2>
      <p className="text-gray-600 mb-3 max-w-4xl">
        Explore one team at a time, then use a cleaner comparison module to stack it
        against another program under the same conditions.
      </p>
      <p className="text-gray-500 text-sm mb-6 max-w-4xl">
        Data excludes postseason games.
      </p>

      <div className="mb-6">
        <label className="mr-2">Select Team</label>
        <select value={selectedTeam} onChange={(e) => setSelectedTeam(e.target.value)}>
          <option value="">Select a team</option>
          {teams.map((team) => (
            <option key={team.value} value={team.value}>
              {team.label}
            </option>
          ))}
        </select>
      </div>

      {hasConfChampGames && (
        <label className="team-profile-toggle">
          <input
            type="checkbox"
            checked={includeConfChamp}
            onChange={(e) => setIncludeConfChamp(e.target.checked)}
          />
          <span>Include conference championship games</span>
        </label>
      )}

      {loading && <p>Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && !error && profile && view && (
        <>
          <div className="profile-hero-shell mb-8" style={theme}>
            <div className="profile-hero">
              {logoUrl && (
                <img
                  src={logoUrl}
                  alt={`${profile.team} logo`}
                  className="profile-hero-logo"
                />
              )}
              <div>
                <div className="profile-hero-kicker">Team Profile</div>
                <h3 className="profile-hero-title">{profile.team}</h3>
                <p className="profile-hero-subtitle">
                  {view.summary.games} tracked games across {view.summary.years_available.length} seasons
                </p>
              </div>
            </div>

            <div className="profile-metrics">
              <MetricCard
                label="FBS Brand Rank"
                value={
                  profile.summary.brand_rank != null ? `#${profile.summary.brand_rank}` : "N/A"
                }
              />
              <MetricCard
                label="Lift %"
                value={formatPercent(profile.summary.viewership_lift_pct)}
              />
              <MetricCard
                label="All-Time Average"
                value={formatMillions(view.summary.average_viewers)}
              />
              <MetricCard
                label="All-Time Median"
                value={formatMillions(view.summary.median_viewers)}
              />
            </div>

            <div className="profile-metrics">
              <MetricCard
                label="Typical FBS Expected"
                value={formatMillions(profile.summary.expected_average_viewers)}
              />
              <MetricCard
                label="Above / Below Expected"
                value={formatDifference(profile.summary.average_minus_expected)}
              />
              <MetricCard
                label="Over / Under Expected"
                value={formatPercent(profile.summary.overperformance_pct)}
              />
              <MetricCard
                label="Games Above Expected"
                value={
                  profile.summary.games != null
                    ? `${profile.summary.games_above_expected}/${profile.summary.games}`
                    : "N/A"
                }
              />
            </div>

            {Array.isArray(profile.summary.brand_trend) && profile.summary.brand_trend.length > 0 && (
              <div className="profile-brand-trend">
                <div className="profile-brand-trend-header">
                  <div>
                    <div className="profile-hero-kicker">Brand Trend</div>
                    <p className="profile-brand-trend-copy">
                      Lower rank is better. Lift values below show the yearly estimated brand premium.
                    </p>
                  </div>
                </div>
                <BrandTrendChart rows={profile.summary.brand_trend} team={profile.team} />
              </div>
            )}
          </div>

          <div className="card mb-8">
            <p className="text-gray-600 mb-2">Largest audience on record</p>
            <p className="text-xl font-semibold">
              {view.summary.peak_matchup || "N/A"} · {formatMillions(view.summary.peak_viewers)}
            </p>
          </div>

          <div className="scenario-shell scenario-shell-premium mb-8">
            <div className="scenario-header">
              <div>
                <div className="profile-hero-kicker">Comparison</div>
                <h3 className="text-2xl font-semibold mb-1">Scenario Simulator</h3>
                <p className="text-gray-600">
                  Compare {profile.team} to another team with the same filters, then
                  drill into shared opponents and direct matchups.
                </p>
              </div>
              <div className="comparison-select-card">
                <label className="comparison-select-label">Compare To</label>
                <select value={compareTeam} onChange={(e) => setCompareTeam(e.target.value)}>
                  <option value="">Select a team</option>
                  {teams
                    .filter((team) => team.value !== selectedTeam)
                    .map((team) => (
                      <option key={team.value} value={team.value}>
                        {team.label}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            <div className="simulator-showcase">
              <div className="simulator-team-display">
                {logoUrl && (
                  <img src={logoUrl} alt={`${profile.team} logo`} className="simulator-showcase-logo" />
                )}
                <div className="simulator-showcase-name">{profile.team}</div>
                <div className="simulator-showcase-meta">
                  Rank {profile.summary.brand_rank != null ? `#${profile.summary.brand_rank}` : "N/A"}
                </div>
              </div>

              <div className="simulator-versus-badge">vs</div>

              <div className="simulator-team-display">
                {compareLogoUrl && (
                  <img
                    src={compareLogoUrl}
                    alt={`${compareTeam} logo`}
                    className="simulator-showcase-logo"
                  />
                )}
                <div className="simulator-showcase-name">{compareTeam || "Select team"}</div>
                <div className="simulator-showcase-meta">
                  Rank {compareProfile?.summary?.brand_rank != null
                    ? `#${compareProfile.summary.brand_rank}`
                    : "N/A"}
                </div>
              </div>
            </div>

            <div className="scenario-controls">
              <ScenarioSelect
                label="From Year"
                value={scenarioFilters.year_start}
                onChange={(value) =>
                  setScenarioFilters((prev) => {
                    const next = { ...prev, year_start: value };
                    if (
                      value !== "all" &&
                      prev.year_end !== "all" &&
                      Number(value) > Number(prev.year_end)
                    ) {
                      next.year_end = value;
                    }
                    return next;
                  })
                }
                options={scenarioYearOptions}
              />
              <ScenarioSelect
                label="To Year"
                value={scenarioFilters.year_end}
                onChange={(value) =>
                  setScenarioFilters((prev) => {
                    const next = { ...prev, year_end: value };
                    if (
                      value !== "all" &&
                      prev.year_start !== "all" &&
                      Number(value) < Number(prev.year_start)
                    ) {
                      next.year_start = value;
                    }
                    return next;
                  })
                }
                options={scenarioYearOptions}
              />
              <ScenarioSelect
                label="Network"
                value={scenarioFilters.network}
                onChange={(value) =>
                  setScenarioFilters((prev) => ({ ...prev, network: value }))
                }
                options={scenarioData?.available_filters?.networks || ["all"]}
              />
              <ScenarioSelect
                label="Time Slot"
                value={scenarioFilters.time_bucket}
                onChange={(value) =>
                  setScenarioFilters((prev) => ({ ...prev, time_bucket: value }))
                }
                options={scenarioData?.available_filters?.time_buckets || ["all"]}
              />
              <ScenarioSelect
                label="Rankings"
                value={scenarioFilters.rank_bucket}
                onChange={(value) =>
                  setScenarioFilters((prev) => ({ ...prev, rank_bucket: value }))
                }
                options={scenarioData?.available_filters?.rank_buckets || ["all"]}
              />
            </div>

            <div className="scenario-stat-grid">
              <MetricCard
                label={
                  <MetricTeamLabel team={profile.team} logoUrl={logoUrl} suffix="Average" />
                }
                value={scenarioLoading ? "Loading…" : formatMillions(scenarioData?.team_average_viewers)}
              />
              <MetricCard
                label={
                  <MetricTeamLabel
                    team={scenarioData?.compare_team || compareTeam}
                    logoUrl={compareLogoUrl}
                    suffix="Average"
                  />
                }
                value={
                  scenarioLoading
                    ? "Loading…"
                    : formatMillions(scenarioData?.compare_team_average_viewers)
                }
              />
              <MetricCard
                label="Difference"
                value={scenarioLoading ? "Loading…" : formatDifference(scenarioData?.difference_viewers)}
              />
              <MetricCard
                label={`Lift Vs ${scenarioData?.compare_team || compareTeam}`}
                value={scenarioLoading ? "Loading…" : formatPercent(scenarioData?.difference_pct)}
              />
            </div>

            {scenarioData && !scenarioLoading && (
              <div className="scenario-summary-card">
                <p className="text-gray-600 mb-2">Actual vs Typical FBS Expectation</p>
                <div className="scenario-expected-grid">
                  <div>
                    <p className="text-sm text-gray-600 mb-1">{profile.team}</p>
                    <p className="text-lg font-semibold">
                      {formatDifference(scenarioData.team_average_minus_expected)}
                    </p>
                    <p className="text-gray-600 text-sm">
                      Expected {formatMillions(scenarioData.team_expected_average_viewers)} ·{" "}
                      {formatPercent(scenarioData.team_overperformance_pct)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">{scenarioData.compare_team}</p>
                    <p className="text-lg font-semibold">
                      {formatDifference(scenarioData.compare_team_average_minus_expected)}
                    </p>
                    <p className="text-gray-600 text-sm">
                      Expected {formatMillions(scenarioData.compare_team_expected_average_viewers)} ·{" "}
                      {formatPercent(scenarioData.compare_team_overperformance_pct)}
                    </p>
                  </div>
                </div>
                <p className="text-gray-500 text-sm mt-3">
                  Positive numbers mean the team drew more viewers than a typical FBS team
                  would have been expected to draw in the same conditions. Negative numbers
                  mean it drew less.
                </p>
              </div>
            )}

            {scenarioData && !scenarioLoading && (
              <div className="scenario-summary-card">
                <p className="text-gray-600 mb-2">Scenario sample sizes</p>
                <p className="text-lg font-semibold">
                  {profile.team}: {scenarioData.team_sample_size} games ·{" "}
                  {scenarioData.compare_team}: {scenarioData.compare_team_sample_size} games
                </p>
              </div>
            )}

            {scenarioData && !scenarioLoading && (
              <div className="scenario-subsection">
                <h4 className="text-xl font-semibold">Shared Opponents</h4>
                {scenarioData.shared_opponents?.length ? (
                  <div className="overflow-x-auto scenario-table-wrap">
                    <table className="min-w-max w-full">
                      <thead>
                        <tr>
                          <th>Opponent</th>
                          <th>
                            <TableTeamHeader team={profile.team} logoUrl={logoUrl} />
                          </th>
                          <th>
                            <TableTeamHeader
                              team={scenarioData.compare_team}
                              logoUrl={compareLogoUrl}
                            />
                          </th>
                          <th>Difference</th>
                          <th>Games</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scenarioData.shared_opponents.map((row) => (
                          <tr key={row.opponent}>
                            <td>
                              <TableTeamHeader
                                team={row.opponent}
                                logoUrl={getTeamLogoUrl(row.opponent)}
                              />
                            </td>
                            <td>{formatMillions(row.team_average_viewers)}</td>
                            <td>{formatMillions(row.compare_average_viewers)}</td>
                            <td>
                              <DifferenceBubble value={row.difference_viewers} />
                            </td>
                            <td>{row.team_games}-{row.compare_games}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-600">
                    No shared opponents match the current scenario filters.
                  </p>
                )}
              </div>
            )}

            {scenarioData && !scenarioLoading && (
              <div className="scenario-subsection">
                <h4 className="text-xl font-semibold">Head-to-Head Games</h4>
                {scenarioData.head_to_head_games?.length ? (
                  <div className="overflow-x-auto scenario-table-wrap">
                    <table className="min-w-max w-full">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Year</th>
                          <th>Matchup</th>
                          <th>Network</th>
                          <th>Time Slot</th>
                          <th>Audience</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scenarioData.head_to_head_games.map((game) => (
                          <tr key={`${game.date}-${game.matchup}`}>
                            <td>{game.date}</td>
                            <td>{game.year}</td>
                            <td>
                              <GameLabel matchup={game.matchup} confChamp={game.conf_champ} />
                            </td>
                            <td>{game.network}</td>
                            <td>{game.time_bucket}</td>
                            <td>{formatMillions(game.viewers)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-600">
                    No head-to-head games match the current scenario filters.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="team-profile-sections">
            <div className="team-profile-section">
              <h3 className="text-2xl font-semibold mb-4">Yearly Summary</h3>
              <div className="overflow-x-auto">
                <table className="min-w-max w-full">
                  <thead>
                    <tr>
                      <th>Year</th>
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
                    {view.yearlyRows.map((row) => (
                      <tr key={row.year}>
                        <td>{row.year}</td>
                        <td>{row.games}</td>
                        <td>{formatMillions(row.average_viewers)}</td>
                        <td>{formatMillions(row.median_viewers)}</td>
                        <td>{row.peak_matchup}</td>
                        <td>{formatMillions(row.peak_viewers)}</td>
                        <td>{row.peak_network || "N/A"}</td>
                        <td>{row.low_matchup}</td>
                        <td>{formatMillions(row.low_viewers)}</td>
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
                        <th>Year</th>
                        <th>Date</th>
                        <th>Matchup</th>
                        <th>Network</th>
                        <th>Audience</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.topGames.map((game) => (
                        <tr key={`${game.rank}-${game.date}-${game.matchup}`}>
                          <td>{game.rank}</td>
                          <td>{game.year}</td>
                          <td>{game.date}</td>
                          <td>
                            <GameLabel matchup={game.matchup} confChamp={game.conf_champ} />
                          </td>
                          <td>{game.network}</td>
                          <td>{formatMillions(game.viewers)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="team-profile-section">
              <div className="team-profile-filter-row">
                <h3 className="text-2xl font-semibold">Games By Year</h3>
                <div className="team-profile-year-filter">
                  <label className="mr-2">Year</label>
                  <select value={selectedYear} onChange={(e) => setSelectedYear(e.target.value)}>
                    <option value="all">All Years</option>
                    {view.summary.years_available
                      .slice()
                      .sort((a, b) => b - a)
                      .map((year) => (
                        <option key={year} value={String(year)}>
                          {year}
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              <div className="scenario-controls mb-4">
                <ScenarioSelect
                  label="Network"
                  value={gameTableFilters.network}
                  onChange={(value) =>
                    setGameTableFilters((prev) => ({ ...prev, network: value }))
                  }
                  options={gameTableOptions.networks}
                />
                <ScenarioSelect
                  label="Time Slot"
                  value={gameTableFilters.time_bucket}
                  onChange={(value) =>
                    setGameTableFilters((prev) => ({ ...prev, time_bucket: value }))
                  }
                  options={gameTableOptions.timeBuckets}
                />
                <ScenarioSelect
                  label="Rankings"
                  value={gameTableFilters.rank_detail}
                  onChange={(value) =>
                    setGameTableFilters((prev) => ({ ...prev, rank_detail: value }))
                  }
                  options={gameTableOptions.rankDetails}
                />
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-max w-full">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Year</th>
                      <th>Matchup</th>
                      <th>Opponent</th>
                      <th>Network</th>
                      <th>Time Slot</th>
                      <th>Rankings</th>
                      <th>Audience</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredGamesByTable.map((game) => (
                      <tr key={`${game.date}-${game.matchup}-${game.year}`}>
                        <td>{game.date}</td>
                        <td>{game.year}</td>
                        <td>
                          <GameLabel matchup={game.matchup} confChamp={game.conf_champ} />
                        </td>
                        <td>{game.opponent}</td>
                        <td>{game.network}</td>
                        <td>{game.time_bucket || "N/A"}</td>
                        <td>{game.rank_detail || "N/A"}</td>
                        <td>{formatMillions(game.viewers)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredGamesByTable.length === 0 && (
                <p className="text-gray-600">No games match the current filter.</p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="metric-card-modern">
      <div className="text-sm text-gray-600 metric-card-label">{label}</div>
      <p className="text-2xl font-semibold mt-1 metric-card-value">{value}</p>
    </div>
  );
}

function MetricTeamLabel({ team, logoUrl, suffix }) {
  return (
    <span className="metric-team-label">
      {logoUrl && <img src={logoUrl} alt={`${team} logo`} className="metric-team-logo" />}
      <span>{team} {suffix}</span>
    </span>
  );
}

function TableTeamHeader({ team, logoUrl }) {
  return (
    <span className="table-team-header">
      {logoUrl && <img src={logoUrl} alt={`${team} logo`} className="metric-team-logo" />}
      <span>{team}</span>
    </span>
  );
}

function DifferenceBubble({ value }) {
  if (value == null) {
    return <span>N/A</span>;
  }

  const normalizedValue = Math.abs(value) < 0.5 ? 0 : value;
  const bubbleClass =
    normalizedValue > 0
      ? "difference-bubble difference-bubble-positive"
      : normalizedValue < 0
        ? "difference-bubble difference-bubble-negative"
        : "difference-bubble difference-bubble-neutral";

  return <span className={bubbleClass}>{formatDifference(normalizedValue)}</span>;
}

function ScenarioSelect({ label, value, onChange, options }) {
  return (
    <div className="scenario-select-block">
      <label className="scenario-select-label">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "all" ? "All" : option}
          </option>
        ))}
      </select>
    </div>
  );
}

function GameLabel({ matchup, confChamp }) {
  return (
    <span className="game-label">
      <span>{matchup}</span>
      {confChamp && <span className="game-badge">Conf Champ</span>}
    </span>
  );
}
