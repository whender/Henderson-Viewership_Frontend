"""Deterministic calibration of committee-style pairwise ranking models.

Historical data assembly intentionally lives outside this module.  Callers supply
already-oriented pairwise comparisons: feature values are ``first - second`` and
``outcome`` says whether the first team was ranked higher by the committee.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np

from cfbpredict.committee import COMMITTEE_FEATURE_SCHEMA, CommitteeModel

__all__ = [
    "CommitteeTrainingConfig",
    "CommitteeTrainingObservation",
    "fit_committee_model",
]

_FIRST_COMMITTEE_SEASON = 2014
_MAX_SEASON = 2200
_LINE_SEARCH_STEPS = 24
_LOGIT_LIMIT = 40.0
_PROBABILITY_FLOOR = 1e-12


def _finite(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _bounded_pairwise_value(value: object, field: str) -> float:
    parsed = _finite(value, field)
    if not -1.0 <= parsed <= 1.0:
        raise ValueError(f"{field} must be between -1 and 1")
    return parsed


@dataclass(frozen=True, slots=True)
class CommitteeTrainingObservation:
    """One historical pair ordered as first team minus second team.

    ``outcome`` is one when the committee ranked the first team higher and zero
    otherwise.  Head-to-head and common-opponent values use the first team's
    perspective and therefore live in ``[-1, 1]``.
    """

    season: int
    feature_differences: Mapping[str, float]
    head_to_head_value: float
    common_opponent_value: float
    outcome: float
    sample_weight: float = 1.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.season, int)
            or isinstance(self.season, bool)
            or not _FIRST_COMMITTEE_SEASON <= self.season <= _MAX_SEASON
        ):
            raise ValueError(
                f"season must be an integer from {_FIRST_COMMITTEE_SEASON} through "
                f"{_MAX_SEASON}"
            )
        if not isinstance(self.feature_differences, Mapping):
            raise ValueError("feature_differences must be a mapping")
        supplied_names = tuple(self.feature_differences)
        if any(not isinstance(name, str) for name in supplied_names):
            raise ValueError("feature_differences keys must be strings")
        supplied = set(supplied_names)
        expected = set(COMMITTEE_FEATURE_SCHEMA)
        if supplied != expected:
            missing = sorted(expected - supplied)
            extra = sorted(supplied - expected)
            raise ValueError(
                "feature_differences do not match the committee schema; "
                f"missing={missing}, extra={extra}"
            )
        differences = {
            name: _finite(
                self.feature_differences[name],
                f"feature_differences[{name!r}]",
            )
            for name in COMMITTEE_FEATURE_SCHEMA
        }
        outcome = _finite(self.outcome, "outcome")
        if outcome not in {0.0, 1.0}:
            raise ValueError("outcome must be 0 or 1")
        sample_weight = _finite(self.sample_weight, "sample_weight")
        if sample_weight <= 0.0:
            raise ValueError("sample_weight must be positive")

        object.__setattr__(self, "feature_differences", MappingProxyType(differences))
        object.__setattr__(
            self,
            "head_to_head_value",
            _bounded_pairwise_value(self.head_to_head_value, "head_to_head_value"),
        )
        object.__setattr__(
            self,
            "common_opponent_value",
            _bounded_pairwise_value(
                self.common_opponent_value, "common_opponent_value"
            ),
        )
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "sample_weight", sample_weight)


@dataclass(frozen=True, slots=True)
class CommitteeTrainingConfig:
    """Bounds and regularization for pairwise logistic calibration."""

    ridge_alpha: float = 1.0
    min_observations: int = 20
    max_iterations: int = 100
    tolerance: float = 1e-9
    scale_floor: float = 1e-8
    max_step_norm: float = 10.0
    comparable_window: float = 2.0

    def __post_init__(self) -> None:
        ridge_alpha = _finite(self.ridge_alpha, "ridge_alpha")
        if ridge_alpha <= 0.0:
            raise ValueError("ridge_alpha must be positive")
        if (
            not isinstance(self.min_observations, int)
            or isinstance(self.min_observations, bool)
            or self.min_observations < 2
        ):
            raise ValueError("min_observations must be an integer of at least 2")
        if (
            not isinstance(self.max_iterations, int)
            or isinstance(self.max_iterations, bool)
            or self.max_iterations < 1
        ):
            raise ValueError("max_iterations must be a positive integer")
        tolerance = _finite(self.tolerance, "tolerance")
        if tolerance <= 0.0:
            raise ValueError("tolerance must be positive")
        scale_floor = _finite(self.scale_floor, "scale_floor")
        if scale_floor <= 0.0:
            raise ValueError("scale_floor must be positive")
        max_step_norm = _finite(self.max_step_norm, "max_step_norm")
        if max_step_norm <= 0.0:
            raise ValueError("max_step_norm must be positive")
        comparable_window = _finite(self.comparable_window, "comparable_window")
        if comparable_window < 0.0:
            raise ValueError("comparable_window must be non-negative")

        object.__setattr__(self, "ridge_alpha", ridge_alpha)
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "scale_floor", scale_floor)
        object.__setattr__(self, "max_step_norm", max_step_norm)
        object.__setattr__(self, "comparable_window", comparable_window)


def _observation_sort_key(
    observation: CommitteeTrainingObservation,
) -> tuple[float, ...]:
    return (
        float(observation.season),
        *(observation.feature_differences[name] for name in COMMITTEE_FEATURE_SCHEMA),
        observation.head_to_head_value,
        observation.common_opponent_value,
        observation.outcome,
        observation.sample_weight,
    )


def _objective(
    design: np.ndarray,
    outcomes: np.ndarray,
    weights: np.ndarray,
    coefficients: np.ndarray,
    prior: np.ndarray,
    ridge_alpha: float,
) -> float:
    logits = np.clip(design @ coefficients, -_LOGIT_LIMIT, _LOGIT_LIMIT)
    likelihood = np.sum(weights * (np.logaddexp(0.0, logits) - outcomes * logits))
    penalty = 0.5 * ridge_alpha * float(np.dot(coefficients - prior, coefficients - prior))
    return float(likelihood + penalty)


def _fit_coefficients(
    design: np.ndarray,
    outcomes: np.ndarray,
    weights: np.ndarray,
    prior: np.ndarray,
    config: CommitteeTrainingConfig,
) -> tuple[np.ndarray, int, bool]:
    coefficients = prior.astype(np.float64, copy=True)
    identity = np.eye(design.shape[1], dtype=np.float64)
    converged = False
    iterations = 0

    for iteration in range(1, config.max_iterations + 1):
        logits = np.clip(design @ coefficients, -_LOGIT_LIMIT, _LOGIT_LIMIT)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        variances = np.clip(probabilities * (1.0 - probabilities), 1e-9, None)
        gradient = (
            design.T @ (weights * (outcomes - probabilities))
            - config.ridge_alpha * (coefficients - prior)
        )
        hessian = (
            design.T @ ((weights * variances)[:, None] * design)
            + config.ridge_alpha * identity
        )
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
        step_norm = float(np.linalg.norm(step))
        if step_norm > config.max_step_norm:
            step *= config.max_step_norm / step_norm

        current_objective = _objective(
            design,
            outcomes,
            weights,
            coefficients,
            prior,
            config.ridge_alpha,
        )
        factor = 1.0
        candidate = coefficients
        accepted = False
        for _ in range(_LINE_SEARCH_STEPS):
            proposed = coefficients + factor * step
            if _objective(
                design,
                outcomes,
                weights,
                proposed,
                prior,
                config.ridge_alpha,
            ) <= current_objective:
                candidate = proposed
                accepted = True
                break
            factor *= 0.5

        iterations = iteration
        if not accepted:
            break
        change = float(np.max(np.abs(candidate - coefficients)))
        coefficients = candidate
        if change <= config.tolerance:
            converged = True
            break

    if not np.isfinite(coefficients).all():
        raise ValueError("Committee calibration produced non-finite coefficients")
    return coefficients, iterations, converged


def fit_committee_model(
    observations: Iterable[CommitteeTrainingObservation],
    *,
    config: CommitteeTrainingConfig | None = None,
    prior_model: CommitteeModel | None = None,
    provenance: str | None = None,
) -> CommitteeModel:
    """Fit a regularized pairwise logistic committee model.

    Resume coefficients are standardized without centering so a pair and its
    reversal remain exact opposites.  Ridge regularization is centered on the
    supplied model, or on :meth:`CommitteeModel.protocol_default`, which keeps
    protocol-informed behavior for features with little historical variation.
    """

    training_config = config or CommitteeTrainingConfig()
    if not isinstance(training_config, CommitteeTrainingConfig):
        raise ValueError("config must be a CommitteeTrainingConfig")
    prior = prior_model or CommitteeModel.protocol_default()
    if not isinstance(prior, CommitteeModel):
        raise ValueError("prior_model must be a CommitteeModel")
    if provenance is not None and (not isinstance(provenance, str) or not provenance.strip()):
        raise ValueError("provenance must be a non-empty string")

    supplied = tuple(observations)
    for index, observation in enumerate(supplied):
        if not isinstance(observation, CommitteeTrainingObservation):
            raise ValueError(
                f"observations[{index}] must be a CommitteeTrainingObservation"
            )
    if len(supplied) < training_config.min_observations:
        raise ValueError(
            f"At least {training_config.min_observations} pairwise observations are required"
        )
    ordered = tuple(sorted(supplied, key=_observation_sort_key))

    row_count = len(ordered)
    feature_count = len(COMMITTEE_FEATURE_SCHEMA)
    raw_features = np.empty((row_count, feature_count), dtype=np.float64)
    outcomes = np.empty(row_count, dtype=np.float64)
    weights = np.empty(row_count, dtype=np.float64)
    head_to_head = np.empty(row_count, dtype=np.float64)
    common_opponents = np.empty(row_count, dtype=np.float64)
    for row_index, observation in enumerate(ordered):
        for column, name in enumerate(COMMITTEE_FEATURE_SCHEMA):
            raw_features[row_index, column] = observation.feature_differences[name]
        outcomes[row_index] = observation.outcome
        weights[row_index] = observation.sample_weight
        head_to_head[row_index] = observation.head_to_head_value
        common_opponents[row_index] = observation.common_opponent_value

    total_weight = float(np.sum(weights))
    weighted_mean_squares = np.sum(weights[:, None] * np.square(raw_features), axis=0)
    weighted_mean_squares /= total_weight
    observed_scales = np.sqrt(np.maximum(weighted_mean_squares, 0.0))
    fallback_scales = np.asarray(
        [prior.feature_scales[name] for name in COMMITTEE_FEATURE_SCHEMA],
        dtype=np.float64,
    )
    scales = np.where(
        observed_scales > training_config.scale_floor,
        observed_scales,
        fallback_scales,
    )
    standardized = raw_features / scales
    design = np.column_stack((standardized, head_to_head, common_opponents))

    raw_prior_slopes = np.asarray(
        [
            prior.coefficients[name] / prior.feature_scales[name]
            for name in COMMITTEE_FEATURE_SCHEMA
        ],
        dtype=np.float64,
    )
    prior_coefficients = np.concatenate(
        (
            raw_prior_slopes * scales,
            np.asarray(
                [prior.head_to_head_coefficient, prior.common_opponent_coefficient],
                dtype=np.float64,
            ),
        )
    )
    fitted, iterations, converged = _fit_coefficients(
        design,
        outcomes,
        weights,
        prior_coefficients,
        training_config,
    )

    logits = np.clip(design @ fitted, -_LOGIT_LIMIT, _LOGIT_LIMIT)
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    clipped = np.clip(probabilities, _PROBABILITY_FLOOR, 1.0 - _PROBABILITY_FLOOR)
    log_loss = -float(
        np.sum(
            weights
            * (outcomes * np.log(clipped) + (1.0 - outcomes) * np.log(1.0 - clipped))
        )
        / total_weight
    )
    predictions = probabilities >= 0.5
    accuracy = float(np.sum(weights * (predictions == outcomes)) / total_weight)
    seasons = {observation.season for observation in ordered}
    evaluation = {
        "pairwise_accuracy": accuracy,
        "pairwise_log_loss": log_loss,
        "training_observations": float(row_count),
        "training_sample_weight": total_weight,
        "training_seasons": float(len(seasons)),
        "first_season": float(min(seasons)),
        "last_season": float(max(seasons)),
        "optimization_iterations": float(iterations),
        "optimization_converged": float(converged),
        "ridge_alpha": training_config.ridge_alpha,
    }
    model_provenance = (
        provenance.strip()
        if provenance is not None
        else (
            "Regularized pairwise logistic calibration over "
            f"{row_count} historical committee comparisons from "
            f"{min(seasons)}-{max(seasons)}, centered on the protocol prior"
        )
    )
    return CommitteeModel(
        feature_scales={
            name: float(scales[index])
            for index, name in enumerate(COMMITTEE_FEATURE_SCHEMA)
        },
        coefficients={
            name: float(fitted[index])
            for index, name in enumerate(COMMITTEE_FEATURE_SCHEMA)
        },
        head_to_head_coefficient=float(fitted[feature_count]),
        common_opponent_coefficient=float(fitted[feature_count + 1]),
        comparable_window=training_config.comparable_window,
        provenance=model_provenance,
        evaluation=evaluation,
    )
