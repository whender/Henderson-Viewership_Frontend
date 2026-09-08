"""Pure construction of annual CFBD preseason team features.

The builder in this module deliberately knows nothing about HTTP, caches, or files.  Callers
provide raw CFBD endpoint records grouped by the season they requested.  ``None`` means an
endpoint was unavailable; an empty iterable means it was successfully observed and contained
no rows.  That distinction prevents unavailable preseason data from silently becoming zeroes.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

RawRecord = Mapping[str, Any]
FeatureValue = int | float | None

PORTAL_POSITION_GROUPS = ("qb", "skill", "ol", "dl", "lb", "db", "st", "other")
_PORTAL_AGGREGATES = ("all", *PORTAL_POSITION_GROUPS)

_RETURNING_FIELDS = (
    ("totalPPA", "returning_total_ppa"),
    ("totalPassingPPA", "returning_total_passing_ppa"),
    ("totalReceivingPPA", "returning_total_receiving_ppa"),
    ("totalRushingPPA", "returning_total_rushing_ppa"),
    ("percentPPA", "returning_percent_ppa"),
    ("percentPassingPPA", "returning_percent_passing_ppa"),
    ("percentReceivingPPA", "returning_percent_receiving_ppa"),
    ("percentRushingPPA", "returning_percent_rushing_ppa"),
    ("usage", "returning_usage"),
    ("passingUsage", "returning_passing_usage"),
    ("receivingUsage", "returning_receiving_usage"),
    ("rushingUsage", "returning_rushing_usage"),
)
_RETURNING_TOTAL_FIELDS = _RETURNING_FIELDS[:4]

_TALENT_FEATURES = (
    "talent",
    "talent_z",
    "talent_robust_z",
    "talent_source_season",
    "talent_age_seasons",
    "talent_current_missing",
    "talent_missing",
    "talent_stale",
)
_RECRUITING_FEATURES = (
    "recruiting_rank",
    "recruiting_points",
    "recruiting_points_z",
    "recruiting_points_robust_z",
    "recruiting_missing",
)
_RETURNING_FEATURES = (
    *(feature for _, feature in _RETURNING_FIELDS),
    *(
        f"{feature}_{suffix}"
        for _, feature in _RETURNING_TOTAL_FIELDS
        for suffix in ("z", "robust_z")
    ),
    "returning_metric_coverage",
    "returning_missing",
)
_PORTAL_FEATURES = (
    "portal_missing",
    *(
        f"portal_{group}_{metric}"
        for group in _PORTAL_AGGREGATES
        for metric in (
            "incoming_count",
            "outgoing_count",
            "net_count",
            "net_rating",
            "net_rating_z",
            "net_rating_robust_z",
            "rating_coverage",
        )
    ),
    *(
        f"portal_{group}_{metric}"
        for group in _PORTAL_AGGREGATES
        for metric in (
            "incoming_expected_contribution",
            "outgoing_expected_contribution",
            "net_expected_contribution",
            "expected_contribution_coverage",
        )
    ),
    "portal_qb_incoming_max_rating_z",
    "portal_qb_projected_rating_z",
    "portal_qb_projected_average_ppa",
    "portal_qb_projected_total_ppa",
    "portal_qb_projected_passing_average_ppa",
    "portal_qb_projected_passing_total_ppa",
    "portal_qb_projected_passing_usage",
    "portal_qb_projected_history_coverage",
    "portal_qb_replacement_rating_z",
)
_DRAFT_FEATURES = (
    "draft_missing",
    "draft_departures",
    "draft_capital",
    "draft_offense_departures",
    "draft_offense_capital",
    "draft_defense_departures",
    "draft_defense_capital",
    "draft_ol_departures",
    "draft_ol_capital",
)
_ROSTER_FEATURES = (
    "roster_current_count",
    "roster_prior_count",
    "roster_retained_count",
    "roster_retention_rate",
    "roster_offense_prior_count",
    "roster_offense_retained_count",
    "roster_offense_retention_rate",
    "roster_defense_prior_count",
    "roster_defense_retained_count",
    "roster_defense_retention_rate",
    "roster_experience_retention_rate",
    "roster_offense_experience_retention_rate",
    "roster_defense_experience_retention_rate",
    "roster_ol_experience_retention_rate",
    "roster_draft_adjusted_retention_rate",
    "roster_offense_draft_adjusted_retention_rate",
    "roster_defense_draft_adjusted_retention_rate",
    "roster_ol_draft_adjusted_retention_rate",
    "roster_skill_usage_retention_rate",
    "roster_skill_usage_coverage",
    "roster_missing",
    "roster_estimated",
    "roster_estimation_coverage",
    "roster_estimated_eligibility_losses",
    "roster_estimated_portal_exits",
    "roster_estimated_draft_departures",
    "roster_estimated_portal_additions",
    "qb_prior_count",
    "qb_retained_count",
    "qb_room_retention_rate",
    "qb_starter_returns",
    "qb_pass_usage_retention_rate",
    "qb_returning_average_ppa",
    "qb_returning_total_ppa",
    "qb_projection_coverage",
    "qb_pass_usage_missing",
    "qb_retention_missing",
)
_COACH_FEATURES = (
    "coach_change",
    "coach_tenure_years",
    "coach_tenure_censored",
    "coach_is_interim",
    "coach_current_missing",
    "coach_continuity_missing",
    "coach_interim_missing",
    "coach_internal_successor",
)

PRESEASON_FEATURE_SCHEMA = (
    *_TALENT_FEATURES,
    *_RECRUITING_FEATURES,
    *_RETURNING_FEATURES,
    *_PORTAL_FEATURES,
    *_DRAFT_FEATURES,
    *_ROSTER_FEATURES,
    *_COACH_FEATURES,
)


def _freeze_rows(
    value: Iterable[RawRecord] | None, *, field_name: str
) -> tuple[dict[str, Any], ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of mappings or None")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise TypeError(f"{field_name} rows must be mappings")
        rows.append(dict(row))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class PreseasonSourceData:
    """Raw endpoint payloads associated with one requested CFBD season.

    ``head_coaches`` accepts records from ``/coaches``, ``/coaches/seasons``, or
    ``/coaches/tenures``.  ``player_usage`` is optional; when supplied for the prior season it
    lets the builder identify the primary quarterback and weight QB-room retention.
    """

    season: int
    talent: Iterable[RawRecord] | None = None
    team_recruiting: Iterable[RawRecord] | None = None
    returning_production: Iterable[RawRecord] | None = None
    portal: Iterable[RawRecord] | None = None
    draft_picks: Iterable[RawRecord] | None = None
    roster: Iterable[RawRecord] | None = None
    head_coaches: Iterable[RawRecord] | None = None
    player_usage: Iterable[RawRecord] | None = None
    player_ppa: Iterable[RawRecord] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.season, bool) or not isinstance(self.season, int) or self.season < 1869:
            raise ValueError("season must be a valid integer season")
        for item in fields(self):
            if item.name == "season":
                continue
            frozen = _freeze_rows(getattr(self, item.name), field_name=item.name)
            object.__setattr__(self, item.name, frozen)


@dataclass(frozen=True, slots=True)
class PreseasonFeatureRow:
    """One canonical team-season row in the named feature schema."""

    season: int
    team: str
    values: tuple[FeatureValue, ...]

    def __post_init__(self) -> None:
        if len(self.values) != len(PRESEASON_FEATURE_SCHEMA):
            raise ValueError("feature value count does not match PRESEASON_FEATURE_SCHEMA")
        for value in self.values:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("feature values must be finite or None")

    def to_record(self) -> dict[str, int | float | str | None]:
        """Return a strict-JSON-compatible flat record."""

        record: dict[str, int | float | str | None] = {"season": self.season, "team": self.team}
        record.update(dict(zip(PRESEASON_FEATURE_SCHEMA, self.values, strict=True)))
        return record

    def vector(self) -> np.ndarray:
        """Return a numeric vector, representing explicit missing values as ``numpy.nan``."""

        return np.asarray(
            [np.nan if value is None else float(value) for value in self.values],
            dtype=np.float64,
        )


@dataclass(frozen=True, slots=True)
class PreseasonFeatureTable:
    """Deterministically ordered preseason feature rows."""

    season: int
    rows: tuple[PreseasonFeatureRow, ...]
    schema: tuple[str, ...] = PRESEASON_FEATURE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PRESEASON_FEATURE_SCHEMA:
            raise ValueError("schema must be PRESEASON_FEATURE_SCHEMA")
        expected = sorted((row.team for row in self.rows), key=_team_sort_key)
        actual = [row.team for row in self.rows]
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("feature rows must contain unique teams in deterministic order")
        if any(row.season != self.season for row in self.rows):
            raise ValueError("all feature rows must match the table season")

    def to_records(self) -> list[dict[str, int | float | str | None]]:
        return [row.to_record() for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "schema": list(self.schema),
            "records": self.to_records(),
        }

    def matrix(self) -> np.ndarray:
        if not self.rows:
            return np.empty((0, len(self.schema)), dtype=np.float64)
        return np.vstack([row.vector() for row in self.rows])


def standard_and_robust_zscores(
    values: Mapping[str, float | int | None],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Calculate standard and median/MAD z-scores without filling missing values.

    When observed values have zero spread, their transformed value is the legitimate center
    value ``0.0``.  If the median absolute deviation is zero but standard deviation is not, the
    robust transform falls back to the standard transform.
    """

    cleaned = {key: _number(value) for key, value in values.items()}
    observed = np.asarray(
        [value for value in cleaned.values() if value is not None], dtype=np.float64
    )
    standard: dict[str, float | None] = {key: None for key in values}
    robust: dict[str, float | None] = {key: None for key in values}
    if observed.size == 0:
        return standard, robust

    mean = float(np.mean(observed))
    std = float(np.std(observed))
    median = float(np.median(observed))
    mad = float(np.median(np.abs(observed - median)))
    robust_scale = 1.4826 * mad

    for key, value in cleaned.items():
        if value is None:
            continue
        standard_value = 0.0 if std <= 1e-12 else (value - mean) / std
        standard[key] = float(standard_value)
        robust[key] = (
            float((value - median) / robust_scale)
            if robust_scale > 1e-12
            else float(standard_value)
        )
    return standard, robust


class _TeamResolver:
    def __init__(self, names: Mapping[str, str]) -> None:
        self._aliases: dict[str, str] = {}
        self.canonical_names: set[str] = set()
        for raw, canonical in names.items():
            if not isinstance(raw, str) or not isinstance(canonical, str):
                raise TypeError("canonical_team_names must map strings to strings")
            raw_clean = _clean_name(raw)
            canonical_clean = _clean_name(canonical)
            if not raw_clean or not canonical_clean:
                raise ValueError("canonical team names cannot be empty")
            key = _normalize_name(raw_clean)
            existing = self._aliases.get(key)
            if existing is not None and existing != canonical_clean:
                raise ValueError(f"conflicting canonical names for {raw_clean!r}")
            self._aliases[key] = canonical_clean
            self.canonical_names.add(canonical_clean)
        for canonical in self.canonical_names:
            self._aliases.setdefault(_normalize_name(canonical), canonical)

    def resolve(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = _clean_name(value)
        if not cleaned:
            return None
        return self._aliases.get(_normalize_name(cleaned), cleaned)


def _clean_name(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_name(value: str) -> str:
    return _clean_name(value).casefold()


def _team_sort_key(value: str) -> tuple[str, str]:
    return (_normalize_name(value), value)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _identifier(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    text = str(int(value)) if isinstance(value, float) else str(value).strip()
    return text or None


def _unique_numeric_by_team(
    rows: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    *,
    value_key: str,
    label: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows or ():
        team = resolver.resolve(row.get("team"))
        value = _number(row.get(value_key))
        if team is None or value is None:
            continue
        if team in result and not math.isclose(result[team], value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"conflicting {label} rows for {team}")
        result[team] = value
    return result


def _unique_rows_by_team(
    rows: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    *,
    label: str,
) -> dict[str, RawRecord]:
    result: dict[str, RawRecord] = {}
    for row in rows or ():
        team = resolver.resolve(row.get("team"))
        if team is None:
            continue
        if team in result and dict(result[team]) != dict(row):
            raise ValueError(f"conflicting {label} rows for {team}")
        result[team] = row
    return result


def _position_group(value: Any) -> str:
    position = str(value or "").strip().upper().replace("-", "")
    if position in {"QB", "QUARTERBACK"}:
        return "qb"
    if position in {
        "RB", "HB", "FB", "WR", "TE", "H", "APB", "RUNNING BACK", "WIDE RECEIVER",
        "TIGHT END", "FULLBACK",
    }:
        return "skill"
    if position in {
        "OL", "OT", "T", "IOL", "OG", "G", "C", "OFFENSIVE LINE", "OFFENSIVE TACKLE",
        "OFFENSIVE GUARD", "CENTER",
    }:
        return "ol"
    if position in {
        "DL", "DE", "DT", "NT", "EDGE", "ED", "DEFENSIVE LINE", "DEFENSIVE END",
        "DEFENSIVE TACKLE",
    }:
        return "dl"
    if position in {"LB", "ILB", "OLB", "MLB", "LINEBACKER"}:
        return "lb"
    if position in {
        "DB", "CB", "S", "FS", "SS", "NB", "DEFENSIVE BACK", "CORNERBACK", "SAFETY",
    }:
        return "db"
    if position in {"K", "P", "PK", "LS"}:
        return "st"
    return "other"


_OFFENSE_GROUPS = {"qb", "skill", "ol"}
_DEFENSE_GROUPS = {"dl", "lb", "db"}


@dataclass(frozen=True, slots=True)
class _DraftDeparture:
    team: str
    player_id: str | None
    player_name: str
    position_group: str
    overall: int | None


def _draft_departures(
    rows: Sequence[RawRecord], resolver: _TeamResolver
) -> tuple[_DraftDeparture, ...]:
    departures: dict[tuple[str, str, str], _DraftDeparture] = {}
    for row in rows:
        team = resolver.resolve(row.get("collegeTeam"))
        if team is None:
            continue
        player_id = _identifier(row.get("collegeAthleteId"))
        player_name = _normalize_name(str(row.get("name") or ""))
        overall = _year(row.get("overall"))
        departure = _DraftDeparture(
            team, player_id, player_name, _position_group(row.get("position")), overall
        )
        departures[(team, player_id or "", player_name)] = departure
    return tuple(departures[key] for key in sorted(departures))


def _draft_features(
    rows: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    teams: Sequence[str],
) -> dict[str, dict[str, FeatureValue]]:
    result = {team: {} for team in teams}
    if rows is None:
        for values in result.values():
            values["draft_missing"] = 1
        return result
    departures = _draft_departures(rows, resolver)
    for team, values in result.items():
        team_rows = [row for row in departures if row.team == team]
        values["draft_missing"] = 0
        for label, groups in (
            ("", set(PORTAL_POSITION_GROUPS)),
            ("offense_", _OFFENSE_GROUPS),
            ("defense_", _DEFENSE_GROUPS),
            ("ol_", {"ol"}),
        ):
            selected = [row for row in team_rows if row.position_group in groups]
            values[f"draft_{label}departures"] = len(selected)
            values[f"draft_{label}capital"] = sum(
                1.0 / math.sqrt(row.overall) for row in selected if row.overall
            )
    return result


@dataclass(frozen=True, slots=True)
class _PortalEvent:
    key: tuple[str, ...]
    origin: str | None
    destination: str | None
    position_group: str
    rating: float | None
    player_name: str
    expected_contribution: float | None
    average_ppa: float | None
    passing_average_ppa: float | None
    passing_total_ppa: float | None
    passing_usage: float | None


def _player_ppa_indexes(
    rows: Sequence[RawRecord] | None, resolver: _TeamResolver
) -> tuple[
    dict[str, tuple[float | None, float | None]],
    dict[tuple[str, str], tuple[float | None, float | None]],
]:
    """Index actual player-season efficiency and volume as (average, total) PPA."""

    by_id: dict[str, tuple[float | None, float | None]] = {}
    by_team_name: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    for row in rows or ():
        team = resolver.resolve(row.get("team"))
        player_id = _identifier(row.get("id", row.get("playerId")))
        player_name = _normalize_name(str(row.get("name", row.get("player")) or ""))
        average = row.get("averagePPA")
        total = row.get("totalPPA")
        average_all = _number(average.get("all")) if isinstance(average, Mapping) else None
        total_all = _number(total.get("all")) if isinstance(total, Mapping) else None
        values = (average_all, total_all)
        if player_id is not None:
            by_id[player_id] = values
        if team is not None and player_name:
            by_team_name[(team, player_name)] = values
    return by_id, by_team_name


def _portal_events(
    rows: Sequence[RawRecord],
    resolver: _TeamResolver,
    season: int,
    prior_player_ppa: Sequence[RawRecord] | None = None,
    prior_player_usage: Sequence[RawRecord] | None = None,
) -> tuple[_PortalEvent, ...]:
    unique: dict[tuple[str, ...], _PortalEvent] = {}
    _, ppa_by_team_name = _player_ppa_indexes(prior_player_ppa, resolver)
    passing_ppa_by_team_name: dict[
        tuple[str, str], tuple[float | None, float | None]
    ] = {}
    for row in prior_player_ppa or ():
        team = resolver.resolve(row.get("team"))
        player_name = _normalize_name(str(row.get("name", row.get("player")) or ""))
        average = row.get("averagePPA")
        total = row.get("totalPPA")
        if team is not None and player_name:
            passing_ppa_by_team_name[(team, player_name)] = (
                _number(average.get("pass")) if isinstance(average, Mapping) else None,
                _number(total.get("pass")) if isinstance(total, Mapping) else None,
            )
    passing_usage_by_team_name: dict[tuple[str, str], float] = {}
    for row in prior_player_usage or ():
        team = resolver.resolve(row.get("team"))
        player_name = _normalize_name(str(row.get("name", row.get("player")) or ""))
        usage = row.get("usage")
        passing_usage = _number(usage.get("pass")) if isinstance(usage, Mapping) else None
        if team is not None and player_name and passing_usage is not None:
            passing_usage_by_team_name[(team, player_name)] = passing_usage
    for row in rows:
        origin = resolver.resolve(row.get("origin"))
        destination = resolver.resolve(row.get("destination"))
        group = _position_group(row.get("position"))
        key = (
            str(row.get("season", season)),
            _normalize_name(str(row.get("firstName") or "")),
            _normalize_name(str(row.get("lastName") or "")),
            str(row.get("position") or "").strip().upper(),
            origin or "",
            destination or "",
            str(row.get("transferDate") or ""),
        )
        player_name = _normalize_name(
            f"{row.get('firstName') or ''} {row.get('lastName') or ''}"
        )
        prior_ppa = ppa_by_team_name.get((origin, player_name)) if origin else None
        prior_passing_ppa = (
            passing_ppa_by_team_name.get((origin, player_name)) if origin else None
        )
        event = _PortalEvent(
            key,
            origin,
            destination,
            group,
            _number(row.get("rating")),
            player_name,
            prior_ppa[1] if prior_ppa is not None else None,
            prior_ppa[0] if prior_ppa is not None else None,
            prior_passing_ppa[0] if prior_passing_ppa is not None else None,
            prior_passing_ppa[1] if prior_passing_ppa is not None else None,
            passing_usage_by_team_name.get((origin, player_name)) if origin else None,
        )
        existing = unique.get(key)
        if existing is not None and existing != event:
            raise ValueError(f"conflicting portal rows for {' '.join(key[1:3]).strip()}")
        unique[key] = event
    return tuple(unique[key] for key in sorted(unique))


def _portal_features(
    rows: Sequence[RawRecord] | None,
    prior_player_ppa: Sequence[RawRecord] | None,
    prior_player_usage: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    season: int,
    teams: Sequence[str],
) -> dict[str, dict[str, FeatureValue]]:
    result = {team: {} for team in teams}
    if rows is None:
        for values in result.values():
            values["portal_missing"] = 1
        return result

    events = _portal_events(
        rows, resolver, season, prior_player_ppa, prior_player_usage
    )
    rating_values = {str(index): event.rating for index, event in enumerate(events)}
    rating_z, rating_robust_z = standard_and_robust_zscores(rating_values)

    for team in teams:
        values = result[team]
        values["portal_missing"] = 0
        for group in _PORTAL_AGGREGATES:
            incoming_indices = [
                index
                for index, event in enumerate(events)
                if event.destination == team
                and (group == "all" or event.position_group == group)
            ]
            outgoing_indices = [
                index
                for index, event in enumerate(events)
                if event.origin == team and (group == "all" or event.position_group == group)
            ]
            all_indices = incoming_indices + outgoing_indices
            prefix = f"portal_{group}"
            values[f"{prefix}_incoming_count"] = len(incoming_indices)
            values[f"{prefix}_outgoing_count"] = len(outgoing_indices)
            values[f"{prefix}_net_count"] = len(incoming_indices) - len(outgoing_indices)

            incoming_contribution = [
                events[index].expected_contribution
                for index in incoming_indices
                if events[index].expected_contribution is not None
            ]
            outgoing_contribution = [
                events[index].expected_contribution
                for index in outgoing_indices
                if events[index].expected_contribution is not None
            ]
            contribution_observed = len(incoming_contribution) + len(outgoing_contribution)
            values[f"{prefix}_incoming_expected_contribution"] = float(
                sum(incoming_contribution)
            )
            values[f"{prefix}_outgoing_expected_contribution"] = float(
                sum(outgoing_contribution)
            )
            values[f"{prefix}_net_expected_contribution"] = float(
                sum(incoming_contribution) - sum(outgoing_contribution)
            )
            values[f"{prefix}_expected_contribution_coverage"] = (
                1.0 if not all_indices else contribution_observed / len(all_indices)
            )

            rated = sum(events[index].rating is not None for index in all_indices)
            values[f"{prefix}_rating_coverage"] = (
                1.0 if not all_indices else rated / len(all_indices)
            )
            complete = all(events[index].rating is not None for index in all_indices)
            if not complete:
                values[f"{prefix}_net_rating"] = None
                values[f"{prefix}_net_rating_z"] = None
                values[f"{prefix}_net_rating_robust_z"] = None
                continue

            values[f"{prefix}_net_rating"] = float(
                sum(events[index].rating or 0.0 for index in incoming_indices)
                - sum(events[index].rating or 0.0 for index in outgoing_indices)
            )
            values[f"{prefix}_net_rating_z"] = float(
                sum(rating_z[str(index)] or 0.0 for index in incoming_indices)
                - sum(rating_z[str(index)] or 0.0 for index in outgoing_indices)
            )
            values[f"{prefix}_net_rating_robust_z"] = float(
                sum(rating_robust_z[str(index)] or 0.0 for index in incoming_indices)
                - sum(rating_robust_z[str(index)] or 0.0 for index in outgoing_indices)
            )

        incoming_qbs = [
            event
            for event in events
            if event.destination == team and event.position_group == "qb"
        ]
        rated_incoming_qbs = [event for event in incoming_qbs if event.rating is not None]
        values["portal_qb_incoming_max_rating_z"] = (
            max(
                (rating_z[str(index)] or 0.0)
                for index, event in enumerate(events)
                if event in rated_incoming_qbs
            )
            if rated_incoming_qbs
            else (0.0 if not incoming_qbs else None)
        )
        projected_qb = max(
            incoming_qbs,
            key=lambda event: (
                event.passing_usage if event.passing_usage is not None else -1.0,
                (
                    event.passing_total_ppa
                    if event.passing_total_ppa is not None
                    else -math.inf
                ),
                event.rating if event.rating is not None else -math.inf,
                event.player_name,
            ),
            default=None,
        )
        if projected_qb is None:
            values.update(
                {
                    "portal_qb_projected_rating_z": 0.0,
                    "portal_qb_projected_average_ppa": 0.0,
                    "portal_qb_projected_total_ppa": 0.0,
                    "portal_qb_projected_passing_average_ppa": 0.0,
                    "portal_qb_projected_passing_total_ppa": 0.0,
                    "portal_qb_projected_passing_usage": 0.0,
                    "portal_qb_projected_history_coverage": 1.0,
                }
            )
        else:
            projected_index = events.index(projected_qb)
            history_values = (
                projected_qb.average_ppa,
                projected_qb.expected_contribution,
                projected_qb.passing_average_ppa,
                projected_qb.passing_total_ppa,
                projected_qb.passing_usage,
            )
            values.update(
                {
                    "portal_qb_projected_rating_z": rating_z[str(projected_index)],
                    "portal_qb_projected_average_ppa": projected_qb.average_ppa,
                    "portal_qb_projected_total_ppa": projected_qb.expected_contribution,
                    "portal_qb_projected_passing_average_ppa": (
                        projected_qb.passing_average_ppa
                    ),
                    "portal_qb_projected_passing_total_ppa": projected_qb.passing_total_ppa,
                    "portal_qb_projected_passing_usage": projected_qb.passing_usage,
                    "portal_qb_projected_history_coverage": sum(
                        value is not None for value in history_values
                    )
                    / len(history_values),
                }
            )
    return result


@dataclass(frozen=True, slots=True)
class _RosterPlayer:
    position_group: str
    player_name: str
    class_year: int | None


def _roster_class_year(row: RawRecord) -> int | None:
    """Return CFBD's 1-6 roster class, rejecting malformed calendar-year values."""

    for field_name in ("year", "classYear", "academicYear", "classification"):
        value = _number(row.get(field_name))
        if value is not None and value.is_integer() and 1 <= value <= 6:
            return int(value)
    return None


def _roster_index(
    rows: Sequence[RawRecord] | None, resolver: _TeamResolver
) -> dict[str, dict[str, _RosterPlayer]]:
    result: dict[str, dict[str, _RosterPlayer]] = {}
    for row in rows or ():
        team = resolver.resolve(row.get("team"))
        if team is None:
            continue
        players = result.setdefault(team, {})
        player_id = _identifier(row.get("id"))
        if player_id is None:
            continue
        player = _RosterPlayer(
            position_group=_position_group(row.get("position")),
            player_name=_normalize_name(
                f"{row.get('firstName') or ''} {row.get('lastName') or ''}"
            ),
            class_year=_roster_class_year(row),
        )
        if player_id in players and players[player_id] != player:
            raise ValueError(f"conflicting roster positions for player {player_id}")
        players[player_id] = player
    return result


def _estimated_current_roster(
    team: str,
    prior_players: Mapping[str, _RosterPlayer],
    portal_rows: Sequence[RawRecord] | None,
    draft_rows: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    season: int,
) -> tuple[dict[str, _RosterPlayer], dict[str, FeatureValue]]:
    """Project a roster from eligibility and named portal movement.

    The estimate is deliberately conservative: fourth-year-and-later players are treated as
    eligibility losses unless they later appear on the official roster. Portal exits take
    precedence so the two departure counts remain mutually exclusive.
    """

    events = _portal_events(portal_rows or (), resolver, season)
    draft = [row for row in _draft_departures(draft_rows or (), resolver) if row.team == team]
    draft_ids = {row.player_id for row in draft if row.player_id}
    draft_names = {row.player_name for row in draft if row.player_name}
    outgoing_names = {
        event.player_name
        for event in events
        if event.origin == team and event.player_name
    }
    incoming = [event for event in events if event.destination == team]
    retained: dict[str, _RosterPlayer] = {}
    portal_exits = 0
    draft_departures = 0
    eligibility_losses = 0
    known_classes = 0
    for player_id, player in prior_players.items():
        known_classes += player.class_year is not None
        if player_id in draft_ids or (player.player_name and player.player_name in draft_names):
            draft_departures += 1
            continue
        if player.player_name and player.player_name in outgoing_names:
            portal_exits += 1
            continue
        if player.class_year is not None and player.class_year >= 4:
            eligibility_losses += 1
            continue
        retained[player_id] = player

    estimated = dict(retained)
    for index, event in enumerate(incoming):
        synthetic_id = f"portal:{season}:{team}:{event.player_name}:{index}"
        estimated[synthetic_id] = _RosterPlayer(event.position_group, event.player_name, None)

    class_coverage = known_classes / len(prior_players) if prior_players else 0.0
    movement_coverage = 0.5 * (
        (1.0 if portal_rows is not None else 0.0)
        + (1.0 if draft_rows is not None else 0.0)
    )
    audit: dict[str, FeatureValue] = {
        "roster_estimated": 1,
        "roster_estimation_coverage": 0.5 * (class_coverage + movement_coverage),
        "roster_estimated_eligibility_losses": eligibility_losses,
        "roster_estimated_portal_exits": portal_exits,
        "roster_estimated_draft_departures": draft_departures,
        "roster_estimated_portal_additions": len(incoming),
    }
    return estimated, audit


def _usage_indexes(
    rows: Sequence[RawRecord] | None, resolver: _TeamResolver
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    overall_result: dict[str, dict[str, float]] = {}
    pass_result: dict[str, dict[str, float]] = {}
    for row in rows or ():
        group = _position_group(row.get("position"))
        team = resolver.resolve(row.get("team"))
        player_id = _identifier(row.get("id", row.get("playerId")))
        usage = row.get("usage")
        overall_usage = _number(usage.get("overall")) if isinstance(usage, Mapping) else None
        pass_usage = _number(usage.get("pass")) if isinstance(usage, Mapping) else None
        if team is None or player_id is None:
            continue
        if group in {"qb", "skill"} and overall_usage is not None:
            existing = overall_result.setdefault(team, {}).get(player_id)
            overall_result[team][player_id] = (
                overall_usage if existing is None else max(existing, overall_usage)
            )
        if group == "qb" and pass_usage is not None:
            existing = pass_result.setdefault(team, {}).get(player_id)
            pass_result[team][player_id] = (
                pass_usage if existing is None else max(existing, pass_usage)
            )
    return overall_result, pass_result


def _experience_weight(player: _RosterPlayer) -> float:
    return {1: 1.0, 2: 1.5, 3: 2.0, 4: 2.5, 5: 2.5, 6: 2.5}.get(
        player.class_year, 1.0
    )


def _weighted_retention(
    prior_players: Mapping[str, _RosterPlayer],
    retained_ids: set[str],
    groups: set[str] | None = None,
    extra_weights: Mapping[str, float] | None = None,
) -> float | None:
    eligible = {
        player_id: player
        for player_id, player in prior_players.items()
        if groups is None or player.position_group in groups
    }
    bonuses = extra_weights or {}
    total = sum(
        _experience_weight(player) + max(bonuses.get(player_id, 0.0), 0.0)
        for player_id, player in eligible.items()
    )
    if total <= 0.0:
        return None
    return sum(
        _experience_weight(player) + max(bonuses.get(player_id, 0.0), 0.0)
        for player_id, player in eligible.items()
        if player_id in retained_ids
    ) / total


def _roster_features(
    current_rows: Sequence[RawRecord] | None,
    prior_rows: Sequence[RawRecord] | None,
    prior_usage_rows: Sequence[RawRecord] | None,
    prior_player_ppa_rows: Sequence[RawRecord] | None,
    portal_rows: Sequence[RawRecord] | None,
    draft_rows: Sequence[RawRecord] | None,
    resolver: _TeamResolver,
    season: int,
    teams: Sequence[str],
) -> dict[str, dict[str, FeatureValue]]:
    current = _roster_index(current_rows, resolver)
    prior = _roster_index(prior_rows, resolver)
    overall_usage, pass_usage = _usage_indexes(prior_usage_rows, resolver)
    ppa_by_id, ppa_by_team_name = _player_ppa_indexes(prior_player_ppa_rows, resolver)
    draft_by_team: dict[str, tuple[_DraftDeparture, ...]] = {}
    for departure in _draft_departures(draft_rows or (), resolver):
        draft_by_team.setdefault(departure.team, ())
        draft_by_team[departure.team] = (*draft_by_team[departure.team], departure)
    result: dict[str, dict[str, FeatureValue]] = {}

    for team in teams:
        values: dict[str, FeatureValue] = {}
        current_players = current.get(team)
        prior_players = prior.get(team)
        if current_players is not None:
            values.update(
                {
                    "roster_estimated": 0,
                    "roster_estimation_coverage": 1.0,
                    "roster_estimated_eligibility_losses": 0,
                    "roster_estimated_portal_exits": 0,
                    "roster_estimated_draft_departures": 0,
                    "roster_estimated_portal_additions": 0,
                }
            )
        elif prior_players is not None:
            current_players, audit = _estimated_current_roster(
                team, prior_players, portal_rows, draft_rows, resolver, season
            )
            values.update(audit)
        values["roster_current_count"] = (
            len(current_players) if current_players is not None else None
        )
        values["roster_prior_count"] = len(prior_players) if prior_players is not None else None
        values["roster_missing"] = int(current_players is None or prior_players is None)

        if current_players is not None and prior_players is not None:
            current_ids = set(current_players)
            prior_ids = set(prior_players)
            retained = prior_ids & current_ids
            values["roster_retained_count"] = len(retained)
            values["roster_retention_rate"] = (
                len(retained) / len(prior_ids) if prior_ids else None
            )
            values["roster_experience_retention_rate"] = _weighted_retention(
                prior_players, retained
            )
            draft_bonuses: dict[str, float] = {}
            for player_id, player in prior_players.items():
                matching = next(
                    (
                        departure
                        for departure in draft_by_team.get(team, ())
                        if departure.player_id == player_id
                        or (
                            player.player_name
                            and departure.player_name == player.player_name
                        )
                    ),
                    None,
                )
                if matching is not None and matching.overall:
                    draft_bonuses[player_id] = 4.0 / math.sqrt(matching.overall)
            values["roster_draft_adjusted_retention_rate"] = _weighted_retention(
                prior_players, retained, extra_weights=draft_bonuses
            )
            for label, groups in (("offense", _OFFENSE_GROUPS), ("defense", _DEFENSE_GROUPS)):
                prior_group_ids = {
                    player_id
                    for player_id, player in prior_players.items()
                    if player.position_group in groups
                }
                retained_group_ids = prior_group_ids & current_ids
                values[f"roster_{label}_prior_count"] = len(prior_group_ids)
                values[f"roster_{label}_retained_count"] = len(retained_group_ids)
                values[f"roster_{label}_retention_rate"] = (
                    len(retained_group_ids) / len(prior_group_ids)
                    if prior_group_ids
                    else None
                )
                values[f"roster_{label}_experience_retention_rate"] = (
                    _weighted_retention(prior_players, retained, groups)
                )
                values[f"roster_{label}_draft_adjusted_retention_rate"] = (
                    _weighted_retention(
                        prior_players, retained, groups, draft_bonuses
                    )
                )
            values["roster_ol_experience_retention_rate"] = _weighted_retention(
                prior_players, retained, {"ol"}
            )
            values["roster_ol_draft_adjusted_retention_rate"] = _weighted_retention(
                prior_players, retained, {"ol"}, draft_bonuses
            )

            skill_ids = {
                player_id
                for player_id, player in prior_players.items()
                if player.position_group in {"qb", "skill"}
            }
            team_overall_usage = overall_usage.get(team, {})
            observed_skill_ids = skill_ids & set(team_overall_usage)
            total_skill_usage = sum(
                max(team_overall_usage[player_id], 0.0) for player_id in observed_skill_ids
            )
            values["roster_skill_usage_coverage"] = (
                len(observed_skill_ids) / len(skill_ids) if skill_ids else None
            )
            values["roster_skill_usage_retention_rate"] = (
                sum(
                    max(team_overall_usage[player_id], 0.0)
                    for player_id in observed_skill_ids & retained
                )
                / total_skill_usage
                if total_skill_usage > 0.0
                else None
            )

            prior_qbs = {
                player_id
                for player_id, player in prior_players.items()
                if player.position_group == "qb"
            }
            retained_qbs = prior_qbs & current_ids
            values["qb_prior_count"] = len(prior_qbs)
            values["qb_retained_count"] = len(retained_qbs)
            values["qb_room_retention_rate"] = (
                len(retained_qbs) / len(prior_qbs) if prior_qbs else None
            )
            values["qb_retention_missing"] = int(not prior_qbs)

            qb_usage = pass_usage.get(team, {})
            if qb_usage:
                values["qb_pass_usage_missing"] = 0
                starter_id = max(qb_usage, key=lambda player_id: (qb_usage[player_id], player_id))
                values["qb_starter_returns"] = int(starter_id in current_ids)
                total_usage = sum(max(value, 0.0) for value in qb_usage.values())
                values["qb_pass_usage_retention_rate"] = (
                    sum(max(qb_usage.get(player_id, 0.0), 0.0) for player_id in retained_qbs)
                    / total_usage
                    if total_usage > 0.0
                    else None
                )
                starter = prior_players.get(starter_id)
                starter_ppa = ppa_by_id.get(starter_id)
                if starter_ppa is None and starter is not None and starter.player_name:
                    starter_ppa = ppa_by_team_name.get((team, starter.player_name))
                starter_returns = starter_id in current_ids
                values["qb_returning_average_ppa"] = (
                    starter_ppa[0] if starter_returns and starter_ppa is not None else None
                )
                values["qb_returning_total_ppa"] = (
                    starter_ppa[1] if starter_returns and starter_ppa is not None else None
                )
                values["qb_projection_coverage"] = int(
                    starter_returns and starter_ppa is not None
                )
            else:
                values["qb_pass_usage_missing"] = 1
                values["qb_projection_coverage"] = 0
        else:
            values["qb_pass_usage_missing"] = 1
            values["qb_retention_missing"] = 1
            values["qb_projection_coverage"] = 0
        result[team] = values
    return result


@dataclass(frozen=True, slots=True)
class _CoachInfo:
    coach_id: str
    start_year: int | None
    is_interim: bool | None
    season_games: int | None


def _year(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _date_year(value: Any) -> int | None:
    if not isinstance(value, str) or len(value.strip()) < 4:
        return None
    try:
        year = int(value.strip()[:4])
    except ValueError:
        return None
    return year if 1869 <= year <= 2200 else None


def _coach_index(
    rows: Sequence[RawRecord] | None, resolver: _TeamResolver, requested_season: int
) -> dict[str, _CoachInfo]:
    candidates: dict[str, list[_CoachInfo]] = {}
    for row in rows or ():
        nested_coach = row.get("coach")
        coach_id = _identifier(
            nested_coach.get("id") if isinstance(nested_coach, Mapping) else row.get("id")
        )
        if coach_id is None:
            continue
        interim_raw = row.get("isInterim")
        interim = interim_raw if isinstance(interim_raw, bool) else None
        hire_year = _date_year(row.get("hireDate"))
        seasons = row.get("seasons")
        if isinstance(seasons, Sequence) and not isinstance(seasons, (str, bytes)):
            season_rows = [item for item in seasons if isinstance(item, Mapping)]
            current_rows = [
                item
                for item in season_rows
                if _year(item.get("year")) == requested_season
            ]
            for season_row in current_rows:
                team = resolver.resolve(season_row.get("school"))
                if team is None:
                    continue
                team_years = [
                    _year(item.get("year"))
                    for item in season_rows
                    if resolver.resolve(item.get("school")) == team
                ]
                known_years = [year for year in team_years if year is not None]
                start_year = hire_year or (min(known_years) if known_years else None)
                candidates.setdefault(team, []).append(
                    _CoachInfo(
                        coach_id,
                        start_year,
                        interim,
                        _year(season_row.get("games")),
                    )
                )
            continue

        row_season = _year(row.get("year"))
        if row_season is not None and row_season != requested_season:
            continue
        nested_team = row.get("team")
        raw_team = nested_team.get("school") if isinstance(nested_team, Mapping) else nested_team
        team = resolver.resolve(raw_team)
        if team is None:
            continue
        candidates.setdefault(team, []).append(
            _CoachInfo(
                coach_id,
                _year(row.get("startYear")) or hire_year,
                interim,
                _year(row.get("games")),
            )
        )

    result: dict[str, _CoachInfo] = {}
    for team, options in candidates.items():
        by_id: dict[str, list[_CoachInfo]] = {}
        for option in options:
            by_id.setdefault(option.coach_id, []).append(option)
        if len(by_id) > 1:
            non_interim = {
                coach_id
                for coach_id, coach_options in by_id.items()
                if any(option.is_interim is False for option in coach_options)
            }
            if len(non_interim) == 1:
                selected_id = next(iter(non_interim))
            else:
                # CFBD can assign the retiring coach and the bowl-game successor to
                # the same season without marking either as interim. Treat the coach
                # responsible for the unique largest number of games as that season's
                # primary coach. A tie remains genuinely ambiguous and is left missing.
                game_totals = {
                    coach_id: max(
                        (
                            option.season_games
                            for option in coach_options
                            if option.season_games is not None
                        ),
                        default=-1,
                    )
                    for coach_id, coach_options in by_id.items()
                }
                largest = max(game_totals.values())
                leaders = {
                    coach_id for coach_id, games in game_totals.items() if games == largest
                }
                if largest < 0 or len(leaders) != 1:
                    continue
                selected_id = next(iter(leaders))
        else:
            selected_id = next(iter(by_id))
        selected = by_id[selected_id]
        starts = [option.start_year for option in selected if option.start_year is not None]
        interim_values = {option.is_interim for option in selected if option.is_interim is not None}
        result[team] = _CoachInfo(
            selected_id,
            min(starts) if starts else None,
            next(iter(interim_values)) if len(interim_values) == 1 else None,
            max(
                (
                    option.season_games
                    for option in selected
                    if option.season_games is not None
                ),
                default=None,
            ),
        )
    return result


def _coach_candidate_ids(
    rows: Sequence[RawRecord] | None, resolver: _TeamResolver, requested_season: int
) -> dict[str, set[str]]:
    """Return every coach credited to a team-season, including bowl successors."""

    result: dict[str, set[str]] = {}
    for row in rows or ():
        nested_coach = row.get("coach")
        coach_id = _identifier(
            nested_coach.get("id") if isinstance(nested_coach, Mapping) else row.get("id")
        )
        if coach_id is None:
            continue
        seasons = row.get("seasons")
        if isinstance(seasons, Sequence) and not isinstance(seasons, (str, bytes)):
            for season_row in seasons:
                if not isinstance(season_row, Mapping):
                    continue
                if _year(season_row.get("year")) != requested_season:
                    continue
                team = resolver.resolve(season_row.get("school"))
                if team is not None:
                    result.setdefault(team, set()).add(coach_id)
            continue
        if (row_year := _year(row.get("year"))) is not None and row_year != requested_season:
            continue
        nested_team = row.get("team")
        raw_team = nested_team.get("school") if isinstance(nested_team, Mapping) else nested_team
        team = resolver.resolve(raw_team)
        if team is not None:
            result.setdefault(team, set()).add(coach_id)
    return result


def _coach_features(
    sources: Mapping[int, PreseasonSourceData],
    resolver: _TeamResolver,
    season: int,
    teams: Sequence[str],
) -> dict[str, dict[str, FeatureValue]]:
    indexes = {
        year: _coach_index(source.head_coaches, resolver, year)
        for year, source in sources.items()
        if source.head_coaches is not None
    }
    current = indexes.get(season, {})
    prior = indexes.get(season - 1, {})
    prior_available = season - 1 in indexes
    prior_candidates = _coach_candidate_ids(
        sources.get(season - 1).head_coaches if season - 1 in sources else None,
        resolver,
        season - 1,
    )
    result: dict[str, dict[str, FeatureValue]] = {}

    for team in teams:
        values: dict[str, FeatureValue] = {}
        current_coach = current.get(team)
        prior_coach = prior.get(team)
        values["coach_current_missing"] = int(current_coach is None)
        values["coach_continuity_missing"] = int(
            current_coach is None or not prior_available or prior_coach is None
        )
        if current_coach is not None and prior_available and prior_coach is not None:
            values["coach_change"] = int(current_coach.coach_id != prior_coach.coach_id)
            values["coach_internal_successor"] = int(
                current_coach.coach_id != prior_coach.coach_id
                and current_coach.coach_id in prior_candidates.get(team, set())
            )

        if current_coach is not None:
            values["coach_is_interim"] = (
                int(current_coach.is_interim) if current_coach.is_interim is not None else None
            )
            values["coach_interim_missing"] = int(current_coach.is_interim is None)
            if current_coach.start_year is not None and current_coach.start_year <= season:
                values["coach_tenure_years"] = season - current_coach.start_year + 1
                values["coach_tenure_censored"] = 0
            else:
                tenure = 1
                cursor = season - 1
                censored = 1
                while cursor in indexes:
                    historical = indexes[cursor].get(team)
                    if historical is None:
                        break
                    if historical.coach_id != current_coach.coach_id:
                        censored = 0
                        break
                    tenure += 1
                    cursor -= 1
                values["coach_tenure_years"] = tenure
                values["coach_tenure_censored"] = censored
        else:
            values["coach_interim_missing"] = 1
        result[team] = values
    return result


def _discover_target_teams(source: PreseasonSourceData, resolver: _TeamResolver) -> set[str]:
    discovered: set[str] = set()
    for rows in (
        source.talent,
        source.team_recruiting,
        source.returning_production,
        source.roster,
        source.player_usage,
        source.player_ppa,
    ):
        for row in rows or ():
            team = resolver.resolve(row.get("team"))
            if team is not None:
                discovered.add(team)
    for row in source.portal or ():
        for field_name in ("origin", "destination"):
            team = resolver.resolve(row.get(field_name))
            if team is not None:
                discovered.add(team)
    for row in source.draft_picks or ():
        team = resolver.resolve(row.get("collegeTeam"))
        if team is not None:
            discovered.add(team)
    discovered.update(_coach_index(source.head_coaches, resolver, source.season))
    return discovered


def build_preseason_features(
    season: int,
    source_data: Iterable[PreseasonSourceData],
    canonical_team_names: Mapping[str, str],
    *,
    teams: Iterable[str] | None = None,
    max_talent_staleness: int = 2,
) -> PreseasonFeatureTable:
    """Aggregate raw annual CFBD data into canonical, deterministic feature rows.

    ``source_data`` should normally include ``season`` and ``season - 1``; older seasons allow
    stale talent fallback and a longer observed coaching tenure.  If ``teams`` is omitted, the
    canonical mapping's values define the output universe.  With an empty mapping, teams are
    discovered from the target-season payloads.
    """

    if isinstance(season, bool) or not isinstance(season, int):
        raise ValueError("season must be an integer")
    if (
        isinstance(max_talent_staleness, bool)
        or not isinstance(max_talent_staleness, int)
        or max_talent_staleness < 0
    ):
        raise ValueError("max_talent_staleness must be a non-negative integer")

    sources: dict[int, PreseasonSourceData] = {}
    for source in source_data:
        if not isinstance(source, PreseasonSourceData):
            raise TypeError("source_data must contain PreseasonSourceData instances")
        if source.season in sources:
            raise ValueError(f"duplicate source data for season {source.season}")
        sources[source.season] = source

    resolver = _TeamResolver(canonical_team_names)
    target = sources.get(season, PreseasonSourceData(season))
    if teams is not None:
        resolved_teams = {resolver.resolve(team) for team in teams}
        team_names = {team for team in resolved_teams if team is not None}
    elif resolver.canonical_names:
        team_names = set(resolver.canonical_names)
    else:
        team_names = _discover_target_teams(target, resolver)
    ordered_teams = tuple(sorted(team_names, key=_team_sort_key))

    talent_by_year: dict[int, dict[str, float]] = {}
    talent_z_by_year: dict[int, dict[str, float | None]] = {}
    talent_robust_by_year: dict[int, dict[str, float | None]] = {}
    for year, source in sources.items():
        raw = _unique_numeric_by_team(
            source.talent, resolver, value_key="talent", label=f"{year} talent"
        )
        talent_by_year[year] = raw
        talent_z_by_year[year], talent_robust_by_year[year] = (
            standard_and_robust_zscores(raw)
        )

    recruiting_rows = _unique_rows_by_team(
        target.team_recruiting, resolver, label=f"{season} recruiting"
    )
    recruiting_points = {
        team: value
        for team, row in recruiting_rows.items()
        if (value := _number(row.get("points"))) is not None
    }
    recruiting_z, recruiting_robust = standard_and_robust_zscores(recruiting_points)

    returning_rows = _unique_rows_by_team(
        target.returning_production, resolver, label=f"{season} returning production"
    )
    returning_transforms: dict[str, tuple[dict[str, float | None], dict[str, float | None]]] = {}
    for raw_field, _ in _RETURNING_TOTAL_FIELDS:
        values = {
            team: value
            for team, row in returning_rows.items()
            if (value := _number(row.get(raw_field))) is not None
        }
        returning_transforms[raw_field] = standard_and_robust_zscores(values)

    prior = sources.get(season - 1, PreseasonSourceData(season - 1))
    portal = _portal_features(
        target.portal,
        prior.player_ppa,
        prior.player_usage,
        resolver,
        season,
        ordered_teams,
    )
    draft = _draft_features(target.draft_picks, resolver, ordered_teams)
    roster = _roster_features(
        target.roster,
        prior.roster,
        prior.player_usage,
        prior.player_ppa,
        target.portal,
        target.draft_picks,
        resolver,
        season,
        ordered_teams,
    )
    coaches = _coach_features(sources, resolver, season, ordered_teams)

    rows: list[PreseasonFeatureRow] = []
    for team in ordered_teams:
        values: dict[str, FeatureValue] = {name: None for name in PRESEASON_FEATURE_SCHEMA}

        current_talent = talent_by_year.get(season, {}).get(team)
        source_year: int | None = season if current_talent is not None else None
        if source_year is None:
            for candidate in range(season - 1, season - max_talent_staleness - 1, -1):
                if team in talent_by_year.get(candidate, {}):
                    source_year = candidate
                    break
        values["talent_current_missing"] = int(current_talent is None)
        values["talent_missing"] = int(source_year is None)
        if source_year is not None:
            age = season - source_year
            values["talent"] = talent_by_year[source_year][team]
            values["talent_z"] = talent_z_by_year[source_year][team]
            values["talent_robust_z"] = talent_robust_by_year[source_year][team]
            values["talent_source_season"] = source_year
            values["talent_age_seasons"] = age
            values["talent_stale"] = int(age > 0)

        recruiting_row = recruiting_rows.get(team)
        recruiting_value = recruiting_points.get(team)
        values["recruiting_missing"] = int(recruiting_value is None)
        if recruiting_row is not None:
            values["recruiting_rank"] = _number(recruiting_row.get("rank"))
        if recruiting_value is not None:
            values["recruiting_points"] = recruiting_value
            values["recruiting_points_z"] = recruiting_z[team]
            values["recruiting_points_robust_z"] = recruiting_robust[team]

        returning_row = returning_rows.get(team)
        observed_returning = 0
        if returning_row is not None:
            for raw_field, feature in _RETURNING_FIELDS:
                metric = _number(returning_row.get(raw_field))
                values[feature] = metric
                observed_returning += metric is not None
            for raw_field, feature in _RETURNING_TOTAL_FIELDS:
                standard, robust = returning_transforms[raw_field]
                values[f"{feature}_z"] = standard.get(team)
                values[f"{feature}_robust_z"] = robust.get(team)
        values["returning_metric_coverage"] = (
            observed_returning / len(_RETURNING_FIELDS) if returning_row is not None else None
        )
        values["returning_missing"] = int(returning_row is None or observed_returning == 0)

        values.update(portal[team])
        values.update(draft[team])
        values.update(roster[team])
        values.update(coaches[team])

        incoming_qb_rating = values.get("portal_qb_incoming_max_rating_z")
        starter_returns = values.get("qb_starter_returns")
        values["portal_qb_replacement_rating_z"] = (
            None
            if incoming_qb_rating is None
            else float(incoming_qb_rating)
            * (1.0 - min(max(float(starter_returns), 0.0), 1.0))
            if starter_returns is not None
            else float(incoming_qb_rating)
        )

        row_values = tuple(_json_feature_value(values[name]) for name in PRESEASON_FEATURE_SCHEMA)
        rows.append(PreseasonFeatureRow(season, team, row_values))

    return PreseasonFeatureTable(season, tuple(rows))


def _json_feature_value(value: FeatureValue) -> FeatureValue:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return numeric
