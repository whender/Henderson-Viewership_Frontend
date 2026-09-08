"""Opponent-adjusted, time-decayed point ratings."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from cfbpredict.games import Game, atomic_write_json, completed_games, parse_datetime

ARTIFACT_SCHEMA_VERSION = 2


class ModelNotFittedError(RuntimeError):
    """Raised when predictions are requested before fitting a model."""


class InsufficientDataError(ValueError):
    """Raised when there are too few valid results to estimate ratings."""


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Hyperparameters for the baseline point-rating model."""

    ridge_alpha: float = 0.5
    half_life_days: float = 170.0
    home_field_prior: float = 2.5
    home_field_prior_weight: float = 4.0
    team_home_field_prior_weight: float = 20.0
    min_residual_sigma: float = 7.0
    result_buffer_hours: float = 12.0
    fbs_only: bool = True
    margin_diminishing_threshold: float | None = None
    margin_tail_scale: float = 14.0

    def validate(self) -> None:
        numeric = {
            "ridge_alpha": self.ridge_alpha,
            "half_life_days": self.half_life_days,
            "home_field_prior": self.home_field_prior,
            "home_field_prior_weight": self.home_field_prior_weight,
            "team_home_field_prior_weight": self.team_home_field_prior_weight,
            "min_residual_sigma": self.min_residual_sigma,
            "result_buffer_hours": self.result_buffer_hours,
            "margin_tail_scale": self.margin_tail_scale,
        }
        for name, value in numeric.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.ridge_alpha < 0:
            raise ValueError("ridge_alpha must be non-negative")
        if self.half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if self.home_field_prior_weight < 0:
            raise ValueError("home_field_prior_weight must be non-negative")
        if self.team_home_field_prior_weight < 0:
            raise ValueError("team_home_field_prior_weight must be non-negative")
        if self.min_residual_sigma <= 0:
            raise ValueError("min_residual_sigma must be positive")
        if self.result_buffer_hours < 0:
            raise ValueError("result_buffer_hours must be non-negative")
        if self.margin_diminishing_threshold is not None:
            if not math.isfinite(self.margin_diminishing_threshold):
                raise ValueError("margin_diminishing_threshold must be finite")
            if self.margin_diminishing_threshold <= 0:
                raise ValueError("margin_diminishing_threshold must be positive")
        if self.margin_tail_scale < 0:
            raise ValueError("margin_tail_scale must be non-negative")


@dataclass(frozen=True, slots=True)
class TeamSummary:
    key: str
    team_id: int | None
    team: str
    classification: str | None
    rating: float
    record_season: int
    games: int
    effective_games: float
    wins: int
    losses: int
    ties: int
    last_played: str


@dataclass(frozen=True, slots=True)
class Prediction:
    home_team: str
    away_team: str
    neutral_site: bool
    home_rating: float
    away_rating: float
    home_field_points: float
    predicted_margin: float
    home_win_probability: float
    away_win_probability: float
    margin_interval_80: tuple[float, float]
    margin_interval_95: tuple[float, float]
    unknown_teams: tuple[str, ...]

    @property
    def favorite(self) -> str:
        if self.predicted_margin > 0:
            return self.home_team
        if self.predicted_margin < 0:
            return self.away_team
        return "Pick'em"


def _is_fbs(value: str | None) -> bool:
    return value is not None and value.casefold() == "fbs"


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def diminishing_margin(
    margin: float,
    *,
    threshold: float | None,
    tail_scale: float,
) -> float:
    """Compress blowout margins while preserving sign and ordinary results.

    Margins through ``threshold`` are unchanged. Beyond it, a logarithmic tail has
    unit slope at the join and progressively discounts additional points. A zero
    ``tail_scale`` produces a hard cap, which is useful as a comparison candidate.
    """

    value = float(margin)
    if threshold is None or abs(value) <= threshold:
        return value
    sign = 1.0 if value > 0.0 else -1.0
    excess = abs(value) - threshold
    if tail_scale == 0.0:
        return sign * threshold
    return sign * (threshold + tail_scale * math.log1p(excess / tail_scale))


class PointRatingModel:
    """Estimate each team's neutral-field value in points above average.

    A completed game's margin is modeled as::

        home_rating - away_rating + home_field_advantage

    Ridge shrinkage stabilizes teams with few observations. Exponential sample
    weights let recent results matter more without discarding prior seasons.
    """

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()
        self.config.validate()
        self.ratings: dict[str, float] = {}
        self.teams: dict[str, TeamSummary] = {}
        self.home_field_advantage = self.config.home_field_prior
        self.team_home_field_adjustments: dict[str, float] = {}
        self.residual_sigma = 14.0
        self.margin_error_80 = 1.281_551_565_545 * self.residual_sigma
        self.margin_error_95 = 1.959_963_984_54 * self.residual_sigma
        self.margin_interval_method = "normal_training_residuals"
        self.probability_intercept = 0.0
        self.probability_slope = 1.6 / self.residual_sigma
        self.probability_method = "residual_logistic_approximation"
        self.as_of: datetime | None = None
        self.trained_at: datetime | None = None
        self.training_games = 0
        self._name_index: dict[str, str] = {}

    @property
    def is_fitted(self) -> bool:
        return bool(self.ratings) and self.as_of is not None

    def fit(
        self,
        games: Iterable[Game],
        *,
        as_of: datetime | None = None,
        live_results: bool = False,
    ) -> PointRatingModel:
        """Fit buffered historical results, or confirmed finals from a live snapshot."""
        if live_results and as_of is None:
            as_of = datetime.now(UTC)
        supplied_games = list(games)
        if not supplied_games:
            raise InsufficientDataError("No games were supplied")

        if as_of is None:
            finished = completed_games(supplied_games)
            if self.config.fbs_only:
                finished = [
                    game
                    for game in finished
                    if _is_fbs(game.home_classification) and _is_fbs(game.away_classification)
                ]
            if not finished:
                raise InsufficientDataError("No completed eligible games were supplied")
            latest = max(game.start_date for game in finished)
            cutoff = latest + timedelta(hours=self.config.result_buffer_hours, microseconds=1)
        else:
            cutoff = as_of.astimezone(UTC) if as_of.tzinfo else as_of.replace(tzinfo=UTC)

        usable = completed_games(
            supplied_games,
            as_of=cutoff,
            result_buffer=timedelta(hours=0 if live_results else self.config.result_buffer_hours),
        )
        if self.config.fbs_only:
            usable = [
                game
                for game in usable
                if _is_fbs(game.home_classification) and _is_fbs(game.away_classification)
            ]
        if len(usable) < 2:
            scope = "FBS-vs-FBS " if self.config.fbs_only else ""
            raise InsufficientDataError(f"At least two completed {scope}games are required")

        usable.sort(key=lambda game: (game.start_date, game.id))
        team_keys = sorted({game.home_key for game in usable} | {game.away_key for game in usable})
        team_index = {key: index for index, key in enumerate(team_keys)}

        team_count = len(team_keys)
        design = np.zeros((len(usable), 2 * team_count + 1), dtype=np.float64)
        margins = np.empty(len(usable), dtype=np.float64)
        weights = np.empty(len(usable), dtype=np.float64)

        for row, game in enumerate(usable):
            design[row, team_index[game.home_key]] = 1.0
            design[row, team_index[game.away_key]] = -1.0
            if not game.neutral_site:
                design[row, team_count + team_index[game.home_key]] = 1.0
                design[row, -1] = 1.0
            margins[row] = diminishing_margin(
                game.margin,
                threshold=self.config.margin_diminishing_threshold,
                tail_scale=self.config.margin_tail_scale,
            )
            age_days = max((cutoff - game.start_date).total_seconds() / 86_400.0, 0.0)
            weights[row] = 0.5 ** (age_days / self.config.half_life_days)

        weighted_design = design * weights[:, None]
        system = design.T @ weighted_design
        target = design.T @ (weights * margins)

        diagonal = np.full(2 * team_count + 1, self.config.ridge_alpha)
        diagonal[team_count : 2 * team_count] = self.config.team_home_field_prior_weight
        diagonal[-1] = self.config.home_field_prior_weight
        system += np.diag(diagonal)
        target[-1] += self.config.home_field_prior_weight * self.config.home_field_prior

        try:
            coefficients = np.linalg.solve(system, target)
        except np.linalg.LinAlgError:
            coefficients = np.linalg.lstsq(system, target, rcond=None)[0]

        fitted = design @ coefficients
        if not np.isfinite(coefficients).all() or not np.isfinite(fitted).all():
            raise ValueError("Training data produced non-finite model coefficients")
        residuals = margins - fitted
        weighted_mse = float(np.average(np.square(residuals), weights=weights))

        self.ratings = {key: float(coefficients[index]) for key, index in team_index.items()}
        self.team_home_field_adjustments = {
            key: float(coefficients[team_count + index])
            for key, index in team_index.items()
        }
        self.home_field_advantage = float(coefficients[-1])
        self.residual_sigma = max(math.sqrt(weighted_mse), self.config.min_residual_sigma)
        self.margin_error_80 = 1.281_551_565_545 * self.residual_sigma
        self.margin_error_95 = 1.959_963_984_54 * self.residual_sigma
        self.margin_interval_method = "normal_training_residuals"
        self.probability_intercept = 0.0
        self.probability_slope = 1.6 / self.residual_sigma
        self.probability_method = "residual_logistic_approximation"
        self.as_of = cutoff
        self.trained_at = datetime.now(UTC)
        self.training_games = len(usable)
        self.teams = self._summarize_teams(usable, weights)
        self._rebuild_name_index()
        return self

    def _summarize_teams(
        self, games: Sequence[Game], weights: np.ndarray
    ) -> dict[str, TeamSummary]:
        raw: dict[str, dict[str, Any]] = {}
        for game, weight in zip(games, weights, strict=True):
            home_result = 1 if game.margin > 0 else (-1 if game.margin < 0 else 0)
            away_result = -home_result
            for key, team_id, name, classification, result in (
                (
                    game.home_key,
                    game.home_id,
                    game.home_team,
                    game.home_classification,
                    home_result,
                ),
                (
                    game.away_key,
                    game.away_id,
                    game.away_team,
                    game.away_classification,
                    away_result,
                ),
            ):
                entry = raw.setdefault(
                    key,
                    {
                        "team_id": team_id,
                        "team": name,
                        "classification": classification,
                        "record_season": game.season,
                        "games": 0,
                        "effective_games": 0.0,
                        "wins": 0,
                        "losses": 0,
                        "ties": 0,
                        "last_played": game.start_date,
                    },
                )
                entry["team_id"] = team_id
                entry["team"] = name
                entry["classification"] = classification
                entry["effective_games"] += float(weight)
                entry["last_played"] = max(entry["last_played"], game.start_date)
                if game.season > entry["record_season"]:
                    entry["record_season"] = game.season
                    entry["games"] = 0
                    entry["wins"] = 0
                    entry["losses"] = 0
                    entry["ties"] = 0
                if game.season == entry["record_season"]:
                    entry["games"] += 1
                    entry["wins"] += int(result > 0)
                    entry["losses"] += int(result < 0)
                    entry["ties"] += int(result == 0)

        return {
            key: TeamSummary(
                key=key,
                team_id=entry["team_id"],
                team=entry["team"],
                classification=entry["classification"],
                rating=self.ratings[key],
                record_season=entry["record_season"],
                games=entry["games"],
                effective_games=entry["effective_games"],
                wins=entry["wins"],
                losses=entry["losses"],
                ties=entry["ties"],
                last_played=entry["last_played"].isoformat(),
            )
            for key, entry in raw.items()
        }

    def _rebuild_name_index(self) -> None:
        self._name_index = {
            " ".join(summary.team.casefold().split()): key for key, summary in self.teams.items()
        }

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise ModelNotFittedError("Fit or load a model before predicting")

    def resolve_team(self, team: str | int, *, team_id: int | None = None) -> str | None:
        self._require_fitted()
        if team_id is not None:
            candidate = f"id:{team_id}"
            return candidate if candidate in self.ratings else None
        if isinstance(team, int) or (isinstance(team, str) and team.strip().isdigit()):
            candidate = f"id:{int(team)}"
            return candidate if candidate in self.ratings else None
        normalized = " ".join(str(team).casefold().split())
        return self._name_index.get(normalized)

    def suggest_teams(self, query: str, *, limit: int = 5) -> list[str]:
        normalized = query.casefold().strip()
        starts = [
            summary.team
            for summary in self.teams.values()
            if summary.team.casefold().startswith(normalized)
        ]
        contains = [
            summary.team
            for summary in self.teams.values()
            if normalized in summary.team.casefold() and summary.team not in starts
        ]
        return sorted(starts)[:limit] + sorted(contains)[: max(0, limit - len(starts))]

    def predict(
        self,
        home_team: str,
        away_team: str,
        *,
        neutral_site: bool = False,
        home_id: int | None = None,
        away_id: int | None = None,
    ) -> Prediction:
        self._require_fitted()
        home_key = self.resolve_team(home_team, team_id=home_id)
        away_key = self.resolve_team(away_team, team_id=away_id)
        normalized_home = " ".join(str(home_team).casefold().split())
        normalized_away = " ".join(str(away_team).casefold().split())
        if (home_key is not None and home_key == away_key) or normalized_home == normalized_away:
            raise ValueError("home_team and away_team must be different teams")
        unknown: list[str] = []
        if home_key is None:
            unknown.append(home_team)
        if away_key is None:
            unknown.append(away_team)

        home_rating = self.ratings.get(home_key or "", 0.0)
        away_rating = self.ratings.get(away_key or "", 0.0)
        home_points = (
            0.0
            if neutral_site
            else self.home_field_advantage
            + self.team_home_field_adjustments.get(home_key or "", 0.0)
        )
        margin = home_rating - away_rating + home_points
        probability = _sigmoid(self.probability_intercept + self.probability_slope * margin)
        return Prediction(
            home_team=home_team,
            away_team=away_team,
            neutral_site=neutral_site,
            home_rating=home_rating,
            away_rating=away_rating,
            home_field_points=home_points,
            predicted_margin=margin,
            home_win_probability=probability,
            away_win_probability=1.0 - probability,
            margin_interval_80=(margin - self.margin_error_80, margin + self.margin_error_80),
            margin_interval_95=(margin - self.margin_error_95, margin + self.margin_error_95),
            unknown_teams=tuple(unknown),
        )

    def predict_game(self, game: Game) -> Prediction:
        return self.predict(
            game.home_team,
            game.away_team,
            neutral_site=game.neutral_site,
            home_id=game.home_id,
            away_id=game.away_id,
        )

    def calibrate_probabilities(
        self,
        predicted_margins: Sequence[float],
        home_wins: Sequence[bool | int],
    ) -> PointRatingModel:
        """Fit Platt calibration from temporal out-of-sample predictions.

        Callers are responsible for supplying walk-forward predictions. Training-set
        fitted margins should not be used here because they give optimistic probabilities.
        """

        self._require_fitted()
        if len(predicted_margins) != len(home_wins):
            raise ValueError("predicted_margins and home_wins must be the same length")
        if len(predicted_margins) < 25:
            raise InsufficientDataError("At least 25 out-of-sample games are needed")

        x = np.asarray(predicted_margins, dtype=np.float64)
        y = np.asarray(home_wins, dtype=np.float64)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("probability calibration values must be finite")
        if not np.isin(y, [0.0, 1.0]).all() or len(np.unique(y)) < 2:
            raise ValueError("home_wins must contain both 0 and 1 outcomes")

        design = np.column_stack((np.ones_like(x), x))
        beta = np.asarray([self.probability_intercept, self.probability_slope])
        penalty = np.diag([0.01, 0.01])
        for _ in range(50):
            logits = np.clip(design @ beta, -30.0, 30.0)
            probabilities = 1.0 / (1.0 + np.exp(-logits))
            variance = np.clip(probabilities * (1.0 - probabilities), 1e-6, None)
            gradient = design.T @ (y - probabilities) - penalty @ beta
            hessian = design.T @ (variance[:, None] * design) + penalty
            update = np.linalg.solve(hessian, gradient)
            beta += update
            if float(np.max(np.abs(update))) < 1e-8:
                break

        if beta[1] <= 0:
            raise ValueError("Calibration produced a non-positive margin slope")
        self.probability_intercept = float(beta[0])
        self.probability_slope = float(beta[1])
        self.probability_method = "temporal_platt_scaling"
        return self

    def calibrate_uncertainty(
        self,
        actual_margins: Sequence[float],
        predicted_margins: Sequence[float],
    ) -> PointRatingModel:
        """Set empirical margin intervals from temporal out-of-sample residuals."""

        self._require_fitted()
        if len(actual_margins) != len(predicted_margins):
            raise ValueError("actual_margins and predicted_margins must be the same length")
        if len(actual_margins) < 25:
            raise InsufficientDataError("At least 25 out-of-sample games are needed")
        errors = np.abs(
            np.asarray(actual_margins, dtype=np.float64)
            - np.asarray(predicted_margins, dtype=np.float64)
        )
        if not np.isfinite(errors).all():
            raise ValueError("margin calibration values must be finite")
        self.margin_error_80 = max(float(np.quantile(errors, 0.80)), 1.0)
        self.margin_error_95 = max(float(np.quantile(errors, 0.95)), self.margin_error_80)
        self.margin_interval_method = "temporal_absolute_residual_quantiles"
        self.residual_sigma = max(
            float(math.sqrt(float(np.mean(np.square(errors))))),
            self.config.min_residual_sigma,
        )
        return self

    def rankings(
        self,
        *,
        limit: int | None = None,
        min_games: int = 1,
        classification: str | None = "fbs",
    ) -> list[TeamSummary]:
        self._require_fitted()
        rows = [
            team
            for team in self.teams.values()
            if team.games >= min_games
            and (
                classification is None
                or (team.classification or "").casefold() == classification.casefold()
            )
        ]
        rows.sort(key=lambda team: (-team.rating, team.team))
        return rows if limit is None else rows[:limit]

    def to_dict(self) -> dict[str, Any]:
        self._require_fitted()
        assert self.as_of is not None and self.trained_at is not None
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "model_type": "time_decayed_opponent_adjusted_point_rating",
            "trained_at": self.trained_at.isoformat(),
            "as_of": self.as_of.isoformat(),
            "training_games": self.training_games,
            "config": asdict(self.config),
            "home_field_advantage": self.home_field_advantage,
            "team_home_field_adjustments": self.team_home_field_adjustments,
            "residual_sigma": self.residual_sigma,
            "margin_intervals": {
                "method": self.margin_interval_method,
                "error_80": self.margin_error_80,
                "error_95": self.margin_error_95,
            },
            "probability": {
                "method": self.probability_method,
                "intercept": self.probability_intercept,
                "slope": self.probability_slope,
            },
            "ratings": self.ratings,
            "teams": {key: asdict(summary) for key, summary in self.teams.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PointRatingModel:
        if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported model schema version: {payload.get('schema_version')!r}")
        model = cls(ModelConfig(**payload["config"]))
        model.ratings = {key: float(value) for key, value in payload["ratings"].items()}
        model.teams = {key: TeamSummary(**summary) for key, summary in payload["teams"].items()}
        model.home_field_advantage = float(payload["home_field_advantage"])
        model.team_home_field_adjustments = {
            key: float(value)
            for key, value in payload.get("team_home_field_adjustments", {}).items()
        }
        model.residual_sigma = float(payload["residual_sigma"])
        margin_intervals = payload.get("margin_intervals", {})
        model.margin_error_80 = float(
            margin_intervals.get("error_80", 1.281_551_565_545 * model.residual_sigma)
        )
        model.margin_error_95 = float(
            margin_intervals.get("error_95", 1.959_963_984_54 * model.residual_sigma)
        )
        model.margin_interval_method = str(
            margin_intervals.get("method", "normal_training_residuals")
        )
        probability = payload.get("probability", {})
        model.probability_intercept = float(probability.get("intercept", 0.0))
        model.probability_slope = float(probability.get("slope", 1.6 / model.residual_sigma))
        model.probability_method = str(probability.get("method", "residual_logistic_approximation"))
        model.as_of = parse_datetime(payload["as_of"])
        model.trained_at = parse_datetime(payload["trained_at"])
        model.training_games = int(payload["training_games"])
        numeric_values = [
            *model.ratings.values(),
            *(summary.rating for summary in model.teams.values()),
            model.home_field_advantage,
            *model.team_home_field_adjustments.values(),
            model.residual_sigma,
            model.margin_error_80,
            model.margin_error_95,
            model.probability_intercept,
            model.probability_slope,
        ]
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("Model artifact contains non-finite numeric values")
        if model.residual_sigma <= 0:
            raise ValueError("Model artifact residual_sigma must be positive")
        if not 0 <= model.margin_error_80 <= model.margin_error_95:
            raise ValueError("Model artifact margin intervals are invalid")
        if model.probability_slope <= 0:
            raise ValueError("Model artifact probability slope must be positive")
        if model.training_games < 1:
            raise ValueError("Model artifact training_games must be positive")
        model._rebuild_name_index()
        return model

    def save(self, path: str | Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> PointRatingModel:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in model artifact {path}")
        return cls.from_dict(payload)
