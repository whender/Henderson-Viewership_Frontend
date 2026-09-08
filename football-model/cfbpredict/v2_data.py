"""Adapters from provenance-stamped CFBD snapshots to V2 preseason features."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cfbpredict.config import DEFAULT_PLAYER_AVAILABILITY_PATH, DEFAULT_TEAM_CONTINUITY_PATH
from cfbpredict.enrichment_data import enrichment_path, load_enrichment_year
from cfbpredict.games import read_json
from cfbpredict.preseason import PreseasonSourceData, build_preseason_features

# A deliberately curated subset of the full auditable table. Highly duplicated raw,
# standard-z, and robust-z variants are not all sent to the prior regression.
BASE_PRIOR_FEATURES = (
    "talent_z",
    "talent_age_seasons",
    "talent_current_missing",
    "talent_missing",
    "talent_stale",
    "recruiting_points_z",
    "recruiting_missing",
    "returning_total_ppa_z",
    "returning_total_passing_ppa_z",
    "returning_total_receiving_ppa_z",
    "returning_total_rushing_ppa_z",
    "returning_percent_ppa",
    "returning_percent_passing_ppa",
    "returning_percent_receiving_ppa",
    "returning_percent_rushing_ppa",
    "returning_usage",
    "returning_passing_usage",
    "returning_receiving_usage",
    "returning_rushing_usage",
    "returning_missing",
    "portal_all_net_count",
    "portal_all_net_rating_z",
    "portal_all_net_expected_contribution",
    "portal_all_expected_contribution_coverage",
    "portal_all_rating_coverage",
    "portal_qb_incoming_count",
    "portal_qb_outgoing_count",
    "portal_qb_net_rating_z",
    "portal_qb_net_expected_contribution",
    "portal_qb_replacement_rating_z",
    "portal_skill_net_count",
    "portal_skill_net_rating_z",
    "portal_skill_net_expected_contribution",
    "portal_ol_net_count",
    "portal_ol_net_rating_z",
    "portal_ol_net_expected_contribution",
    "portal_dl_net_count",
    "portal_dl_net_rating_z",
    "portal_dl_net_expected_contribution",
    "portal_lb_net_count",
    "portal_lb_net_rating_z",
    "portal_lb_net_expected_contribution",
    "portal_db_net_count",
    "portal_db_net_rating_z",
    "portal_db_net_expected_contribution",
    "portal_missing",
    "draft_departures",
    "draft_capital",
    "draft_offense_departures",
    "draft_offense_capital",
    "draft_defense_departures",
    "draft_defense_capital",
    "draft_ol_departures",
    "draft_ol_capital",
    "draft_missing",
    "roster_retention_rate",
    "roster_offense_retention_rate",
    "roster_defense_retention_rate",
    "roster_experience_retention_rate",
    "roster_offense_experience_retention_rate",
    "roster_defense_experience_retention_rate",
    "roster_ol_experience_retention_rate",
    "roster_ol_starter_retention_rate",
    "roster_ol_starter_retention_missing",
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
    "qb_room_retention_rate",
    "qb_starter_returns",
    "qb_pass_usage_retention_rate",
    "qb_returning_average_ppa",
    "qb_returning_total_ppa",
    "qb_projection_coverage",
    "qb_pass_usage_missing",
    "qb_retention_missing",
    "coach_change",
    "coach_tenure_years",
    "coach_current_missing",
    "coach_continuity_missing",
    "coach_internal_successor",
    "coach_staff_retention_rate",
    "coach_staff_retention_missing",
    "coach_offense_staff_retention_rate",
    "coach_offense_staff_retention_missing",
)

PREVIOUS_EFFICIENCY_FEATURES = (
    "previous_offense_ppa",
    "previous_defense_ppa",
    "previous_offense_success",
    "previous_defense_success",
    "previous_efficiency_missing",
    "talent_z_change",
    "reconciled_offense_continuity",
    "reconciled_passing_continuity",
    "returning_reconciliation_factor",
    "reconciled_returning_total_ppa_z",
    "reconciled_returning_passing_ppa_z",
    "previous_offense_x_continuity",
    "previous_defense_x_continuity",
    "previous_offense_x_passing_continuity",
)

PRIOR_FEATURE_SCHEMA = (*BASE_PRIOR_FEATURES, *PREVIOUS_EFFICIENCY_FEATURES)
PRIOR_AUDIT_FEATURES = {
    "draft_departures",
    "draft_capital",
    "draft_offense_departures",
    "draft_offense_capital",
    "draft_defense_departures",
    "draft_defense_capital",
    "draft_ol_departures",
    "draft_ol_capital",
    "roster_estimated",
    "roster_estimation_coverage",
    "roster_estimated_eligibility_losses",
    "roster_estimated_portal_exits",
    "roster_estimated_draft_departures",
    "roster_estimated_portal_additions",
    "roster_ol_starter_retention_rate",
    "coach_staff_retention_rate",
    "coach_offense_staff_retention_rate",
    "coach_internal_successor",
}
PRIOR_MEAN_FEATURE_SCHEMA = tuple(
    name
    for name in PRIOR_FEATURE_SCHEMA
    if not name.endswith("_missing")
    and name != "previous_efficiency_missing"
    and name not in PRIOR_AUDIT_FEATURES
    and not name.startswith("returning_")
    and not (name.startswith("portal_") and name.endswith("_count"))
)

_TEAM_CONTINUITY_RATE_SPECS = (
    (
        "roster_ol_starter_retention_rate",
        "roster_ol_starter_retention_missing",
        "ol_starters_returning",
        "ol_starters_total",
    ),
    (
        "coach_staff_retention_rate",
        "coach_staff_retention_missing",
        "on_field_coaches_retained",
        "on_field_coaches_total",
    ),
    (
        "coach_offense_staff_retention_rate",
        "coach_offense_staff_retention_missing",
        "offense_coaches_retained",
        "offense_coaches_total",
    ),
)
_TEAM_CONTINUITY_REQUIRED_FIELDS = {
    "season",
    "team",
    "ol_starters_returning",
    "ol_starters_total",
    "on_field_coaches_retained",
    "on_field_coaches_total",
    "offense_coaches_retained",
    "offense_coaches_total",
    "reason",
    "official_source_urls",
}


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _finite(value: Any, *, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default if value is None else float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _feature_value(record: Mapping[str, Any], name: str) -> float:
    value = record.get(name)
    if value is not None:
        return _finite(value)
    # Missing z-scores are naturally neutral at zero. Missing continuity rates are
    # unknown, not zero retention; use a neutral 50% and let explicit flags widen
    # the prior precision rather than pushing its mean toward a roster collapse.
    if (
        "retention_rate" in name
        or name.startswith("returning_percent_")
        or name
        in {
            "returning_usage",
            "returning_passing_usage",
            "returning_receiving_usage",
            "returning_rushing_usage",
            "qb_starter_returns",
            "coach_change",
        }
    ):
        return 0.5
    if name == "coach_tenure_years":
        return 1.0
    return 0.0


def _load_team_continuity_overrides(
    path: str | Path | None,
) -> tuple[dict[str, Any], ...]:
    """Load fully audited team-level continuity counts from the schema-1 file."""

    if path is None or not Path(path).exists():
        return ()
    payload = read_json(path)
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported team continuity file at {path}")
    raw_overrides = payload.get("overrides")
    if not isinstance(raw_overrides, Sequence) or isinstance(raw_overrides, (str, bytes)):
        raise ValueError("Team continuity overrides must be an array")

    overrides: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for index, raw in enumerate(raw_overrides):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Team continuity override {index} must be an object")
        missing_fields = _TEAM_CONTINUITY_REQUIRED_FIELDS - raw.keys()
        unknown_fields = raw.keys() - _TEAM_CONTINUITY_REQUIRED_FIELDS
        if missing_fields:
            fields = ", ".join(sorted(missing_fields))
            raise ValueError(f"Team continuity override {index} is missing: {fields}")
        if unknown_fields:
            fields = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Team continuity override {index} has unknown fields: {fields}")

        season = raw["season"]
        team = raw["team"]
        if type(season) is not int or season <= 0:
            raise ValueError(f"Team continuity override {index} has an invalid season")
        if not isinstance(team, str) or not team.strip():
            raise ValueError(f"Team continuity override {index} has an invalid team")

        clean = dict(raw)
        clean["team"] = " ".join(team.split())
        for _, _, retained_name, total_name in _TEAM_CONTINUITY_RATE_SPECS:
            retained = raw[retained_name]
            total = raw[total_name]
            if type(retained) is not int or type(total) is not int:
                raise ValueError(
                    f"Team continuity override {index} counts must be integers"
                )
            if total <= 0 or retained < 0 or retained > total:
                raise ValueError(
                    f"Team continuity override {index} has invalid "
                    f"{retained_name}/{total_name} counts"
                )

        if clean["offense_coaches_total"] > clean["on_field_coaches_total"] or clean[
            "offense_coaches_retained"
        ] > clean["on_field_coaches_retained"]:
            raise ValueError(
                f"Team continuity override {index} offense coaches must be a staff subset"
            )

        reason = raw["reason"]
        source_urls = raw["official_source_urls"]
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Team continuity override {index} requires a reason")
        if not isinstance(source_urls, Sequence) or isinstance(source_urls, (str, bytes)):
            raise ValueError(
                f"Team continuity override {index} official_source_urls must be an array"
            )
        if not source_urls:
            raise ValueError(
                f"Team continuity override {index} requires official source URLs"
            )
        clean_urls: list[str] = []
        for source_url in source_urls:
            if not isinstance(source_url, str):
                raise ValueError(
                    f"Team continuity override {index} has an invalid official source URL"
                )
            parsed = urlparse(source_url.strip())
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(
                    f"Team continuity override {index} has an invalid official source URL"
                )
            clean_urls.append(source_url.strip())
        clean["reason"] = reason.strip()
        clean["official_source_urls"] = tuple(clean_urls)

        target = (season, _normalized(clean["team"]))
        if target in seen:
            raise ValueError(
                f"Duplicate team continuity override for {clean['team']} in {season}"
            )
        seen.add(target)
        overrides.append(clean)
    return tuple(overrides)


def _team_continuity_features(
    overrides: Sequence[Mapping[str, Any]],
    *,
    season: int,
    identities: Mapping[int, TeamIdentity],
    aliases: Mapping[str, str],
) -> dict[str, dict[str, float]]:
    """Resolve current-season override targets and calculate auditable rates."""

    identities_by_name = {
        _normalized(identity.team): identity for identity in identities.values()
    }
    alias_targets = {
        _normalized(alias): identities_by_name[_normalized(canonical)].key
        for alias, canonical in aliases.items()
        if _normalized(canonical) in identities_by_name
    }
    alias_targets.update(
        {_normalized(identity.team): identity.key for identity in identities.values()}
    )

    by_key: dict[str, dict[str, float]] = {}
    for override in overrides:
        if override["season"] != season:
            continue
        team = str(override["team"])
        team_key = alias_targets.get(_normalized(team))
        if team_key is None:
            raise ValueError(
                f"Team continuity override target is not an FBS team in {season}: {team}"
            )
        if team_key in by_key:
            raise ValueError(
                f"Multiple team continuity override aliases target {team_key} in {season}"
            )
        feature_values: dict[str, float] = {}
        for rate_name, missing_name, retained_name, total_name in _TEAM_CONTINUITY_RATE_SPECS:
            feature_values[rate_name] = override[retained_name] / override[total_name]
            feature_values[missing_name] = 0.0
        by_key[team_key] = feature_values
    return by_key


@dataclass(frozen=True, slots=True)
class TeamIdentity:
    key: str
    team_id: int
    team: str
    conference: str | None
    classification: str


@dataclass(frozen=True, slots=True)
class TeamSeasonFeatures:
    season: int
    identity: TeamIdentity
    features: dict[str, float]

    def __post_init__(self) -> None:
        schema = tuple(self.features)
        supported = schema in {BASE_PRIOR_FEATURES, PRIOR_FEATURE_SCHEMA}
        extended_prior = (
            len(schema) > len(PRIOR_FEATURE_SCHEMA)
            and schema[: len(PRIOR_FEATURE_SCHEMA)] == PRIOR_FEATURE_SCHEMA
            and len(schema) == len(set(schema))
        )
        if not supported and not extended_prior:
            raise ValueError("Team-season features do not match a supported schema")
        if not all(math.isfinite(value) for value in self.features.values()):
            raise ValueError("Team-season features must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "identity": asdict(self.identity),
            "features": self.features,
        }


@dataclass(frozen=True, slots=True)
class SeasonFeatureTable:
    season: int
    rows: tuple[TeamSeasonFeatures, ...]
    feature_schema: tuple[str, ...]

    def __post_init__(self) -> None:
        keys = [row.identity.key for row in self.rows]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Season feature rows must have unique sorted team keys")
        if any(row.season != self.season for row in self.rows):
            raise ValueError("Season feature rows have inconsistent seasons")
        if any(tuple(row.features) != self.feature_schema for row in self.rows):
            raise ValueError("Season feature row schema is inconsistent")

    @property
    def by_key(self) -> dict[str, TeamSeasonFeatures]:
        return {row.identity.key: row for row in self.rows}

    @property
    def by_name(self) -> dict[str, TeamSeasonFeatures]:
        return {_normalized(row.identity.team): row for row in self.rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "feature_schema": list(self.feature_schema),
            "rows": [row.to_dict() for row in self.rows],
        }


def append_engineered_features(
    table: SeasonFeatureTable,
    feature_builder: Callable[[Mapping[str, float]], Mapping[str, float]],
) -> SeasonFeatureTable:
    """Append deterministic experiment features to an augmented preseason table.

    Production tables retain their fixed schema. This helper permits leakage-safe
    experiments to derive nonlinear terms exclusively from the same preseason inputs.
    """

    if table.feature_schema[: len(PRIOR_FEATURE_SCHEMA)] != PRIOR_FEATURE_SCHEMA:
        raise ValueError("Engineered features require an augmented preseason table")
    rows: list[TeamSeasonFeatures] = []
    added_schema: tuple[str, ...] | None = None
    for row in table.rows:
        additions = {
            str(name): _finite(value)
            for name, value in feature_builder(row.features).items()
        }
        if not additions:
            raise ValueError("Engineered feature builder returned no features")
        names = tuple(additions)
        if added_schema is None:
            added_schema = names
        elif names != added_schema:
            raise ValueError("Engineered feature schema must be identical for every team")
        overlap = set(row.features) & set(additions)
        if overlap:
            raise ValueError(f"Engineered features already exist: {sorted(overlap)}")
        rows.append(
            TeamSeasonFeatures(
                row.season,
                row.identity,
                {**row.features, **additions},
            )
        )
    if added_schema is None:
        raise ValueError("Cannot engineer features for an empty table")
    schema = (*table.feature_schema, *added_schema)
    return SeasonFeatureTable(table.season, tuple(rows), schema)


def _snapshot_or_none(root: str | Path, dataset: str, year: int) -> list[dict[str, Any]] | None:
    if not enrichment_path(root, dataset, year).exists():
        return None
    return load_enrichment_year(root, dataset, year)


def _target_identities(team_rows: Sequence[Mapping[str, Any]]) -> dict[int, TeamIdentity]:
    identities: dict[int, TeamIdentity] = {}
    for row in team_rows:
        try:
            team_id = int(row["id"])
            school = str(row["school"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Malformed CFBD team row: {row!r}") from exc
        if not school:
            raise ValueError(f"CFBD team {team_id} has an empty school name")
        classification = str(row.get("classification") or "fbs").casefold()
        if classification != "fbs":
            continue
        identity = TeamIdentity(
            key=f"id:{team_id}",
            team_id=team_id,
            team=school,
            conference=(str(row["conference"]) if row.get("conference") else None),
            classification="fbs",
        )
        existing = identities.get(team_id)
        if existing is not None and existing != identity:
            raise ValueError(f"Conflicting team rows for CFBD ID {team_id}")
        identities[team_id] = identity
    if not identities:
        raise ValueError("No FBS teams were found for the requested season")
    return identities


def _canonical_aliases(
    identities: Mapping[int, TeamIdentity],
    team_rows_by_year: Mapping[int, Sequence[Mapping[str, Any]]],
) -> dict[str, str]:
    candidates: dict[str, set[str]] = defaultdict(set)
    display: dict[tuple[str, str], str] = {}
    for rows in team_rows_by_year.values():
        for row in rows:
            try:
                team_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                continue
            identity = identities.get(team_id)
            if identity is None:
                continue
            raw_names = [row.get("school"), *(row.get("alternateNames") or [])]
            for raw in raw_names:
                if not isinstance(raw, str) or not raw.strip():
                    continue
                clean = " ".join(raw.split())
                normalized = _normalized(clean)
                candidates[normalized].add(identity.team)
                display[(normalized, identity.team)] = clean
    for identity in identities.values():
        normalized = _normalized(identity.team)
        candidates[normalized].add(identity.team)
        display[(normalized, identity.team)] = identity.team
    return {
        display[(normalized, next(iter(canonical)))]: next(iter(canonical))
        for normalized, canonical in candidates.items()
        if len(canonical) == 1
    }


def build_local_preseason_table(
    enrichment_root: str | Path,
    season: int,
    *,
    history_start: int | None = None,
    availability_path: str | Path | None = DEFAULT_PLAYER_AVAILABILITY_PATH,
    team_continuity_path: str | Path | None = DEFAULT_TEAM_CONTINUITY_PATH,
) -> SeasonFeatureTable:
    """Build one season without treating missing snapshot files as observed empty data."""

    target_team_rows = load_enrichment_year(enrichment_root, "teams", season)
    identities = _target_identities(target_team_rows)
    earliest = history_start if history_start is not None else max(1869, season - 12)
    team_rows_by_year = {
        year: rows
        for year in range(earliest, season + 1)
        if (rows := _snapshot_or_none(enrichment_root, "teams", year)) is not None
    }
    aliases = _canonical_aliases(identities, team_rows_by_year)
    continuity_by_key = _team_continuity_features(
        _load_team_continuity_overrides(team_continuity_path),
        season=season,
        identities=identities,
        aliases=aliases,
    )

    overrides: list[Mapping[str, Any]] = []
    if availability_path is not None and Path(availability_path).exists():
        payload = read_json(availability_path)
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise ValueError(f"Unsupported player availability file at {availability_path}")
        raw_overrides = payload.get("overrides")
        if not isinstance(raw_overrides, Sequence) or isinstance(
            raw_overrides, (str, bytes)
        ):
            raise ValueError("Player availability overrides must be an array")
        overrides = [row for row in raw_overrides if isinstance(row, Mapping)]

    def apply_availability(
        rows: list[dict[str, Any]] | None, *, year: int, dataset: str
    ) -> list[dict[str, Any]] | None:
        if rows is None:
            return None
        relevant = [
            row
            for row in overrides
            if int(row.get("season", 0)) == year and row.get("available") is False
        ]
        adjusted = [dict(row) for row in rows]
        for override in relevant:
            player = _normalized(str(override.get("player") or ""))
            team = _normalized(str(override.get("team") or ""))
            if not player or not team:
                raise ValueError("Unavailable-player overrides require player and team")
            for row in adjusted:
                row_player = _normalized(
                    str(
                        row.get("name")
                        or f"{row.get('firstName') or ''} {row.get('lastName') or ''}"
                    )
                )
                if row_player != player:
                    continue
                if dataset == "portal" and _normalized(
                    str(row.get("destination") or "")
                ) == team:
                    # Preserve the source team's departure while preventing the unavailable
                    # player from becoming a destination contribution or synthetic roster row.
                    row["destination"] = None
                elif dataset == "roster" and _normalized(
                    str(row.get("team") or "")
                ) == team:
                    row["team"] = None
        return adjusted

    sources: list[PreseasonSourceData] = []
    for year in range(earliest, season + 1):
        portal = _snapshot_or_none(enrichment_root, "portal", year)
        roster = _snapshot_or_none(enrichment_root, "roster", year)
        sources.append(
            PreseasonSourceData(
                season=year,
                talent=_snapshot_or_none(enrichment_root, "talent", year),
                team_recruiting=_snapshot_or_none(enrichment_root, "recruiting", year),
                returning_production=_snapshot_or_none(enrichment_root, "returning", year),
                portal=apply_availability(portal, year=year, dataset="portal"),
                draft_picks=_snapshot_or_none(enrichment_root, "draft", year),
                roster=apply_availability(roster, year=year, dataset="roster"),
                head_coaches=_snapshot_or_none(enrichment_root, "coaches", year),
                player_usage=_snapshot_or_none(enrichment_root, "usage", year),
                player_ppa=_snapshot_or_none(enrichment_root, "player_ppa", year),
            )
        )
    raw_table = build_preseason_features(
        season,
        sources,
        aliases,
        teams=[identity.team for identity in identities.values()],
    )
    identities_by_name = {_normalized(identity.team): identity for identity in identities.values()}
    rows: list[TeamSeasonFeatures] = []
    for raw_row in raw_table.rows:
        identity = identities_by_name.get(_normalized(raw_row.team))
        if identity is None:
            raise ValueError(f"Preseason feature team has no CFBD ID: {raw_row.team}")
        record = raw_row.to_record()
        for rate_name, missing_name, _, _ in _TEAM_CONTINUITY_RATE_SPECS:
            record[rate_name] = 0.5
            record[missing_name] = 1.0
        record.update(continuity_by_key.get(identity.key, {}))
        features = {name: _feature_value(record, name) for name in BASE_PRIOR_FEATURES}
        rows.append(TeamSeasonFeatures(season, identity, features))
    rows.sort(key=lambda row: row.identity.key)
    return SeasonFeatureTable(season, tuple(rows), BASE_PRIOR_FEATURES)


def augment_previous_efficiency(
    current: SeasonFeatureTable,
    previous_efficiency: Mapping[str, Mapping[str, float]],
    *,
    previous_features: SeasonFeatureTable | None = None,
) -> SeasonFeatureTable:
    """Add prior performance and explicit continuity interactions.

    Retention controls how much last year's performance carries forward. It does
    not add an unconditional reward: retaining a weak unit preserves a weak prior.
    """

    if current.feature_schema != BASE_PRIOR_FEATURES:
        raise ValueError("Current table must contain unaugmented base features")
    prior_feature_rows = previous_features.by_key if previous_features is not None else {}
    rows: list[TeamSeasonFeatures] = []
    for row in current.rows:
        base = dict(row.features)
        prior = previous_efficiency.get(row.identity.key)
        missing = prior is None
        offense = _finite(prior.get("offense_ppa") if prior else None)
        defense = _finite(prior.get("defense_ppa") if prior else None)
        offense_success = _finite(prior.get("offense_success") if prior else None)
        defense_success = _finite(prior.get("defense_success") if prior else None)

        returning_available = base["returning_missing"] < 0.5
        roster_available = base["roster_missing"] < 0.5
        raw_offense_continuity = (
            base["returning_percent_ppa"] if returning_available else None
        )
        raw_passing_continuity = (
            base["returning_percent_passing_ppa"] if returning_available else None
        )
        roster_offense_continuity = None
        if roster_available:
            roster_offense_continuity = (
                base["roster_skill_usage_retention_rate"]
                if base["roster_skill_usage_coverage"] > 0.0
                else base["roster_offense_draft_adjusted_retention_rate"]
            )
            if base["roster_ol_starter_retention_missing"] < 0.5:
                ol_depth_retention = min(
                    max(base["roster_ol_experience_retention_rate"], 0.0),
                    max(base["roster_ol_draft_adjusted_retention_rate"], 0.0),
                    1.0,
                )
                ol_starter_retention = min(
                    max(base["roster_ol_starter_retention_rate"], 0.0), 1.0
                )
                effective_ol = 0.5 * (ol_depth_retention + ol_starter_retention)
                roster_offense_continuity = min(
                    roster_offense_continuity, effective_ol
                )
            if (
                base["coach_change"] > 0.5
                and base["coach_offense_staff_retention_missing"] < 0.5
            ):
                offense_staff_retention = min(
                    max(base["coach_offense_staff_retention_rate"], 0.0), 1.0
                )
                roster_offense_continuity *= 0.70 + 0.30 * offense_staff_retention
        roster_passing_continuity = None
        if roster_available:
            if base["qb_pass_usage_missing"] < 0.5:
                roster_passing_continuity = base["qb_pass_usage_retention_rate"]
            elif base["qb_retention_missing"] < 0.5:
                roster_passing_continuity = base["qb_starter_returns"]
            else:
                roster_passing_continuity = base["qb_room_retention_rate"]

        offense_candidates = [
            value
            for value in (raw_offense_continuity, roster_offense_continuity)
            if value is not None
        ]
        passing_candidates = [
            value
            for value in (raw_passing_continuity, roster_passing_continuity)
            if value is not None
        ]
        offense_continuity = min(offense_candidates) if offense_candidates else 0.5
        passing_continuity = min(passing_candidates) if passing_candidates else 0.5
        reconciliation_factor = (
            min(max(offense_continuity / raw_offense_continuity, 0.0), 1.0)
            if raw_offense_continuity is not None and raw_offense_continuity > 0.0
            else 1.0
        )
        defense_continuity = (
            base["roster_defense_draft_adjusted_retention_rate"]
            if base["roster_missing"] < 0.5
            else 0.5
        )
        prior_features = prior_feature_rows.get(row.identity.key)
        talent_change = (
            base["talent_z"] - prior_features.features["talent_z"]
            if prior_features is not None
            else 0.0
        )
        added = {
            "previous_offense_ppa": offense,
            "previous_defense_ppa": defense,
            "previous_offense_success": offense_success,
            "previous_defense_success": defense_success,
            "previous_efficiency_missing": float(missing),
            "talent_z_change": talent_change,
            "reconciled_offense_continuity": offense_continuity,
            "reconciled_passing_continuity": passing_continuity,
            "returning_reconciliation_factor": reconciliation_factor,
            "reconciled_returning_total_ppa_z": (
                base["returning_total_ppa_z"] * reconciliation_factor
            ),
            "reconciled_returning_passing_ppa_z": (
                base["returning_total_passing_ppa_z"]
                * (
                    min(max(passing_continuity / raw_passing_continuity, 0.0), 1.0)
                    if raw_passing_continuity is not None
                    and raw_passing_continuity > 0.0
                    else 1.0
                )
            ),
            "previous_offense_x_continuity": offense * offense_continuity,
            "previous_defense_x_continuity": defense * defense_continuity,
            "previous_offense_x_passing_continuity": offense * passing_continuity,
        }
        features = {**base, **added}
        rows.append(TeamSeasonFeatures(current.season, row.identity, features))
    return SeasonFeatureTable(current.season, tuple(rows), PRIOR_FEATURE_SCHEMA)
