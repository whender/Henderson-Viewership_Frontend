import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl } from "./teamLogos";

const CONFERENCE_OPTIONS = ["Big 10", "SEC", "Big 12", "ACC"];
const RANKING_POLICIES = [
  ["espn_2026_preseason", "ESPN 2026 Preseason"],
  ["final_ap_2021_2025", "Final AP 2021-2025"],
  ["unranked", "All Unranked"],
];
const DEFAULT_PROTECTED_OPPONENTS = ["USC", "Washington", "Oregon", "UCLA"];
const SCHEDULE_TIME_SLOT_ORDER = [
  "Friday",
  "Sat Early (11:00a-2:00p)",
  "Sat Mid (2:30p-6:30p)",
  "Primetime (7:00p-9:00p)",
  "Sat Late (9:30p-Later)",
  "No national TV window",
];

function formatViewers(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(2)}M`;
  if (Math.abs(number) >= 1_000) return `${Math.round(number / 1_000)}K`;
  return `${Math.round(number)}`;
}

function formatSignedViewers(value) {
  const number = Number(value || 0);
  const sign = number > 0 ? "+" : "";
  return `${sign}${formatViewers(number)}`;
}

function formatSignedPercent(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "N/A";
  }
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(1)}%`;
}

function formatSignedNumber(value) {
  const number = Number(value || 0);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number}`;
}

function formatSignedRatio(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "N/A";
  }
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}`;
}

function rankLabel(rank) {
  return rank > 0 ? `#${rank}` : "UR";
}

export default function RealignmentSimulator({ teams }) {
  const [simMode, setSimMode] = useState("realignment");
  const [conference, setConference] = useState("Big 10");
  const [expansionTeam, setExpansionTeam] = useState("Utah");
  const [expansionTeam2, setExpansionTeam2] = useState("");
  const [protectedOpponentsByTeam, setProtectedOpponentsByTeam] = useState({
    Utah: DEFAULT_PROTECTED_OPPONENTS,
  });
  const [gamesPerTeam, setGamesPerTeam] = useState(9);
  const [rankingPolicy, setRankingPolicy] = useState("espn_2026_preseason");
  const [superleagueTeams, setSuperleagueTeams] = useState([]);
  const [simulation, setSimulation] = useState(null);
  const [conferenceTeams, setConferenceTeams] = useState([]);
  const [editableConferences, setEditableConferences] = useState(CONFERENCE_OPTIONS);
  const [leagueMemberships, setLeagueMemberships] = useState({});
  const [leagueAddTeam, setLeagueAddTeam] = useState("");
  const [leagueProtectedMatchupsByTeam, setLeagueProtectedMatchupsByTeam] = useState({});
  const [leagueProtectedExpanded, setLeagueProtectedExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const teamOptions = useMemo(
    () => (teams || []).slice().sort((a, b) => a.label.localeCompare(b.label)),
    [teams]
  );
  const expansionTeams = useMemo(
    () => [expansionTeam, expansionTeam2].filter(Boolean),
    [expansionTeam, expansionTeam2]
  );
  const leagueTeamsByConference = useMemo(
    () => Object.fromEntries(
      editableConferences.map((option) => [
        option,
        Object.entries(leagueMemberships)
          .filter(([, teamConference]) => teamConference === option)
          .map(([team]) => team)
          .sort((a, b) => a.localeCompare(b)),
      ])
    ),
    [editableConferences, leagueMemberships]
  );
  const availableLeagueAddTeams = useMemo(
    () => teamOptions.filter((team) => !leagueMemberships[team.value]),
    [teamOptions, leagueMemberships]
  );
  const totalProtectedOpponents = useMemo(
    () => expansionTeams.reduce(
      (total, team) => total + (protectedOpponentsByTeam[team] || []).filter(Boolean).length,
      0
    ),
    [expansionTeams, protectedOpponentsByTeam]
  );

  const runSimulation = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const isSuperleague = simMode === "superleague";
      const isLeagueEditor = simMode === "realignment";
      const protectedOpponentsPayload = Object.fromEntries(
        expansionTeams.map((team) => [team, (protectedOpponentsByTeam[team] || []).filter(Boolean)])
      );

      const response = await fetch(`${BACKEND_BASE}${
        isSuperleague
          ? "/realignment/superleague"
          : isLeagueEditor
            ? "/realignment/league-simulate"
            : "/realignment/simulate"
      }`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          isSuperleague
            ? {
            teams: superleagueTeams,
            games_per_team: Number(gamesPerTeam),
            ranking_policy: rankingPolicy,
          }
            : isLeagueEditor
              ? {
                memberships: leagueMemberships,
                protected_matchups_by_team: leagueProtectedMatchupsByTeam,
                games_per_team: Number(gamesPerTeam),
                ranking_policy: rankingPolicy,
              }
              : {
            conference,
            expansion_teams: expansionTeams,
            protected_opponents: (protectedOpponentsByTeam[expansionTeam] || []).filter(Boolean),
            protected_opponents_by_team: protectedOpponentsPayload,
            games_per_team: Number(gamesPerTeam),
            ranking_policy: rankingPolicy,
          }),
      });

      if (!response.ok) {
        throw new Error(`Simulation failed with status ${response.status}`);
      }

      const data = await response.json();
      setSimulation(data);
    } catch (err) {
      console.error("Realignment simulation error:", err);
      setError("Failed to run realignment simulation.");
    } finally {
      setLoading(false);
    }
  }, [conference, expansionTeam, expansionTeams, protectedOpponentsByTeam, gamesPerTeam, rankingPolicy, simMode, superleagueTeams, leagueMemberships, leagueProtectedMatchupsByTeam]);

  function toggleProtectedOpponent(expansion, opponent) {
    setProtectedOpponentsByTeam((current) => {
      const active = new Set((current[expansion] || []).filter(Boolean));
      if (active.has(opponent)) {
        active.delete(opponent);
      } else {
        active.add(opponent);
      }
      return {
        ...current,
        [expansion]: Array.from(active),
      };
    });
  }

  function toggleSuperleagueTeam(team) {
    setSuperleagueTeams((current) => {
      if (current.includes(team)) {
        return current.filter((selected) => selected !== team);
      }
      return [...current, team];
    });
  }

  function moveLeagueTeam(team, destinationConference) {
    setLeagueMemberships((current) => ({
      ...current,
      [team]: destinationConference,
    }));
  }

  function toggleLeagueProtectedMatchup(team, opponent) {
    setLeagueProtectedMatchupsByTeam((current) => {
      const teamActive = new Set((current[team] || []).filter(Boolean));
      const opponentActive = new Set((current[opponent] || []).filter(Boolean));
      if (teamActive.has(opponent) || opponentActive.has(team)) {
        teamActive.delete(opponent);
        opponentActive.delete(team);
      } else {
        const teamCount = selectedConferenceTeams.filter((candidate) => (
          candidate !== team
          && (
            teamActive.has(candidate)
            || (current[candidate] || []).includes(team)
          )
        )).length;
        const opponentCount = selectedConferenceTeams.filter((candidate) => (
          candidate !== opponent
          && (
            opponentActive.has(candidate)
            || (current[candidate] || []).includes(opponent)
          )
        )).length;
        if (teamCount >= 2 || opponentCount >= 2) {
          return current;
        }
        teamActive.add(opponent);
      }
      return {
        ...current,
        [team]: Array.from(teamActive),
        [opponent]: Array.from(opponentActive),
      };
    });
  }

  function isLeagueProtectedMatchup(team, opponent) {
    return (leagueProtectedMatchupsByTeam[team] || []).includes(opponent)
      || (leagueProtectedMatchupsByTeam[opponent] || []).includes(team);
  }

  function leagueProtectedCount(team) {
    return selectedConferenceTeams.filter((opponent) => (
      opponent !== team && isLeagueProtectedMatchup(team, opponent)
    )).length;
  }

  function canAddLeagueProtectedMatchup(team, opponent) {
    return isLeagueProtectedMatchup(team, opponent)
      || (leagueProtectedCount(team) < 2 && leagueProtectedCount(opponent) < 2);
  }

  function addLeagueTeam() {
    if (!leagueAddTeam) return;
    moveLeagueTeam(leagueAddTeam, conference);
    setLeagueAddTeam("");
  }

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ conference });

    fetch(`${BACKEND_BASE}/realignment/conference-members?${params.toString()}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Conference members failed with status ${response.status}`);
        return response.json();
      })
      .then((data) => setConferenceTeams(data.teams || []))
      .catch((err) => {
        if (err.name !== "AbortError") {
          console.error("Conference members error:", err);
          setConferenceTeams([]);
        }
      });

    return () => controller.abort();
  }, [conference]);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${BACKEND_BASE}/realignment/memberships`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Conference memberships failed with status ${response.status}`);
        return response.json();
      })
      .then((data) => {
        setEditableConferences(data.conferences || CONFERENCE_OPTIONS);
        setLeagueMemberships(data.memberships || {});
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          console.error("Conference memberships error:", err);
        }
      });

    return () => controller.abort();
  }, []);

  const isSuperleagueMode = simMode === "superleague";
  const isLeagueEditorMode = simMode === "realignment";
  const isSuperleagueResult = simulation?.mode === "superleague";
  const isLeagueResult = simulation?.mode === "league_realignment";
  const impact = simulation?.impact || {};
  const baseline = simulation?.baseline?.summary || {};
  const expanded = simulation?.expanded?.summary || {};
  const topExpansionGames = simulation?.top_expansion_games || [];
  const conferenceTeamOptionsByExpansion = useMemo(
    () => Object.fromEntries(
      expansionTeams.map((team) => [
        team,
        conferenceTeams.filter((conferenceTeam) => conferenceTeam !== team),
      ])
    ),
    [conferenceTeams, expansionTeams]
  );
  const expandedRows = useMemo(
    () => simulation?.expanded?.rows || [],
    [simulation]
  );
  const superleagueRows = useMemo(
    () => simulation?.slate?.rows || [],
    [simulation]
  );
  const leagueRows = useMemo(
    () => simulation?.rows || [],
    [simulation]
  );
  const selectedLeagueRows = useMemo(
    () => leagueRows.filter((row) => row.conference === conference),
    [leagueRows, conference]
  );
  const selectedLeagueTeamStats = useMemo(
    () => buildTeamStats(selectedLeagueRows),
    [selectedLeagueRows]
  );
  const displayedRows = isLeagueResult ? selectedLeagueRows : isSuperleagueResult ? superleagueRows : expandedRows;
  const expandedTopRows = useMemo(
    () => displayedRows
      .slice()
      .sort((a, b) => Number(b.predicted_viewers || 0) - Number(a.predicted_viewers || 0))
      .slice(0, 40),
    [displayedRows]
  );
  useEffect(() => {
    if (!conferenceTeams.length) return;
    setProtectedOpponentsByTeam((current) => {
      const next = {};
      expansionTeams.forEach((team) => {
        next[team] = (current[team] || []).filter(
          (opponent) => conferenceTeams.includes(opponent) && opponent !== team
        );
      });
      return next;
    });
  }, [conferenceTeams, expansionTeams]);
  const expansionTeamRows = useMemo(() => {
    const expansionTeams = new Set(simulation?.expansion_teams || []);
    return expandedRows
      .filter((row) => expansionTeams.has(row.team1) || expansionTeams.has(row.team2))
      .sort((a, b) => {
        if (a.protected !== b.protected) return a.protected ? -1 : 1;
        return Number(b.predicted_viewers || 0) - Number(a.predicted_viewers || 0);
      });
  }, [expandedRows, simulation]);
  const backendSupportsProtectedAudit = simulation?.realignment_simulator_version >= 2;
  const protectedAuditRows = useMemo(
    () => simulation?.protected_matchups || [],
    [simulation]
  );
  const protectedMissingCount = Number(simulation?.protected_missing_count || 0);
  const protectedStatusRows = useMemo(() => {
    if (backendSupportsProtectedAudit) {
      return protectedAuditRows.map((row) => ({
        expansionTeam: row.expansion_team || expansionTeams.find((team) => row.team1 === team || row.team2 === team) || expansionTeam,
        opponent: row.opponent || (row.team1 === expansionTeam ? row.team2 : row.team1),
        included: Boolean(row.scheduled),
        projected: row.predicted_viewers,
      }));
    }

    return expansionTeams.flatMap((team) => (protectedOpponentsByTeam[team] || []).filter(Boolean).map((opponent) => ({
      expansionTeam: team,
      opponent,
      included: false,
      projected: null,
    })));
  }, [backendSupportsProtectedAudit, expansionTeam, expansionTeams, protectedAuditRows, protectedOpponentsByTeam]);
  const hasInvalidProtectedResponse = Boolean(
    simulation
    && !isLeagueResult
    && !isSuperleagueResult
    && totalProtectedOpponents > 0
    && (!backendSupportsProtectedAudit || protectedMissingCount > 0)
  );
  const superleagueSummary = simulation?.slate?.summary || {};
  const selectedLeagueSummary = simulation?.conference_summaries?.[conference] || {};
  const selectedMembershipChange = simulation?.conference_membership_changes?.[conference] || {};
  const selectedLeagueDistribution = simulation?.conference_distribution_metrics?.[conference] || [];
  const selectedConferenceTeams = leagueTeamsByConference[conference] || [];
  const selectedConferenceProtectedCount = new Set(
    selectedConferenceTeams.flatMap((team) => (leagueProtectedMatchupsByTeam[team] || [])
      .filter((opponent) => selectedConferenceTeams.includes(opponent) && opponent !== team)
      .map((opponent) => [team, opponent].sort().join("::")))
  ).size;

  return (
    <>
      <h2 className="text-3xl font-semibold mb-4">Conference Realignment Simulator</h2>
      <p className="text-gray-500 text-sm mb-6 max-w-3xl leading-relaxed">
        Move teams between conferences, lock additional protected matchups, and simulate every conference schedule with the football viewership model.
      </p>

      <div className="sim-mode-toggle mb-6" role="group" aria-label="Simulation mode">
        <button
          className={`sim-mode-button ${simMode === "realignment" ? "sim-mode-button-active" : ""}`}
          type="button"
          onClick={() => setSimMode("realignment")}
        >
          Realignment
        </button>
        <button
          className={`sim-mode-button ${simMode === "superleague" ? "sim-mode-button-active" : ""}`}
          type="button"
          onClick={() => setSimMode("superleague")}
        >
          Superleague
        </button>
      </div>

      <div className="scenario-controls mb-6">
        {!isSuperleagueMode && !isLeagueEditorMode && (
          <>
            <label className="brand-filter-card">
              <span className="brand-filter-label">Conference</span>
              <select
                className="brand-filter-select"
                value={conference}
                onChange={(e) => setConference(e.target.value)}
              >
                {CONFERENCE_OPTIONS.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="brand-filter-card">
              <span className="brand-filter-label">Expansion Team 1</span>
              <select
                className="brand-filter-select"
                value={expansionTeam}
                onChange={(e) => setExpansionTeam(e.target.value)}
              >
                {teamOptions.map((team) => (
                  <option key={team.value} value={team.value}>
                    {team.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="brand-filter-card">
              <span className="brand-filter-label">Expansion Team 2</span>
              <select
                className="brand-filter-select"
                value={expansionTeam2}
                onChange={(e) => setExpansionTeam2(e.target.value)}
              >
                <option value="">None</option>
                {teamOptions.map((team) => (
                  <option key={team.value} value={team.value}>
                    {team.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {isLeagueEditorMode && (
          <label className="brand-filter-card">
            <span className="brand-filter-label">Edit Conference</span>
            <select
              className="brand-filter-select"
              value={conference}
              onChange={(e) => setConference(e.target.value)}
            >
              {editableConferences.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        )}

        <label className="brand-filter-card">
          <span className="brand-filter-label">{isSuperleagueMode || isLeagueEditorMode ? "League Games" : "Conference Games"}</span>
          <select
            className="brand-filter-select"
            value={gamesPerTeam}
            onChange={(e) => setGamesPerTeam(Number(e.target.value))}
          >
            {[7, 8, 9, 10, 11, 12].map((option) => (
              <option key={option} value={option}>
                {option} per team
              </option>
            ))}
          </select>
        </label>

        <label className="brand-filter-card">
          <span className="brand-filter-label">Rankings</span>
          <select
            className="brand-filter-select"
            value={rankingPolicy}
            onChange={(e) => setRankingPolicy(e.target.value)}
          >
            {RANKING_POLICIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!isSuperleagueMode && !isLeagueEditorMode && (
        <div className="scenario-summary-card mb-6">
        <h3 className="text-xl font-semibold mb-3">Protected Matchups</h3>
        <p className="text-gray-500 text-sm mb-4">
          Select conference opponents that are locked onto each expansion team&apos;s schedule before the remaining games are filled.
          {" "}{totalProtectedOpponents} selected.
        </p>
        <div className="protected-team-sections">
          {expansionTeams.map((team) => {
            const selectedOpponents = protectedOpponentsByTeam[team] || [];
            const teamOptionsForExpansion = conferenceTeamOptionsByExpansion[team] || [];

            return (
              <div className="protected-team-section" key={team}>
                <div className="protected-team-section-header">
                  {getTeamLogoUrl(team) && (
                    <img
                      alt={`${team} logo`}
                      className="protected-team-section-logo"
                      src={getTeamLogoUrl(team)}
                    />
                  )}
                  <div>
                    <h4>{team}</h4>
                    <p>{selectedOpponents.length} protected</p>
                  </div>
                </div>
                <div className="protected-team-grid">
                  {teamOptionsForExpansion.map((opponent) => {
                    const selected = selectedOpponents.includes(opponent);
                    const logoUrl = getTeamLogoUrl(opponent);

                    return (
                      <button
                        className={`protected-team-card ${selected ? "protected-team-card-active" : ""}`}
                        key={`${team}-${opponent}`}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => toggleProtectedOpponent(team, opponent)}
                      >
                        {logoUrl && (
                          <img
                            alt={`${opponent} logo`}
                            className="protected-team-logo"
                            src={logoUrl}
                          />
                        )}
                        <span>{opponent}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      )}

      {isLeagueEditorMode && (
        <div className="scenario-summary-card mb-6">
          <div className="league-editor-header">
            <div>
              <h3 className="text-xl font-semibold mb-1">{conference} Membership</h3>
              <p className="text-gray-500 text-sm">
                Move teams out of this conference or add available teams into it. {selectedConferenceTeams.length} teams currently assigned.
              </p>
            </div>
            <div className="league-add-control">
              <select
                className="brand-filter-select"
                value={leagueAddTeam}
                onChange={(e) => setLeagueAddTeam(e.target.value)}
              >
                <option value="">Add team</option>
                {availableLeagueAddTeams.map((team) => (
                  <option key={team.value} value={team.value}>
                    {team.label}
                  </option>
                ))}
              </select>
              <button className="btn-primary" type="button" onClick={addLeagueTeam}>
                Add
              </button>
            </div>
          </div>
          <div className="league-team-grid mt-5">
            {selectedConferenceTeams.map((team) => {
              const logoUrl = getTeamLogoUrl(team);
              return (
                <div className="league-team-card" key={team}>
                  {logoUrl && (
                    <img
                      alt={`${team} logo`}
                      className="protected-team-logo"
                      src={logoUrl}
                    />
                  )}
                  <span>{team}</span>
                  <select
                    className="brand-filter-select"
                    value={leagueMemberships[team] || conference}
                    onChange={(e) => moveLeagueTeam(team, e.target.value)}
                  >
                    {editableConferences.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>

          <div className="league-protected-panel mt-6">
            <div className="league-editor-header">
              <div>
                <h3 className="text-xl font-semibold mb-1">Additional Protected Matchups</h3>
                <p className="text-gray-500 text-sm">
                  Default rivalry games are already protected. Add any extra locked games for {conference}. {selectedConferenceProtectedCount} selected.
                </p>
              </div>
              <button
                className="btn-secondary"
                type="button"
                aria-expanded={leagueProtectedExpanded}
                onClick={() => setLeagueProtectedExpanded((expanded) => !expanded)}
              >
                {leagueProtectedExpanded ? "Collapse" : "Expand"}
              </button>
            </div>
            {leagueProtectedExpanded && (
              <div className="protected-team-sections mt-5">
                {selectedConferenceTeams.map((team) => {
                  const logoUrl = getTeamLogoUrl(team);
                  const selectedCount = leagueProtectedCount(team);

                  return (
                    <div className="protected-team-section league-protected-section" key={`protected-${team}`}>
                      <div className="league-protected-row">
                        <span className="protected-team-section-header">
                          {logoUrl && (
                            <img
                              alt={`${team} logo`}
                              className="protected-team-section-logo"
                              src={logoUrl}
                            />
                          )}
                          <span>
                            <span className="league-protected-team-name">{team}</span>
                            <span className="league-protected-team-count">{selectedCount}/2 added</span>
                          </span>
                        </span>
                        <span className="league-protected-opponent-strip">
                          {selectedConferenceTeams
                            .filter((opponent) => opponent !== team)
                            .map((opponent) => {
                              const selected = isLeagueProtectedMatchup(team, opponent);
                              const opponentLogoUrl = getTeamLogoUrl(opponent);
                              const canSelect = canAddLeagueProtectedMatchup(team, opponent);

                              return (
                                <button
                                  className={`league-protected-logo-button ${selected ? "league-protected-logo-button-active" : ""}`}
                                  key={`${team}-${opponent}`}
                                  type="button"
                                  aria-label={`${selected ? "Remove" : "Add"} ${team} vs ${opponent}`}
                                  aria-pressed={selected}
                                  disabled={!canSelect}
                                  title={opponent}
                                  onClick={() => toggleLeagueProtectedMatchup(team, opponent)}
                                >
                                  {opponentLogoUrl ? (
                                    <img
                                      alt=""
                                      className="league-protected-logo"
                                      src={opponentLogoUrl}
                                    />
                                  ) : (
                                    <span>{opponent}</span>
                                  )}
                                </button>
                              );
                            })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {isSuperleagueMode && (
        <div className="scenario-summary-card mb-6">
          <h3 className="text-xl font-semibold mb-3">Draft Superleague Teams</h3>
          <p className="text-gray-500 text-sm mb-4">
            Select teams for the superleague slate. {superleagueTeams.length} teams selected.
          </p>
          <div className="protected-team-grid">
            {teamOptions.map((team) => {
              const selected = superleagueTeams.includes(team.value);
              const logoUrl = getTeamLogoUrl(team.value);

              return (
                <button
                  className={`protected-team-card ${selected ? "protected-team-card-active" : ""}`}
                  key={team.value}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => toggleSuperleagueTeam(team.value)}
                >
                  {logoUrl && (
                    <img
                      alt={`${team.label} logo`}
                      className="protected-team-logo"
                      src={logoUrl}
                    />
                  )}
                  <span>{team.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <button onClick={runSimulation} className="btn-primary" disabled={loading}>
        {loading ? "Running..." : "Refresh Simulation"}
      </button>

      {error && <p className="text-red-600 mt-6">{error}</p>}

      {simulation && !error && (
        <div className="realignment-sim mt-8">
          <div className="scenario-stat-grid realignment-metrics">
            {isLeagueResult ? (
              <>
                <MetricCard label={`${conference} Viewers`} value={formatViewers(selectedLeagueSummary.total_viewers)} />
                <MetricCard label={`${conference} Avg.`} value={formatViewers(selectedLeagueSummary.average_viewers)} />
                <MetricCard label={`${conference} TV Games`} value={selectedLeagueSummary.nationally_rated_games || selectedLeagueSummary.games || 0} />
                <MetricCard label={`${conference} Scheduled`} value={selectedLeagueSummary.scheduled_games || selectedLeagueSummary.games || 0} />
                <MetricCard label={`${conference} Teams`} value={selectedLeagueSummary.teams || selectedConferenceTeams.length || 0} />
                <MetricCard
                  label="Membership Change"
                  value={`${formatSignedNumber(selectedMembershipChange.team_delta)} teams (${formatSignedPercent(selectedMembershipChange.pct_delta)})`}
                />
              </>
            ) : isSuperleagueResult ? (
              <>
                <MetricCard label="Total Viewers" value={formatViewers(impact.total_viewers)} />
                <MetricCard label="Average Game" value={formatViewers(impact.average_viewers)} />
                <MetricCard label="Games" value={impact.games || 0} />
                <MetricCard label="Teams" value={impact.teams || 0} />
              </>
            ) : (
              <>
                <MetricCard label="Total Viewer Delta" value={formatSignedViewers(impact.total_viewer_delta)} />
                <MetricCard label="Average Game Delta" value={formatSignedViewers(impact.average_viewer_delta)} />
                <MetricCard label="Expansion Games" value={impact.expansion_team_games || 0} />
                <MetricCard label="Expansion Avg." value={formatViewers(impact.expansion_team_average_viewers)} />
              </>
            )}
          </div>

          {isLeagueResult ? (
            <>
              <div className="scenario-summary-card mt-6">
                <h3 className="text-xl font-semibold mb-4">Conference Summaries</h3>
                <div className="brand-table-wrap">
                  <table className="brand-rankings-table realignment-table">
                    <thead>
                      <tr>
                        <th>Conference</th>
                        <th>Teams</th>
                        <th>TV Games</th>
                        <th>Scheduled</th>
                        <th>Unrated</th>
                        <th>Total</th>
                        <th>Average</th>
                      </tr>
                    </thead>
                    <tbody>
                      {editableConferences.map((option) => {
                        const summary = simulation?.conference_summaries?.[option] || {};
                        return (
                          <tr key={option}>
                            <td>{option === conference ? `${option} (selected)` : option}</td>
                            <td>{summary.teams || 0}</td>
                            <td>{summary.nationally_rated_games || summary.games || 0}</td>
                            <td>{summary.scheduled_games || summary.games || 0}</td>
                            <td>{summary.unrated_games || 0}</td>
                            <td>{formatViewers(summary.total_viewers)}</td>
                            <td>{formatViewers(summary.average_viewers)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
              <DistributionMetricsTable conference={conference} rows={selectedLeagueDistribution} />
            </>
          ) : isSuperleagueResult ? (
            <div className="scenario-expected-grid mt-6">
              <SummaryCard
                title="Superleague Slate"
                teams={superleagueSummary.teams}
                games={superleagueSummary.games}
                total={superleagueSummary.total_viewers}
                average={superleagueSummary.average_viewers}
              />
              <div className="scenario-summary-card">
                <h3 className="text-xl font-semibold mb-4">TV Plan</h3>
                <table>
                  <tbody>
                    <tr>
                      <td>Plan</td>
                      <td>{simulation?.settings?.tv_network_plan || "Superleague National TV Mix"}</td>
                    </tr>
                    <tr>
                      <td>Rankings</td>
                      <td>{simulation?.settings?.ranking_policy || rankingPolicy}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <>
              <div className="scenario-expected-grid mt-6">
                <SummaryCard
                  title="Current Slate"
                  teams={baseline.teams}
                  games={baseline.games}
                  total={baseline.total_viewers}
                  average={baseline.average_viewers}
                />
                <SummaryCard
                  title="Expanded Slate"
                  teams={expanded.teams}
                  games={expanded.games}
                  total={expanded.total_viewers}
                  average={expanded.average_viewers}
                />
              </div>

              <div className="scenario-summary-card mt-6">
                <h3 className="text-xl font-semibold mb-3">Top Expansion Games</h3>
                <ScheduleTable rows={topExpansionGames} compact />
              </div>

              <div className="scenario-summary-card mt-6">
                <h3 className="text-xl font-semibold mb-3">Expansion Team Schedule</h3>
                {protectedStatusRows.length > 0 && (
                  <div className="team-pill-row" style={{ justifyContent: "flex-start" }}>
                    {protectedStatusRows.map((row) => (
                      <span
                        key={`${row.expansionTeam}-${row.opponent}`}
                        className={`difference-bubble ${row.included ? "difference-bubble-positive" : "difference-bubble-negative"}`}
                      >
                        {row.included ? "Included" : "Missing"}: {row.expansionTeam} vs {row.opponent}
                        {row.projected ? ` (${formatViewers(row.projected)})` : ""}
                      </span>
                    ))}
                  </div>
                )}
                {hasInvalidProtectedResponse && (
                  <p className="text-red-600 text-sm mb-4">
                    The backend response did not schedule every selected protected matchup. Restart or redeploy the backend with the latest realignment simulator code before trusting these totals.
                  </p>
                )}
                <ScheduleTable rows={expansionTeamRows} />
              </div>
            </>
          )}

          <div className="scenario-summary-card mt-6">
            <h3 className="text-xl font-semibold mb-3">
              {isLeagueResult ? `${conference} Week-by-Week Schedule` : isSuperleagueResult ? "Superleague Slate: Top 40 Games" : "Expanded Conference Slate: Top 40 Games"}
            </h3>
            {isLeagueResult ? (
              <>
                <ScheduleGrid rows={selectedLeagueRows} />
                <TeamStatsTable rows={selectedLeagueTeamStats} />
              </>
            ) : (
              <ScheduleTable rows={expandedTopRows} />
            )}
          </div>

          <p className="text-gray-500 text-sm mt-6 max-w-3xl leading-relaxed">
            Method: {simulation.methodology}
          </p>
        </div>
      )}
    </>
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

function SummaryCard({ title, teams, games, total, average }) {
  return (
    <div className="scenario-summary-card">
      <h3 className="text-xl font-semibold mb-4">{title}</h3>
      <table>
        <tbody>
          <tr>
            <td>Teams</td>
            <td>{teams || 0}</td>
          </tr>
          <tr>
            <td>Games</td>
            <td>{games || 0}</td>
          </tr>
          <tr>
            <td>Total Viewers</td>
            <td>{formatViewers(total)}</td>
          </tr>
          <tr>
            <td>Average Viewers</td>
            <td>{formatViewers(average)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ScheduleGrid({ rows }) {
  if (!rows?.length) {
    return <p className="text-gray-600">No games generated.</p>;
  }

  const weeks = Array.from(
    { length: Math.max(13, ...rows.map((row) => Number(row.week || 0))) },
    (_, idx) => idx + 1
  );
  const gridSlot = (row) => {
    const slot = row.time_slot || "No national TV window";
    return slot.includes("Black Friday") ? "Friday" : slot;
  };
  const discoveredSlots = Array.from(new Set(rows.map(gridSlot)));
  const timeSlots = [
    ...SCHEDULE_TIME_SLOT_ORDER.filter((slot) => discoveredSlots.includes(slot)),
    ...discoveredSlots
      .filter((slot) => !SCHEDULE_TIME_SLOT_ORDER.includes(slot))
      .sort((a, b) => a.localeCompare(b)),
  ];
  const gridRows = timeSlots.map((slot) => ({
    slot,
    weeks: weeks.map((week) => rows
      .filter((row) => Number(row.week) === week && gridSlot(row) === slot)
      .sort((a, b) => {
        if (Boolean(a.nationally_rated) !== Boolean(b.nationally_rated)) {
          return a.nationally_rated ? -1 : 1;
        }
        return Number(b.predicted_viewers || 0) - Number(a.predicted_viewers || 0);
      })),
  }));

  return (
    <div className="schedule-grid-wrap">
      <div className="schedule-grid" style={{ gridTemplateColumns: `156px repeat(${weeks.length}, minmax(146px, 1fr))` }}>
        <div className="schedule-grid-corner">Window</div>
        {weeks.map((week) => (
          <div className="schedule-grid-week" key={`week-${week}`}>
            Week {week}
          </div>
        ))}
        {gridRows.map(({ slot, weeks: weekCells }) => (
          <Fragment key={slot}>
            <div className="schedule-grid-slot" key={`${slot}-label`}>
              {slot}
            </div>
            {weekCells.map((games, idx) => (
              <div className="schedule-grid-cell" key={`${slot}-week-${weeks[idx]}`}>
                {games.map((game) => (
                  <div
                    className={`schedule-grid-game ${game.nationally_rated ? "" : "schedule-grid-game-unrated"}`}
                    key={`${game.game_number}-${game.matchup}-${game.network}-${game.week}`}
                    title={`${game.matchup} | ${game.network} | ${formatViewers(game.predicted_viewers)}`}
                  >
                    <div className="schedule-grid-matchup">
                      {game.matchup}
                      {game.protected && <span className="game-badge">Protected</span>}
                    </div>
                    <div className="schedule-grid-meta">
                      <span>{rankLabel(game.rank1)} / {rankLabel(game.rank2)}</span>
                      <span>{game.network}</span>
                      <span>{game.nationally_rated ? formatViewers(game.predicted_viewers) : "Unrated"}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function buildTeamStats(rows) {
  const stats = new Map();
  const ensureTeam = (team) => {
    if (!stats.has(team)) {
      stats.set(team, {
        team,
        scheduled_games: 0,
        tv_games: 0,
        unrated_games: 0,
        total_viewers: 0,
        average_viewers: 0,
        best_game_viewers: 0,
        best_game: "",
      });
    }
    return stats.get(team);
  };

  (rows || []).forEach((row) => {
    [row.team1, row.team2].filter(Boolean).forEach((team) => {
      const teamRow = ensureTeam(team);
      teamRow.scheduled_games += 1;

      if (row.nationally_rated) {
        const viewers = Number(row.predicted_viewers || 0);
        teamRow.tv_games += 1;
        teamRow.total_viewers += viewers;
        if (viewers > teamRow.best_game_viewers) {
          teamRow.best_game_viewers = viewers;
          teamRow.best_game = row.matchup || `${row.team1} vs ${row.team2}`;
        }
      } else {
        teamRow.unrated_games += 1;
      }
    });
  });

  return Array.from(stats.values())
    .map((row) => ({
      ...row,
      average_viewers: row.tv_games ? row.total_viewers / row.tv_games : 0,
    }))
    .sort((a, b) => {
      if (b.total_viewers !== a.total_viewers) return b.total_viewers - a.total_viewers;
      if (b.average_viewers !== a.average_viewers) return b.average_viewers - a.average_viewers;
      return a.team.localeCompare(b.team);
    });
}

function DistributionMetricsTable({ conference, rows }) {
  if (!rows?.length) {
    return null;
  }

  return (
    <div className="scenario-summary-card mt-6">
      <h3 className="text-xl font-semibold mb-4">{conference} Viewership Distribution</h3>
      <div className="brand-table-wrap">
        <table className="brand-rankings-table realignment-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Current</th>
              <th>Original</th>
              <th>Viewer Delta</th>
              <th>% Change</th>
              <th>Membership Elasticity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>{row.label}</td>
                <td>{formatViewers(row.current_viewers)}</td>
                <td>{formatViewers(row.baseline_viewers)}</td>
                <td>{formatSignedViewers(row.viewer_delta)}</td>
                <td>{formatSignedPercent(row.pct_delta)}</td>
                <td>{formatSignedRatio(row.membership_elasticity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TeamStatsTable({ rows }) {
  if (!rows?.length) {
    return null;
  }

  return (
    <div className="mt-6">
      <h4 className="text-lg font-semibold mb-3">Team Viewership Stats</h4>
      <div className="brand-table-wrap">
        <table className="brand-rankings-table realignment-table">
          <thead>
            <tr>
              <th>Team</th>
              <th>TV Games</th>
              <th>Scheduled</th>
              <th>Unrated</th>
              <th>Total</th>
              <th>Average</th>
              <th>Top Game</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.team}>
                <td>
                  <span className="realignment-team-stat-team">
                    {getTeamLogoUrl(row.team) && (
                      <img
                        alt={`${row.team} logo`}
                        className="realignment-team-stat-logo"
                        src={getTeamLogoUrl(row.team)}
                      />
                    )}
                    <span>{row.team}</span>
                  </span>
                </td>
                <td>{row.tv_games}</td>
                <td>{row.scheduled_games}</td>
                <td>{row.unrated_games}</td>
                <td>{formatViewers(row.total_viewers)}</td>
                <td>{formatViewers(row.average_viewers)}</td>
                <td>
                  {row.best_game ? `${row.best_game} (${formatViewers(row.best_game_viewers)})` : "No rated games"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScheduleTable({ rows, compact = false, showConference = false, showWeek = false }) {
  if (!rows?.length) {
    return <p className="text-gray-600">No games generated.</p>;
  }

  return (
    <div className="brand-table-wrap">
      <table className="brand-rankings-table realignment-table">
        <thead>
          <tr>
            <th>Game</th>
            {showWeek && <th>Week</th>}
            {showConference && <th>Conference</th>}
            <th>Matchup</th>
            <th>Ranks</th>
            <th>Network</th>
            <th>Window</th>
            <th>Projected</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, compact ? 12 : rows.length).map((row) => (
            <tr key={`${row.game_number}-${row.matchup}-${row.network}`}>
              <td>{row.global_game_number || row.game_number}</td>
              {showWeek && <td>{row.week || ""}</td>}
              {showConference && <td>{row.conference || ""}</td>}
              <td>
                <span className="game-label">
                  {row.matchup}
                  {row.protected && <span className="game-badge">Protected</span>}
                </span>
              </td>
              <td>{rankLabel(row.rank1)} / {rankLabel(row.rank2)}</td>
              <td>{row.network}</td>
              <td>{row.time_slot}</td>
              <td>{formatViewers(row.predicted_viewers)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
