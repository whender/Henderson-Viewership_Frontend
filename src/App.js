import { useEffect, useState } from "react";
import WeeklyPredictions from "./WeeklyPredictions";
import "./App.css";

const BACKEND_BASE = "https://henderson-viewership-backend.onrender.com";

export default function App() {
  const [activeTab, setActiveTab] = useState("predictor");

  // Predictor State
  const [teams, setTeams] = useState([]);
  const [team1, setTeam1] = useState("");
  const [team2, setTeam2] = useState("");
  const [rank1, setRank1] = useState(0);
  const [rank2, setRank2] = useState(0);
  const [spread, setSpread] = useState("");
  const [network, setNetwork] = useState("");
  const [timeSlot, setTimeSlot] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [compTier1, setCompTier1] = useState(0);

  // Brand Rankings
  const [brandYears, setBrandYears] = useState([]);
  const [brandYear, setBrandYear] = useState("all");
  const [brandRows, setBrandRows] = useState([]);
  const [brandLoading, setBrandLoading] = useState(false);
  const [brandError, setBrandError] = useState("");

  // Fetch Brand Rankings
  async function fetchBrandRankings(yearValue) {
    try {
      setBrandLoading(true);
      setBrandError("");

      let url = `${BACKEND_BASE}/brand-rankings`;
      if (yearValue !== "all") url += `?year=${yearValue}`;

      const res = await fetch(url);
      const data = await res.json();
      setBrandRows(data.rows || []);
    } catch (err) {
      console.error("Brand load error:", err);
      setBrandError("Failed to load brand rankings.");
    } finally {
      setBrandLoading(false);
    }
  }

  // Initial Load
  useEffect(() => {
    fetch(`${BACKEND_BASE}/teams`)
      .then((res) => res.json())
      .then((data) => setTeams(data.teams || []));

    fetch(`${BACKEND_BASE}/brand-years`)
      .then((res) => res.json())
      .then((data) => setBrandYears(data.years || []));

    fetchBrandRankings("all");
  }, []);

  // Prediction Handler
  async function handlePredict() {
    const body = {
      team1,
      team2,
      rank1,
      rank2,
      spread: spread === "" ? 0 : Number(spread),
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

  // Spread Input Validation
  function handleSpreadInput(val) {
    if (val === "") return setSpread("");
    if (!/^\d*\.?\d*$/.test(val)) return;
    if (val.endsWith(".")) return setSpread(val);
    if (/^\d+\.$/.test(val)) return setSpread(val.slice(0, -1));
    if (val.includes(".")) {
      const parts = val.split(".");
      if (parts[1] !== "5") return;
      return setSpread(val);
    }
    setSpread(val);
  }

  return (
    <div className="min-h-screen bg-main flex flex-col">
      <div className="flex-1 px-10 py-12">

        {/* Title */}
        <h1 className="text-4xl font-semibold mb-2">
          Will Henderson — College Football Viewership Model
        </h1>
        <p className="text-gray-600 mb-8">
          Predict hypothetical TV audiences using a trained statistical model.
        </p>

        {/* ---------------------------------------------------------
            Responsive Navigation
        ---------------------------------------------------------- */}

        {/* Mobile Dropdown */}
        <div className="mb-10 md:hidden">
          <select
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value)}
            className="w-full p-3 bg-gray-100 border border-gray-300 rounded"
          >
            <option value="predictor">Game Predictor</option>
            <option value="brands">Brand Rankings</option>
            <option value="weekly">Weekly Predictions</option>
            <option value="model">Model Explanation</option>
          </select>
        </div>

        {/* Desktop Tabs */}
        <div className="hidden md:flex space-x-6 mb-10 text-lg font-medium">
          {[
            ["predictor", "GAME PREDICTOR"],
            ["brands", "BRAND RANKINGS"],
            ["weekly", "WEEKLY PREDICTIONS"],
            ["model", "MODEL EXPLANATION"],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={
                "tab-btn " + (activeTab === key ? "tab-btn-active" : "")
              }
            >
              {label}
            </button>
          ))}
        </div>

        {/* ---------------------------------------------------------
            TAB: GAME PREDICTOR
        ---------------------------------------------------------- */}
        {activeTab === "predictor" && (
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
              <label>Betting Spread (ex: "2.5")</label>
              <input
                value={spread}
                onChange={(e) => {
                  handleSpreadInput(e.target.value);
                  setPrediction(null);
                }}
                placeholder="Enter spread"
              />
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

                {/* Info Button */}
                <div className="relative group cursor-pointer">
                  <span className="info-icon">i</span>

                  {/* Tooltip */}
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

                <p className="text-gray-600 text-lg">
                  {team1 && team2 ? `${team1} vs ${team2}` : ""}
                  {network ? ` | ${network}` : ""}
                  {timeSlot ? ` | ${timeSlot}` : ""}
                </p>
              </div>
            )}
          </>
        )}

        {/* ---------------------------------------------------------
             TAB: BRAND POWER
        ---------------------------------------------------------- */}
        {activeTab === "brands" && (
          <>
            <h2 className="text-3xl font-semibold mb-4">
              Brand Pull Rankings
            </h2>
            <p className="text-gray-500 italic mb-6">
              These rankings use Nielsen viewership data and supporting metadata from over 2,000 college football games since 2018. 
              Lift % shows how much a team increases expected TV viewership, compared to a neutral baseline team, independent of structural variables like network, time-slot, opponent, rankings, and competing games.
            </p>

            <div className="mb-6">
              <label className="mr-2">Select Year</label>
              <select
                value={brandYear}
                onChange={(e) => {
                  setBrandYear(e.target.value);
                  fetchBrandRankings(e.target.value);
                }}
              >
                <option value="all">All Years</option>
                {brandYears.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </div>

            {brandLoading && <p>Loading…</p>}
            {brandError && <p className="text-red-600">{brandError}</p>}

            {!brandLoading && !brandError && (
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Team</th>
                    <th>Lift (%)</th>
                    <th>Games Used</th>
                  </tr>
                </thead>
                <tbody>
                  {brandRows.map((row) => (
                    <tr key={row.team}>
                      <td>{row.rank}</td>
                      <td>{row.team}</td>
                      <td>{row.viewership_lift_pct.toFixed(1)}</td>
                      <td>{row.games_used}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="text-gray-500 text-sm mt-8 leading-relaxed max-w-3xl">
              <strong>What is Lift %?</strong><br />
              Lift % measures a team’s intrinsic drawing power on national television. The
              model controls for network, time slot, rankings, rivalry status, competitiveness,
              and competing games, isolating only the brand effect. A Lift % of +150%, for
              example, means adding that team to a neutral baseline matchup would be expected
              to increase viewership by 150% (i.e., multiply the audience by 2.5×). Higher Lift %
              values therefore represent stronger national brands that consistently attract
              larger TV audiences.
            </p>
          </>
        )}

        {/* ---------------------------------------------------------
             TAB: WEEKLY PREDICTIONS
        ---------------------------------------------------------- */}
        {activeTab === "weekly" && <WeeklyPredictions />}

        {/* ---------------------------------------------------------
             TAB: MODEL EXPLANATION
        ---------------------------------------------------------- */}
        {activeTab === "model" && (
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
        )}
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