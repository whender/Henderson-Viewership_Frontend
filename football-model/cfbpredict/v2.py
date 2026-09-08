"""Roster-informed offense/defense model and hybrid game predictions."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cfbpredict.efficiency import (
    OpponentAdjustedEfficiencyModel,
    TeamEfficiencyPrior,
)
from cfbpredict.fcs import FCSModel
from cfbpredict.games import atomic_write_json, parse_datetime
from cfbpredict.hybrid import HybridMarginModel
from cfbpredict.model import ModelNotFittedError, PointRatingModel
from cfbpredict.prior import PreseasonPriorModel, PreseasonScorePriorModel
from cfbpredict.v2_data import SeasonFeatureTable, TeamIdentity

V2_ARTIFACT_SCHEMA_VERSION = 3
HYBRID_FEATURE_SCHEMA = (
    "score_rating_diff",
    "early_large_score_gap",
    "home_field_points",
    "preseason_ppa_edge",
    "inseason_ppa_update_edge",
    "preseason_success_edge",
    "inseason_success_update_edge",
    "rest_advantage_days",
    "away_travel_thousand_miles",
)

_CONTINUITY_COMPONENTS = (
    ("roster_experience_retention_rate", 0.25),
    ("roster_offense_experience_retention_rate", 0.15),
    ("roster_defense_experience_retention_rate", 0.15),
    ("roster_ol_experience_retention_rate", 0.15),
    ("roster_skill_usage_retention_rate", 0.15),
    ("qb_pass_usage_retention_rate", 0.15),
)
_LARGE_SCORE_GAP_THRESHOLD = 15.0
_LARGE_SCORE_GAP_CAP = 20.0
_LARGE_SCORE_GAP_DECAY_WEEKS = 3.0


def score_carryover_factor(
    features: Mapping[str, float] | None,
    *,
    current_season_games: int = 0,
) -> float:
    """Shrink inherited score strength when the people producing it have left.

    The preseason factor combines unit/player continuity with staff-system continuity.
    It fades exponentially toward one as new-season results replace inherited evidence.
    """

    if not features:
        return 1.0
    observed: list[tuple[float, float]] = []
    for name, weight in _CONTINUITY_COMPONENTS:
        if name not in features:
            continue
        value = max(0.0, min(float(features[name]), 1.0))
        if (
            name == "roster_ol_experience_retention_rate"
            and features.get("roster_ol_starter_retention_missing", 1.0) < 0.5
        ):
            # Roster overlap can badly overstate continuity when every primary
            # starter leaves but experienced reserves remain.  When an audited
            # starter rate exists, give top-unit and depth continuity equal weight.
            draft_adjusted = max(
                0.0,
                min(
                    float(
                        features.get(
                            "roster_ol_draft_adjusted_retention_rate", value
                        )
                    ),
                    1.0,
                ),
            )
            starter_retention = max(
                0.0,
                min(float(features["roster_ol_starter_retention_rate"]), 1.0),
            )
            depth_retention = min(value, draft_adjusted)
            value = 0.5 * (depth_retention + starter_retention)
        observed.append((value, weight))
    if not observed:
        roster_continuity = 0.5
    else:
        weight_total = sum(weight for _, weight in observed)
        roster_continuity = sum(value * weight for value, weight in observed) / weight_total
    coach_change = max(0.0, min(float(features.get("coach_change", 0.0)), 1.0))
    internal_successor = max(
        0.0, min(float(features.get("coach_internal_successor", 0.0)), 1.0)
    )
    if features.get("coach_staff_retention_missing", 1.0) < 0.5:
        staff_retention = max(
            0.0, min(float(features["coach_staff_retention_rate"]), 1.0)
        )
        # Being an internal hire only warrants continuity credit to the extent
        # that the staff and systems around that hire actually remain intact.
        internal_successor *= staff_retention
    system_continuity = 1.0 - coach_change * (0.30 - 0.20 * internal_successor)
    preseason_factor = max(0.10, min(roster_continuity * system_continuity, 1.0))
    games = max(int(current_season_games), 0)
    return 1.0 - (1.0 - preseason_factor) * math.exp(-games / 4.0)


def anchored_score_rating(
    raw_rating: float,
    program_prior: float,
    carryover: float,
) -> float:
    """Blend inherited point strength toward a learned preseason program prior."""

    values = (float(raw_rating), float(program_prior), float(carryover))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Score rating anchor inputs must be finite")
    if not 0.0 <= carryover <= 1.0:
        raise ValueError("Score rating carryover must be between zero and one")
    return program_prior + carryover * (raw_rating - program_prior)


def early_large_score_gap_feature(score_rating_diff: float, season_week: float) -> float:
    """Bound and fade the extreme preseason mismatch signal learned by the hybrid."""

    gap = float(score_rating_diff)
    week = float(season_week)
    if not math.isfinite(gap) or not math.isfinite(week):
        raise ValueError("Early score-gap inputs must be finite")
    excess = min(max(abs(gap) - _LARGE_SCORE_GAP_THRESHOLD, 0.0), _LARGE_SCORE_GAP_CAP)
    decay = math.exp(-max(week - 1.0, 0.0) / _LARGE_SCORE_GAP_DECAY_WEEKS)
    return math.copysign(excess * decay, gap)


def game_context_features(
    game: Any,
    season_games: Sequence[Any],
    team_locations: Mapping[str, tuple[float, float]],
) -> dict[str, float]:
    """Build schedule-only context without using outcomes from the target game."""

    def rest_days(team_key: str) -> float:
        previous = [
            other.start_date
            for other in season_games
            if other.id != game.id
            and other.start_date < game.start_date
            and team_key in {other.home_key, other.away_key}
        ]
        if not previous:
            return 7.0
        days = (game.start_date - max(previous)).total_seconds() / 86_400.0
        return max(3.0, min(days, 21.0))

    travel = 0.0
    if not game.neutral_site:
        home_location = team_locations.get(game.home_key)
        away_location = team_locations.get(game.away_key)
        if home_location is not None and away_location is not None:
            lat1, lon1 = (math.radians(value) for value in away_location)
            lat2, lon2 = (math.radians(value) for value in home_location)
            delta_lat = lat2 - lat1
            delta_lon = lon2 - lon1
            haversine = (
                math.sin(delta_lat / 2.0) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
            )
            travel = 2.0 * 3_958.8 * math.asin(min(math.sqrt(haversine), 1.0))
    team_openers = [
        other.start_date
        for other in season_games
        if other.start_date <= game.start_date
        and (
            game.home_key in {other.home_key, other.away_key}
            or game.away_key in {other.home_key, other.away_key}
        )
    ]
    season_age_weeks = (
        max((game.start_date - min(team_openers)).total_seconds() / (7.0 * 86_400.0), 0.0)
        if team_openers
        else max(float(game.week - 1), 0.0)
    )
    return {
        "season_age_weeks": season_age_weeks,
        "rest_advantage_days": rest_days(game.home_key) - rest_days(game.away_key),
        "away_travel_thousand_miles": travel / 1_000.0,
    }


@dataclass(frozen=True, slots=True)
class V2Prediction:
    home_team: str
    away_team: str
    neutral_site: bool
    predicted_margin: float
    home_win_probability: float
    away_win_probability: float
    margin_interval_80: tuple[float, float]
    margin_interval_95: tuple[float, float]
    score_margin: float
    preseason_ppa_edge: float
    current_ppa_edge: float
    preseason_success_edge: float
    current_success_edge: float
    home_field_points: float
    unknown_teams: tuple[str, ...]
    model_scope: str = "fbs"

    @property
    def favorite(self) -> str:
        if self.predicted_margin > 0:
            return self.home_team
        if self.predicted_margin < 0:
            return self.away_team
        return "Pick'em"


@dataclass(frozen=True, slots=True)
class V2Ranking:
    key: str
    team_id: int
    team: str
    conference: str | None
    rating: float
    preseason_efficiency_strength: float
    current_efficiency_strength: float
    games: int
    talent_current_missing: bool
    turnover_data_missing: bool
    roster_estimated: bool
    roster_estimation_coverage: float
    draft_departures: int
    skill_usage_retention_rate: float
    ol_experience_retention_rate: float
    ol_draft_adjusted_retention_rate: float
    ol_starter_retention_rate: float | None
    coach_staff_retention_rate: float | None
    coach_offense_staff_retention_rate: float | None


def build_team_efficiency_priors(
    prior_model: PreseasonPriorModel,
    features: SeasonFeatureTable,
) -> dict[str, TeamEfficiencyPrior]:
    """Convert learned team-season estimates to dynamic efficiency priors."""

    priors: dict[str, TeamEfficiencyPrior] = {}
    for row in features.rows:
        estimate = prior_model.predict(row.features)
        multiplier = estimate.precision_multiplier
        priors[row.identity.key] = TeamEfficiencyPrior(
            team=row.identity.team,
            team_id=row.identity.team_id,
            classification=row.identity.classification,
            offense_ppa=max(-1.0, min(estimate.offense_ppa, 1.0)),
            defense_ppa_prevented=max(-1.0, min(estimate.defense_ppa, 1.0)),
            offense_success_rate=max(0.0, min(estimate.offense_success, 1.0)),
            defense_success_rate_prevented=max(-0.5, min(estimate.defense_success, 0.5)),
            offense_ppa_precision=multiplier,
            defense_ppa_precision=multiplier,
            offense_success_precision=multiplier,
            defense_success_precision=multiplier,
        )
    return priors


def _prior_matchup(
    home_key: str | None,
    away_key: str | None,
    priors: dict[str, TeamEfficiencyPrior],
    efficiency: OpponentAdjustedEfficiencyModel,
    *,
    metric: str,
) -> float:
    home = priors.get(home_key or "")
    away = priors.get(away_key or "")
    if metric == "ppa":
        league = efficiency.config.ppa_prior
        home_offense = league if home is None or home.offense_ppa is None else home.offense_ppa
        away_offense = league if away is None or away.offense_ppa is None else away.offense_ppa
        home_defense = (
            0.0
            if home is None or home.defense_ppa_prevented is None
            else home.defense_ppa_prevented
        )
        away_defense = (
            0.0
            if away is None or away.defense_ppa_prevented is None
            else away.defense_ppa_prevented
        )
    elif metric == "success_rate":
        league = efficiency.config.success_rate_prior
        home_offense = (
            league
            if home is None or home.offense_success_rate is None
            else home.offense_success_rate
        )
        away_offense = (
            league
            if away is None or away.offense_success_rate is None
            else away.offense_success_rate
        )
        home_defense = (
            0.0
            if home is None or home.defense_success_rate_prevented is None
            else home.defense_success_rate_prevented
        )
        away_defense = (
            0.0
            if away is None or away.defense_success_rate_prevented is None
            else away.defense_success_rate_prevented
        )
    else:
        raise ValueError(f"Unknown efficiency metric: {metric}")
    return (home_offense - away_defense) - (away_offense - home_defense)


def _current_matchup(
    home_key: str | None,
    away_key: str | None,
    efficiency: OpponentAdjustedEfficiencyModel,
    *,
    metric: str,
) -> float:
    ratings = efficiency.metrics[metric]
    home_expected = ratings.predict(home_key or "", away_key or "")
    away_expected = ratings.predict(away_key or "", home_key or "")
    return home_expected - away_expected


def matchup_feature_values(
    home_key: str | None,
    away_key: str | None,
    *,
    neutral_site: bool,
    baseline: PointRatingModel,
    efficiency: OpponentAdjustedEfficiencyModel,
    priors: dict[str, TeamEfficiencyPrior],
    preseason_features: Mapping[str, Mapping[str, float]] | None = None,
    context: Mapping[str, float] | None = None,
    score_rating_fallbacks: Mapping[str, float] | None = None,
    score_rating_priors: Mapping[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Build the exact hybrid schema plus interpretable component values."""

    baseline._require_fitted()
    efficiency._require_fitted()
    if home_key is not None and home_key == away_key:
        raise ValueError("home and away teams must differ")
    rating_fallbacks = score_rating_fallbacks or {}
    home_rating = baseline.ratings.get(
        home_key or "", rating_fallbacks.get(home_key or "", 0.0)
    )
    away_rating = baseline.ratings.get(
        away_key or "", rating_fallbacks.get(away_key or "", 0.0)
    )
    if not baseline.config.fbs_only and score_rating_priors:
        # Joint ratings are zero-centered across both divisions, whereas learned
        # program priors are on the FBS-centered scale. Align before blending.
        fbs_ratings = [baseline.ratings[key] for key in score_rating_priors
                       if key in baseline.ratings]
        offset = sum(fbs_ratings) / len(fbs_ratings) if fbs_ratings else 0.0
        home_rating -= offset
        away_rating -= offset
    feature_rows = preseason_features or {}
    home_games = efficiency.teams.get(home_key or "")
    away_games = efficiency.teams.get(away_key or "")
    home_carryover = score_carryover_factor(
        feature_rows.get(home_key or ""),
        current_season_games=home_games.games if home_games is not None else 0,
    )
    away_carryover = score_carryover_factor(
        feature_rows.get(away_key or ""),
        current_season_games=away_games.games if away_games is not None else 0,
    )
    if score_rating_priors is None:
        # Preserve legacy and cross-division behavior when no comparable
        # point-scale FBS program prior is available.
        home_score_prior = 0.0
        away_score_prior = 0.0
    else:
        home_score_prior = float(score_rating_priors.get(home_key or "", home_rating))
        away_score_prior = float(score_rating_priors.get(away_key or "", away_rating))
    adjusted_home_rating = anchored_score_rating(
        home_rating,
        home_score_prior,
        home_carryover,
    )
    adjusted_away_rating = anchored_score_rating(
        away_rating,
        away_score_prior,
        away_carryover,
    )
    home_field = (
        0.0
        if neutral_site
        else baseline.home_field_advantage
        + baseline.team_home_field_adjustments.get(home_key or "", 0.0)
    )
    preseason_ppa = _prior_matchup(home_key, away_key, priors, efficiency, metric="ppa")
    current_ppa = _current_matchup(home_key, away_key, efficiency, metric="ppa")
    preseason_success = _prior_matchup(
        home_key, away_key, priors, efficiency, metric="success_rate"
    )
    current_success = _current_matchup(home_key, away_key, efficiency, metric="success_rate")
    supplied_context = context or {}
    score_rating_diff = adjusted_home_rating - adjusted_away_rating
    early_large_gap = (
        0.0
        if score_rating_priors is None
        else early_large_score_gap_feature(
            score_rating_diff,
            float(supplied_context.get("season_age_weeks", 0.0)) + 1.0,
        )
    )
    features = {
        "score_rating_diff": score_rating_diff,
        "early_large_score_gap": early_large_gap,
        "home_field_points": home_field,
        "preseason_ppa_edge": preseason_ppa,
        "inseason_ppa_update_edge": current_ppa - preseason_ppa,
        "preseason_success_edge": preseason_success,
        "inseason_success_update_edge": current_success - preseason_success,
        "rest_advantage_days": float(supplied_context.get("rest_advantage_days", 0.0)),
        "away_travel_thousand_miles": float(
            supplied_context.get("away_travel_thousand_miles", 0.0)
        ),
    }
    components = {
        "score_margin": adjusted_home_rating - adjusted_away_rating + home_field,
        "raw_score_rating_diff": home_rating - away_rating,
        "home_score_carryover": home_carryover,
        "away_score_carryover": away_carryover,
        "home_score_program_prior": home_score_prior,
        "away_score_program_prior": away_score_prior,
        "preseason_ppa_edge": preseason_ppa,
        "current_ppa_edge": current_ppa,
        "preseason_success_edge": preseason_success,
        "current_success_edge": current_success,
        "home_field_points": home_field,
    }
    if tuple(features) != HYBRID_FEATURE_SCHEMA:
        raise RuntimeError("Internal hybrid feature schema drifted")
    return features, components


class CollegeFootballV2Model:
    """Serializable final model combining scores, rosters, and efficiency."""

    def __init__(self) -> None:
        self.season: int | None = None
        self.as_of: datetime | None = None
        self.baseline: PointRatingModel | None = None
        self.prior_model: PreseasonPriorModel | None = None
        self.score_prior_model: PreseasonScorePriorModel | None = None
        self.efficiency: OpponentAdjustedEfficiencyModel | None = None
        self.hybrid: HybridMarginModel | None = None
        self.identities: dict[str, TeamIdentity] = {}
        self.team_priors: dict[str, TeamEfficiencyPrior] = {}
        self.score_rating_priors: dict[str, float] = {}
        self.preseason_features: dict[str, dict[str, float]] = {}
        self.evaluation: dict[str, Any] = {}
        self.source_notes: tuple[str, ...] = ()
        self.team_locations: dict[str, tuple[float, float]] = {}
        self.fcs_model: FCSModel | None = None
        self._name_index: dict[str, str] = {}

    @property
    def is_fitted(self) -> bool:
        return (
            self.season is not None
            and self.as_of is not None
            and self.baseline is not None
            and self.baseline.is_fitted
            and self.prior_model is not None
            and self.prior_model.is_fitted
            and self.efficiency is not None
            and self.efficiency.is_fitted
            and self.hybrid is not None
            and self.hybrid.is_fitted
            and bool(self.identities)
            and (self.fcs_model is None or self.fcs_model.is_fitted)
        )

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise ModelNotFittedError("Fit or load the V2 model before predicting")

    def _rebuild_name_index(self) -> None:
        fcs_names = (
            {
                " ".join(identity.team.casefold().split()): key
                for key, identity in self.fcs_model.identities.items()
            }
            if self.fcs_model is not None
            else {}
        )
        self._name_index = dict(fcs_names)
        self._name_index.update(
            {
                " ".join(identity.team.casefold().split()): key
                for key, identity in self.identities.items()
            }
        )

    def _known_team_keys(self) -> set[str]:
        keys = set(self.identities)
        if self.fcs_model is not None:
            keys.update(self.fcs_model.identities)
        return keys

    def resolve_team(self, team: str | int, *, team_id: int | None = None) -> str | None:
        self._require_fitted()
        if team_id is not None:
            key = f"id:{team_id}"
            return key if key in self._known_team_keys() else None
        if isinstance(team, int) or (isinstance(team, str) and team.strip().isdigit()):
            key = f"id:{int(team)}"
            return key if key in self._known_team_keys() else None
        return self._name_index.get(" ".join(str(team).casefold().split()))

    def suggest_teams(self, query: str, *, limit: int = 5) -> list[str]:
        self._require_fitted()
        normalized = query.casefold().strip()
        identities = list(self.identities.values())
        if self.fcs_model is not None:
            identities.extend(self.fcs_model.identities.values())
        starts = sorted(
            identity.team
            for identity in identities
            if identity.team.casefold().startswith(normalized)
        )
        contains = sorted(
            identity.team
            for identity in identities
            if normalized in identity.team.casefold() and identity.team not in starts
        )
        return starts[:limit] + contains[: max(0, limit - len(starts))]

    def _predict_keys(
        self,
        home_key: str | None,
        away_key: str | None,
        *,
        home_team: str,
        away_team: str,
        neutral_site: bool,
        context: Mapping[str, float] | None = None,
    ) -> V2Prediction:
        self._require_fitted()
        assert self.baseline is not None and self.efficiency is not None and self.hybrid is not None
        if (home_key is not None and home_key == away_key) or (
            " ".join(home_team.casefold().split()) == " ".join(away_team.casefold().split())
        ):
            raise ValueError("home_team and away_team must be different teams")
        home_is_fcs = bool(
            self.fcs_model is not None and home_key in self.fcs_model.identities
        )
        away_is_fcs = bool(
            self.fcs_model is not None and away_key in self.fcs_model.identities
        )
        if home_is_fcs and away_is_fcs:
            raise ValueError(
                "The bundled FCS model is calibrated for FBS-versus-FCS matchups, "
                "not FCS-versus-FCS predictions"
            )
        use_fcs_model = bool(
            self.fcs_model is not None and (home_is_fcs or away_is_fcs)
        )
        if use_fcs_model:
            assert self.fcs_model is not None
            baseline = self.fcs_model.baseline
            efficiency = self.fcs_model.efficiency
            hybrid = self.fcs_model.hybrid
            priors = efficiency.priors
            fallback = self.fcs_model.mean_fcs_score_rating
            score_rating_fallbacks = {
                key: fallback for key in self.fcs_model.identities
            }
            score_rating_priors = None
        else:
            baseline = self.baseline
            efficiency = self.efficiency
            hybrid = self.hybrid
            priors = self.team_priors
            score_rating_fallbacks = None
            score_rating_priors = self.score_rating_priors or None
        features, components = matchup_feature_values(
            home_key,
            away_key,
            neutral_site=neutral_site,
            baseline=baseline,
            efficiency=efficiency,
            priors=priors,
            preseason_features=self.preseason_features,
            context=context,
            score_rating_fallbacks=score_rating_fallbacks,
            score_rating_priors=score_rating_priors,
        )
        # The cross-division layer is trained in a canonical FBS-minus-FCS
        # orientation. This keeps its learned division-level intercept valid even
        # for the rare game hosted by an FCS team or a reversed direct query.
        cross_orientation = -1.0 if home_is_fcs else 1.0
        model_features = {
            name: cross_orientation * features[name]
            for name in hybrid.feature_names
        }
        result = hybrid.predict(model_features)
        predicted_margin = cross_orientation * result.predicted_margin
        if cross_orientation > 0.0:
            home_probability = result.home_win_probability
            away_probability = result.away_win_probability
            interval_80 = result.margin_interval_80
            interval_95 = result.margin_interval_95
        else:
            home_probability = result.away_win_probability
            away_probability = result.home_win_probability
            interval_80 = (-result.margin_interval_80[1], -result.margin_interval_80[0])
            interval_95 = (-result.margin_interval_95[1], -result.margin_interval_95[0])
        unknown = tuple(
            team for team, key in ((home_team, home_key), (away_team, away_key)) if key is None
        )
        return V2Prediction(
            home_team=home_team,
            away_team=away_team,
            neutral_site=neutral_site,
            predicted_margin=predicted_margin,
            home_win_probability=home_probability,
            away_win_probability=away_probability,
            margin_interval_80=interval_80,
            margin_interval_95=interval_95,
            score_margin=components["score_margin"],
            preseason_ppa_edge=components["preseason_ppa_edge"],
            current_ppa_edge=components["current_ppa_edge"],
            preseason_success_edge=components["preseason_success_edge"],
            current_success_edge=components["current_success_edge"],
            home_field_points=components["home_field_points"],
            unknown_teams=unknown,
            model_scope="cross_division" if use_fcs_model else "fbs",
        )

    def predict(
        self,
        home_team: str,
        away_team: str,
        *,
        neutral_site: bool = False,
        home_id: int | None = None,
        away_id: int | None = None,
    ) -> V2Prediction:
        home_key = self.resolve_team(home_team, team_id=home_id)
        away_key = self.resolve_team(away_team, team_id=away_id)
        return self._predict_keys(
            home_key,
            away_key,
            home_team=home_team,
            away_team=away_team,
            neutral_site=neutral_site,
        )

    def predict_game(self, game: Any, season_games: Sequence[Any]) -> V2Prediction:
        context = game_context_features(game, season_games, self.team_locations)
        home_key = self.resolve_team(game.home_team, team_id=game.home_id)
        away_key = self.resolve_team(game.away_team, team_id=game.away_id)
        return self._predict_keys(
            home_key,
            away_key,
            home_team=game.home_team,
            away_team=game.away_team,
            neutral_site=game.neutral_site,
            context=context,
        )

    def rankings(self, *, limit: int | None = None) -> list[V2Ranking]:
        """Rank by average symmetric neutral-field margin versus the FBS field."""

        self._require_fitted()
        assert self.efficiency is not None
        keys = sorted(self.identities)
        ratings: dict[str, float] = {}
        for key in keys:
            pairwise: list[float] = []
            for opponent in keys:
                if opponent == key:
                    continue
                forward = self._predict_keys(
                    key,
                    opponent,
                    home_team=self.identities[key].team,
                    away_team=self.identities[opponent].team,
                    neutral_site=True,
                ).predicted_margin
                reverse = self._predict_keys(
                    opponent,
                    key,
                    home_team=self.identities[opponent].team,
                    away_team=self.identities[key].team,
                    neutral_site=True,
                ).predicted_margin
                pairwise.append(0.5 * (forward - reverse))
            ratings[key] = sum(pairwise) / len(pairwise) if pairwise else 0.0

        rows: list[V2Ranking] = []
        for key, identity in self.identities.items():
            prior = self.team_priors[key]
            current = self.efficiency.teams[key]
            features = self.preseason_features.get(key, {})
            rows.append(
                V2Ranking(
                    key=key,
                    team_id=identity.team_id,
                    team=identity.team,
                    conference=identity.conference,
                    rating=ratings[key],
                    preseason_efficiency_strength=(prior.offense_ppa or 0.0)
                    + (prior.defense_ppa_prevented or 0.0),
                    current_efficiency_strength=current.offense_ppa + current.defense_ppa_prevented,
                    games=current.games,
                    talent_current_missing=bool(features.get("talent_current_missing", 1.0)),
                    turnover_data_missing=bool(
                        features.get("returning_missing", 1.0)
                        or features.get("roster_missing", 1.0)
                    ),
                    roster_estimated=bool(features.get("roster_estimated", 0.0)),
                    roster_estimation_coverage=features.get(
                        "roster_estimation_coverage", 0.0
                    ),
                    draft_departures=int(features.get("draft_departures", 0.0)),
                    skill_usage_retention_rate=features.get(
                        "roster_skill_usage_retention_rate", 0.5
                    ),
                    ol_experience_retention_rate=features.get(
                        "roster_ol_experience_retention_rate", 0.5
                    ),
                    ol_draft_adjusted_retention_rate=features.get(
                        "roster_ol_draft_adjusted_retention_rate", 0.5
                    ),
                    ol_starter_retention_rate=(
                        None
                        if features.get(
                            "roster_ol_starter_retention_missing", 1.0
                        )
                        else features.get(
                            "roster_ol_starter_retention_rate", 0.5
                        )
                    ),
                    coach_staff_retention_rate=(
                        None
                        if features.get("coach_staff_retention_missing", 1.0)
                        else features.get("coach_staff_retention_rate", 0.5)
                    ),
                    coach_offense_staff_retention_rate=(
                        None
                        if features.get(
                            "coach_offense_staff_retention_missing", 1.0
                        )
                        else features.get(
                            "coach_offense_staff_retention_rate", 0.5
                        )
                    ),
                )
            )
        rows.sort(key=lambda row: (-row.rating, row.team))
        return rows if limit is None else rows[:limit]

    def to_dict(self) -> dict[str, Any]:
        self._require_fitted()
        assert (
            self.season is not None
            and self.as_of is not None
            and self.baseline is not None
            and self.prior_model is not None
            and self.efficiency is not None
            and self.hybrid is not None
        )
        return {
            "schema_version": (
                V2_ARTIFACT_SCHEMA_VERSION
                if self.score_prior_model is not None
                else 2
            ),
            "model_type": "roster_prior_dynamic_efficiency_hybrid_margin",
            "season": self.season,
            "as_of": self.as_of.isoformat(),
            "source_notes": list(self.source_notes),
            "team_locations": {
                key: list(value) for key, value in self.team_locations.items()
            },
            "identities": {key: asdict(value) for key, value in self.identities.items()},
            "preseason_features": self.preseason_features,
            "team_priors": {key: value.to_dict() for key, value in self.team_priors.items()},
            "baseline": self.baseline.to_dict(),
            "prior_model": self.prior_model.to_dict(),
            "score_prior_model": (
                None
                if self.score_prior_model is None
                else self.score_prior_model.to_dict()
            ),
            "score_rating_priors": self.score_rating_priors,
            "efficiency": self.efficiency.to_dict(),
            "hybrid": self.hybrid.to_dict(),
            "fcs_model": (
                None if self.fcs_model is None else self.fcs_model.to_dict()
            ),
            "evaluation": self.evaluation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CollegeFootballV2Model:
        artifact_schema = payload.get("schema_version")
        if artifact_schema not in {1, 2, V2_ARTIFACT_SCHEMA_VERSION}:
            raise ValueError(f"Unsupported V2 model schema: {payload.get('schema_version')!r}")
        if payload.get("model_type") != "roster_prior_dynamic_efficiency_hybrid_margin":
            raise ValueError(f"Unsupported V2 model type: {payload.get('model_type')!r}")
        model = cls()
        model.season = int(payload["season"])
        model.as_of = parse_datetime(payload["as_of"])
        model.source_notes = tuple(str(value) for value in payload.get("source_notes", ()))
        model.team_locations = {
            str(key): (float(value[0]), float(value[1]))
            for key, value in dict(payload.get("team_locations", {})).items()
        }
        model.identities = {
            str(key): TeamIdentity(**value) for key, value in dict(payload["identities"]).items()
        }
        model.preseason_features = {
            str(key): {str(name): float(value) for name, value in dict(features).items()}
            for key, features in dict(payload["preseason_features"]).items()
        }
        model.team_priors = {
            str(key): TeamEfficiencyPrior.from_dict(value)
            for key, value in dict(payload["team_priors"]).items()
        }
        model.baseline = PointRatingModel.from_dict(payload["baseline"])
        model.prior_model = PreseasonPriorModel.from_dict(payload["prior_model"])
        raw_score_prior_model = payload.get("score_prior_model")
        model.score_prior_model = (
            None
            if raw_score_prior_model is None
            else PreseasonScorePriorModel.from_dict(raw_score_prior_model)
        )
        model.score_rating_priors = {
            str(key): float(value)
            for key, value in dict(payload.get("score_rating_priors", {})).items()
        }
        model.efficiency = OpponentAdjustedEfficiencyModel.from_dict(payload["efficiency"])
        model.hybrid = HybridMarginModel.from_dict(payload["hybrid"])
        raw_fcs_model = payload.get("fcs_model")
        model.fcs_model = (
            None if raw_fcs_model is None else FCSModel.from_dict(raw_fcs_model)
        )
        model.evaluation = dict(payload.get("evaluation", {}))
        expected = set(model.identities)
        if set(model.team_priors) != expected or set(model.preseason_features) != expected:
            raise ValueError("V2 artifact team components have inconsistent keys")
        if model.score_rating_priors and set(model.score_rating_priors) != expected:
            raise ValueError("V2 score-rating priors do not cover the artifact team universe")
        if bool(model.score_prior_model) != bool(model.score_rating_priors):
            raise ValueError("V2 score-prior model and team ratings must be present together")
        if artifact_schema == V2_ARTIFACT_SCHEMA_VERSION and model.score_prior_model is None:
            raise ValueError("V2 schema 3 requires learned score-rating priors")
        efficiency_keys = set(model.efficiency.teams)
        extra_keys = efficiency_keys - expected
        if (
            not expected.issubset(efficiency_keys)
            or (model.efficiency.config.fbs_only and extra_keys)
            or any((model.efficiency.teams[key].classification or "").casefold() != "fcs"
                   for key in extra_keys)
        ):
            raise ValueError("V2 efficiency state does not cover the artifact team universe")
        if any(identity.key != key for key, identity in model.identities.items()):
            raise ValueError("V2 identity keys are inconsistent")
        numeric = [
            model.as_of.timestamp(),
            *model.hybrid.coefficients.values(),
            *model.score_rating_priors.values(),
        ]
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("V2 artifact contains non-finite values")
        model._rebuild_name_index()
        return model

    def save(self, path: str | Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> CollegeFootballV2Model:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in V2 model artifact {path}")
        return cls.from_dict(payload)
