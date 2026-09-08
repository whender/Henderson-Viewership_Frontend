"""Leakage-safe hybrid margin regression and temporal calibration.

This module deliberately knows nothing about CFBD.  Callers build point-in-time
features, stamp them with their availability time, and supply chronological rows.
The model then fits a deterministic standardized ridge regression with Huber IRLS.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from numbers import Integral
from pathlib import Path
from typing import Any

import numpy as np

from cfbpredict.games import atomic_write_json, parse_datetime
from cfbpredict.model import InsufficientDataError, ModelNotFittedError

HYBRID_ARTIFACT_SCHEMA_VERSION = 1
HYBRID_MODEL_TYPE = "standardized_huber_ridge_hybrid_margin"


@dataclass(frozen=True, slots=True)
class HybridConfig:
    """Hyperparameters for the generic hybrid margin model."""

    ridge_alpha: float = 4.0
    huber_delta: float = 1.345
    max_irls_iterations: int = 100
    tolerance: float = 1e-9
    standardization_floor: float = 1e-12
    min_residual_sigma: float = 1.0
    min_margin_error: float = 1.0
    probability_l2: float = 0.01
    min_training_rows: int = 3
    min_calibration_rows: int = 25

    def validate(self) -> None:
        numeric = {
            "ridge_alpha": self.ridge_alpha,
            "huber_delta": self.huber_delta,
            "tolerance": self.tolerance,
            "standardization_floor": self.standardization_floor,
            "min_residual_sigma": self.min_residual_sigma,
            "min_margin_error": self.min_margin_error,
            "probability_l2": self.probability_l2,
        }
        for name, value in numeric.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        integer_fields = {
            "max_irls_iterations": self.max_irls_iterations,
            "min_training_rows": self.min_training_rows,
            "min_calibration_rows": self.min_calibration_rows,
        }
        for name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
        if self.ridge_alpha < 0:
            raise ValueError("ridge_alpha must be non-negative")
        if self.huber_delta <= 0:
            raise ValueError("huber_delta must be positive")
        if self.max_irls_iterations < 1:
            raise ValueError("max_irls_iterations must be positive")
        if self.tolerance <= 0:
            raise ValueError("tolerance must be positive")
        if self.standardization_floor <= 0:
            raise ValueError("standardization_floor must be positive")
        if self.min_residual_sigma <= 0:
            raise ValueError("min_residual_sigma must be positive")
        if self.min_margin_error <= 0:
            raise ValueError("min_margin_error must be positive")
        if self.probability_l2 < 0:
            raise ValueError("probability_l2 must be non-negative")
        if self.min_training_rows < 2:
            raise ValueError("min_training_rows must be at least 2")
        if self.min_calibration_rows < 2:
            raise ValueError("min_calibration_rows must be at least 2")


@dataclass(frozen=True, slots=True)
class HybridTrainingRow:
    """One historical prediction row with an auditable feature cutoff.

    ``feature_as_of`` must not be later than ``prediction_time``. Rows passed to
    :meth:`HybridMarginModel.fit` must already be ordered by ``prediction_time``;
    rejecting disorder avoids silently turning an accidental random split into a
    temporal model fit.
    """

    prediction_time: datetime | str
    feature_as_of: datetime | str
    features: Mapping[str, float]
    actual_margin: float
    sample_weight: float = 1.0


@dataclass(frozen=True, slots=True)
class TemporalMarginPrediction:
    """A genuinely out-of-sample prediction used for temporal calibration."""

    prediction_time: datetime | str
    model_as_of: datetime | str
    predicted_margin: float
    actual_margin: float


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    """Indices for one expanding-window train/validation split."""

    training_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """Serializable fitted schema for one feature."""

    name: str
    mean: float
    scale: float
    coefficient: float
    standardized_coefficient: float


@dataclass(frozen=True, slots=True)
class HybridPrediction:
    """A coherent margin and binary winner prediction."""

    predicted_margin: float
    home_win_probability: float
    away_win_probability: float
    margin_interval_80: tuple[float, float]
    margin_interval_95: tuple[float, float]

    @property
    def favorite(self) -> str:
        if self.predicted_margin > 0:
            return "home"
        if self.predicted_margin < 0:
            return "away"
        return "pick'em"


def _as_time(value: datetime | str, field: str) -> datetime:
    try:
        return parse_datetime(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid datetime") from exc


def _as_finite(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    ordered_weights = weights[order]
    cumulative = np.cumsum(ordered_weights)
    target = quantile * float(cumulative[-1])
    index = min(int(np.searchsorted(cumulative, target, side="left")), len(values) - 1)
    return float(ordered_values[index])


def _conformal_quantile(errors: np.ndarray, coverage: float) -> float:
    """Finite-sample split-conformal absolute-error quantile."""

    ordered = np.sort(errors, kind="stable")
    rank = min(int(math.ceil((len(ordered) + 1) * coverage)), len(ordered))
    return float(ordered[max(rank - 1, 0)])


def _solve_ridge(
    design: np.ndarray,
    targets: np.ndarray,
    weights: np.ndarray,
    ridge_alpha: float,
) -> np.ndarray:
    weighted_design = design * weights[:, None]
    system = design.T @ weighted_design
    penalty = np.full(design.shape[1], ridge_alpha, dtype=np.float64)
    penalty[0] = 0.0
    system += np.diag(penalty)
    target = design.T @ (weights * targets)
    try:
        result = np.linalg.solve(system, target)
    except np.linalg.LinAlgError:
        result = np.linalg.lstsq(system, target, rcond=None)[0]
    if not np.isfinite(result).all():
        raise ValueError("Training data produced non-finite coefficients")
    return result


def _validate_temporal_training_rows(
    rows: Sequence[HybridTrainingRow],
) -> tuple[list[datetime], list[datetime]]:
    prediction_times: list[datetime] = []
    feature_times: list[datetime] = []
    previous: datetime | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, HybridTrainingRow):
            raise ValueError(f"rows[{index}] must be a HybridTrainingRow")
        prediction_time = _as_time(row.prediction_time, f"rows[{index}].prediction_time")
        feature_time = _as_time(row.feature_as_of, f"rows[{index}].feature_as_of")
        if feature_time > prediction_time:
            raise ValueError(
                f"rows[{index}] leaks future data: feature_as_of is after prediction_time"
            )
        if previous is not None and prediction_time < previous:
            raise ValueError("training rows must be chronological by prediction_time")
        prediction_times.append(prediction_time)
        feature_times.append(feature_time)
        previous = prediction_time
    return prediction_times, feature_times


def expanding_window_splits(
    rows: Sequence[HybridTrainingRow],
    *,
    min_training_rows: int,
    validation_rows: int,
) -> tuple[TemporalSplit, ...]:
    """Build expanding temporal splits without dividing equal-time slates."""

    if min_training_rows < 1:
        raise ValueError("min_training_rows must be positive")
    if validation_rows < 1:
        raise ValueError("validation_rows must be positive")
    prediction_times, _ = _validate_temporal_training_rows(rows)
    if len(rows) <= min_training_rows:
        return ()

    group_ends: list[int] = []
    for index in range(1, len(rows) + 1):
        if index == len(rows) or prediction_times[index] != prediction_times[index - 1]:
            group_ends.append(index)

    train_end = next((end for end in group_ends if end >= min_training_rows), len(rows))
    splits: list[TemporalSplit] = []
    while train_end < len(rows):
        desired_end = min(train_end + validation_rows, len(rows))
        validation_end = next((end for end in group_ends if end >= desired_end), len(rows))
        splits.append(
            TemporalSplit(
                training_indices=tuple(range(train_end)),
                validation_indices=tuple(range(train_end, validation_end)),
            )
        )
        train_end = validation_end
    return tuple(splits)


class HybridMarginModel:
    """Fit a robust standardized ridge model over point-in-time feature rows."""

    def __init__(self, config: HybridConfig | None = None) -> None:
        self.config = config or HybridConfig()
        self.config.validate()
        self._feature_names: tuple[str, ...] = ()
        self._feature_means = np.asarray([], dtype=np.float64)
        self._feature_scales = np.asarray([], dtype=np.float64)
        self._standardized_coefficients = np.asarray([], dtype=np.float64)
        self._coefficients = np.asarray([], dtype=np.float64)
        self.intercept = 0.0
        self.standardized_intercept = 0.0
        self.margin_bias = 0.0
        self.residual_sigma = 14.0
        self.margin_error_80 = 1.281_551_565_545 * self.residual_sigma
        self.margin_error_95 = 1.959_963_984_54 * self.residual_sigma
        self.margin_interval_method = "unfitted"
        self.probability_intercept = 0.0
        self.probability_slope = 1.6 / self.residual_sigma
        self.probability_method = "unfitted"
        self.calibration_source = "unfitted"
        self.huber_scale = 0.0
        self.irls_iterations = 0
        self.training_rows = 0
        self.as_of: datetime | None = None
        self.trained_at: datetime | None = None

    @property
    def is_fitted(self) -> bool:
        return bool(self._feature_names) and self.as_of is not None

    @property
    def feature_names(self) -> tuple[str, ...]:
        self._require_fitted()
        return self._feature_names

    @property
    def coefficients(self) -> dict[str, float]:
        self._require_fitted()
        return dict(zip(self._feature_names, self._coefficients, strict=True))

    @property
    def standardized_coefficients(self) -> dict[str, float]:
        self._require_fitted()
        return dict(
            zip(self._feature_names, self._standardized_coefficients, strict=True)
        )

    @property
    def feature_schema(self) -> tuple[FeatureSpec, ...]:
        self._require_fitted()
        return tuple(
            FeatureSpec(name, float(mean), float(scale), float(coefficient), float(standardized))
            for name, mean, scale, coefficient, standardized in zip(
                self._feature_names,
                self._feature_means,
                self._feature_scales,
                self._coefficients,
                self._standardized_coefficients,
                strict=True,
            )
        )

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise ModelNotFittedError("Fit or load a hybrid model before predicting")

    def fit(
        self,
        rows: Iterable[HybridTrainingRow],
        *,
        feature_names: Sequence[str] | None = None,
    ) -> HybridMarginModel:
        supplied = tuple(rows)
        if len(supplied) < self.config.min_training_rows:
            raise InsufficientDataError(
                f"At least {self.config.min_training_rows} chronological rows are required"
            )
        prediction_times, _ = _validate_temporal_training_rows(supplied)

        if feature_names is None:
            if not isinstance(supplied[0].features, Mapping):
                raise ValueError("rows[0].features must be a mapping")
            first_keys = tuple(supplied[0].features.keys())
            if not first_keys:
                raise ValueError("At least one feature is required")
            if any(not isinstance(name, str) or not name.strip() for name in first_keys):
                raise ValueError("feature names must be non-empty strings")
            names = tuple(sorted(first_keys))
        else:
            if isinstance(feature_names, (str, bytes)):
                raise ValueError("feature_names must be a sequence of names")
            names = tuple(feature_names)
            if not names:
                raise ValueError("At least one feature is required")
            if any(not isinstance(name, str) or not name.strip() for name in names):
                raise ValueError("feature names must be non-empty strings")
            if len(set(names)) != len(names):
                raise ValueError("feature_names must be unique")

        expected = set(names)
        matrix = np.empty((len(supplied), len(names)), dtype=np.float64)
        targets = np.empty(len(supplied), dtype=np.float64)
        base_weights = np.empty(len(supplied), dtype=np.float64)
        for row_index, row in enumerate(supplied):
            if not isinstance(row.features, Mapping):
                raise ValueError(f"rows[{row_index}].features must be a mapping")
            row_keys = tuple(row.features)
            if any(not isinstance(name, str) or not name.strip() for name in row_keys):
                raise ValueError(f"rows[{row_index}] feature names must be non-empty strings")
            actual_keys = set(row_keys)
            if actual_keys != expected:
                missing = sorted(expected - actual_keys)
                extra = sorted(actual_keys - expected)
                raise ValueError(
                    f"rows[{row_index}] feature schema mismatch; missing={missing}, extra={extra}"
                )
            for column, name in enumerate(names):
                matrix[row_index, column] = _as_finite(
                    row.features[name], f"rows[{row_index}].features[{name!r}]"
                )
            targets[row_index] = _as_finite(
                row.actual_margin, f"rows[{row_index}].actual_margin"
            )
            weight = _as_finite(row.sample_weight, f"rows[{row_index}].sample_weight")
            if weight <= 0:
                raise ValueError(f"rows[{row_index}].sample_weight must be positive")
            base_weights[row_index] = weight

        total_weight = float(np.sum(base_weights))
        means = np.sum(base_weights[:, None] * matrix, axis=0) / total_weight
        variance = np.sum(base_weights[:, None] * np.square(matrix - means), axis=0)
        variance /= total_weight
        scales = np.sqrt(np.maximum(variance, 0.0))
        scales = np.where(scales <= self.config.standardization_floor, 1.0, scales)
        standardized = (matrix - means) / scales
        design = np.column_stack((np.ones(len(supplied), dtype=np.float64), standardized))

        beta = _solve_ridge(design, targets, base_weights, self.config.ridge_alpha)
        robust_weights = np.ones(len(supplied), dtype=np.float64)
        huber_scale = self.config.standardization_floor
        iterations = 0
        for iteration in range(1, self.config.max_irls_iterations + 1):
            residuals = targets - design @ beta
            center = _weighted_quantile(residuals, base_weights, 0.5)
            absolute_deviations = np.abs(residuals - center)
            mad_scale = 1.4826 * _weighted_quantile(
                absolute_deviations, base_weights, 0.5
            )
            rms_scale = math.sqrt(
                float(np.average(np.square(residuals), weights=base_weights))
            )
            huber_scale = max(
                mad_scale if mad_scale > self.config.standardization_floor else rms_scale,
                self.config.standardization_floor,
            )
            threshold = self.config.huber_delta * huber_scale
            absolute_residuals = np.abs(residuals)
            robust_weights = np.ones_like(absolute_residuals)
            outside = absolute_residuals > threshold
            robust_weights[outside] = threshold / absolute_residuals[outside]
            updated = _solve_ridge(
                design,
                targets,
                base_weights * robust_weights,
                self.config.ridge_alpha,
            )
            iterations = iteration
            if float(np.max(np.abs(updated - beta))) <= self.config.tolerance:
                beta = updated
                break
            beta = updated

        standardized_coefficients = beta[1:]
        coefficients = standardized_coefficients / scales
        intercept = float(beta[0] - np.dot(coefficients, means))
        fitted = intercept + matrix @ coefficients
        residuals = targets - fitted
        residual_sigma = max(
            math.sqrt(float(np.average(np.square(residuals), weights=base_weights))),
            self.config.min_residual_sigma,
        )
        absolute_errors = np.abs(residuals)
        error_80 = max(
            _weighted_quantile(absolute_errors, base_weights, 0.80),
            self.config.min_margin_error,
        )
        error_95 = max(
            _weighted_quantile(absolute_errors, base_weights, 0.95),
            error_80,
        )

        self._feature_names = names
        self._feature_means = means.astype(np.float64, copy=True)
        self._feature_scales = scales.astype(np.float64, copy=True)
        self._standardized_coefficients = standardized_coefficients.astype(
            np.float64, copy=True
        )
        self._coefficients = coefficients.astype(np.float64, copy=True)
        self.intercept = intercept
        self.standardized_intercept = float(beta[0])
        self.margin_bias = 0.0
        self.residual_sigma = residual_sigma
        self.margin_error_80 = error_80
        self.margin_error_95 = error_95
        self.margin_interval_method = "training_absolute_residual_quantiles"
        self.probability_intercept = 0.0
        self.probability_slope = 1.6 / residual_sigma
        self.probability_method = "training_residual_logistic_approximation"
        self.calibration_source = "training_residuals"
        self.huber_scale = float(huber_scale)
        self.irls_iterations = iterations
        self.training_rows = len(supplied)
        self.as_of = prediction_times[-1]
        self.trained_at = datetime.now(UTC)
        return self

    def _feature_vector(self, features: Mapping[str, float]) -> np.ndarray:
        self._require_fitted()
        if not isinstance(features, Mapping):
            raise ValueError("features must be a mapping")
        expected = set(self._feature_names)
        actual = set(features)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"feature schema mismatch; missing={missing}, extra={extra}")
        return np.asarray(
            [_as_finite(features[name], f"features[{name!r}]") for name in self._feature_names],
            dtype=np.float64,
        )

    def predict_margin(self, features: Mapping[str, float]) -> float:
        """Return calibrated expected home margin for exactly the fitted schema."""

        vector = self._feature_vector(features)
        return float(self.intercept + np.dot(vector, self._coefficients) + self.margin_bias)

    def predict(self, features: Mapping[str, float]) -> HybridPrediction:
        margin = self.predict_margin(features)
        probability = _sigmoid(
            self.probability_intercept + self.probability_slope * margin
        )
        return HybridPrediction(
            predicted_margin=margin,
            home_win_probability=probability,
            away_win_probability=1.0 - probability,
            margin_interval_80=(margin - self.margin_error_80, margin + self.margin_error_80),
            margin_interval_95=(margin - self.margin_error_95, margin + self.margin_error_95),
        )

    def calibrate_oof(
        self,
        predictions: Iterable[TemporalMarginPrediction],
    ) -> HybridMarginModel:
        """Calibrate bias, intervals, and win probabilities from temporal OOF rows.

        ``model_as_of`` is checked against each kickoff and equal-time slates are
        allowed. Fitted/training-set predictions should not be supplied here.
        """

        self._require_fitted()
        supplied = tuple(predictions)
        if len(supplied) < self.config.min_calibration_rows:
            raise InsufficientDataError(
                f"At least {self.config.min_calibration_rows} out-of-sample rows are required"
            )
        predicted = np.empty(len(supplied), dtype=np.float64)
        actual = np.empty(len(supplied), dtype=np.float64)
        previous: datetime | None = None
        for index, row in enumerate(supplied):
            if not isinstance(row, TemporalMarginPrediction):
                raise ValueError(
                    f"predictions[{index}] must be a TemporalMarginPrediction"
                )
            prediction_time = _as_time(
                row.prediction_time, f"predictions[{index}].prediction_time"
            )
            model_as_of = _as_time(row.model_as_of, f"predictions[{index}].model_as_of")
            if model_as_of > prediction_time:
                raise ValueError(
                    f"predictions[{index}] leaks future data: model_as_of is after prediction_time"
                )
            if previous is not None and prediction_time < previous:
                raise ValueError("calibration predictions must be chronological")
            predicted[index] = _as_finite(
                row.predicted_margin, f"predictions[{index}].predicted_margin"
            )
            actual[index] = _as_finite(
                row.actual_margin, f"predictions[{index}].actual_margin"
            )
            previous = prediction_time

        bias = float(np.mean(actual - predicted))
        calibrated_margins = predicted + bias
        errors = actual - calibrated_margins
        residual_sigma = max(
            math.sqrt(float(np.mean(np.square(errors)))),
            self.config.min_residual_sigma,
        )
        absolute_errors = np.abs(errors)
        error_80 = max(
            _conformal_quantile(absolute_errors, 0.80), self.config.min_margin_error
        )
        error_95 = max(_conformal_quantile(absolute_errors, 0.95), error_80)

        decisions = actual != 0.0
        if int(np.sum(decisions)) < self.config.min_calibration_rows:
            raise InsufficientDataError(
                f"At least {self.config.min_calibration_rows} non-tied rows are required"
            )
        x = calibrated_margins[decisions]
        y = (actual[decisions] > 0.0).astype(np.float64)
        if len(np.unique(y)) < 2:
            raise ValueError("calibration outcomes must contain both home and away wins")
        design = np.column_stack((np.ones_like(x), x))
        beta = np.asarray([0.0, 1.6 / residual_sigma], dtype=np.float64)
        penalty = np.diag([self.config.probability_l2, self.config.probability_l2])
        for _ in range(100):
            logits = np.clip(design @ beta, -30.0, 30.0)
            probabilities = 1.0 / (1.0 + np.exp(-logits))
            variance = np.clip(probabilities * (1.0 - probabilities), 1e-6, None)
            gradient = design.T @ (y - probabilities) - penalty @ beta
            hessian = design.T @ (variance[:, None] * design) + penalty
            try:
                update = np.linalg.solve(hessian, gradient)
            except np.linalg.LinAlgError:
                update = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
            beta += update
            if float(np.max(np.abs(update))) <= self.config.tolerance:
                break
        if not np.isfinite(beta).all():
            raise ValueError("Probability calibration produced non-finite coefficients")
        if beta[1] <= 0:
            raise ValueError("Probability calibration produced a non-positive margin slope")

        self.margin_bias = bias
        self.residual_sigma = residual_sigma
        self.margin_error_80 = error_80
        self.margin_error_95 = error_95
        self.margin_interval_method = "temporal_split_conformal_absolute_residuals"
        self.probability_intercept = float(beta[0])
        self.probability_slope = float(beta[1])
        self.probability_method = "temporal_platt_scaling"
        self.calibration_source = "temporal_oof_predictions"
        return self

    def to_dict(self) -> dict[str, Any]:
        self._require_fitted()
        assert self.as_of is not None and self.trained_at is not None
        return {
            "schema_version": HYBRID_ARTIFACT_SCHEMA_VERSION,
            "model_type": HYBRID_MODEL_TYPE,
            "trained_at": self.trained_at.isoformat(),
            "as_of": self.as_of.isoformat(),
            "training_rows": self.training_rows,
            "config": asdict(self.config),
            "feature_schema": [asdict(spec) for spec in self.feature_schema],
            "fit": {
                "intercept": self.intercept,
                "standardized_intercept": self.standardized_intercept,
                "huber_scale": self.huber_scale,
                "irls_iterations": self.irls_iterations,
            },
            "calibration": {
                "source": self.calibration_source,
                "margin_bias": self.margin_bias,
                "residual_sigma": self.residual_sigma,
                "margin_interval_method": self.margin_interval_method,
                "error_80": self.margin_error_80,
                "error_95": self.margin_error_95,
            },
            "probability": {
                "method": self.probability_method,
                "intercept": self.probability_intercept,
                "slope": self.probability_slope,
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HybridMarginModel:
        if payload.get("schema_version") != HYBRID_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported hybrid model schema version: {payload.get('schema_version')!r}"
            )
        if payload.get("model_type") != HYBRID_MODEL_TYPE:
            raise ValueError(f"Unsupported hybrid model type: {payload.get('model_type')!r}")
        try:
            model = cls(HybridConfig(**payload["config"]))
            raw_schema = payload["feature_schema"]
            if not isinstance(raw_schema, list) or not raw_schema:
                raise ValueError("Hybrid artifact feature_schema must be a non-empty list")
            specs = tuple(FeatureSpec(**item) for item in raw_schema)
            fit = payload["fit"]
            calibration = payload["calibration"]
            probability = payload["probability"]
            model._feature_names = tuple(spec.name for spec in specs)
            model._feature_means = np.asarray([spec.mean for spec in specs], dtype=np.float64)
            model._feature_scales = np.asarray([spec.scale for spec in specs], dtype=np.float64)
            model._coefficients = np.asarray(
                [spec.coefficient for spec in specs], dtype=np.float64
            )
            model._standardized_coefficients = np.asarray(
                [spec.standardized_coefficient for spec in specs], dtype=np.float64
            )
            model.intercept = float(fit["intercept"])
            model.standardized_intercept = float(fit["standardized_intercept"])
            model.huber_scale = float(fit["huber_scale"])
            model.irls_iterations = int(fit["irls_iterations"])
            model.calibration_source = str(calibration["source"])
            model.margin_bias = float(calibration["margin_bias"])
            model.residual_sigma = float(calibration["residual_sigma"])
            model.margin_interval_method = str(calibration["margin_interval_method"])
            model.margin_error_80 = float(calibration["error_80"])
            model.margin_error_95 = float(calibration["error_95"])
            model.probability_method = str(probability["method"])
            model.probability_intercept = float(probability["intercept"])
            model.probability_slope = float(probability["slope"])
            model.as_of = parse_datetime(payload["as_of"])
            model.trained_at = parse_datetime(payload["trained_at"])
            model.training_rows = int(payload["training_rows"])
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("Hybrid artifact"):
                raise
            raise ValueError("Malformed hybrid model artifact") from exc

        names = model._feature_names
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Hybrid artifact feature names must be non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("Hybrid artifact feature names must be unique")
        numeric_arrays = (
            model._feature_means,
            model._feature_scales,
            model._coefficients,
            model._standardized_coefficients,
        )
        numeric_values = [
            model.intercept,
            model.standardized_intercept,
            model.huber_scale,
            model.margin_bias,
            model.residual_sigma,
            model.margin_error_80,
            model.margin_error_95,
            model.probability_intercept,
            model.probability_slope,
        ]
        if not all(np.isfinite(array).all() for array in numeric_arrays) or not all(
            math.isfinite(value) for value in numeric_values
        ):
            raise ValueError("Hybrid artifact contains non-finite numeric values")
        if np.any(model._feature_scales <= 0):
            raise ValueError("Hybrid artifact feature scales must be positive")
        expected_raw = model._standardized_coefficients / model._feature_scales
        if not np.allclose(expected_raw, model._coefficients, rtol=1e-10, atol=1e-12):
            raise ValueError("Hybrid artifact feature coefficients are inconsistent")
        expected_intercept = model.standardized_intercept - float(
            np.dot(model._coefficients, model._feature_means)
        )
        if not math.isclose(expected_intercept, model.intercept, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("Hybrid artifact intercepts are inconsistent")
        if model.huber_scale <= 0:
            raise ValueError("Hybrid artifact huber_scale must be positive")
        if model.irls_iterations < 1:
            raise ValueError("Hybrid artifact irls_iterations must be positive")
        if model.training_rows < model.config.min_training_rows:
            raise ValueError("Hybrid artifact has too few training rows")
        if model.residual_sigma <= 0:
            raise ValueError("Hybrid artifact residual_sigma must be positive")
        if not 0 < model.margin_error_80 <= model.margin_error_95:
            raise ValueError("Hybrid artifact margin intervals are invalid")
        if model.probability_slope <= 0:
            raise ValueError("Hybrid artifact probability slope must be positive")
        return model

    def save(self, path: str | Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> HybridMarginModel:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in hybrid model artifact {path}")
        return cls.from_dict(payload)
