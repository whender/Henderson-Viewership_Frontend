import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import WeeklyPredictions from "./WeeklyPredictions";
import TeamProfiles from "./TeamProfiles";
import ViewershipRankings from "./ViewershipRankings";
import RealignmentSimulator from "./RealignmentSimulator";
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
  ["home", "/", "HOME"],
  ["predictor", "/predictor", "GAME PREDICTOR"],
  ["brands", "/brands", "BRAND RANKINGS"],
  ["viewership-rankings", "/viewership-rankings", "VIEWERSHIP RANKINGS"],
  ["comparison", "/comparison", "COMPARISON"],
  ["realignment", "/realignment", "REALIGNMENT SIM"],
  ["weekly", "/weekly", "WEEKLY PREDICTIONS"],
  ["articles", "/articles", "ARTICLES"],
  ["model", "/model", "MODEL EXPLANATION"],
];

const TOOL_NAV_KEYS = new Set([
  "predictor",
  "brands",
  "viewership-rankings",
  "comparison",
  "realignment",
  "weekly",
  "model",
]);

const FOOTBALL_TOOL_NAV_KEYS = [
  "predictor",
  "brands",
  "viewership-rankings",
  "comparison",
  "realignment",
  "weekly",
  "model",
];

const BASKETBALL_TOOL_NAV_KEYS = [
  "predictor",
  "brands",
  "viewership-rankings",
  "comparison",
  "model",
];

const NAV_ITEM_BY_KEY = Object.fromEntries(
  NAV_ITEMS.map((item) => [item[0], item])
);

const TOOL_NAV_ITEMS_BY_SPORT = {
  football: FOOTBALL_TOOL_NAV_KEYS.map((key) => NAV_ITEM_BY_KEY[key]),
  basketball: BASKETBALL_TOOL_NAV_KEYS.map((key) => NAV_ITEM_BY_KEY[key]),
};

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
  const location = useLocation();
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
  const [homeBrandRows, setHomeBrandRows] = useState([]);
  const [homeViewershipRows, setHomeViewershipRows] = useState([]);
  const [navMenuOpen, setNavMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pageCopy = activeTab === "home" ? {
    title: "Will Henderson - Viewership Model",
    description: "Viewership tools, rankings, profiles, and conference analysis.",
  } : sportCopy;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedSport = params.get("sport");
    if (requestedSport === "football" || requestedSport === "basketball") {
      setSport(requestedSport);
      localStorage.setItem("henderson-viewership-sport", requestedSport);
    }
  }, [activeTab, location.search]);

  useEffect(() => {
    setNavMenuOpen(false);
    setMobileMenuOpen(false);
  }, [location.pathname]);

  function handleSportChange(nextSport) {
    setSport(nextSport);
    localStorage.setItem("henderson-viewership-sport", nextSport);

    const teamPageMatch = location.pathname.match(/^\/teams\/(?:football|basketball)\/(.+)$/);
    if (teamPageMatch) {
      navigate(`/teams/${nextSport}/${teamPageMatch[1]}`);
    }
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

    fetch(`${BACKEND_BASE}/brand-rankings?scope=combined`)
      .then((res) => res.json())
      .then((data) => setHomeBrandRows(data.rows || []))
      .catch((err) => console.error("Home brand preview load error:", err));

    fetch(`${BACKEND_BASE}/cbb/teams`)
      .then((res) => res.json())
      .then((data) => setBasketballTeams(data.teams || []));

    fetch(`${BACKEND_BASE}/cbb/filters`)
      .then((res) => res.json())
      .then(setBasketballFilters);

    fetch(`${BACKEND_BASE}/cbb/metadata`)
      .then((res) => res.json())
      .then(setBasketballMetadata);

    const params = new URLSearchParams({
      min_games: "1",
      network: "all",
      time_bucket: "all",
      rank_bucket: "all",
      opponent: "all",
      include_conf_champ: "false",
    });
    fetch(`${BACKEND_BASE}/team-viewership-rankings?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => setHomeViewershipRows((data.rows || []).slice(0, 5)))
      .catch((err) => console.error("Home viewership preview load error:", err));
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
      setPrediction({
        formatted: data.prediction_formatted,
        warnings: data.warnings || [],
      });
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
              {pageCopy.title}
            </h1>
            <p className="text-gray-600 mb-8">
              {pageCopy.description}
            </p>
          </div>
          <button
            type="button"
            className="mobile-menu-button md:hidden"
            aria-label="Open menu"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(true)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>

        <MobileDashboardMenu
          open={mobileMenuOpen}
          activeTab={activeTab}
          sport={sport}
          onClose={() => setMobileMenuOpen(false)}
          onSportChange={handleSportChange}
          footballTeams={teams}
          basketballTeams={basketballTeams}
        />

        <DashboardNav
          activeTab={activeTab}
          sport={sport}
          onSportChange={handleSportChange}
          footballTeams={teams}
          basketballTeams={basketballTeams}
          navMenuOpen={navMenuOpen}
          setNavMenuOpen={setNavMenuOpen}
        />

        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                sport={sport}
                brandRows={homeBrandRows}
                viewershipRows={homeViewershipRows}
              />
            }
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
            path="/teams/:profileSport/:teamId"
            element={
              <TeamProfileRoute
                footballTeams={teams}
                basketballTeams={basketballTeams}
                setSport={setSport}
              />
            }
          />
          <Route
            path="/comparison"
            element={isBasketball ? <BasketballProfiles teams={basketballTeams} comparisonOnly /> : <TeamProfiles teams={teams} comparisonOnly />}
          />
          <Route
            path="/realignment"
            element={isBasketball ? <BasketballRealignmentPage /> : <RealignmentSimulator teams={teams} />}
          />
          <Route path="/weekly" element={isBasketball ? <BasketballWeeklyPage /> : <WeeklyPredictions />} />
          <Route path="/articles" element={<ArticlesPage />} />
          <Route path="/model" element={isBasketball ? <BasketballModelExplanation metadata={basketballMetadata} /> : <ModelExplanationPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
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

function DashboardNav({
  activeTab,
  sport,
  onSportChange,
  footballTeams,
  basketballTeams,
  navMenuOpen,
  setNavMenuOpen,
}) {
  const navigate = useNavigate();
  const toolsActive = TOOL_NAV_KEYS.has(activeTab);
  const handleToolClick = (nextSport) => {
    onSportChange(nextSport);
    setNavMenuOpen(false);
  };
  const teamOptionsBySport = {
    football: footballTeams || [],
    basketball: basketballTeams || [],
  };
  const handleTeamSelect = (nextSport, team) => {
    if (!team) return;
    onSportChange(nextSport);
    setNavMenuOpen(false);
    navigate(`/teams/${nextSport}/${encodeURIComponent(team)}`);
  };

  return (
    <nav className="dashboard-nav hidden md:flex" aria-label="Dashboard navigation">
      <Link
        to="/"
        className={"dashboard-nav-link " + (activeTab === "home" ? "dashboard-nav-link-active" : "")}
      >
        Home
      </Link>

      <div className="dashboard-menu-wrap">
        <button
          type="button"
          className={"dashboard-nav-link dashboard-menu-trigger " + (toolsActive ? "dashboard-nav-link-active" : "")}
          onClick={() => setNavMenuOpen((open) => !open)}
          aria-expanded={navMenuOpen}
          aria-haspopup="menu"
        >
          Tools
          <span className="dashboard-menu-caret" aria-hidden="true" />
        </button>

        {navMenuOpen && (
          <div className="dashboard-menu" role="menu">
            {["football", "basketball"].map((sportKey) => (
              <div className="dashboard-menu-section" key={sportKey}>
                <div className="dashboard-menu-section-title">
                  {SPORT_COPY[sportKey].label}
                </div>
                <div className="dashboard-team-select-block">
                  <label>Team Profiles</label>
                  <select
                    value=""
                    onChange={(event) => handleTeamSelect(sportKey, event.target.value)}
                  >
                    <option value="">Select a team</option>
                    {teamOptionsBySport[sportKey].map((team) => (
                      <option key={team.value} value={team.value}>
                        {team.label}
                      </option>
                    ))}
                  </select>
                </div>
                {TOOL_NAV_ITEMS_BY_SPORT[sportKey].map(([key, path, label]) => (
                  <Link
                    key={`${sportKey}-${key}`}
                    to={path}
                    role="menuitem"
                    onClick={() => handleToolClick(sportKey)}
                    className={
                      "dashboard-menu-item "
                      + (activeTab === key && sport === sportKey ? "dashboard-menu-item-active" : "")
                    }
                  >
                    <span>{label}</span>
                    <span>{navItemDescription(key, sportKey)}</span>
                  </Link>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      <Link
        to="/articles"
        className={"dashboard-nav-link " + (activeTab === "articles" ? "dashboard-nav-link-active" : "")}
      >
        Articles
      </Link>
    </nav>
  );
}

function MobileDashboardMenu({
  open,
  activeTab,
  sport,
  onClose,
  onSportChange,
  footballTeams,
  basketballTeams,
}) {
  const navigate = useNavigate();
  const [expandedSport, setExpandedSport] = useState(sport || "football");
  const teamOptionsBySport = {
    football: footballTeams || [],
    basketball: basketballTeams || [],
  };

  useEffect(() => {
    if (open) {
      setExpandedSport(sport || "football");
    }
  }, [open, sport]);

  const handleToolClick = (sportKey) => {
    onSportChange(sportKey);
    onClose();
  };

  const handleTeamSelect = (sportKey, team) => {
    if (!team) return;
    onSportChange(sportKey);
    navigate(`/teams/${sportKey}/${encodeURIComponent(team)}`);
    onClose();
  };

  return (
    <div className={`mobile-drawer-shell ${open ? "mobile-drawer-shell-open" : ""}`} aria-hidden={!open}>
      <button
        type="button"
        className="mobile-drawer-backdrop"
        aria-label="Close menu"
        onClick={onClose}
      />
      <aside className="mobile-drawer" aria-label="Mobile navigation">
        <div className="mobile-drawer-header">
          <div>
            <span>Menu</span>
            <strong>Viewership Model</strong>
          </div>
          <button type="button" className="mobile-drawer-close" onClick={onClose} aria-label="Close menu">
            Close
          </button>
        </div>

        <div className="mobile-drawer-main-links">
          <Link
            to="/"
            className={"mobile-drawer-link " + (activeTab === "home" ? "mobile-drawer-link-active" : "")}
            onClick={onClose}
          >
            Home
          </Link>
          <Link
            to="/articles"
            className={"mobile-drawer-link " + (activeTab === "articles" ? "mobile-drawer-link-active" : "")}
            onClick={onClose}
          >
            Articles
          </Link>
        </div>

        {["football", "basketball"].map((sportKey) => {
          const expanded = expandedSport === sportKey;
          return (
            <section className="mobile-sport-section" key={sportKey}>
              <button
                type="button"
                className="mobile-sport-trigger"
                aria-expanded={expanded}
                onClick={() => setExpandedSport(expanded ? "" : sportKey)}
              >
                <span>{SPORT_COPY[sportKey].label}</span>
                <span className={`mobile-sport-caret ${expanded ? "mobile-sport-caret-open" : ""}`} />
              </button>

              {expanded && (
                <div className="mobile-sport-panel">
                  <label className="mobile-team-select-label">Team Profiles</label>
                  <select
                    value=""
                    onChange={(event) => handleTeamSelect(sportKey, event.target.value)}
                  >
                    <option value="">Select a team</option>
                    {teamOptionsBySport[sportKey].map((team) => (
                      <option key={team.value} value={team.value}>
                        {team.label}
                      </option>
                    ))}
                  </select>

                  <div className="mobile-feature-list">
                    {TOOL_NAV_ITEMS_BY_SPORT[sportKey].map(([key, path, label]) => (
                      <Link
                        key={`${sportKey}-${key}`}
                        to={path}
                        onClick={() => handleToolClick(sportKey)}
                        className={
                          "mobile-feature-link "
                          + (activeTab === key && sport === sportKey ? "mobile-feature-link-active" : "")
                        }
                      >
                        <span>{label}</span>
                        <small>{navItemDescription(key, sportKey)}</small>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </section>
          );
        })}
      </aside>
    </div>
  );
}

function navItemDescription(key, sportKey = "football") {
  const descriptions = {
    predictor: "Single-game projections",
    brands: "Media-rights brand value",
    "viewership-rankings": "Team audience tables",
    comparison: "Team profile comparison",
    realignment: "Conference schedule simulation",
    weekly: "Weekly game projections",
    model: "Model explanation",
  };
  return descriptions[key] || "";
}

function HomePage({ sport, brandRows, viewershipRows }) {
  const brandPreviewRows = (brandRows || []).slice(0, 5);
  const quickLinks = [
    {
      title: "Game Predictor",
      description: "Project a hypothetical matchup by team, rank, network, window, and competing games.",
      path: "/predictor",
      meta: sport === "basketball" ? "Basketball active" : "Football active",
    },
    {
      title: "Brand Rankings",
      description: "Compare football, basketball, and combined media-rights brand value.",
      path: "/brands",
      meta: "Media index",
    },
    {
      title: "Viewership Rankings",
      description: "Rank teams by average and median audiences under selected TV conditions.",
      path: "/viewership-rankings",
      meta: "Filterable table",
    },
    {
      title: "Comparison",
      description: "Compare two team profiles side by side using the active sport.",
      path: "/comparison",
      meta: sport === "basketball" ? "Basketball active" : "Football active",
    },
    {
      title: "Realignment Simulator",
      description: "Edit conference memberships and simulate schedules, TV slots, and projected viewers.",
      path: "/realignment",
      meta: "Football model",
    },
  ];

  return (
    <div className="home-page">
      <section className="home-hero">
        <div>
          <p className="home-kicker">Dashboard Home</p>
          <h2>Viewership tools, rankings, and conference simulations in one place.</h2>
        </div>
        <div className="home-hero-actions">
          <Link to="/realignment" className="btn-primary">Open Realignment</Link>
          <Link to="/brands" className="btn-secondary">View Rankings</Link>
        </div>
      </section>

      <section className="home-grid">
        <div className="home-panel home-panel-large">
          <div className="home-panel-header">
            <div>
              <p className="home-kicker">Preview</p>
              <h3>Combined Brand Rankings</h3>
            </div>
            <Link to="/brands" className="home-panel-link">Full rankings</Link>
          </div>
          <div className="home-ranking-list">
            {brandPreviewRows.length ? brandPreviewRows.map((row) => (
              <div className="home-ranking-row" key={row.team}>
                <span className="home-ranking-rank">{row.rank}</span>
                <TeamPill
                  team={row.team}
                  compact
                  profileSport={getProfileSportForBrandRow(row, "combined")}
                />
                <span className="home-ranking-value">
                  {row.media_brand_index != null
                    ? row.media_brand_index.toFixed(1)
                    : formatLiftCell(row.viewership_lift_pct)}
                </span>
              </div>
            )) : (
              <p className="text-gray-600">Loading brand rankings…</p>
            )}
          </div>
        </div>

        <div className="home-panel">
          <div className="home-panel-header">
            <div>
              <p className="home-kicker">Preview</p>
              <h3>Football Viewership</h3>
            </div>
            <Link to="/viewership-rankings" className="home-panel-link">Open table</Link>
          </div>
          <div className="home-ranking-list">
            {viewershipRows.length ? viewershipRows.map((row) => (
              <div className="home-ranking-row" key={row.team}>
                <span className="home-ranking-rank">{row.rank}</span>
                <TeamPill team={row.team} compact profileSport="football" />
                <span className="home-ranking-value">
                  {formatHomeViewers(row.average_viewers)}
                </span>
              </div>
            )) : (
              <p className="text-gray-600">Loading viewership rankings…</p>
            )}
          </div>
        </div>
      </section>

      <section className="home-grid home-grid-secondary">
        <div className="home-panel home-panel-large">
          <div className="home-panel-header">
            <div>
              <p className="home-kicker">Start</p>
              <h3>Quick Links</h3>
            </div>
          </div>
          <div className="home-link-grid">
            {quickLinks.map((item) => (
              <Link to={item.path} className="home-link-card" key={item.title}>
                <span className="home-link-meta">{item.meta}</span>
                <strong>{item.title}</strong>
                <span>{item.description}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="home-panel">
          <div className="home-panel-header">
            <div>
              <p className="home-kicker">Articles</p>
              <h3>Notebook</h3>
            </div>
            <Link to="/articles" className="home-panel-link">Open</Link>
          </div>
          <p className="home-article-empty">
            No articles published yet.
          </p>
        </div>
      </section>
    </div>
  );
}

function formatHomeViewers(value) {
  const number = Number(value || 0);
  if (!number) return "No data";
  return `${(number / 1000).toFixed(2)}M`;
}

function ArticlesPage() {
  return (
    <div className="articles-page">
      <div className="home-panel articles-empty-panel">
        <p className="home-kicker">Articles</p>
        <h2>Notebook</h2>
        <p className="text-gray-600">
          No articles published yet.
        </p>
      </div>
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
            Predicted Viewers: {prediction.formatted || prediction}
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

          {Array.isArray(prediction.warnings) && prediction.warnings.length > 0 && (
            <div className="prediction-warning">
              {prediction.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
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

function BasketballRealignmentPage() {
  return (
    <div className="card" style={{ maxWidth: "860px", lineHeight: 1.6 }}>
      <h2 className="text-3xl font-semibold mb-4">Conference Realignment Simulator</h2>
      <p className="text-gray-600">
        The realignment simulator is currently wired to the football viewership model.
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

function TeamProfileRoute({ footballTeams, basketballTeams, setSport }) {
  const { profileSport, teamId } = useParams();
  const decodedTeam = decodeURIComponent(teamId || "");
  const resolvedSport = profileSport === "basketball" ? "basketball" : "football";

  useEffect(() => {
    setSport(resolvedSport);
    localStorage.setItem("henderson-viewership-sport", resolvedSport);
  }, [resolvedSport, setSport]);

  if (resolvedSport === "basketball") {
    return <BasketballProfiles teams={basketballTeams} initialTeam={decodedTeam} profileOnly />;
  }

  return <TeamProfiles teams={footballTeams} initialTeam={decodedTeam} profileOnly />;
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
        to={`/teams/${profileSport}/${encodeURIComponent(team)}`}
        className={`team-pill team-profile-link ${compact ? "team-pill-compact" : ""}`}
      >
        {content}
      </Link>
    );
  }

  return <span className={`team-pill ${compact ? "team-pill-compact" : ""}`}>{content}</span>;
}
