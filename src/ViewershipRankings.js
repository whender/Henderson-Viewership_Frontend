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
    network: "all",
    time_bucket: "all",
    rank_bucket: "all",
    opponent: "all",
    min_games: "1",
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
          min_games: filters.min_games === "" ? "1" : filters.min_games,
          network: filters.network,
          time_bucket: filters.time_bucket,
          rank_bucket: filters.rank_bucket,
          opponent: filters.opponent,
          include_conf_champ: String(filters.include_conf_champ),
        });
        const res = await fetch(`${BACKEND_BASE}/team-viewership-rankings?${params.toString()}`);
        const payload = await res.json();
        setData(payload);
      } catch (err) {
        console.error("Viewership rankings load error:", err);
        setError("Failed to load team viewership rankings.");
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
        Rank every FBS team by average and median viewership under the exact TV
        conditions you choose.
      </p>
      <p className="text-gray-500 text-sm mb-6 max-w-4xl">
        Data excludes postseason games.
      </p>

      <div className="scenario-controls mb-6">
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
          label="Opponent"
          value={filters.opponent}
          onChange={(value) => setFilters((prev) => ({ ...prev, opponent: value }))}
          options={data.available_filters?.opponents || ["all"]}
        />
        <div className="scenario-select-block">
          <label className="scenario-select-label">Minimum Games</label>
          <input
            value={filters.min_games}
            onChange={(e) => {
              const value = e.target.value.replace(/[^\d]/g, "");
              setFilters((prev) => ({ ...prev, min_games: value }));
            }}
            inputMode="numeric"
          />
        </div>
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
                <th>Team</th>
                <th>Conference</th>
                <th>Games</th>
                <th>Average Viewership</th>
                <th>Median Viewership</th>
              </tr>
            </thead>
            <tbody>
              {data.rows?.map((row) => (
                <tr key={row.team}>
                  <td>{row.rank}</td>
                  <td>
                    <Link
                      to={`/profiles?team=${encodeURIComponent(row.team)}&sport=football`}
                      className="team-pill team-pill-compact team-profile-link"
                    >
                      {getTeamLogoUrl(row.team) && (
                        <img
                          src={getTeamLogoUrl(row.team)}
                          alt={`${row.team} logo`}
                          className="team-logo"
                        />
                      )}
                      <span>{row.team}</span>
                    </Link>
                  </td>
                  <td>{row.conference}</td>
                  <td>{row.games}</td>
                  <td>{formatMillions(row.average_viewers)}</td>
                  <td>{formatMillions(row.median_viewers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
