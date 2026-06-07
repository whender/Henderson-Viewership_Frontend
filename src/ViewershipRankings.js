import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl } from "./teamLogos";

function formatMillions(value) {
  if (value == null) {
    return "N/A";
  }

  return `${(value / 1000).toFixed(2)}M`;
}

function FilterSelect({ label, value, onChange, options }) {
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

export default function ViewershipRankings() {
  const [filters, setFilters] = useState({
    season: "all",
    conference: "all",
    network: "all",
    time_bucket: "all",
    rank_bucket: "all",
    team: "all",
    include_conf_champ: true,
  });
  const [data, setData] = useState({
    rows: [],
    available_filters: {
      networks: ["all"],
      time_buckets: ["all"],
      rank_buckets: ["all"],
    },
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadRankings() {
      try {
        setLoading(true);
        setError("");

        const params = new URLSearchParams({
          season: filters.season,
          conference: filters.conference,
          network: filters.network,
          time_bucket: filters.time_bucket,
          rank_bucket: filters.rank_bucket,
          team: filters.team,
          include_conf_champ: String(filters.include_conf_champ),
        });
        const res = await fetch(`${BACKEND_BASE}/game-viewership-rankings?${params.toString()}`);
        const payload = await res.json();
        setData(payload);
      } catch (err) {
        console.error("Viewership rankings load error:", err);
        setError("Failed to load game viewership rankings.");
      } finally {
        setLoading(false);
      }
    }

    loadRankings();
  }, [filters]);

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Viewership Rankings</h2>
      <p className="text-gray-600 mb-3 max-w-4xl">
        Rank every rated college football game by viewership, then filter the board
        by season, network, team, rankings, and TV window.
      </p>
      <p className="text-gray-500 text-sm mb-6 max-w-4xl">
        Conference championship games can be included or removed with the filter below.
      </p>

      <div className="scenario-controls mb-6">
        <FilterSelect
          label="Season"
          value={filters.season}
          onChange={(value) => setFilters((prev) => ({ ...prev, season: value }))}
          options={data.available_filters?.seasons || ["all"]}
        />
        <FilterSelect
          label="Conference"
          value={filters.conference}
          onChange={(value) => setFilters((prev) => ({ ...prev, conference: value }))}
          options={data.available_filters?.conferences || ["all"]}
        />
        <FilterSelect
          label="Network"
          value={filters.network}
          onChange={(value) => setFilters((prev) => ({ ...prev, network: value }))}
          options={data.available_filters?.networks || ["all"]}
        />
        <FilterSelect
          label="Time Slot"
          value={filters.time_bucket}
          onChange={(value) => setFilters((prev) => ({ ...prev, time_bucket: value }))}
          options={data.available_filters?.time_buckets || ["all"]}
        />
        <FilterSelect
          label="Rankings"
          value={filters.rank_bucket}
          onChange={(value) => setFilters((prev) => ({ ...prev, rank_bucket: value }))}
          options={data.available_filters?.rank_buckets || ["all"]}
        />
        <FilterSelect
          label="Team"
          value={filters.team}
          onChange={(value) => setFilters((prev) => ({ ...prev, team: value }))}
          options={data.available_filters?.teams || ["all"]}
        />
      </div>
      <div className="mt-3">
        <label className="team-profile-toggle">
          <input
            type="checkbox"
            checked={filters.include_conf_champ}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                include_conf_champ: e.target.checked,
              }))
            }
          />
          Include conference championship games
        </label>
      </div>

      {loading && <p>Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && !error && (
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
                <th>Rankings</th>
                <th>Viewership</th>
              </tr>
            </thead>
            <tbody>
              {data.rows?.map((row) => (
                <tr key={`${row.rank}-${row.season}-${row.date}-${row.matchup}`}>
                  <td>{row.rank}</td>
                  <td>{row.date}</td>
                  <td>{row.season}</td>
                  <td>
                    <span className="matchup-cell">
                      <span className="matchup-logos">
                        {[row.team1, row.team2].map((team) => (
                          getTeamLogoUrl(team) ? (
                            <img
                              key={team}
                              src={getTeamLogoUrl(team)}
                              alt={`${team} logo`}
                              className="team-logo"
                            />
                          ) : null
                        ))}
                      </span>
                      <span>
                        <Link to={`/teams/football/${encodeURIComponent(row.team1)}`} className="team-profile-link">
                          {row.team1}
                        </Link>
                        {" vs "}
                        <Link to={`/teams/football/${encodeURIComponent(row.team2)}`} className="team-profile-link">
                          {row.team2}
                        </Link>
                        {row.conference_championship && <span className="game-badge">Conf Champ</span>}
                      </span>
                    </span>
                  </td>
                  <td>{row.network}</td>
                  <td>{row.raw_time_slot || row.time_slot}</td>
                  <td>{row.rank_bucket}</td>
                  <td>{formatMillions(row.viewers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
