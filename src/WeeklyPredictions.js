import { useEffect, useState } from "react";

const BACKEND_BASE = "https://henderson-viewership-backend.onrender.com";

export default function WeeklyPredictions() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [weeks, setWeeks] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [openWeek, setOpenWeek] = useState(null);

  async function loadWeekly() {
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_BASE}/weekly-predictions`);
      const data = await res.json();

      setWeeks(data.weeks || []);
      setMetrics(data.metrics || null);

      if (data.weeks && data.weeks.length > 0) {
        setOpenWeek(data.weeks[0].week);
      }
    } catch (e) {
      console.error(e);
      setError("Failed to load weekly predictions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWeekly();
  }, []);

  if (loading) return <p>Loading weekly predictions…</p>;
  if (error) return <p className="text-red-600">{error}</p>;

  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Weekly Predictions</h2>

      {/* === Summary Metrics (Pregame + Postgame) === */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-10">
          {/* Pregame */}
          <div>
            <h3 className="text-xl font-semibold mb-2">Pregame Model</h3>
            <div className="grid grid-cols-4 gap-6">
              <Metric label="Median % Error" value={`${metrics.pregame.median_error.toFixed(1)}%`} />
              <Metric label="Mean % Error" value={`${metrics.pregame.mean_error.toFixed(1)}%`} />
              <Metric label="Within 10%" value={`${metrics.pregame.pct_within_10}%`} />
              <Metric label="Within 25%" value={`${metrics.pregame.pct_within_25}%`} />
            </div>
          </div>

          {/* Postgame */}
          <div>
            <h3 className="text-xl font-semibold mb-2">Postgame Model</h3>
            <div className="grid grid-cols-4 gap-6">
              <Metric label="Median % Error" value={`${metrics.postgame.median_error.toFixed(1)}%`} />
              <Metric label="Mean % Error" value={`${metrics.postgame.mean_error.toFixed(1)}%`} />
              <Metric label="Within 10%" value={`${metrics.postgame.pct_within_10}%`} />
              <Metric label="Within 25%" value={`${metrics.postgame.pct_within_25}%`} />
            </div>
          </div>
        </div>
      )}

      {/* === Week Sections === */}
      {weeks.map((week) => (
        <div key={week.week} className="mb-6 border rounded overflow-hidden">

          {/* Week Header */}
          <button
            onClick={() =>
              setOpenWeek(openWeek === week.week ? null : week.week)
            }
            className="w-full text-left p-4 bg-gray-100 hover:bg-gray-200 font-semibold"
          >
            Week {week.week} {week.year ? `(${week.year})` : ""}
          </button>

          {openWeek === week.week && (
            <div className="overflow-x-auto">
              <table className="min-w-max w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="p-2 text-left">Date</th>
                    <th className="p-2 text-left">Time</th>
                    <th className="p-2 text-left">Matchup</th>
                    <th className="p-2 text-left">Spread</th>
                    <th className="p-2 text-left">Network</th>

                    {/* Pregame */}
                    <th className="p-2 text-left">Pregame Pred</th>
                    <th className="p-2 text-left">% Error (Pre)</th>
                    <th className="p-2 text-left">Accuracy (Pre)</th>

                    {/* Postgame */}
                    <th className="p-2 text-left">Postgame Pred</th>
                    <th className="p-2 text-left">% Error (Post)</th>
                    <th className="p-2 text-left">Accuracy (Post)</th>

                    <th className="p-2 text-left">Actual</th>
                  </tr>
                </thead>

                <tbody>
                  {week.games.map((g, i) => (
                    <tr key={i} className="border-b">
                      <td className="p-2">{g.date}</td>
                      <td className="p-2">{g.time_slot}</td>
                      <td className="p-2">{g.matchup}</td>
                      <td className="p-2">{g.spread}</td>
                      <td className="p-2">{g.network}</td>

                      {/* Pregame */}
                      <td className="p-2">{g.predicted}</td>
                      <td className={`p-2 ${colorClass(g.percent_error)}`}>
                        {g.percent_error != null ? `${g.percent_error.toFixed(1)}%` : ""}
                      </td>
                      <td className="p-2">{g.accuracy}</td>

                      {/* Postgame */}
                      <td className="p-2">{g.post_predicted || ""}</td>
                      <td className={`p-2 ${colorClass(g.post_percent_error)}`}>
                        {g.post_percent_error != null
                          ? `${g.post_percent_error.toFixed(1)}%`
                          : ""}
                      </td>
                      <td className="p-2">{g.post_accuracy}</td>

                      {/* Actual */}
                      <td className="p-2">{g.actual || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ================== Helper Components ================== */

function Metric({ label, value }) {
  return (
    <div className="border rounded p-4 bg-gray-50 text-center">
      <p className="text-sm text-gray-600">{label}</p>
      <p className="text-2xl font-semibold mt-1">{value}</p>
    </div>
  );
}

function colorClass(e) {
  if (e == null) return "";
  if (e >= 35) return "bg-red-100";
  if (e >= 25) return "bg-yellow-100";
  return "bg-green-100";
}