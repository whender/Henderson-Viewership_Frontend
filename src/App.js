import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import WeeklyPredictions from "./WeeklyPredictions";
import TeamProfiles from "./TeamProfiles";
import ViewershipRankings from "./ViewershipRankings";
import {
  BasketballModelExplanation,
  BasketballPredictor,
  BasketballProfiles,
  BasketballViewershipRankings,
} from "./BasketballDashboard";
import BACKEND_BASE from "./config";
import { getTeamLogoUrl } from "./teamLogos";
import "./App.css";

const NAV_ITEMS = [
  ["predictor", "/predictor", "GAME PREDICTOR"],
  ["brands", "/brands", "BRAND RANKINGS"],
  ["viewership-rankings", "/viewership-rankings", "VIEWERSHIP RANKINGS"],
  ["comparison", "/comparison", "COMPARISON"],
  ["weekly", "/weekly", "WEEKLY PREDICTIONS"],
  ["model", "/model", "MODEL EXPLANATION"],
];

const SPORT_COPY = {
  football: {
    label: "College Football",
    title: "Will Henderson — College Football Viewership Model",
    description: "Predict hypothetical TV audiences using a trained statistical model.",
  },
  basketball: {
    label: "College Basketball",
    title: "Will Henderson — College Basketball Viewership Model",
    description: "Predict hypothetical TV audiences using the basketball version of the same model framework.",
  },
};

function useActiveTab() {
  const location = useLocation();
  const active = NAV_ITEMS.find(([, path]) => (
    location.pathname === path || (path !== "/" && location.pathname.startsWith(`${path}/`))
  ));
  return active?.[0] || "";
}

export default function App() {
  const activeTab = useActiveTab();
  const navigate = useNavigate();
  const [sport, setSport] = useState(() => localStorage.getItem("henderson-viewership-sport") || "football");
  const isBasketball = sport === "basketball";
  const sportCopy = SPORT_COPY[sport] || SPORT_COPY.football;

  const [teams, setTeams] = useState([]);
  const [team1, setTeam1] = useState("");
  const [team2, setTeam2] = useState("");
  const [rank1, setRank1] = useState(0);
  const [rank2, setRank2] = useState(0);
  const [network, setNetwork] = useState("");
  const [timeSlot, setTimeSlot] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [compTier1, setCompTier1] = useState(0);

  const [brandYears, setBrandYears] = useState([]);
  const [brandYear, setBrandYear] = useState("all");
  const [brandScope, setBrandScope] = useState("combined");
  const [brandControlDeion, setBrandControlDeion] = useState(false);
  const [brandConference, setBrandConference] = useState("all");
  const [brandRows, setBrandRows] = useState([]);
  const [brandMetadata, setBrandMetadata] = useState(null);
  const [brandLoading, setBrandLoading] = useState(false);
  const [brandError, setBrandError] = useState("");
  const [basketballTeams, setBasketballTeams] = useState([]);
  const [basketballFilters, setBasketballFilters] = useState(null);
  const [basketballMetadata, setBasketballMetadata] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedSport = params.get("sport");
    if (requestedSport === "football" || requestedSport === "basketball") {
      setSport(requestedSport);
      localStorage.setItem("henderson-viewership-sport", requestedSport);
    }
  }, [activeTab]);

  function handleSportChange(nextSport) {
    setSport(nextSport);
    localStorage.setItem("henderson-viewership-sport", nextSport);
  }

  async function fetchBrandRankings(
    yearValue = brandYear,
    scopeValue = brandScope,
    controlDeionValue = brandControlDeion
  ) {
    try {
      setBrandLoading(true);
      setBrandError("");

      const params = new URLSearchParams({ scope: scopeValue });
      if (controlDeionValue && scopeValue !== "basketball") {
        params.set("control_deion", "true");
      }
      if (yearValue !== "all") {
        params.set("year", yearValue);
      }

      const res = await fetch(`${BACKEND_BASE}/brand-rankings?${params.toString()}`);
      const data = await res.json();
      setBrandRows(data.rows || []);
      setBrandMetadata(data.metadata || null);
    } catch (err) {
      console.error("Brand load error:", err);
      setBrandError("Failed to load brand rankings.");
    } finally {
      setBrandLoading(false);
    }
  }

  const filteredBrandRows = useMemo(
    () => brandRows.filter((row) => (brandConference === "all" ? true : row.conference === brandConference)),
    [brandRows, brandConference]
  );

  const brandConferenceOptions = useMemo(
    () => [
      "all",
      ...new Set(
        brandRows
          .map((row) => row.conference)
          .filter(Boolean)
          .sort((a, b) => a.localeCompare(b))
      ),
    ],
    [brandRows]
  );

  useEffect(() => {
    fetch(`${BACKEND_BASE}/teams`)
      .then((res) => res.json())
      .then((data) => setTeams(data.teams || []));

    fetch(`${BACKEND_BASE}/brand-years`)
      .then((res) => res.json())
      .then((data) => setBrandYears(data.years || []));

    fetchBrandRankings("all");

    fetch(`${BACKEND_BASE}/cbb/teams`)
      .then((res) => res.json())
      .then((data) => setBasketballTeams(data.teams || []));

    fetch(`${BACKEND_BASE}/cbb/filters`)
      .then((res) => res.json())
      .then(setBasketballFilters);

    fetch(`${BACKEND_BASE}/cbb/metadata`)
      .then((res) => res.json())
      .then(setBasketballMetadata);
  }, []);

  async function handlePredict() {
    const body = {
      team1,
      team2,
      rank1,
      rank2,
      network,
      time_slot: timeSlot,
      comp_tier1: compTier1,
    };

    try {
      const res = await fetch(`${BACKEND_BASE}/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      setPrediction(data.prediction_formatted);
    } catch (err) {
      console.error("Prediction error:", err);
    }
  }

  return (
    <div className="min-h-screen bg-main flex flex-col">
      <div className="flex-1 px-10 py-12">
        <div className="dashboard-topbar">
          <div>
            <h1 className="text-4xl font-semibold mb-2">
              {sportCopy.title}
            </h1>
            <p className="text-gray-600 mb-8">
              {sportCopy.description}
            </p>
          </div>

          <div className="sport-toggle" aria-label="Sport selector">
            {["football", "basketball"].map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => handleSportChange(option)}
                className={sport === option ? "sport-toggle-active" : ""}
              >
                {SPORT_COPY[option].label.replace("College ", "")}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-10 md:hidden">
          <select
            value={activeTab}
            onChange={(e) => {
              const target = NAV_ITEMS.find(([key]) => key === e.target.value);
              if (target) {
                navigate(target[1]);
              }
            }}
            className="w-full p-3 bg-gray-100 border border-gray-300 rounded"
          >
            {!activeTab && <option value="">Team Profile</option>}
            {NAV_ITEMS.map(([key, , label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div className="hidden md:flex space-x-6 mb-10 text-lg font-medium">
          {NAV_ITEMS.map(([key, path, label]) => (
            <Link
              key={key}
              to={path}
              className={"tab-btn " + (activeTab === key ? "tab-btn-active" : "")}
            >
              {label}
            </Link>
          ))}
        </div>

        <Routes>
          <Route
            path="/"
            element={<Navigate to="/predictor" replace />}
          />
          <Route
            path="/predictor"
            element={
              isBasketball ? (
                <BasketballPredictor teams={basketballTeams} filters={basketballFilters} />
              ) : (
                <PredictorPage
                  teams={teams}
                  team1={team1}
                  setTeam1={setTeam1}
                  team2={team2}
                  setTeam2={setTeam2}
                  rank1={rank1}
                  setRank1={setRank1}
                  rank2={rank2}
                  setRank2={setRank2}
                  network={network}
                  setNetwork={setNetwork}
                  timeSlot={timeSlot}
                  setTimeSlot={setTimeSlot}
                  prediction={prediction}
                  setPrediction={setPrediction}
                  compTier1={compTier1}
                  setCompTier1={setCompTier1}
                  handlePredict={handlePredict}
                />
              )
            }
          />
          <Route
            path="/brands"
            element={
              <BrandRankingsPage
                brandYear={brandYear}
                setBrandYear={setBrandYear}
                brandYears={brandYears}
                brandScope={brandScope}
                setBrandScope={setBrandScope}
                brandControlDeion={brandControlDeion}
                setBrandControlDeion={setBrandControlDeion}
                brandMetadata={brandMetadata}
                brandConference={brandConference}
                setBrandConference={setBrandConference}
                brandConferenceOptions={brandConferenceOptions}
                brandLoading={brandLoading}
                brandError={brandError}
                filteredBrandRows={filteredBrandRows}
                fetchBrandRankings={fetchBrandRankings}
              />
            }
          />
          <Route
            path="/viewership-rankings"
            element={isBasketball ? <BasketballViewershipRankings filters={basketballFilters} /> : <ViewershipRankings />}
          />
          <Route
            path="/profiles"
            element={isBasketball ? <BasketballProfiles teams={basketballTeams} /> : <TeamProfiles teams={teams} />}
          />
          <Route
            path="/comparison"
            element={isBasketball ? <BasketballProfiles teams={basketballTeams} comparisonOnly /> : <TeamProfiles teams={teams} comparisonOnly />}
          />
          <Route path="/weekly" element={isBasketball ? <BasketballWeeklyPage /> : <WeeklyPredictions />} />
          <Route path="/model" element={isBasketball ? <BasketballModelExplanation metadata={basketballMetadata} /> : <ModelExplanationPage />} />
          <Route path="*" element={<Navigate to="/predictor" replace />} />
        </Routes>
      </div>

      <footer className="mt-20 py-6 border-t text-center text-gray-600 text-sm">
        <p>
          Created by <span className="font-semibold">Will Henderson</span>
        </p>
        <p className="mt-1">
          📧 wshenderson7@gmail.com • 𝕏 @willshenderson7
        </p>
      </footer>
    </div>
  );
}

function PredictorPage({
  teams,
  team1,
  setTeam1,
  team2,
  setTeam2,
  rank1,
  setRank1,
  rank2,
  setRank2,
  network,
  setNetwork,
  timeSlot,
  setTimeSlot,
  prediction,
  setPrediction,
  compTier1,
  setCompTier1,
  handlePredict,
}) {
  return (
    <>
      <h2 className="text-3xl font-semibold mb-4">Game Predictor</h2>

      <div className="grid grid-cols-2 gap-8 mb-10">
        <div>
          <label>Team 1</label>
          <select
            value={team1}
            onChange={(e) => {
              setTeam1(e.target.value);
              setPrediction(null);
            }}
          >
            <option value="">Select a team</option>
            {teams.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>Team 2</label>
          <select
            value={team2}
            onChange={(e) => {
              setTeam2(e.target.value);
              setPrediction(null);
            }}
          >
            <option value="">Select a team</option>
            {teams.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 mb-10">
        <div>
          <label>Team 1 Rank (1-25)</label>
          <input
            value={rank1 === 0 ? "" : rank1}
            onChange={(e) => {
              const v = e.target.value.trim();
              if (v === "") return setRank1(0);
              if (/^\d+$/.test(v)) {
                const n = Number(v);
                if (n >= 1 && n <= 25) setRank1(n);
              }
              setPrediction(null);
            }}
            placeholder="Unranked"
          />
        </div>

        <div>
          <label>Team 2 Rank (1-25)</label>
          <input
            value={rank2 === 0 ? "" : rank2}
            onChange={(e) => {
              const v = e.target.value.trim();
              if (v === "") return setRank2(0);
              if (/^\d+$/.test(v)) {
                const n = Number(v);
                if (n >= 1 && n <= 25) setRank2(n);
              }
              setPrediction(null);
            }}
            placeholder="Unranked"
          />
        </div>
      </div>

      <div className="mb-8">
        <label>Network</label>
        <select
          value={network}
          onChange={(e) => {
            setNetwork(e.target.value);
            setPrediction(null);
          }}
        >
          <option value="">Select Network</option>
          {[
            "ABC", "CBS", "NBC", "FOX",
            "ESPN", "ESPN2", "ESPNU",
            "FS1", "FS2", "BTN", "CW", "NFLN", "ESPNNEWS",
          ].map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
      </div>

      <div className="mb-8">
        <label>Time Slot (EST)</label>
        <select
          value={timeSlot}
          onChange={(e) => {
            setTimeSlot(e.target.value);
            setPrediction(null);
          }}
        >
          <option value="">Select Time Slot</option>
          <option value="Primetime (7:00p–9:00p)">Primetime (7:00p-9:00p EST)</option>
          <option value="Sunday">Sunday</option>
          <option value="Monday">Monday</option>
          <option value="Weekday (Tue–Thu)">Weekday</option>
          <option value="Friday">Friday</option>
          <option value="Sat Early (11:00a–2:00p)">Sat Early (11:00a-2:00p EST)</option>
          <option value="Sat Mid (2:30p–6:30p)">Sat Mid (2:30p-6:30p EST)</option>
          <option value="Sat Late (9:30p–11:30p)">Sat Late (9:30p-12:00a EST)</option>
        </select>
      </div>

      <div className="mb-8">
        <label className="flex items-center space-x-2">
          <span>Major Competing Games</span>
          <div className="relative group cursor-pointer">
            <span className="info-icon">i</span>
            <div className="absolute hidden group-hover:block bg-black text-white text-xs rounded p-2 w-64 -left-2 mt-1 shadow-lg z-50">
              A “major competing game” is another nationally relevant, high-profile matchup airing in the same time window that could pull viewers away from your game.
            </div>
          </div>
        </label>

        <input
          value={compTier1 === 0 ? "" : compTier1}
          onChange={(e) => {
            const v = e.target.value.trim();
            if (v === "") return setCompTier1(0);
            if (/^\d+$/.test(v)) {
              const n = Number(v);
              if (n >= 0 && n <= 10) setCompTier1(n);
            }
            setPrediction(null);
          }}
          placeholder="None"
        />
      </div>

      <button onClick={handlePredict} className="btn-primary">
        Predict Viewership
      </button>

      {prediction && (
        <div className="text-center mt-12">
          <h2 className="text-3xl font-bold mb-2">
            Predicted Viewers: {prediction}
          </h2>

          <div className="team-pill-row">
            {[team1, team2].filter(Boolean).map((team) => (
              <TeamPill key={team} team={team} />
            ))}
          </div>

          <p className="text-gray-600 text-lg">
            {team1 && team2 ? `${team1} vs ${team2}` : ""}
            {network ? ` | ${network}` : ""}
            {timeSlot ? ` | ${timeSlot}` : ""}
          </p>
        </div>
      )}
    </>
  );
}

function BrandRankingsPage({
  brandYear,
  setBrandYear,
  brandYears,
  brandScope,
  setBrandScope,
  brandControlDeion,
  setBrandControlDeion,
  brandMetadata,
  brandConference,
  setBrandConference,
  brandConferenceOptions,
  brandLoading,
  brandError,
  filteredBrandRows,
  fetchBrandRankings,
}) {
  return (
    <>
      <h2 className="text-3xl font-semibold mb-4">
        Media Rights Brand Rankings
      </h2>
      <p className="text-gray-500 italic mb-6">
        The main ranking combines football and men’s basketball brand pull into a media-rights index.
        Football receives 85% of the weight and basketball receives 15%, with each sport normalized
        from its shrinkage-adjusted team effect.
      </p>
      <p className="text-gray-500 text-sm mb-6">
        Combined index: 100 is average; each 15 points is roughly one standard deviation of combined media-rights brand value.
      </p>

      <div className="scenario-controls mb-6">
        <label className="brand-filter-card">
          <span className="brand-filter-label">Ranking</span>
          <select
            className="brand-filter-select"
            value={brandScope}
            onChange={(e) => {
              const nextScope = e.target.value;
              setBrandScope(nextScope);
              setBrandConference("all");
              if (nextScope !== "football") {
                setBrandYear("all");
                fetchBrandRankings("all", nextScope, brandControlDeion);
              } else {
                fetchBrandRankings(brandYear, nextScope, brandControlDeion);
              }
            }}
          >
            <option value="combined">Combined Media Index</option>
            <option value="football">Football Only</option>
            <option value="basketball">Basketball Only</option>
          </select>
        </label>
        {brandScope === "football" && (
          <label className="brand-filter-card">
            <span className="brand-filter-label">Year</span>
            <select
              className="brand-filter-select"
              value={brandYear}
              onChange={(e) => {
                setBrandYear(e.target.value);
                fetchBrandRankings(e.target.value, brandScope, brandControlDeion);
              }}
            >
              <option value="all">All Years</option>
              {brandYears.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </label>
        )}
        <label className="brand-filter-card">
          <span className="brand-filter-label">Conference</span>
          <select
            className="brand-filter-select"
            value={brandConference}
            onChange={(e) => setBrandConference(e.target.value)}
          >
            {brandConferenceOptions.map((conference) => (
              <option key={conference} value={conference}>
                {conference === "all" ? "All Conferences" : conference}
              </option>
            ))}
          </select>
        </label>
        {brandScope !== "basketball" && brandYear === "all" && (
          <label className={`brand-deion-toggle ${brandControlDeion ? "brand-deion-toggle-active" : ""}`}>
            <input
              type="checkbox"
              checked={brandControlDeion}
              onChange={(e) => {
                const nextValue = e.target.checked;
                setBrandControlDeion(nextValue);
                fetchBrandRankings(brandYear, brandScope, nextValue);
              }}
            />
            <span className="brand-deion-switch" aria-hidden="true">
              <span />
            </span>
            <span className="brand-deion-copy">
              <span>Colorado Deion Control</span>
              <small>{brandControlDeion ? "Adjusted" : "Included"}</small>
            </span>
          </label>
        )}
      </div>

      {brandMetadata?.scope === "combined" && (
        <p className="text-gray-500 text-sm mb-6 max-w-3xl leading-relaxed">
          Weights: {(brandMetadata.football_weight * 100).toFixed(0)}% football /
          {" "}{(brandMetadata.basketball_weight * 100).toFixed(0)}% men’s basketball.
          Schools without football data receive the bottom football score in the combined index.
        </p>
      )}
      {brandMetadata?.control_deion && (
        <p className="text-gray-500 text-sm mb-6 max-w-3xl leading-relaxed">
          Colorado’s football brand score is adjusted to remove the weighted Deion-era lift
          estimated by the football model.
        </p>
      )}

      {brandScope === "football" && (
        <p className="text-gray-500 text-sm mb-6 max-w-3xl leading-relaxed">
          Single-year brand estimates are noisier than the all-years ranking. Smaller samples,
          unusual schedules, and one-season matchup context can move a team’s yearly lift more
          than its long-run underlying brand strength.
        </p>
      )}

      {/*
      <div className="mb-6">
        <label className="mr-2">Select Year</label>
        <select
          value={brandYear}
          onChange={(e) => {
            setBrandYear(e.target.value);
            fetchBrandRankings(e.target.value, brandScope);
          }}
        >
          <option value="all">All Years</option>
          {brandYears.map((y) => (
            <option key={y}>{y}</option>
          ))}
        </select>
      </div>
      */}

      {brandLoading && <p>Loading…</p>}
      {brandError && <p className="text-red-600">{brandError}</p>}

      {!brandLoading && !brandError && (
        <div className="brand-table-wrap">
          <table className="brand-rankings-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Team</th>
                <th>Conference</th>
                {brandScope === "combined" ? (
                  <>
                    <th>Media Index</th>
                    <th>Football</th>
                    <th>Basketball</th>
                    <th>Primary Driver</th>
                    <th>Games</th>
                  </>
                ) : (
                  <>
                    <th>Lift (%)</th>
                    <th>Games Used</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {filteredBrandRows.map((row) => (
                <tr key={row.team}>
                  <td>{row.rank}</td>
                  <td>
                    <TeamPill
                      team={row.team}
                      compact
                      profileSport={getProfileSportForBrandRow(row, brandScope)}
                    />
                  </td>
                  <td>{row.conference}</td>
                  {brandScope === "combined" ? (
                    <>
                      <td>{row.media_brand_index?.toFixed(1)}</td>
                      <td>{formatLiftCell(row.football_lift_pct)}</td>
                      <td>{formatLiftCell(row.basketball_lift_pct)}</td>
                      <td>{row.primary_driver}</td>
                      <td>{row.football_games} FB / {row.basketball_games} CBB</td>
                    </>
                  ) : (
                    <>
                      <td>{Number(row.viewership_lift_pct || 0).toFixed(1)}</td>
                      <td>{row.games_used}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-gray-500 text-sm mt-8 leading-relaxed max-w-3xl">
        <strong>How to read this:</strong><br />
        The combined score is meant to approximate media-rights brand value, where football
        drives most of the economics and basketball adds secondary value. The sport-only views
        still show each model’s isolated lift against its own sport baseline.
      </p>
    </>
  );
}

function formatLiftCell(liftPct) {
  if (liftPct == null) return "No data";
  return `${Number(liftPct).toFixed(1)}%`;
}

function BasketballWeeklyPage() {
  return (
    <div className="card" style={{ maxWidth: "860px", lineHeight: 1.6 }}>
      <h2 className="text-3xl font-semibold mb-4">Weekly Predictions</h2>
      <p className="text-gray-600 mb-4">
        The basketball model is active, but weekly basketball schedule predictions
        are not wired to a schedule feed yet.
      </p>
      <p className="text-gray-600">
        Use the Game Predictor tab for individual basketball matchups, or switch
        back to football to view the existing weekly football predictions.
      </p>
    </div>
  );
}

function ModelExplanationPage() {
  return (
    <div className="card" style={{ maxWidth: "860px", lineHeight: 1.6 }}>
      <h2 className="text-3xl font-semibold mb-4">Model Explanation</h2>

      <p className="text-gray-600 mb-4">
        This viewership model uses several years of college football TV ratings
        to estimate how many people would watch a hypothetical matchup.
      </p>

      <p className="text-gray-600 mb-4">
        The core idea is simple: certain factors consistently influence TV
        audiences. These include team brand power, rankings, network,
        time slot, rivalry status, and the quality of competing games at the
        same time. The model learns how much each of these variables has
        historically moved viewership up or down.
      </p>

      <p className="text-gray-600 mb-4">
        To do this accurately, the model uses a statistical technique called
        “log-transformed regression,” which helps stabilize variance and
        makes predictions more reliable. After the model makes a prediction
        in log-space, a correction called “smearing” is applied so the
        numbers match real-world viewer counts.
      </p>

      <p className="text-gray-600 mb-4">
        Rankings and conferences help quantify team quality. Network
        indicators represent the impact of national TV exposure. Time-slot
        flags (e.g., Primetime, Friday, Saturday Early) capture when people
        tend to watch more or less football. Rivalry indicators tell the model
        when to expect major viewership spikes that don’t depend on record.
      </p>

      <p className="text-gray-600 mb-4">
        Finally, the model calculates a confidence interval, offering a
        reasonable upper and lower range to show uncertainty around each
        prediction. While no model is perfect, this approach provides a
        consistent, transparent, and data-driven way to forecast viewership.
      </p>
    </div>
  );
}

function getProfileSportForBrandRow(row, brandScope) {
  if (brandScope === "basketball") {
    return "basketball";
  }
  if (brandScope === "football") {
    return "football";
  }
  return (row.football_games || 0) > 0 ? "football" : "basketball";
}

function TeamPill({ team, compact = false, profileSport = null }) {
  const logoUrl = getTeamLogoUrl(team);
  const content = (
    <>
      {logoUrl && <img src={logoUrl} alt={`${team} logo`} className="team-logo" />}
      <span>{team}</span>
    </>
  );

  if (profileSport) {
    return (
      <Link
        to={`/profiles?team=${encodeURIComponent(team)}&sport=${profileSport}`}
        className={`team-pill team-profile-link ${compact ? "team-pill-compact" : ""}`}
      >
        {content}
      </Link>
    );
  }

  return <span className={`team-pill ${compact ? "team-pill-compact" : ""}`}>{content}</span>;
}
