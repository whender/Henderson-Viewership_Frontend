"""Shared-scale FCS ratings and cold-start efficiency priors.

FCS teams are not modeled as generic replacement-level opponents.  The point
and efficiency models stored here are fitted jointly across FBS and FCS games,
which puts both divisions on the same scale.  ``FCSModel`` deliberately limits
public team resolution to its current-season FCS identities so it can be used as
an auxiliary model without changing normal FBS identity handling.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from numbers import Integral
from pathlib import Path
from typing import Any

from cfbpredict.efficiency import (
    OpponentAdjustedEfficiencyModel,
    TeamEfficiencyPrior,
)
from cfbpredict.games import Game, atomic_write_json, canonical_team_key, parse_datetime
from cfbpredict.hybrid import HybridMarginModel
from cfbpredict.model import ModelNotFittedError, PointRatingModel

FCS_ARTIFACT_SCHEMA_VERSION = 1
FCS_MODEL_TYPE = "joint_fbs_fcs_efficiency_hybrid_margin"

_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "offense_ppa": ("offense_ppa",),
    "defense_ppa_prevented": ("defense_ppa", "defense_ppa_prevented"),
    "offense_success_rate": ("offense_success", "offense_success_rate"),
    "defense_success_rate_prevented": (
        "defense_success",
        "defense_success_rate_prevented",
    ),
}
_LEAGUE_DEFAULTS = {
    "offense_ppa": 0.0,
    "defense_ppa_prevented": 0.0,
    "offense_success_rate": 0.42,
    "defense_success_rate_prevented": 0.0,
}


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _is_classification(value: str | None, expected: str) -> bool:
    return isinstance(value, str) and value.strip().casefold() == expected


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class FCSIdentity:
    """Stable current-season identity for one FCS team."""

    key: str
    team_id: int | None
    team: str
    classification: str = "fcs"

    def __post_init__(self) -> None:
        if not isinstance(self.team, str) or not self.team.strip():
            raise ValueError("FCS identity team cannot be empty")
        if self.team_id is not None and (
            isinstance(self.team_id, bool)
            or not isinstance(self.team_id, Integral)
            or self.team_id < 0
        ):
            raise ValueError("FCS identity team_id must be a non-negative integer")
        expected_key = canonical_team_key(
            None if self.team_id is None else int(self.team_id), self.team
        )
        if self.key != expected_key:
            raise ValueError("FCS identity key is inconsistent with its ID and name")
        if not _is_classification(self.classification, "fcs"):
            raise ValueError("FCS identity classification must be 'fcs'")


@dataclass(frozen=True, slots=True)
class FCSRanking:
    """Current FCS team ordered on the joint FBS/FCS point-rating scale."""

    key: str
    team_id: int | None
    team: str
    rating: float
    games: int
    classification: str = "fcs"


def division_games(
    games: Iterable[Game],
    allowed_classifications: Collection[str] = frozenset({"fbs", "fcs"}),
) -> list[Game]:
    """Retain games whose two participants are in the requested divisions."""

    if isinstance(allowed_classifications, (str, bytes)):
        raise ValueError("allowed_classifications must be a collection of names")
    allowed: set[str] = set()
    for value in allowed_classifications:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("allowed_classifications must contain non-empty strings")
        allowed.add(value.strip().casefold())
    return [
        game
        for game in games
        if isinstance(game.home_classification, str)
        and game.home_classification.strip().casefold() in allowed
        and isinstance(game.away_classification, str)
        and game.away_classification.strip().casefold() in allowed
    ]


def fcs_identities(games: Iterable[Game], season: int) -> tuple[FCSIdentity, ...]:
    """Derive de-duplicated FCS identities from both sides of a season's games.

    When a stable team ID is associated with more than one display name, the
    chronologically latest current-season name wins.  The result is sorted by
    canonical key, making it deterministic even when input games are unordered.
    """

    if isinstance(season, bool) or not isinstance(season, Integral) or season < 1:
        raise ValueError("season must be a positive integer")
    latest: dict[str, tuple[datetime, int, FCSIdentity]] = {}
    for game in games:
        if not isinstance(game, Game):
            raise ValueError("games must contain Game objects")
        if game.season != int(season):
            continue
        sides = (
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
        )
        for key, team_id, team, classification in sides:
            if not _is_classification(classification, "fcs"):
                continue
            identity = FCSIdentity(
                key=key,
                team_id=team_id,
                team=team,
                classification="fcs",
            )
            candidate = (game.start_date, game.id, identity)
            current = latest.get(key)
            if current is None or candidate[:2] > current[:2]:
                latest[key] = candidate
    return tuple(latest[key][2] for key in sorted(latest))


def _identity_values(
    identities: Iterable[FCSIdentity] | Mapping[str, FCSIdentity],
) -> tuple[FCSIdentity, ...]:
    values = identities.values() if isinstance(identities, Mapping) else identities
    by_key: dict[str, FCSIdentity] = {}
    for identity in values:
        if not isinstance(identity, FCSIdentity):
            raise ValueError("identities must contain FCSIdentity values")
        existing = by_key.get(identity.key)
        if existing is not None and existing != identity:
            raise ValueError(f"Conflicting FCS identities for key {identity.key!r}")
        by_key[identity.key] = identity
    return tuple(by_key[key] for key in sorted(by_key))


def _target_value(target: Any, field: str, *, context: str) -> float | None:
    names = _TARGET_FIELDS[field]
    if isinstance(target, Mapping):
        for name in names:
            if name in target and target[name] is not None:
                return _finite_float(target[name], f"{context}.{name}")
        return None
    for name in names:
        if hasattr(target, name):
            value = getattr(target, name)
            if value is not None:
                return _finite_float(value, f"{context}.{name}")
    return None


def build_fcs_efficiency_priors(
    identities: Iterable[FCSIdentity] | Mapping[str, FCSIdentity],
    previous_targets: Mapping[str, Any],
    previous_games: Iterable[Game],
    carryover: float = 0.65,
    precision: float = 0.5,
) -> dict[str, TeamEfficiencyPrior]:
    """Build current FCS priors from unified prior-season closing ratings.

    Returning teams retain ``carryover`` of their deviation from the prior FCS
    mean.  A current team without a closing target receives that FCS mean.  For
    sparse historical data, each FCS mean falls back first to the unified league
    mean and then to the efficiency model's neutral league prior.
    """

    current = _identity_values(identities)
    if not isinstance(previous_targets, Mapping):
        raise ValueError("previous_targets must be a mapping")
    carry = _finite_float(carryover, "carryover")
    prior_precision = _finite_float(precision, "precision")
    if not 0.0 <= carry <= 1.0:
        raise ValueError("carryover must be between 0 and 1")
    if prior_precision <= 0.0:
        raise ValueError("precision must be positive")

    targets = {str(key): value for key, value in previous_targets.items()}
    previous_fcs_keys: set[str] = set()
    previous_names: dict[str, set[str]] = defaultdict(set)
    for game in previous_games:
        if not isinstance(game, Game):
            raise ValueError("previous_games must contain Game objects")
        for key, team, classification in (
            (game.home_key, game.home_team, game.home_classification),
            (game.away_key, game.away_team, game.away_classification),
        ):
            if not _is_classification(classification, "fcs"):
                continue
            previous_fcs_keys.add(key)
            normalized = _normalized_name(team)
            previous_names[normalized].add(key)

    values_by_key: dict[str, dict[str, float | None]] = {
        key: {
            field: _target_value(target, field, context=f"previous_targets[{key!r}]")
            for field in _TARGET_FIELDS
        }
        for key, target in targets.items()
    }

    fcs_means: dict[str, float] = {}
    for field in _TARGET_FIELDS:
        league_values = [
            value[field]
            for value in values_by_key.values()
            if value[field] is not None
        ]
        league_mean = (
            sum(league_values) / len(league_values)
            if league_values
            else _LEAGUE_DEFAULTS[field]
        )
        fcs_values = [
            values_by_key[key][field]
            for key in previous_fcs_keys
            if key in values_by_key and values_by_key[key][field] is not None
        ]
        fcs_means[field] = (
            sum(fcs_values) / len(fcs_values) if fcs_values else league_mean
        )

    def prior_target(identity: FCSIdentity) -> dict[str, float | None] | None:
        direct = values_by_key.get(identity.key)
        if direct is not None:
            return direct
        matches = previous_names.get(_normalized_name(identity.team), set())
        matched_keys = [key for key in sorted(matches) if key in values_by_key]
        if len(matched_keys) == 1:
            return values_by_key[matched_keys[0]]
        return None

    result: dict[str, TeamEfficiencyPrior] = {}
    for identity in current:
        target = prior_target(identity)
        means: dict[str, float] = {}
        for field, fcs_mean in fcs_means.items():
            closing = None if target is None else target[field]
            means[field] = (
                fcs_mean
                if closing is None
                else fcs_mean + carry * (closing - fcs_mean)
            )
        result[identity.key] = TeamEfficiencyPrior(
            team=identity.team,
            team_id=identity.team_id,
            classification="fcs",
            offense_ppa=means["offense_ppa"],
            defense_ppa_prevented=means["defense_ppa_prevented"],
            offense_success_rate=min(max(means["offense_success_rate"], 0.0), 1.0),
            defense_success_rate_prevented=means[
                "defense_success_rate_prevented"
            ],
            offense_ppa_precision=prior_precision,
            defense_ppa_precision=prior_precision,
            offense_success_precision=prior_precision,
            defense_success_precision=prior_precision,
        )
    return result


class FCSModel:
    """Serializable auxiliary model with FBS and FCS on shared fitted scales."""

    def __init__(
        self,
        season: int,
        as_of: datetime | str,
        baseline: PointRatingModel,
        efficiency: OpponentAdjustedEfficiencyModel,
        hybrid: HybridMarginModel,
        identities: Iterable[FCSIdentity] | Mapping[str, FCSIdentity],
        evaluation: Mapping[str, Any] | None = None,
        source_notes: Sequence[str] = (),
    ) -> None:
        if isinstance(season, bool) or not isinstance(season, Integral) or season < 1:
            raise ValueError("season must be a positive integer")
        if not isinstance(baseline, PointRatingModel):
            raise ValueError("baseline must be a PointRatingModel")
        if not isinstance(efficiency, OpponentAdjustedEfficiencyModel):
            raise ValueError("efficiency must be an OpponentAdjustedEfficiencyModel")
        if not isinstance(hybrid, HybridMarginModel):
            raise ValueError("hybrid must be a HybridMarginModel")
        if evaluation is not None and not isinstance(evaluation, Mapping):
            raise ValueError("evaluation must be a mapping")
        if isinstance(source_notes, (str, bytes)):
            raise ValueError("source_notes must be a sequence of strings")
        parsed_as_of = parse_datetime(as_of)
        identity_values = _identity_values(identities)
        self.season = int(season)
        self.as_of = parsed_as_of
        self.baseline = baseline
        self.efficiency = efficiency
        self.hybrid = hybrid
        self.identities = {identity.key: identity for identity in identity_values}
        self.evaluation = dict(evaluation or {})
        self.source_notes = tuple(str(note) for note in source_notes)
        self._name_index: dict[str, str] = {}
        self._rebuild_name_index()

    @property
    def is_fitted(self) -> bool:
        return (
            self.baseline.is_fitted
            and self.efficiency.is_fitted
            and self.hybrid.is_fitted
            and bool(self.identities)
        )

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise ModelNotFittedError("Fit or load the FCS model before using ratings")

    def _rebuild_name_index(self) -> None:
        candidates: dict[str, list[str]] = defaultdict(list)
        for key, identity in self.identities.items():
            candidates[_normalized_name(identity.team)].append(key)
        ambiguous = [name for name, keys in candidates.items() if len(keys) > 1]
        if ambiguous:
            raise ValueError("FCS identities contain ambiguous duplicate team names")
        self._name_index = {name: keys[0] for name, keys in candidates.items()}

    def _validate_joint_state(self) -> None:
        self._require_fitted()
        if self.baseline.config.fbs_only:
            raise ValueError("FCS baseline must be fitted jointly with FBS and FCS games")
        if self.efficiency.config.fbs_only:
            raise ValueError("FCS efficiency must be fitted jointly with FBS and FCS games")
        if not set(self.identities).issubset(self.efficiency.teams):
            raise ValueError("FCS efficiency state must cover every current FCS identity")
        if any(key != identity.key for key, identity in self.identities.items()):
            raise ValueError("FCS identity outer keys are inconsistent")

    def resolve_team(self, team: str | int, *, team_id: int | None = None) -> str | None:
        """Resolve only current FCS identities, never an embedded FBS identity."""

        self._require_fitted()
        if team_id is not None:
            if isinstance(team_id, bool) or not isinstance(team_id, Integral):
                return None
            key = f"id:{int(team_id)}"
            return key if key in self.identities else None
        if isinstance(team, Integral) and not isinstance(team, bool):
            key = f"id:{int(team)}"
            return key if key in self.identities else None
        if isinstance(team, str) and team.strip().isdigit():
            key = f"id:{int(team.strip())}"
            return key if key in self.identities else None
        return self._name_index.get(_normalized_name(str(team)))

    def suggest_teams(self, query: str, *, limit: int = 5) -> list[str]:
        self._require_fitted()
        if isinstance(limit, bool) or not isinstance(limit, Integral) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        normalized = _normalized_name(str(query))
        starts = sorted(
            identity.team
            for identity in self.identities.values()
            if _normalized_name(identity.team).startswith(normalized)
        )
        contains = sorted(
            identity.team
            for identity in self.identities.values()
            if normalized in _normalized_name(identity.team) and identity.team not in starts
        )
        count = int(limit)
        return starts[:count] + contains[: max(0, count - len(starts))]

    @property
    def mean_fcs_score_rating(self) -> float:
        """Mean known current-FCS value on the joint score-rating scale."""

        self._require_fitted()
        values = [
            self.baseline.ratings[key]
            for key in self.identities
            if key in self.baseline.ratings
        ]
        if not values:
            values = [
                summary.rating
                for summary in self.baseline.teams.values()
                if _is_classification(summary.classification, "fcs")
            ]
        return float(sum(values) / len(values)) if values else 0.0

    def score_rating(self, team: str | int, *, team_id: int | None = None) -> float:
        """Return a current FCS rating, using the FCS mean for a cold-start team."""

        key = self.resolve_team(team, team_id=team_id)
        return self.baseline.ratings.get(key or "", self.mean_fcs_score_rating)

    def rankings(
        self,
        *,
        limit: int | None = None,
        min_games: int = 0,
    ) -> list[FCSRanking]:
        """Rank current FCS identities by their joint score rating."""

        self._require_fitted()
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, Integral) or limit < 0
        ):
            raise ValueError("limit must be a non-negative integer or None")
        if isinstance(min_games, bool) or not isinstance(min_games, Integral) or min_games < 0:
            raise ValueError("min_games must be a non-negative integer")
        fallback = self.mean_fcs_score_rating
        rows = []
        for key, identity in self.identities.items():
            summary = self.baseline.teams.get(key)
            games = 0 if summary is None else summary.games
            if games < int(min_games):
                continue
            rows.append(
                FCSRanking(
                    key=key,
                    team_id=identity.team_id,
                    team=identity.team,
                    rating=self.baseline.ratings.get(key, fallback),
                    games=games,
                )
            )
        rows.sort(key=lambda row: (-row.rating, row.team))
        return rows if limit is None else rows[: int(limit)]

    def to_dict(self) -> dict[str, Any]:
        self._validate_joint_state()
        return {
            "schema_version": FCS_ARTIFACT_SCHEMA_VERSION,
            "model_type": FCS_MODEL_TYPE,
            "season": self.season,
            "as_of": self.as_of.isoformat(),
            "source_notes": list(self.source_notes),
            "identities": {
                key: asdict(identity) for key, identity in self.identities.items()
            },
            "baseline": self.baseline.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "hybrid": self.hybrid.to_dict(),
            "evaluation": self.evaluation,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> FCSModel:
        if not isinstance(payload, Mapping):
            raise ValueError("FCS model artifact must be an object")
        if payload.get("schema_version") != FCS_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported FCS model schema: {payload.get('schema_version')!r}"
            )
        if payload.get("model_type") != FCS_MODEL_TYPE:
            raise ValueError(f"Unsupported FCS model type: {payload.get('model_type')!r}")
        try:
            raw_identities = payload["identities"]
            if not isinstance(raw_identities, Mapping):
                raise ValueError("FCS artifact identities must be an object")
            identities = {
                str(key): FCSIdentity(
                    key=str(value["key"]),
                    team_id=(
                        None
                        if value.get("team_id") is None
                        else int(value["team_id"])
                    ),
                    team=str(value["team"]),
                    classification=str(value.get("classification", "fcs")),
                )
                for key, value in raw_identities.items()
            }
            if any(key != identity.key for key, identity in identities.items()):
                raise ValueError("FCS identity outer keys are inconsistent")
            model = cls(
                season=int(payload["season"]),
                as_of=payload["as_of"],
                baseline=PointRatingModel.from_dict(dict(payload["baseline"])),
                efficiency=OpponentAdjustedEfficiencyModel.from_dict(
                    dict(payload["efficiency"])
                ),
                hybrid=HybridMarginModel.from_dict(dict(payload["hybrid"])),
                identities=identities,
                evaluation=dict(payload.get("evaluation", {})),
                source_notes=tuple(str(note) for note in payload.get("source_notes", ())),
            )
        except KeyError as exc:
            raise ValueError("Malformed FCS model artifact") from exc
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and (
                str(exc).startswith("FCS ")
                or str(exc).startswith("Unsupported ")
            ):
                raise
            raise ValueError("Malformed FCS model artifact") from exc
        model._validate_joint_state()
        return model

    def save(self, path: str | Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> FCSModel:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Expected a JSON object in FCS model artifact {path}")
        return cls.from_dict(payload)
