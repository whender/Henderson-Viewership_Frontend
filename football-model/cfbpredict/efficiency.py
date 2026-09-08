"""Leakage-safe, opponent-adjusted offense and defense efficiency ratings.

The CFBD advanced game endpoint returns one row per team and game.  For a
metric such as PPA or success rate, this module models an offensive result as::

    result = baseline + offense_effect - defense_prevention_effect

Both effects therefore use the intuitive direction where higher is better.
Observations are joined to :class:`~cfbpredict.games.Game` objects by game ID,
and only completed games whose conservative result-availability time is
strictly before ``as_of`` are eligible for fitting.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from numbers import Real
from typing import Any, Self

import numpy as np

from cfbpredict.games import Game, canonical_team_key, parse_datetime

EFFICIENCY_SCHEMA_VERSION = 2


class EfficiencyDataError(ValueError):
    """Raised when an advanced-stat row cannot be normalized safely."""


class InsufficientEfficiencyDataError(ValueError):
    """Raised when no eligible team-game efficiency samples remain."""


class EfficiencyModelNotFittedError(RuntimeError):
    """Raised when fitted efficiency ratings are requested too early."""


def _first(record: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return default


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EfficiencyDataError(f"{field} must be numeric, not boolean")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EfficiencyDataError(f"Invalid {field}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise EfficiencyDataError(f"{field} must be finite")
    return parsed


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise EfficiencyDataError(f"{field} must be an integer, not boolean")
    if isinstance(value, Real) and not float(value).is_integer():
        raise EfficiencyDataError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EfficiencyDataError(f"Invalid {field}: {value!r}") from exc
    if parsed < minimum:
        raise EfficiencyDataError(f"{field} must be at least {minimum}")
    return parsed


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_fbs(value: str | None) -> bool:
    return value is not None and value.casefold() == "fbs"


@dataclass(frozen=True, slots=True)
class UnitEfficiencyObservation:
    """The play-weighted fields needed from one offense or defense unit."""

    plays: int
    ppa: float
    total_ppa: float
    success_rate: float

    @classmethod
    def from_cfbd(
        cls,
        record: Mapping[str, Any],
        *,
        context: str = "unit",
    ) -> UnitEfficiencyObservation:
        if not isinstance(record, Mapping):
            raise EfficiencyDataError(f"{context} must be an object")
        plays = _integer(_first(record, "plays"), f"{context}.plays", minimum=1)
        ppa = _finite_float(_first(record, "ppa"), f"{context}.ppa")
        total_value = _first(record, "totalPPA", "totalPpa", "total_ppa")
        total_ppa = ppa * plays if total_value is None else _finite_float(
            total_value, f"{context}.totalPPA"
        )
        if not math.isclose(total_ppa, ppa * plays, rel_tol=1e-6, abs_tol=1e-6):
            raise EfficiencyDataError(
                f"{context}.totalPPA is inconsistent with ppa and plays"
            )
        success_rate = _finite_float(
            _first(record, "successRate", "success_rate"), f"{context}.successRate"
        )
        if not 0.0 <= success_rate <= 1.0:
            raise EfficiencyDataError(f"{context}.successRate must be between 0 and 1")
        return cls(
            plays=plays,
            ppa=ppa,
            total_ppa=total_ppa,
            success_rate=success_rate,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> UnitEfficiencyObservation:
        return cls.from_cfbd(payload)


@dataclass(frozen=True, slots=True)
class AdvancedGameObservation:
    """Normalized CFBD ``/stats/game/advanced`` team-game row."""

    game_id: int
    season: int
    season_type: str
    week: int
    team: str
    opponent: str
    offense: UnitEfficiencyObservation
    defense: UnitEfficiencyObservation

    @classmethod
    def from_cfbd(cls, record: Mapping[str, Any]) -> AdvancedGameObservation:
        if not isinstance(record, Mapping):
            raise EfficiencyDataError("Advanced game stat row must be an object")
        game_id = _integer(
            _first(record, "gameId", "game_id"), "gameId", minimum=1
        )
        season = _integer(_first(record, "season", "year"), "season", minimum=1)
        week = _integer(_first(record, "week"), "week")
        team_value = _first(record, "team")
        opponent_value = _first(record, "opponent")
        if not isinstance(team_value, str) or not team_value.strip():
            raise EfficiencyDataError(f"Game {game_id} is missing team")
        if not isinstance(opponent_value, str) or not opponent_value.strip():
            raise EfficiencyDataError(f"Game {game_id} is missing opponent")
        team = team_value.strip()
        opponent = opponent_value.strip()
        if _normalized_name(team) == _normalized_name(opponent):
            raise EfficiencyDataError(f"Game {game_id} has the same team and opponent")
        season_type = str(
            _first(record, "seasonType", "season_type", default="regular")
        ).strip()
        if not season_type:
            raise EfficiencyDataError(f"Game {game_id} is missing seasonType")
        return cls(
            game_id=game_id,
            season=season,
            season_type=season_type,
            week=week,
            team=team,
            opponent=opponent,
            offense=UnitEfficiencyObservation.from_cfbd(
                _first(record, "offense"), context=f"game {game_id} offense"
            ),
            defense=UnitEfficiencyObservation.from_cfbd(
                _first(record, "defense"), context=f"game {game_id} defense"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "season": self.season,
            "season_type": self.season_type,
            "week": self.week,
            "team": self.team,
            "opponent": self.opponent,
            "offense": self.offense.to_dict(),
            "defense": self.defense.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AdvancedGameObservation:
        return cls.from_cfbd(payload)


def normalize_advanced_game_stats(
    records: Iterable[AdvancedGameObservation | Mapping[str, Any]],
) -> list[AdvancedGameObservation]:
    """Normalize and de-duplicate advanced rows by game and team.

    The last duplicate wins, matching the behavior of the game normalizer.
    """

    by_key: dict[tuple[int, str], AdvancedGameObservation] = {}
    for record in records:
        if isinstance(record, AdvancedGameObservation):
            observation = record
        elif isinstance(record, Mapping):
            observation = AdvancedGameObservation.from_cfbd(record)
        else:
            raise EfficiencyDataError(
                f"Expected an advanced game stat object, received {type(record).__name__}"
            )
        by_key[(observation.game_id, _normalized_name(observation.team))] = observation
    return sorted(
        by_key.values(),
        key=lambda row: (row.season, row.week, row.game_id, _normalized_name(row.team)),
    )


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """One already-weighted offense-versus-defense metric sample."""

    offense_key: str
    defense_key: str
    value: float
    weight: float
    game_id: int | None = None

    def validate(self) -> None:
        if not self.offense_key or not self.defense_key:
            raise EfficiencyDataError("Metric observation team keys cannot be empty")
        if self.offense_key == self.defense_key:
            raise EfficiencyDataError("Metric observation teams must be different")
        if not math.isfinite(self.value):
            raise EfficiencyDataError("Metric observation value must be finite")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise EfficiencyDataError("Metric observation weight must be positive and finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MetricObservation:
        observation = cls(
            offense_key=str(payload["offense_key"]),
            defense_key=str(payload["defense_key"]),
            value=_finite_float(payload["value"], "value"),
            weight=_finite_float(payload["weight"], "weight"),
            game_id=(
                None
                if payload.get("game_id") is None
                else _integer(payload["game_id"], "game_id", minimum=1)
            ),
        )
        observation.validate()
        return observation


@dataclass(frozen=True, slots=True)
class MetricRatings:
    """Opponent-adjusted effects for one efficiency metric.

    ``offense`` and ``defense`` contain effects around ``baseline``.  A matchup
    estimate is ``baseline + offense[team] - defense[opponent]``.  Thus a larger
    defensive value represents more PPA or success rate prevented.
    """

    metric: str
    prior_mean: float
    baseline: float
    offense: dict[str, float]
    defense: dict[str, float]
    residual_rmse: float
    samples: int
    total_weight: float

    def predict(self, offense_key: str, defense_key: str) -> float:
        return (
            self.baseline
            + self.offense.get(offense_key, 0.0)
            - self.defense.get(defense_key, 0.0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "prior_mean": self.prior_mean,
            "baseline": self.baseline,
            "offense": self.offense,
            "defense": self.defense,
            "residual_rmse": self.residual_rmse,
            "samples": self.samples,
            "total_weight": self.total_weight,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MetricRatings:
        ratings = cls(
            metric=str(payload["metric"]),
            prior_mean=_finite_float(payload["prior_mean"], "prior_mean"),
            baseline=_finite_float(payload["baseline"], "baseline"),
            offense={
                str(key): _finite_float(value, f"offense[{key!r}]")
                for key, value in dict(payload["offense"]).items()
            },
            defense={
                str(key): _finite_float(value, f"defense[{key!r}]")
                for key, value in dict(payload["defense"]).items()
            },
            residual_rmse=_finite_float(payload["residual_rmse"], "residual_rmse"),
            samples=_integer(payload["samples"], "samples"),
            total_weight=_finite_float(payload["total_weight"], "total_weight"),
        )
        if not ratings.metric:
            raise EfficiencyDataError("Metric name cannot be empty")
        if ratings.residual_rmse < 0:
            raise EfficiencyDataError("residual_rmse must be non-negative")
        if ratings.total_weight < 0:
            raise EfficiencyDataError("total_weight must be non-negative")
        if (ratings.samples == 0) != (ratings.total_weight == 0):
            raise EfficiencyDataError(
                "Zero-sample metric ratings must have zero total_weight and vice versa"
            )
        if set(ratings.offense) != set(ratings.defense):
            raise EfficiencyDataError("Offense and defense rating keys must match")
        return ratings


def solve_weighted_ridge(
    observations: Iterable[MetricObservation],
    *,
    metric: str,
    prior_mean: float,
    ridge_alpha: float,
    baseline_prior_weight: float = 0.0,
    offense_priors: Mapping[str, float] | None = None,
    defense_priors: Mapping[str, float] | None = None,
    offense_precision: Mapping[str, float] | None = None,
    defense_precision: Mapping[str, float] | None = None,
) -> MetricRatings:
    """Solve a generalized prior-centered, play-weighted metric model.

    Offensive priors are natural metric means for performance against an average
    defense; defensive priors are positive-good prevention effects. Precision
    values are positive multipliers on ``ridge_alpha`` and default to one. The
    offense penalty is coupled to ``baseline + offense_effect``, so a fitted
    baseline cannot move a high-confidence natural prior away from its mean.
    """

    samples = list(observations)
    if not samples:
        raise InsufficientEfficiencyDataError("No metric observations were supplied")
    if not metric.strip():
        raise ValueError("metric cannot be empty")
    numeric = {
        "prior_mean": prior_mean,
        "ridge_alpha": ridge_alpha,
        "baseline_prior_weight": baseline_prior_weight,
    }
    for name, value in numeric.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if ridge_alpha <= 0:
        raise ValueError("ridge_alpha must be positive")
    if baseline_prior_weight < 0:
        raise ValueError("baseline_prior_weight must be non-negative")
    for sample in samples:
        sample.validate()

    raw_offense_priors = dict(offense_priors or {})
    raw_defense_priors = dict(defense_priors or {})
    raw_offense_precision = dict(offense_precision or {})
    raw_defense_precision = dict(defense_precision or {})
    team_keys = sorted(
        {sample.offense_key for sample in samples}
        | {sample.defense_key for sample in samples}
        | set(raw_offense_priors)
        | set(raw_defense_priors)
        | set(raw_offense_precision)
        | set(raw_defense_precision)
    )
    if len(team_keys) < 2:
        raise InsufficientEfficiencyDataError("At least two teams are required")
    team_index = {key: index for index, key in enumerate(team_keys)}
    offense_prior = np.asarray(
        [
            _finite_float(
                raw_offense_priors.get(key, prior_mean), f"offense prior {key}"
            )
            for key in team_keys
        ],
        dtype=np.float64,
    )
    defense_prior = np.asarray(
        [
            _finite_float(raw_defense_priors.get(key, 0.0), f"defense prior {key}")
            for key in team_keys
        ],
        dtype=np.float64,
    )
    offense_precision_values = np.asarray(
        [
            _finite_float(raw_offense_precision.get(key, 1.0), f"offense precision {key}")
            for key in team_keys
        ],
        dtype=np.float64,
    )
    defense_precision_values = np.asarray(
        [
            _finite_float(raw_defense_precision.get(key, 1.0), f"defense precision {key}")
            for key in team_keys
        ],
        dtype=np.float64,
    )
    if np.any(offense_precision_values <= 0) or np.any(defense_precision_values <= 0):
        raise ValueError("Team prior precision multipliers must be positive")

    team_count = len(team_keys)
    coefficient_count = 1 + 2 * team_count
    design = np.zeros((len(samples), coefficient_count), dtype=np.float64)
    targets = np.empty(len(samples), dtype=np.float64)
    weights = np.empty(len(samples), dtype=np.float64)
    for row, sample in enumerate(samples):
        design[row, 0] = 1.0
        design[row, 1 + team_index[sample.offense_key]] = 1.0
        design[row, 1 + team_count + team_index[sample.defense_key]] = -1.0
        targets[row] = sample.value
        weights[row] = sample.weight

    system = design.T @ (design * weights[:, None])
    target = design.T @ (weights * targets)
    system[0, 0] += baseline_prior_weight
    target[0] += baseline_prior_weight * prior_mean
    for index in range(team_count):
        offense_column = 1 + index
        offense_penalty = ridge_alpha * offense_precision_values[index]
        system[0, 0] += offense_penalty
        system[0, offense_column] += offense_penalty
        system[offense_column, 0] += offense_penalty
        system[offense_column, offense_column] += offense_penalty
        target[0] += offense_penalty * offense_prior[index]
        target[offense_column] += offense_penalty * offense_prior[index]

        defense_column = 1 + team_count + index
        defense_penalty = ridge_alpha * defense_precision_values[index]
        system[defense_column, defense_column] += defense_penalty
        target[defense_column] += defense_penalty * defense_prior[index]

    try:
        solution = np.linalg.solve(system, target)
    except np.linalg.LinAlgError:
        solution = np.linalg.lstsq(system, target, rcond=None)[0]
    fitted = design @ solution
    if not np.isfinite(solution).all() or not np.isfinite(fitted).all():
        raise EfficiencyDataError("Efficiency observations produced non-finite ratings")
    residual_rmse = math.sqrt(
        float(np.average(np.square(targets - fitted), weights=weights))
    )
    offense_values = solution[1 : 1 + team_count]
    defense_values = solution[1 + team_count :]
    return MetricRatings(
        metric=metric,
        prior_mean=float(prior_mean),
        baseline=float(solution[0]),
        offense={key: float(offense_values[index]) for key, index in team_index.items()},
        defense={key: float(defense_values[index]) for key, index in team_index.items()},
        residual_rmse=float(residual_rmse),
        samples=len(samples),
        total_weight=float(np.sum(weights)),
    )


@dataclass(frozen=True, slots=True)
class EfficiencyConfig:
    """Hyperparameters expressed in play-equivalent units where applicable."""

    ridge_plays: float = 180.0
    baseline_prior_plays: float = 400.0
    half_life_days: float = 120.0
    ppa_prior: float = 0.0
    success_rate_prior: float = 0.42
    result_buffer_hours: float = 12.0
    fbs_only: bool = True

    def validate(self) -> None:
        numeric = {
            "ridge_plays": self.ridge_plays,
            "baseline_prior_plays": self.baseline_prior_plays,
            "half_life_days": self.half_life_days,
            "ppa_prior": self.ppa_prior,
            "success_rate_prior": self.success_rate_prior,
            "result_buffer_hours": self.result_buffer_hours,
        }
        for name, value in numeric.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.ridge_plays <= 0:
            raise ValueError("ridge_plays must be positive")
        if self.baseline_prior_plays < 0:
            raise ValueError("baseline_prior_plays must be non-negative")
        if self.half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if not 0 <= self.success_rate_prior <= 1:
            raise ValueError("success_rate_prior must be between 0 and 1")
        if self.result_buffer_hours < 4:
            raise ValueError(
                "result_buffer_hours must be at least 4 because CFBD games do not "
                "include a historical final-result timestamp"
            )


@dataclass(frozen=True, slots=True)
class TeamEfficiencyPrior:
    """Pregame unit means and their relative confidence for one team.

    Offensive means are on the natural PPA/success-rate scales. Defensive means
    are prevention effects, where a positive value lowers the opponent's result.
    A ``None`` mean uses the corresponding league prior from
    :class:`EfficiencyConfig`. Precision values multiply ``ridge_plays``.
    """

    team: str
    team_id: int | None = None
    classification: str | None = "fbs"
    offense_ppa: float | None = None
    defense_ppa_prevented: float | None = None
    offense_success_rate: float | None = None
    defense_success_rate_prevented: float | None = None
    offense_ppa_precision: float = 1.0
    defense_ppa_precision: float = 1.0
    offense_success_precision: float = 1.0
    defense_success_precision: float = 1.0

    @property
    def key(self) -> str:
        return canonical_team_key(self.team_id, self.team)

    def validate(self) -> None:
        if not isinstance(self.team, str) or not self.team.strip():
            raise EfficiencyDataError("Prior team name cannot be empty")
        if self.team_id is not None and (
            isinstance(self.team_id, bool)
            or not isinstance(self.team_id, int)
            or self.team_id < 0
        ):
            raise EfficiencyDataError("Prior team_id must be a non-negative integer")
        optional_means = {
            "offense_ppa": self.offense_ppa,
            "defense_ppa_prevented": self.defense_ppa_prevented,
            "offense_success_rate": self.offense_success_rate,
            "defense_success_rate_prevented": self.defense_success_rate_prevented,
        }
        for name, value in optional_means.items():
            if value is not None and (
                not isinstance(value, Real) or not math.isfinite(value)
            ):
                raise EfficiencyDataError(f"{name} must be finite when supplied")
        if self.offense_success_rate is not None and not 0 <= self.offense_success_rate <= 1:
            raise EfficiencyDataError("offense_success_rate must be between 0 and 1")
        precisions = {
            "offense_ppa_precision": self.offense_ppa_precision,
            "defense_ppa_precision": self.defense_ppa_precision,
            "offense_success_precision": self.offense_success_precision,
            "defense_success_precision": self.defense_success_precision,
        }
        for name, value in precisions.items():
            if not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
                raise EfficiencyDataError(f"{name} must be positive and finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TeamEfficiencyPrior:
        def optional_mean(name: str) -> float | None:
            value = payload.get(name)
            return None if value is None else _finite_float(value, name)

        prior = cls(
            team=str(payload["team"]),
            team_id=(
                None
                if payload.get("team_id") is None
                else _integer(payload["team_id"], "team_id")
            ),
            classification=(
                None
                if payload.get("classification") is None
                else str(payload["classification"])
            ),
            offense_ppa=optional_mean("offense_ppa"),
            defense_ppa_prevented=optional_mean("defense_ppa_prevented"),
            offense_success_rate=optional_mean("offense_success_rate"),
            defense_success_rate_prevented=optional_mean(
                "defense_success_rate_prevented"
            ),
            offense_ppa_precision=_finite_float(
                payload.get("offense_ppa_precision", 1.0), "offense_ppa_precision"
            ),
            defense_ppa_precision=_finite_float(
                payload.get("defense_ppa_precision", 1.0), "defense_ppa_precision"
            ),
            offense_success_precision=_finite_float(
                payload.get("offense_success_precision", 1.0),
                "offense_success_precision",
            ),
            defense_success_precision=_finite_float(
                payload.get("defense_success_precision", 1.0),
                "defense_success_precision",
            ),
        )
        prior.validate()
        return prior


def normalize_team_efficiency_priors(
    priors: Iterable[TeamEfficiencyPrior | Mapping[str, Any]],
) -> list[TeamEfficiencyPrior]:
    """Normalize priors, preferring the last duplicate canonical team key."""

    by_key: dict[str, TeamEfficiencyPrior] = {}
    for raw_prior in priors:
        if isinstance(raw_prior, TeamEfficiencyPrior):
            prior = raw_prior
            prior.validate()
        elif isinstance(raw_prior, Mapping):
            prior = TeamEfficiencyPrior.from_dict(raw_prior)
        else:
            raise EfficiencyDataError(
                f"Expected a team efficiency prior, received {type(raw_prior).__name__}"
            )
        by_key[prior.key] = prior
    return sorted(by_key.values(), key=lambda prior: prior.key)


@dataclass(frozen=True, slots=True)
class TeamEfficiency:
    """Opponent-adjusted team summary with all rating directions positive-good."""

    key: str
    team_id: int | None
    team: str
    classification: str | None
    games: int
    offense_plays: int
    defense_plays: int
    effective_offense_plays: float
    effective_defense_plays: float
    offense_ppa: float
    defense_ppa_prevented: float
    offense_success_rate: float
    defense_success_rate_prevented: float
    last_played: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TeamEfficiency:
        summary = cls(
            key=str(payload["key"]),
            team_id=(
                None
                if payload.get("team_id") is None
                else _integer(payload["team_id"], "team_id")
            ),
            team=str(payload["team"]),
            classification=(
                None
                if payload.get("classification") is None
                else str(payload["classification"])
            ),
            games=_integer(payload["games"], "games"),
            offense_plays=_integer(payload["offense_plays"], "offense_plays"),
            defense_plays=_integer(payload["defense_plays"], "defense_plays"),
            effective_offense_plays=_finite_float(
                payload["effective_offense_plays"], "effective_offense_plays"
            ),
            effective_defense_plays=_finite_float(
                payload["effective_defense_plays"], "effective_defense_plays"
            ),
            offense_ppa=_finite_float(payload["offense_ppa"], "offense_ppa"),
            defense_ppa_prevented=_finite_float(
                payload["defense_ppa_prevented"], "defense_ppa_prevented"
            ),
            offense_success_rate=_finite_float(
                payload["offense_success_rate"], "offense_success_rate"
            ),
            defense_success_rate_prevented=_finite_float(
                payload["defense_success_rate_prevented"],
                "defense_success_rate_prevented",
            ),
            last_played=(
                None if payload.get("last_played") is None else str(payload["last_played"])
            ),
        )
        if not summary.key or not summary.team:
            raise EfficiencyDataError("Team summary key and name cannot be empty")
        if summary.effective_offense_plays < 0 or summary.effective_defense_plays < 0:
            raise EfficiencyDataError("Effective play counts must be non-negative")
        if not 0 <= summary.offense_success_rate <= 1:
            raise EfficiencyDataError("offense_success_rate must be between 0 and 1")
        if summary.last_played is not None:
            parse_datetime(summary.last_played)
        if summary.games == 0 and (
            summary.offense_plays
            or summary.defense_plays
            or summary.effective_offense_plays
            or summary.effective_defense_plays
            or summary.last_played is not None
        ):
            raise EfficiencyDataError("A zero-game team summary cannot contain game usage")
        return summary


@dataclass(frozen=True, slots=True)
class _DatedSample:
    game: Game
    offense_key: str
    defense_key: str
    plays: int
    ppa: float
    success_rate: float
    direct: bool


class OpponentAdjustedEfficiencyModel:
    """Fit PPA and success-rate unit ratings without using future games."""

    def __init__(self, config: EfficiencyConfig | None = None) -> None:
        self.config = config or EfficiencyConfig()
        self.config.validate()
        self.metrics: dict[str, MetricRatings] = {}
        self.teams: dict[str, TeamEfficiency] = {}
        self.priors: dict[str, TeamEfficiencyPrior] = {}
        self.as_of: datetime | None = None
        self.trained_at: datetime | None = None
        self.training_games = 0
        self.training_samples = 0
        self.training_game_ids: tuple[int, ...] = ()
        self._name_index: dict[str, str] = {}

    @property
    def is_fitted(self) -> bool:
        return {"ppa", "success_rate"}.issubset(self.metrics) and self.as_of is not None

    def fit(
        self,
        records: Iterable[AdvancedGameObservation | Mapping[str, Any]],
        games: Iterable[Game] = (),
        *,
        as_of: datetime | None = None,
        priors: Iterable[TeamEfficiencyPrior | Mapping[str, Any]] = (),
        live_results: bool = False,
    ) -> Self:
        """Fit using results known strictly before ``as_of``.

        ``Game`` objects are authoritative for team IDs, completion, FBS status,
        and start times. Advanced rows with unknown game IDs are never used.
        The default 12-hour buffer prevents a historical backtest from treating
        a recently started or still-live game as an available final result.
        ``live_results`` bypasses only that buffer for current snapshots;
        completion, scores, and kickoff-before-cutoff checks still apply.
        """

        if live_results and as_of is None:
            as_of = datetime.now(UTC)
        observations = normalize_advanced_game_stats(records)
        supplied_priors = normalize_team_efficiency_priors(priors)
        supplied_games = list(games)
        games_by_id = {game.id: game for game in supplied_games}
        observed_ids = {row.game_id for row in observations}
        base_games = [
            game
            for game_id, game in games_by_id.items()
            if game_id in observed_ids
            and game.completed
            and game.has_score
            and game.home_key != game.away_key
            and (
                not self.config.fbs_only
                or (
                    _is_fbs(game.home_classification)
                    and _is_fbs(game.away_classification)
                )
            )
        ]
        result_buffer = timedelta(
            hours=0 if live_results else self.config.result_buffer_hours
        )
        if as_of is not None:
            cutoff = _as_utc(as_of)
        elif base_games:
            latest = max(game.start_date for game in base_games)
            cutoff = latest + result_buffer + timedelta(microseconds=1)
        else:
            cutoff = datetime.now(UTC)

        if not observations:
            if not supplied_priors:
                raise InsufficientEfficiencyDataError("No advanced game rows were supplied")
            self.priors = self._align_priors(supplied_priors, [], supplied_games)
            return self._finish_prior_only(cutoff)
        if not supplied_games:
            raise InsufficientEfficiencyDataError("No Game objects were supplied")
        if not base_games:
            raise InsufficientEfficiencyDataError(
                "No completed eligible games matched the advanced rows"
            )

        eligible_ids = {
            game.id for game in base_games if game.start_date + result_buffer < cutoff
        }
        candidates: dict[tuple[int, str], _DatedSample] = {}
        for row in observations:
            if row.game_id not in eligible_ids:
                continue
            game = games_by_id[row.game_id]
            team_key, opponent_key = self._resolve_observation_teams(row, game)
            direct = _DatedSample(
                game=game,
                offense_key=team_key,
                defense_key=opponent_key,
                plays=row.offense.plays,
                ppa=row.offense.ppa,
                success_rate=row.offense.success_rate,
                direct=True,
            )
            reverse = _DatedSample(
                game=game,
                offense_key=opponent_key,
                defense_key=team_key,
                plays=row.defense.plays,
                ppa=row.defense.ppa,
                success_rate=row.defense.success_rate,
                direct=False,
            )
            self._add_candidate(candidates, direct)
            self._add_candidate(candidates, reverse)

        samples = sorted(
            candidates.values(), key=lambda sample: (sample.game.start_date, sample.game.id)
        )
        self.priors = self._align_priors(supplied_priors, samples, supplied_games)
        if not samples:
            if self.priors:
                return self._finish_prior_only(cutoff)
            raise InsufficientEfficiencyDataError(
                "No completed advanced observations were available before as_of"
            )
        metric_rows: dict[str, list[MetricObservation]] = {
            "ppa": [],
            "success_rate": [],
        }
        sample_weights: list[float] = []
        for sample in samples:
            age_days = max((cutoff - sample.game.start_date).total_seconds() / 86_400.0, 0.0)
            decay = 0.5 ** (age_days / self.config.half_life_days)
            weight = sample.plays * decay
            sample_weights.append(weight)
            common = {
                "offense_key": sample.offense_key,
                "defense_key": sample.defense_key,
                "weight": weight,
                "game_id": sample.game.id,
            }
            metric_rows["ppa"].append(MetricObservation(value=sample.ppa, **common))
            metric_rows["success_rate"].append(
                MetricObservation(value=sample.success_rate, **common)
            )

        ppa_priors = self._metric_prior_inputs("ppa")
        success_priors = self._metric_prior_inputs("success_rate")
        self.metrics = {
            "ppa": solve_weighted_ridge(
                metric_rows["ppa"],
                metric="ppa",
                prior_mean=self.config.ppa_prior,
                ridge_alpha=self.config.ridge_plays,
                baseline_prior_weight=self.config.baseline_prior_plays,
                offense_priors=ppa_priors[0],
                defense_priors=ppa_priors[1],
                offense_precision=ppa_priors[2],
                defense_precision=ppa_priors[3],
            ),
            "success_rate": solve_weighted_ridge(
                metric_rows["success_rate"],
                metric="success_rate",
                prior_mean=self.config.success_rate_prior,
                ridge_alpha=self.config.ridge_plays,
                baseline_prior_weight=self.config.baseline_prior_plays,
                offense_priors=success_priors[0],
                defense_priors=success_priors[1],
                offense_precision=success_priors[2],
                defense_precision=success_priors[3],
            ),
        }
        self.as_of = cutoff
        self.trained_at = datetime.now(UTC)
        self.training_game_ids = tuple(sorted({sample.game.id for sample in samples}))
        self.training_games = len(self.training_game_ids)
        self.training_samples = len(samples)
        self.teams = self._summarize_teams(samples, sample_weights)
        self._rebuild_name_index()
        return self

    def fit_priors(
        self,
        priors: Iterable[TeamEfficiencyPrior | Mapping[str, Any]],
        *,
        games: Iterable[Game] = (),
        as_of: datetime | None = None,
    ) -> Self:
        """Create a fitted, resolvable preseason model before any games exist."""

        return self.fit((), games, as_of=as_of, priors=priors)

    @classmethod
    def from_priors(
        cls,
        priors: Iterable[TeamEfficiencyPrior | Mapping[str, Any]],
        *,
        config: EfficiencyConfig | None = None,
        games: Iterable[Game] = (),
        as_of: datetime | None = None,
    ) -> OpponentAdjustedEfficiencyModel:
        return cls(config).fit_priors(priors, games=games, as_of=as_of)

    def _align_priors(
        self,
        priors: list[TeamEfficiencyPrior],
        samples: list[_DatedSample],
        games: Iterable[Game] = (),
    ) -> dict[str, TeamEfficiencyPrior]:
        data_metadata: dict[str, tuple[int | None, str, str | None, datetime]] = {}
        keys_by_name: dict[str, set[str]] = {}
        metadata_games = {game.id: game for game in games}
        metadata_games.update({sample.game.id: sample.game for sample in samples})
        for game in metadata_games.values():
            for key, team_id, team, classification in (
                (
                    game.home_key,
                    game.home_id,
                    game.home_team,
                    game.home_classification,
                ),
                (
                    game.away_key,
                    game.away_id,
                    game.away_team,
                    game.away_classification,
                ),
            ):
                previous = data_metadata.get(key)
                if previous is None or game.start_date >= previous[3]:
                    data_metadata[key] = (
                        team_id,
                        team,
                        classification,
                        game.start_date,
                    )
                keys_by_name.setdefault(_normalized_name(team), set()).add(key)

        aligned: dict[str, TeamEfficiencyPrior] = {}
        for prior in priors:
            target_key = prior.key
            matches = keys_by_name.get(_normalized_name(prior.team), set())
            if target_key not in data_metadata and matches:
                if prior.team_id is not None:
                    raise EfficiencyDataError(
                        f"Prior team ID {prior.team_id} for {prior.team!r} does not match "
                        "the supplied Game objects"
                    )
                if len(matches) != 1:
                    raise EfficiencyDataError(
                        f"Prior team name {prior.team!r} matches multiple team keys"
                    )
                target_key = next(iter(matches))
            metadata = data_metadata.get(target_key)
            if metadata is not None:
                team_id, team, classification, _ = metadata
                prior = replace(
                    prior,
                    team=team,
                    team_id=team_id,
                    classification=(
                        prior.classification
                        if prior.classification is not None
                        else classification
                    ),
                )
            if target_key in aligned:
                raise EfficiencyDataError(
                    f"Multiple efficiency priors resolve to team key {target_key!r}"
                )
            aligned[target_key] = prior
        return aligned

    def _metric_prior_inputs(
        self,
        metric: str,
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
        offense_means: dict[str, float] = {}
        defense_means: dict[str, float] = {}
        offense_precision: dict[str, float] = {}
        defense_precision: dict[str, float] = {}
        for key, prior in self.priors.items():
            if metric == "ppa":
                natural_offense = (
                    self.config.ppa_prior
                    if prior.offense_ppa is None
                    else prior.offense_ppa
                )
                offense_means[key] = natural_offense
                defense_means[key] = prior.defense_ppa_prevented or 0.0
                offense_precision[key] = prior.offense_ppa_precision
                defense_precision[key] = prior.defense_ppa_precision
            elif metric == "success_rate":
                natural_offense = (
                    self.config.success_rate_prior
                    if prior.offense_success_rate is None
                    else prior.offense_success_rate
                )
                offense_means[key] = natural_offense
                defense_means[key] = prior.defense_success_rate_prevented or 0.0
                offense_precision[key] = prior.offense_success_precision
                defense_precision[key] = prior.defense_success_precision
            else:
                raise ValueError(f"Unknown efficiency metric: {metric!r}")
        return offense_means, defense_means, offense_precision, defense_precision

    def _finish_prior_only(self, cutoff: datetime) -> Self:
        if not self.priors:
            raise InsufficientEfficiencyDataError("At least one team prior is required")
        ppa = self._metric_prior_inputs("ppa")
        success = self._metric_prior_inputs("success_rate")
        self.metrics = {
            "ppa": MetricRatings(
                metric="ppa",
                prior_mean=self.config.ppa_prior,
                baseline=self.config.ppa_prior,
                offense={
                    key: value - self.config.ppa_prior for key, value in ppa[0].items()
                },
                defense=ppa[1],
                residual_rmse=0.0,
                samples=0,
                total_weight=0.0,
            ),
            "success_rate": MetricRatings(
                metric="success_rate",
                prior_mean=self.config.success_rate_prior,
                baseline=self.config.success_rate_prior,
                offense={
                    key: value - self.config.success_rate_prior
                    for key, value in success[0].items()
                },
                defense=success[1],
                residual_rmse=0.0,
                samples=0,
                total_weight=0.0,
            ),
        }
        self.as_of = cutoff
        self.trained_at = datetime.now(UTC)
        self.training_games = 0
        self.training_samples = 0
        self.training_game_ids = ()
        self.teams = self._summarize_teams([], [])
        self._rebuild_name_index()
        return self

    @staticmethod
    def _add_candidate(
        candidates: dict[tuple[int, str], _DatedSample],
        sample: _DatedSample,
    ) -> None:
        key = (sample.game.id, sample.offense_key)
        existing = candidates.get(key)
        if existing is None:
            candidates[key] = sample
            return
        matches = (
            existing.defense_key == sample.defense_key
            and existing.plays == sample.plays
            and math.isclose(existing.ppa, sample.ppa, rel_tol=1e-8, abs_tol=1e-8)
            and math.isclose(
                existing.success_rate,
                sample.success_rate,
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
        )
        if not matches:
            raise EfficiencyDataError(
                f"Contradictory mirrored advanced rows for Game {sample.game.id} "
                f"and offense {sample.offense_key!r}"
            )
        if sample.direct and not existing.direct:
            candidates[key] = sample

    @staticmethod
    def _resolve_observation_teams(
        observation: AdvancedGameObservation,
        game: Game,
    ) -> tuple[str, str]:
        if (
            observation.season != game.season
            or observation.week != game.week
            or observation.season_type.casefold() != game.season_type.casefold()
        ):
            raise EfficiencyDataError(
                f"Advanced row metadata does not match Game {game.id}: "
                f"{observation.season}/{observation.season_type}/{observation.week} versus "
                f"{game.season}/{game.season_type}/{game.week}"
            )
        team = _normalized_name(observation.team)
        opponent = _normalized_name(observation.opponent)
        home = _normalized_name(game.home_team)
        away = _normalized_name(game.away_team)
        if team == home and opponent == away:
            return game.home_key, game.away_key
        if team == away and opponent == home:
            return game.away_key, game.home_key
        raise EfficiencyDataError(
            f"Advanced row teams {observation.team!r}/{observation.opponent!r} "
            f"do not match Game {game.id} ({game.home_team!r}/{game.away_team!r})"
        )

    def _summarize_teams(
        self,
        samples: list[_DatedSample],
        weights: list[float],
    ) -> dict[str, TeamEfficiency]:
        raw: dict[str, dict[str, Any]] = {
            key: {
                "team_id": prior.team_id,
                "team": prior.team.strip(),
                "classification": prior.classification,
                "games": set(),
                "offense_plays": 0,
                "defense_plays": 0,
                "effective_offense_plays": 0.0,
                "effective_defense_plays": 0.0,
                "last_played": None,
            }
            for key, prior in self.priors.items()
        }

        def metadata(game: Game, key: str) -> tuple[int | None, str, str | None]:
            if key == game.home_key:
                return game.home_id, game.home_team, game.home_classification
            return game.away_id, game.away_team, game.away_classification

        for sample, weight in zip(samples, weights, strict=True):
            for key in (sample.offense_key, sample.defense_key):
                team_id, team, classification = metadata(sample.game, key)
                entry = raw.setdefault(
                    key,
                    {
                        "team_id": team_id,
                        "team": team,
                        "classification": classification,
                        "games": set(),
                        "offense_plays": 0,
                        "defense_plays": 0,
                        "effective_offense_plays": 0.0,
                        "effective_defense_plays": 0.0,
                        "last_played": None,
                    },
                )
                if (
                    entry["last_played"] is None
                    or sample.game.start_date >= entry["last_played"]
                ):
                    entry["team_id"] = team_id
                    entry["team"] = team
                    entry["classification"] = classification
                    entry["last_played"] = sample.game.start_date
                entry["games"].add(sample.game.id)
            offense = raw[sample.offense_key]
            offense["offense_plays"] += sample.plays
            offense["effective_offense_plays"] += weight
            defense = raw[sample.defense_key]
            defense["defense_plays"] += sample.plays
            defense["effective_defense_plays"] += weight

        ppa = self.metrics["ppa"]
        success = self.metrics["success_rate"]
        return {
            key: TeamEfficiency(
                key=key,
                team_id=entry["team_id"],
                team=entry["team"],
                classification=entry["classification"],
                games=len(entry["games"]),
                offense_plays=entry["offense_plays"],
                defense_plays=entry["defense_plays"],
                effective_offense_plays=entry["effective_offense_plays"],
                effective_defense_plays=entry["effective_defense_plays"],
                offense_ppa=ppa.baseline + ppa.offense[key],
                defense_ppa_prevented=ppa.defense[key],
                offense_success_rate=min(
                    max(success.baseline + success.offense[key], 0.0), 1.0
                ),
                defense_success_rate_prevented=success.defense[key],
                last_played=(
                    None
                    if entry["last_played"] is None
                    else entry["last_played"].isoformat()
                ),
            )
            for key, entry in raw.items()
        }

    def _rebuild_name_index(self) -> None:
        self._name_index = {
            _normalized_name(summary.team): key for key, summary in self.teams.items()
        }

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise EfficiencyModelNotFittedError("Fit or load efficiency ratings first")

    def resolve_team(self, team: str | int, *, team_id: int | None = None) -> str | None:
        self._require_fitted()
        if team_id is not None:
            candidate = canonical_team_key(team_id, str(team))
            return candidate if candidate in self.teams else None
        if isinstance(team, int) or (isinstance(team, str) and team.strip().isdigit()):
            candidate = canonical_team_key(int(team), str(team))
            return candidate if candidate in self.teams else None
        return self._name_index.get(_normalized_name(str(team)))

    def get_team(self, team: str | int, *, team_id: int | None = None) -> TeamEfficiency | None:
        key = self.resolve_team(team, team_id=team_id)
        return self.teams.get(key or "")

    def predict_matchup(
        self,
        offense_team: str | int,
        defense_team: str | int,
        *,
        metric: str = "ppa",
        offense_id: int | None = None,
        defense_id: int | None = None,
    ) -> float:
        """Estimate offense efficiency against a defense; unknown teams use priors."""

        self._require_fitted()
        if metric not in self.metrics:
            raise ValueError(f"Unknown efficiency metric: {metric!r}")
        offense_key = self.resolve_team(offense_team, team_id=offense_id)
        defense_key = self.resolve_team(defense_team, team_id=defense_id)
        same_display_name = _normalized_name(str(offense_team)) == _normalized_name(
            str(defense_team)
        )
        if (offense_key is not None and offense_key == defense_key) or same_display_name:
            raise ValueError("offense_team and defense_team must be different teams")
        estimate = self.metrics[metric].predict(offense_key or "", defense_key or "")
        if metric == "success_rate":
            return min(max(estimate, 0.0), 1.0)
        return estimate

    def to_dict(self) -> dict[str, Any]:
        self._require_fitted()
        assert self.as_of is not None and self.trained_at is not None
        return {
            "schema_version": EFFICIENCY_SCHEMA_VERSION,
            "model_type": "opponent_adjusted_efficiency",
            "config": asdict(self.config),
            "as_of": self.as_of.isoformat(),
            "trained_at": self.trained_at.isoformat(),
            "training_games": self.training_games,
            "training_samples": self.training_samples,
            "training_game_ids": list(self.training_game_ids),
            "priors": {key: prior.to_dict() for key, prior in self.priors.items()},
            "metrics": {
                name: ratings.to_dict() for name, ratings in self.metrics.items()
            },
            "teams": {key: summary.to_dict() for key, summary in self.teams.items()},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OpponentAdjustedEfficiencyModel:
        if payload.get("schema_version") != EFFICIENCY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported efficiency schema version: {payload.get('schema_version')!r}"
            )
        if payload.get("model_type") != "opponent_adjusted_efficiency":
            raise ValueError(f"Unsupported efficiency model type: {payload.get('model_type')!r}")
        model = cls(EfficiencyConfig(**dict(payload["config"])))
        model.metrics = {
            str(name): MetricRatings.from_dict(ratings)
            for name, ratings in dict(payload["metrics"]).items()
        }
        model.teams = {
            str(key): TeamEfficiency.from_dict(summary)
            for key, summary in dict(payload["teams"]).items()
        }
        model.priors = {
            str(key): TeamEfficiencyPrior.from_dict(prior)
            for key, prior in dict(payload.get("priors", {})).items()
        }
        model.as_of = parse_datetime(payload["as_of"])
        model.trained_at = parse_datetime(payload["trained_at"])
        model.training_games = _integer(
            payload["training_games"], "training_games"
        )
        model.training_samples = _integer(
            payload["training_samples"], "training_samples"
        )
        model.training_game_ids = tuple(
            sorted(
                {
                    _integer(game_id, "training_game_id", minimum=1)
                    for game_id in payload.get("training_game_ids", [])
                }
            )
        )
        if not model.is_fitted:
            raise ValueError("Efficiency artifact is missing required metrics")
        if set(model.metrics) != {"ppa", "success_rate"}:
            raise ValueError("Efficiency artifact must contain exactly ppa and success_rate")
        for name, ratings in model.metrics.items():
            if ratings.metric != name:
                raise ValueError("Efficiency artifact metric names are inconsistent")
        if not math.isclose(
            model.metrics["ppa"].prior_mean,
            model.config.ppa_prior,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            model.metrics["success_rate"].prior_mean,
            model.config.success_rate_prior,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("Efficiency artifact metric priors disagree with config")
        metric_keys = set(model.metrics["ppa"].offense)
        if metric_keys != set(model.metrics["success_rate"].offense):
            raise ValueError("Efficiency artifact metric team keys do not match")
        if metric_keys != set(model.teams):
            raise ValueError("Efficiency artifact summaries do not match metric teams")
        if any(key != summary.key for key, summary in model.teams.items()):
            raise ValueError("Efficiency artifact outer team keys are inconsistent")
        if model.training_games != len(model.training_game_ids):
            raise ValueError("Efficiency artifact training game count is inconsistent")
        if any(key not in model.teams for key in model.priors):
            raise ValueError("Efficiency artifact contains a prior for an unknown team")
        if any(key != prior.key for key, prior in model.priors.items()):
            raise ValueError("Efficiency artifact outer prior keys are inconsistent")
        metric_samples = {ratings.samples for ratings in model.metrics.values()}
        if metric_samples != {model.training_samples}:
            raise ValueError("Efficiency artifact training sample count is inconsistent")
        if model.training_samples == 0:
            if model.training_games != 0 or not model.priors:
                raise ValueError("Cold-start efficiency artifact metadata is inconsistent")
            if set(model.priors) != metric_keys:
                raise ValueError("Cold-start efficiency artifact requires one prior per team")
            cold_ppa = model._metric_prior_inputs("ppa")
            cold_success = model._metric_prior_inputs("success_rate")
            expected_cold = {
                "ppa": (
                    model.config.ppa_prior,
                    {
                        key: value - model.config.ppa_prior
                        for key, value in cold_ppa[0].items()
                    },
                    cold_ppa[1],
                ),
                "success_rate": (
                    model.config.success_rate_prior,
                    {
                        key: value - model.config.success_rate_prior
                        for key, value in cold_success[0].items()
                    },
                    cold_success[1],
                ),
            }
            for name, ratings in model.metrics.items():
                baseline, offense, defense = expected_cold[name]
                cold_values_match = (
                    math.isclose(ratings.baseline, baseline, rel_tol=0.0, abs_tol=1e-12)
                    and ratings.offense == offense
                    and ratings.defense == defense
                    and ratings.residual_rmse == 0
                    and ratings.total_weight == 0
                )
                if not cold_values_match:
                    raise ValueError("Cold-start efficiency artifact disagrees with priors")
            if any(summary.games != 0 for summary in model.teams.values()):
                raise ValueError("Cold-start efficiency teams must have zero games")
        ppa = model.metrics["ppa"]
        success = model.metrics["success_rate"]
        for key, summary in model.teams.items():
            expected = (
                ppa.baseline + ppa.offense[key],
                ppa.defense[key],
                min(max(success.baseline + success.offense[key], 0.0), 1.0),
                success.defense[key],
            )
            actual = (
                summary.offense_ppa,
                summary.defense_ppa_prevented,
                summary.offense_success_rate,
                summary.defense_success_rate_prevented,
            )
            if any(
                not math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
                for left, right in zip(actual, expected, strict=True)
            ):
                raise ValueError(
                    f"Efficiency artifact summary ratings disagree for team {key!r}"
                )
        model._rebuild_name_index()
        return model
