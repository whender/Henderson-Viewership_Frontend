"""Learned preseason offense/defense priors from team-season features."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

PRIOR_TARGETS = (
    "offense_ppa",
    "defense_ppa",
    "offense_success",
    "defense_success",
)

_OPTIONAL_CONTINUITY_AUDIT_FEATURES = {
    "roster_ol_starter_retention_rate",
    "roster_ol_starter_retention_missing",
    "coach_staff_retention_rate",
    "coach_staff_retention_missing",
    "coach_offense_staff_retention_rate",
    "coach_offense_staff_retention_missing",
}


@dataclass(frozen=True, slots=True)
class PriorConfig:
    ridge_alpha: float = 20.0
    season_half_life: float = 4.0
    minimum_scale: float = 1e-6

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.ridge_alpha < 0:
            raise ValueError("ridge_alpha must be non-negative")
        if self.season_half_life <= 0:
            raise ValueError("season_half_life must be positive")
        if self.minimum_scale <= 0:
            raise ValueError("minimum_scale must be positive")


@dataclass(frozen=True, slots=True)
class PriorTrainingExample:
    season: int
    team_key: str
    features: Mapping[str, float]
    offense_ppa: float
    defense_ppa: float
    offense_success: float
    defense_success: float


@dataclass(frozen=True, slots=True)
class ScorePriorTrainingExample:
    season: int
    team_key: str
    features: Mapping[str, float]
    score_rating: float


@dataclass(frozen=True, slots=True)
class PriorEstimate:
    offense_ppa: float
    defense_ppa: float
    offense_success: float
    defense_success: float
    precision_multiplier: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _finite_float(value: Any, *, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


class PreseasonScorePriorModel:
    """Standardized ridge prior for preseason team strength in point units.

    Callers supply auditable team-season features and closing point-rating targets.
    Training always excludes the prediction season and every later season.
    """

    def __init__(self, config: PriorConfig | None = None) -> None:
        self.config = config or PriorConfig()
        self.config.validate()
        self.feature_names: tuple[str, ...] = ()
        self.means = np.empty(0, dtype=np.float64)
        self.scales = np.empty(0, dtype=np.float64)
        self.coefficients = np.empty(0, dtype=np.float64)
        self.residual_scale = 0.0
        self.target_bounds = (0.0, 0.0)
        self.trained_through: int | None = None
        self.training_examples = 0

    @property
    def is_fitted(self) -> bool:
        return bool(self.feature_names) and self.trained_through is not None

    def fit(
        self,
        examples: Sequence[ScorePriorTrainingExample],
        *,
        predict_season: int,
        feature_names: Sequence[str] | None = None,
    ) -> PreseasonScorePriorModel:
        if predict_season < 1870:
            raise ValueError("predict_season is invalid")
        eligible = [row for row in examples if row.season < predict_season]
        if len(eligible) < 20:
            raise ValueError("At least 20 prior team-season examples are required")
        names = tuple(
            feature_names
            if feature_names is not None
            else sorted({name for row in eligible for name in row.features})
        )
        if not names or len(set(names)) != len(names):
            raise ValueError("feature_names must be non-empty and unique")

        x = np.zeros((len(eligible), len(names)), dtype=np.float64)
        y = np.empty(len(eligible), dtype=np.float64)
        weights = np.empty(len(eligible), dtype=np.float64)
        for index, row in enumerate(eligible):
            for column, name in enumerate(names):
                x[index, column] = _finite_float(
                    row.features.get(name, 0.0), label=f"feature {name}"
                )
            y[index] = _finite_float(row.score_rating, label="score_rating")
            age = max((predict_season - 1) - row.season, 0)
            weights[index] = 0.5 ** (age / self.config.season_half_life)

        weight_total = float(np.sum(weights))
        means = np.sum(weights[:, None] * x, axis=0) / weight_total
        variances = np.sum(weights[:, None] * np.square(x - means), axis=0) / weight_total
        scales = np.sqrt(np.maximum(variances, self.config.minimum_scale**2))
        standardized = (x - means) / scales
        design = np.column_stack((np.ones(len(eligible)), standardized))
        system = design.T @ (weights[:, None] * design)
        penalty = np.diag([0.0, *([self.config.ridge_alpha] * len(names))])
        target = design.T @ (weights * y)
        try:
            coefficients = np.linalg.solve(system + penalty, target)
        except np.linalg.LinAlgError:
            coefficients = np.linalg.lstsq(system + penalty, target, rcond=None)[0]
        fitted = design @ coefficients
        if not np.isfinite(coefficients).all() or not np.isfinite(fitted).all():
            raise ValueError("Score prior training produced non-finite coefficients")
        residuals = y - fitted

        self.feature_names = names
        self.means = means
        self.scales = scales
        self.coefficients = coefficients
        self.residual_scale = max(
            math.sqrt(float(np.sum(weights * np.square(residuals)) / weight_total)),
            self.config.minimum_scale,
        )
        self.target_bounds = (
            float(np.quantile(y, 0.001)),
            float(np.quantile(y, 0.999)),
        )
        self.trained_through = max(row.season for row in eligible)
        self.training_examples = len(eligible)
        return self

    def predict(self, features: Mapping[str, float]) -> float:
        if not self.is_fitted:
            raise RuntimeError("Fit or load the preseason score prior before predicting")
        values = np.asarray(
            [
                _finite_float(features.get(name, 0.0), label=f"feature {name}")
                for name in self.feature_names
            ],
            dtype=np.float64,
        )
        vector = np.concatenate(([1.0], (values - self.means) / self.scales))
        estimate = float(vector @ self.coefficients)
        if not math.isfinite(estimate):
            raise ValueError("Score prior prediction produced a non-finite value")
        return max(self.target_bounds[0], min(estimate, self.target_bounds[1]))

    def to_dict(self) -> dict[str, Any]:
        if not self.is_fitted:
            raise RuntimeError("Fit the preseason score prior before serializing")
        return {
            "schema_version": 1,
            "model_type": "team_season_score_rating_ridge_prior",
            "config": asdict(self.config),
            "feature_names": list(self.feature_names),
            "means": self.means.tolist(),
            "scales": self.scales.tolist(),
            "coefficients": self.coefficients.tolist(),
            "residual_scale": self.residual_scale,
            "target_bounds": list(self.target_bounds),
            "trained_through": self.trained_through,
            "training_examples": self.training_examples,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreseasonScorePriorModel:
        if payload.get("schema_version") != 1:
            raise ValueError(
                f"Unsupported preseason score prior schema: {payload.get('schema_version')}"
            )
        if payload.get("model_type") != "team_season_score_rating_ridge_prior":
            raise ValueError(
                f"Unsupported preseason score prior type: {payload.get('model_type')!r}"
            )
        model = cls(PriorConfig(**dict(payload["config"])))
        model.feature_names = tuple(str(name) for name in payload["feature_names"])
        model.means = np.asarray(payload["means"], dtype=np.float64)
        model.scales = np.asarray(payload["scales"], dtype=np.float64)
        model.coefficients = np.asarray(payload["coefficients"], dtype=np.float64)
        model.residual_scale = _finite_float(
            payload["residual_scale"], label="residual_scale"
        )
        raw_bounds = payload["target_bounds"]
        model.target_bounds = (
            _finite_float(raw_bounds[0], label="target lower bound"),
            _finite_float(raw_bounds[1], label="target upper bound"),
        )
        model.trained_through = int(payload["trained_through"])
        model.training_examples = int(payload["training_examples"])
        expected_features = len(model.feature_names)
        if not model.feature_names or len(set(model.feature_names)) != expected_features:
            raise ValueError("Preseason score prior feature names are invalid")
        if model.coefficients.shape != (expected_features + 1,):
            raise ValueError("Preseason score prior coefficient shape is invalid")
        if model.means.shape != (expected_features,) or model.scales.shape != (
            expected_features,
        ):
            raise ValueError("Preseason score prior standardizer shape is invalid")
        if not all(
            np.isfinite(array).all()
            for array in (model.means, model.scales, model.coefficients)
        ):
            raise ValueError("Preseason score prior artifact contains non-finite values")
        if np.any(model.scales <= 0):
            raise ValueError("Preseason score prior scales must be positive")
        if model.residual_scale <= 0:
            raise ValueError("Preseason score prior residual scale must be positive")
        if model.target_bounds[0] > model.target_bounds[1]:
            raise ValueError("Preseason score prior target bounds are invalid")
        if model.training_examples < 20:
            raise ValueError("Preseason score prior artifact has too few training examples")
        return model


class PreseasonPriorModel:
    """Multi-output standardized ridge model for team-season unit priors.

    The model intentionally knows nothing about CFBD response shapes. Callers pass a
    deterministic named feature mapping and four full-season opponent-adjusted targets.
    The same fitted standardizer is used at prediction time, making artifacts reproducible.
    """

    def __init__(self, config: PriorConfig | None = None) -> None:
        self.config = config or PriorConfig()
        self.config.validate()
        self.feature_names: tuple[str, ...] = ()
        self.means = np.empty(0, dtype=np.float64)
        self.scales = np.empty(0, dtype=np.float64)
        self.coefficients = np.empty((0, len(PRIOR_TARGETS)), dtype=np.float64)
        self.residual_scales: dict[str, float] = {}
        self.target_bounds: dict[str, tuple[float, float]] = {}
        self.trained_through: int | None = None
        self.training_examples = 0

    @property
    def is_fitted(self) -> bool:
        return bool(self.feature_names) and self.trained_through is not None

    def fit(
        self,
        examples: Sequence[PriorTrainingExample],
        *,
        predict_season: int,
        feature_names: Sequence[str] | None = None,
    ) -> PreseasonPriorModel:
        if predict_season < 1870:
            raise ValueError("predict_season is invalid")
        eligible = [row for row in examples if row.season < predict_season]
        if len(eligible) < 20:
            raise ValueError("At least 20 prior team-season examples are required")
        names = tuple(
            feature_names
            if feature_names is not None
            else sorted({name for row in eligible for name in row.features})
        )
        if not names or len(set(names)) != len(names):
            raise ValueError("feature_names must be non-empty and unique")

        x = np.zeros((len(eligible), len(names)), dtype=np.float64)
        y = np.empty((len(eligible), len(PRIOR_TARGETS)), dtype=np.float64)
        weights = np.empty(len(eligible), dtype=np.float64)
        for index, row in enumerate(eligible):
            for column, name in enumerate(names):
                x[index, column] = _finite_float(
                    row.features.get(name, 0.0), label=f"feature {name}"
                )
            y[index] = [
                _finite_float(getattr(row, target), label=target) for target in PRIOR_TARGETS
            ]
            age = max((predict_season - 1) - row.season, 0)
            weights[index] = 0.5 ** (age / self.config.season_half_life)

        weight_total = float(np.sum(weights))
        means = np.sum(weights[:, None] * x, axis=0) / weight_total
        variances = np.sum(weights[:, None] * np.square(x - means), axis=0) / weight_total
        scales = np.sqrt(np.maximum(variances, self.config.minimum_scale**2))
        standardized = (x - means) / scales
        design = np.column_stack((np.ones(len(eligible)), standardized))
        system = design.T @ (weights[:, None] * design)
        penalty = np.diag([0.0, *([self.config.ridge_alpha] * len(names))])
        target = design.T @ (weights[:, None] * y)
        try:
            coefficients = np.linalg.solve(system + penalty, target)
        except np.linalg.LinAlgError:
            coefficients = np.linalg.lstsq(system + penalty, target, rcond=None)[0]
        fitted = design @ coefficients
        if not np.isfinite(coefficients).all() or not np.isfinite(fitted).all():
            raise ValueError("Prior training produced non-finite coefficients")
        residuals = y - fitted
        residual_scales = np.sqrt(
            np.sum(weights[:, None] * np.square(residuals), axis=0) / weight_total
        )

        self.feature_names = names
        self.means = means
        self.scales = scales
        self.coefficients = coefficients
        self.residual_scales = {
            target_name: max(float(scale), self.config.minimum_scale)
            for target_name, scale in zip(PRIOR_TARGETS, residual_scales, strict=True)
        }
        self.target_bounds = {
            target_name: (
                float(np.quantile(y[:, index], 0.001)),
                float(np.quantile(y[:, index], 0.999)),
            )
            for index, target_name in enumerate(PRIOR_TARGETS)
        }
        self.trained_through = max(row.season for row in eligible)
        self.training_examples = len(eligible)
        return self

    def _vector(self, features: Mapping[str, float]) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Fit or load the preseason prior model before predicting")
        values = np.asarray(
            [
                _finite_float(features.get(name, 0.0), label=f"feature {name}")
                for name in self.feature_names
            ],
            dtype=np.float64,
        )
        return np.concatenate(([1.0], (values - self.means) / self.scales))

    @staticmethod
    def precision_multiplier(features: Mapping[str, float]) -> float:
        """Translate observed turnover/coverage into prior confidence.

        Missing inputs and leadership change widen the prior. Roster retention tightens
        it. These adjustments affect the rate at which games overwhelm the prior, not
        the direction of the rating itself.
        """

        missing_values = [
            max(0.0, min(_finite_float(value, label=name), 1.0))
            for name, value in features.items()
            if name.endswith("_missing")
            and name not in _OPTIONAL_CONTINUITY_AUDIT_FEATURES
        ]
        missing_fraction = float(np.mean(missing_values)) if missing_values else 0.0
        retention_candidates = [
            _finite_float(value, label=name)
            for name, value in features.items()
            if "retention" in name and not name.endswith("_missing")
            and name not in _OPTIONAL_CONTINUITY_AUDIT_FEATURES
        ]
        retention = (
            float(np.mean(np.clip(retention_candidates, 0.0, 1.0))) if retention_candidates else 0.5
        )
        coach_change = max(
            (
                _finite_float(value, label=name)
                for name, value in features.items()
                if name in {"coach_change", "coach_changed", "new_head_coach"}
            ),
            default=0.0,
        )
        multiplier = (0.65 + 0.70 * retention) * (1.0 - 0.45 * missing_fraction)
        multiplier *= 1.0 - 0.20 * max(0.0, min(coach_change, 1.0))
        estimated = max(
            (
                max(0.0, min(_finite_float(value, label=name), 1.0))
                for name, value in features.items()
                if name == "roster_estimated"
            ),
            default=0.0,
        )
        coverage = max(
            0.0,
            min(
                _finite_float(
                    features.get("roster_estimation_coverage", 1.0),
                    label="roster_estimation_coverage",
                ),
                1.0,
            ),
        )
        # A projection can direct the mean, but never receives the confidence of an official
        # roster. Better class/portal coverage narrows (without eliminating) that penalty.
        multiplier *= 1.0 - estimated * (0.30 - 0.15 * coverage)
        return max(0.35, min(multiplier, 1.50))

    def predict(self, features: Mapping[str, float]) -> PriorEstimate:
        values = self._vector(features) @ self.coefficients
        if not np.isfinite(values).all():
            raise ValueError("Prior prediction produced non-finite values")
        values = np.asarray(
            [
                np.clip(value, *self.target_bounds[target])
                for value, target in zip(values, PRIOR_TARGETS, strict=True)
            ],
            dtype=np.float64,
        )
        return PriorEstimate(
            offense_ppa=float(values[0]),
            defense_ppa=float(values[1]),
            offense_success=float(values[2]),
            defense_success=float(values[3]),
            precision_multiplier=self.precision_multiplier(features),
        )

    def to_dict(self) -> dict[str, Any]:
        if not self.is_fitted:
            raise RuntimeError("Fit the preseason prior model before serializing")
        return {
            "schema_version": 1,
            "model_type": "team_season_multioutput_ridge_prior",
            "config": asdict(self.config),
            "feature_names": list(self.feature_names),
            "target_names": list(PRIOR_TARGETS),
            "means": self.means.tolist(),
            "scales": self.scales.tolist(),
            "coefficients": self.coefficients.tolist(),
            "residual_scales": self.residual_scales,
            "target_bounds": {name: list(bounds) for name, bounds in self.target_bounds.items()},
            "trained_through": self.trained_through,
            "training_examples": self.training_examples,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreseasonPriorModel:
        if payload.get("schema_version") != 1:
            raise ValueError(f"Unsupported preseason prior schema: {payload.get('schema_version')}")
        if tuple(payload.get("target_names", ())) != PRIOR_TARGETS:
            raise ValueError("Preseason prior target schema does not match this version")
        model = cls(PriorConfig(**dict(payload["config"])))
        model.feature_names = tuple(str(name) for name in payload["feature_names"])
        model.means = np.asarray(payload["means"], dtype=np.float64)
        model.scales = np.asarray(payload["scales"], dtype=np.float64)
        model.coefficients = np.asarray(payload["coefficients"], dtype=np.float64)
        model.residual_scales = {
            str(name): _finite_float(value, label=f"residual scale {name}")
            for name, value in dict(payload["residual_scales"]).items()
        }
        model.target_bounds = {
            str(name): (
                _finite_float(bounds[0], label=f"target lower bound {name}"),
                _finite_float(bounds[1], label=f"target upper bound {name}"),
            )
            for name, bounds in dict(payload["target_bounds"]).items()
        }
        model.trained_through = int(payload["trained_through"])
        model.training_examples = int(payload["training_examples"])
        expected_shape = (len(model.feature_names) + 1, len(PRIOR_TARGETS))
        if model.coefficients.shape != expected_shape:
            raise ValueError("Preseason prior coefficient shape is invalid")
        if model.means.shape != (len(model.feature_names),) or model.scales.shape != (
            len(model.feature_names),
        ):
            raise ValueError("Preseason prior standardizer shape is invalid")
        if not all(
            np.isfinite(array).all() for array in (model.means, model.scales, model.coefficients)
        ):
            raise ValueError("Preseason prior artifact contains non-finite values")
        if np.any(model.scales <= 0):
            raise ValueError("Preseason prior scales must be positive")
        if set(model.target_bounds) != set(PRIOR_TARGETS) or any(
            lower > upper for lower, upper in model.target_bounds.values()
        ):
            raise ValueError("Preseason prior target bounds are invalid")
        if model.training_examples < 20:
            raise ValueError("Preseason prior artifact has too few training examples")
        return model
