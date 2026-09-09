"""Explainable resume construction and committee-style team ordering."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cfbpredict.games import atomic_write_json

COMMITTEE_MODEL_SCHEMA_VERSION = 1
COMMITTEE_FEATURE_SCHEMA = (
    "wins",
    "losses",
    "win_percentage",
    "record_strength",
    "schedule_strength",
    "average_opponent_quality",
    "strong_schedule_rate",
    "best_win_quality",
    "second_best_win_quality",
    "top_10_wins",
    "top_25_wins",
    "road_quality_wins",
    "bad_losses",
    "fcs_games",
    "conference_champion",
    "conference_runner_up",
    "power_rating",
    "undefeated",
    "one_loss",
)


def _finite(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


@dataclass(frozen=True, slots=True)
class ResumeTeam:
    """Current FBS identity needed by the committee layer."""

    key: str
    team: str
    conference: str | None


@dataclass(frozen=True, slots=True)
class ResumeGameResult:
    """One completed or simulated result used to construct team resumes."""

    game_id: int
    home_key: str
    away_key: str
    home_team: str
    away_team: str
    home_classification: str
    away_classification: str
    home_win: bool
    neutral_site: bool = False
    conference_game: bool = False
    championship_game: bool = False

    @property
    def winner_key(self) -> str:
        return self.home_key if self.home_win else self.away_key

    @property
    def loser_key(self) -> str:
        return self.away_key if self.home_win else self.home_key


@dataclass(frozen=True, slots=True)
class TeamResume:
    """Scenario-specific, margin-free summary of one team's season."""

    key: str
    team: str
    conference: str | None
    wins: int
    losses: int
    conference_wins: int
    conference_losses: int
    fbs_wins: int
    fbs_losses: int
    fcs_wins: int
    fcs_losses: int
    road_wins: int
    neutral_wins: int
    record_strength: float
    schedule_strength: float
    average_opponent_quality: float
    strong_schedule_rate: float
    best_win_quality: float
    second_best_win_quality: float
    top_10_wins: int
    top_25_wins: int
    road_quality_wins: float
    bad_losses: int
    fcs_games: int
    conference_champion: bool
    conference_runner_up: bool
    power_rating: float

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def win_percentage(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def feature_values(self) -> dict[str, float]:
        values = {
            "wins": float(self.wins),
            "losses": float(self.losses),
            "win_percentage": self.win_percentage,
            "record_strength": self.record_strength,
            "schedule_strength": self.schedule_strength,
            "average_opponent_quality": self.average_opponent_quality,
            "strong_schedule_rate": self.strong_schedule_rate,
            "best_win_quality": self.best_win_quality,
            "second_best_win_quality": self.second_best_win_quality,
            "top_10_wins": float(self.top_10_wins),
            "top_25_wins": float(self.top_25_wins),
            "road_quality_wins": self.road_quality_wins,
            "bad_losses": float(self.bad_losses),
            "fcs_games": float(self.fcs_games),
            "conference_champion": float(self.conference_champion),
            "conference_runner_up": float(self.conference_runner_up),
            "power_rating": self.power_rating,
            "undefeated": float(self.games > 0 and self.losses == 0),
            "one_loss": float(self.losses == 1),
        }
        if tuple(values) != COMMITTEE_FEATURE_SCHEMA:
            raise RuntimeError("Committee resume feature schema drifted")
        return values


def _classification(value: str) -> str:
    return value.strip().casefold()


def _opponent_side(result: ResumeGameResult, team_key: str) -> tuple[str, str, str, bool]:
    if result.home_key == team_key:
        return result.away_key, result.away_team, result.away_classification, result.home_win
    if result.away_key == team_key:
        return result.home_key, result.home_team, result.home_classification, not result.home_win
    raise ValueError(f"Team {team_key!r} did not participate in game {result.game_id}")


def build_team_resumes(
    teams: Mapping[str, ResumeTeam],
    results: Sequence[ResumeGameResult],
    power_ratings: Mapping[str, float],
    *,
    conference_champions: frozenset[str] = frozenset(),
    conference_runners_up: frozenset[str] = frozenset(),
) -> dict[str, TeamResume]:
    """Build opponent- and site-aware resumes from one coherent season outcome."""

    if not teams:
        raise ValueError("At least one FBS team is required to build resumes")
    if set(teams) != {team.key for team in teams.values()}:
        raise ValueError("Resume team outer keys must match their identities")
    if not set(teams).issubset(power_ratings):
        missing = sorted(set(teams) - set(power_ratings))
        raise ValueError(f"Missing power ratings for FBS teams: {', '.join(missing[:5])}")
    if not conference_champions.issubset(teams):
        raise ValueError("Conference champions must be current FBS teams")
    if not conference_runners_up.issubset(teams):
        raise ValueError("Conference runners-up must be current FBS teams")

    team_results: dict[str, list[ResumeGameResult]] = {key: [] for key in teams}
    seen_ids: set[int] = set()
    for result in results:
        if not isinstance(result, ResumeGameResult):
            raise ValueError("results must contain ResumeGameResult values")
        if result.game_id in seen_ids:
            raise ValueError(f"Duplicate resume game ID: {result.game_id}")
        seen_ids.add(result.game_id)
        if result.home_key in teams:
            team_results[result.home_key].append(result)
        if result.away_key in teams:
            team_results[result.away_key].append(result)

    records: dict[str, tuple[int, int]] = {}
    for key, rows in team_results.items():
        wins = sum(_opponent_side(result, key)[3] for result in rows)
        records[key] = (wins, len(rows) - wins)

    ordered_power = sorted(
        ((key, _finite(power_ratings[key], f"power_ratings[{key!r}]")) for key in teams),
        key=lambda item: (-item[1], teams[item[0]].team.casefold()),
    )
    power_rank = {key: rank for rank, (key, _) in enumerate(ordered_power, start=1)}
    fbs_values = np.asarray([value for _, value in ordered_power], dtype=np.float64)
    median_power = float(np.median(fbs_values))
    reference_power = float(fbs_values[min(24, len(fbs_values) - 1)])
    minimum_power = float(np.min(fbs_values))

    def opponent_power(opponent_key: str, classification: str) -> float:
        supplied = power_ratings.get(opponent_key)
        if supplied is not None:
            return _finite(supplied, f"power_ratings[{opponent_key!r}]")
        return minimum_power - (8.0 if _classification(classification) == "fcs" else 15.0)

    def opponent_win_percentage(
        opponent_key: str,
        opponent_won_game: bool,
    ) -> float:
        if opponent_key not in records:
            return 0.35
        wins, losses = records[opponent_key]
        adjusted_wins = wins - int(opponent_won_game)
        adjusted_losses = losses - int(not opponent_won_game)
        games = adjusted_wins + adjusted_losses
        return adjusted_wins / games if games else 0.5

    base_owp: dict[str, float] = {}
    for key, rows in team_results.items():
        values: list[float] = []
        for result in rows:
            opponent_key, _, _, won = _opponent_side(result, key)
            values.append(opponent_win_percentage(opponent_key, not won))
        base_owp[key] = sum(values) / len(values) if values else 0.0

    resumes: dict[str, TeamResume] = {}
    for key, identity in teams.items():
        rows = team_results[key]
        wins = 0
        conference_wins = 0
        conference_losses = 0
        fbs_wins = 0
        fbs_losses = 0
        fcs_wins = 0
        fcs_losses = 0
        road_wins = 0
        neutral_wins = 0
        record_strength = 0.0
        opponent_win_pcts: list[float] = []
        opponent_owps: list[float] = []
        opponent_qualities: list[float] = []
        win_qualities: list[float] = []
        top_10_wins = 0
        top_25_wins = 0
        road_quality_wins = 0.0
        bad_losses = 0
        fcs_games = 0

        for result in rows:
            opponent_key, _, classification, won = _opponent_side(result, key)
            opponent_is_fbs = _classification(classification) == "fbs"
            opponent_is_fcs = _classification(classification) == "fcs"
            site = (
                "neutral"
                if result.neutral_site
                else ("home" if result.home_key == key else "away")
            )
            wins += int(won)
            if result.conference_game:
                conference_wins += int(won)
                conference_losses += int(not won)
            if opponent_is_fbs:
                fbs_wins += int(won)
                fbs_losses += int(not won)
            elif opponent_is_fcs:
                fcs_games += 1
                fcs_wins += int(won)
                fcs_losses += int(not won)
            if won and site == "away":
                road_wins += 1
            if won and site == "neutral":
                neutral_wins += 1

            rating = opponent_power(opponent_key, classification)
            quality = _sigmoid((rating - median_power) / 7.0)
            opponent_qualities.append(quality)
            opponent_win_pcts.append(opponent_win_percentage(opponent_key, not won))
            opponent_owps.append(base_owp.get(opponent_key, 0.30))
            site_points = 2.0 if site == "home" else (-2.0 if site == "away" else 0.0)
            reference_win_probability = _sigmoid(
                (reference_power - rating + site_points) / 8.5
            )
            reference_win_probability = max(
                0.03, min(reference_win_probability, 0.97)
            )
            record_strength += (
                -math.log(reference_win_probability)
                if won
                else math.log(1.0 - reference_win_probability)
            )
            if won:
                win_qualities.append(quality)
                opponent_rank = power_rank.get(opponent_key)
                top_10_wins += int(opponent_rank is not None and opponent_rank <= 10)
                top_25_wins += int(opponent_rank is not None and opponent_rank <= 25)
                if site in {"away", "neutral"}:
                    road_quality_wins += quality
            else:
                opponent_rank = power_rank.get(opponent_key, len(teams) + 1)
                bad_losses += int(opponent_rank > 50 or not opponent_is_fbs)

        losses = len(rows) - wins
        opponent_win_pct = (
            sum(opponent_win_pcts) / len(opponent_win_pcts)
            if opponent_win_pcts
            else 0.0
        )
        opponents_opponent_win_pct = (
            sum(opponent_owps) / len(opponent_owps) if opponent_owps else 0.0
        )
        schedule_strength = (
            (2.0 * opponent_win_pct + opponents_opponent_win_pct) / 3.0
        )
        ordered_wins = sorted(win_qualities, reverse=True)
        resumes[key] = TeamResume(
            key=key,
            team=identity.team,
            conference=identity.conference,
            wins=wins,
            losses=losses,
            conference_wins=conference_wins,
            conference_losses=conference_losses,
            fbs_wins=fbs_wins,
            fbs_losses=fbs_losses,
            fcs_wins=fcs_wins,
            fcs_losses=fcs_losses,
            road_wins=road_wins,
            neutral_wins=neutral_wins,
            record_strength=record_strength,
            schedule_strength=schedule_strength,
            average_opponent_quality=(
                sum(opponent_qualities) / len(opponent_qualities)
                if opponent_qualities
                else 0.0
            ),
            strong_schedule_rate=(
                sum(value >= 0.70 for value in opponent_qualities)
                / len(opponent_qualities)
                if opponent_qualities
                else 0.0
            ),
            best_win_quality=ordered_wins[0] if ordered_wins else 0.0,
            second_best_win_quality=ordered_wins[1] if len(ordered_wins) > 1 else 0.0,
            top_10_wins=top_10_wins,
            top_25_wins=top_25_wins,
            road_quality_wins=road_quality_wins,
            bad_losses=bad_losses,
            fcs_games=fcs_games,
            conference_champion=key in conference_champions,
            conference_runner_up=key in conference_runners_up,
            power_rating=float(power_ratings[key]),
        )
    return resumes


@dataclass(frozen=True, slots=True)
class CommitteeRanking:
    """One team in committee-emulator order."""

    rank: int
    key: str
    team: str
    score: float
    base_score: float
    resume: TeamResume
    contributions: tuple[tuple[str, float], ...]


def head_to_head_value(
    first_key: str,
    second_key: str,
    results: Sequence[ResumeGameResult],
) -> float:
    """Return +1/-1 for the direct result from the first team's perspective."""

    values = []
    for result in results:
        if {result.home_key, result.away_key} != {first_key, second_key}:
            continue
        values.append(1.0 if result.winner_key == first_key else -1.0)
    if not values:
        return 0.0
    return max(-1.0, min(sum(values) / len(values), 1.0))


def common_opponent_value(
    first_key: str,
    second_key: str,
    results: Sequence[ResumeGameResult],
) -> float:
    """Compare win rates against opponents shared by two teams."""

    records: dict[str, dict[str, list[bool]]] = {
        first_key: defaultdict(list),
        second_key: defaultdict(list),
    }
    for result in results:
        for key in (first_key, second_key):
            if result.home_key == key:
                opponent = result.away_key
                won = result.home_win
            elif result.away_key == key:
                opponent = result.home_key
                won = not result.home_win
            else:
                continue
            if opponent not in {first_key, second_key}:
                records[key][opponent].append(won)
    common = set(records[first_key]) & set(records[second_key])
    if not common:
        return 0.0
    differences = []
    for opponent in common:
        first = records[first_key][opponent]
        second = records[second_key][opponent]
        differences.append(
            sum(first) / len(first) - sum(second) / len(second)
        )
    return sum(differences) / len(differences)


class CommitteeModel:
    """Pairwise committee emulator over scenario-specific resume features."""

    def __init__(
        self,
        *,
        feature_scales: Mapping[str, float],
        coefficients: Mapping[str, float],
        head_to_head_coefficient: float,
        common_opponent_coefficient: float,
        comparable_window: float,
        provenance: str,
        evaluation: Mapping[str, float] | None = None,
    ) -> None:
        if set(feature_scales) != set(COMMITTEE_FEATURE_SCHEMA):
            raise ValueError("Committee feature scales do not match the schema")
        if set(coefficients) != set(COMMITTEE_FEATURE_SCHEMA):
            raise ValueError("Committee coefficients do not match the schema")
        self.feature_scales = {
            name: _finite(feature_scales[name], f"feature_scales[{name!r}]")
            for name in COMMITTEE_FEATURE_SCHEMA
        }
        if any(value <= 0.0 for value in self.feature_scales.values()):
            raise ValueError("Committee feature scales must be positive")
        self.coefficients = {
            name: _finite(coefficients[name], f"coefficients[{name!r}]")
            for name in COMMITTEE_FEATURE_SCHEMA
        }
        self.head_to_head_coefficient = _finite(
            head_to_head_coefficient, "head_to_head_coefficient"
        )
        self.common_opponent_coefficient = _finite(
            common_opponent_coefficient, "common_opponent_coefficient"
        )
        self.comparable_window = _finite(comparable_window, "comparable_window")
        if self.comparable_window < 0.0:
            raise ValueError("comparable_window must be non-negative")
        if not isinstance(provenance, str) or not provenance.strip():
            raise ValueError("Committee model provenance must be a non-empty string")
        self.provenance = provenance.strip()
        self.evaluation = {
            str(name): _finite(value, f"evaluation[{name!r}]")
            for name, value in dict(evaluation or {}).items()
        }

    @classmethod
    def protocol_default(cls) -> CommitteeModel:
        """Return an interpretable prior before historical coefficient fitting."""

        scales = {
            "wins": 2.0,
            "losses": 1.0,
            "win_percentage": 0.10,
            "record_strength": 2.0,
            "schedule_strength": 0.08,
            "average_opponent_quality": 0.15,
            "strong_schedule_rate": 0.20,
            "best_win_quality": 0.20,
            "second_best_win_quality": 0.20,
            "top_10_wins": 1.0,
            "top_25_wins": 1.0,
            "road_quality_wins": 1.5,
            "bad_losses": 1.0,
            "fcs_games": 1.0,
            "conference_champion": 1.0,
            "conference_runner_up": 1.0,
            "power_rating": 8.0,
            "undefeated": 1.0,
            "one_loss": 1.0,
        }
        coefficients = {
            "wins": 0.40,
            "losses": -1.15,
            "win_percentage": 0.90,
            "record_strength": 1.20,
            "schedule_strength": 0.75,
            "average_opponent_quality": 0.50,
            "strong_schedule_rate": 0.35,
            "best_win_quality": 0.65,
            "second_best_win_quality": 0.35,
            "top_10_wins": 0.45,
            "top_25_wins": 0.25,
            "road_quality_wins": 0.20,
            "bad_losses": -0.90,
            "fcs_games": -0.10,
            "conference_champion": 0.55,
            "conference_runner_up": 0.10,
            "power_rating": 0.40,
            "undefeated": 0.85,
            "one_loss": 0.30,
        }
        return cls(
            feature_scales=scales,
            coefficients=coefficients,
            head_to_head_coefficient=0.85,
            common_opponent_coefficient=0.35,
            comparable_window=2.0,
            provenance=(
                "Official CFP protocol prior: record strength, schedule strength, "
                "head-to-head, common opponents, and championships"
            ),
        )

    def _base_score(self, resume: TeamResume) -> tuple[float, dict[str, float]]:
        values = resume.feature_values
        contributions = {
            name: self.coefficients[name] * values[name] / self.feature_scales[name]
            for name in COMMITTEE_FEATURE_SCHEMA
        }
        return sum(contributions.values()), contributions

    def rank(
        self,
        resumes: Mapping[str, TeamResume],
        results: Sequence[ResumeGameResult],
    ) -> list[CommitteeRanking]:
        """Rank every supplied team through pairwise committee-style comparisons."""

        if not resumes:
            raise ValueError("At least one resume is required")
        if set(resumes) != {resume.key for resume in resumes.values()}:
            raise ValueError("Resume outer keys must match resume identities")
        keys = sorted(resumes, key=lambda key: resumes[key].team.casefold())
        base: dict[str, float] = {}
        contributions: dict[str, dict[str, float]] = {}
        for key in keys:
            base[key], contributions[key] = self._base_score(resumes[key])

        direct_results: dict[tuple[str, str], list[float]] = defaultdict(list)
        opponent_results: dict[str, dict[str, list[bool]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for result in results:
            direct_results[(result.home_key, result.away_key)].append(
                1.0 if result.home_win else -1.0
            )
            direct_results[(result.away_key, result.home_key)].append(
                -1.0 if result.home_win else 1.0
            )
            opponent_results[result.home_key][result.away_key].append(result.home_win)
            opponent_results[result.away_key][result.home_key].append(not result.home_win)

        def direct_value(first: str, second: str) -> float:
            values = direct_results.get((first, second), ())
            if not values:
                return 0.0
            return max(-1.0, min(sum(values) / len(values), 1.0))

        def common_value(first: str, second: str) -> float:
            first_records = opponent_results.get(first, {})
            second_records = opponent_results.get(second, {})
            common = (set(first_records) & set(second_records)) - {first, second}
            if not common:
                return 0.0
            differences = []
            for opponent in common:
                first_values = first_records[opponent]
                second_values = second_records[opponent]
                differences.append(
                    sum(first_values) / len(first_values)
                    - sum(second_values) / len(second_values)
                )
            return sum(differences) / len(differences)

        pairwise = {key: 0.0 for key in keys}
        for index, first in enumerate(keys):
            for second in keys[index + 1 :]:
                logit = base[first] - base[second]
                if abs(logit) <= self.comparable_window:
                    logit += self.head_to_head_coefficient * direct_value(first, second)
                    logit += self.common_opponent_coefficient * common_value(first, second)
                probability = _sigmoid(logit)
                pairwise[first] += probability
                pairwise[second] += 1.0 - probability

        denominator = max(len(keys) - 1, 1)
        ordered = sorted(
            keys,
            key=lambda key: (
                -pairwise[key] / denominator,
                -base[key],
                resumes[key].team.casefold(),
            ),
        )
        rankings = []
        for rank, key in enumerate(ordered, start=1):
            ordered_contributions = tuple(
                sorted(
                    contributions[key].items(),
                    key=lambda item: (-abs(item[1]), item[0]),
                )
            )
            rankings.append(
                CommitteeRanking(
                    rank=rank,
                    key=key,
                    team=resumes[key].team,
                    score=100.0 * pairwise[key] / denominator if len(keys) > 1 else 100.0,
                    base_score=base[key],
                    resume=resumes[key],
                    contributions=ordered_contributions,
                )
            )
        return rankings

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMMITTEE_MODEL_SCHEMA_VERSION,
            "model_type": "pairwise_resume_committee_emulator",
            "feature_schema": list(COMMITTEE_FEATURE_SCHEMA),
            "feature_scales": self.feature_scales,
            "coefficients": self.coefficients,
            "head_to_head_coefficient": self.head_to_head_coefficient,
            "common_opponent_coefficient": self.common_opponent_coefficient,
            "comparable_window": self.comparable_window,
            "provenance": self.provenance,
            "evaluation": self.evaluation,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CommitteeModel:
        if payload.get("schema_version") != COMMITTEE_MODEL_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported committee model schema: {payload.get('schema_version')!r}"
            )
        if payload.get("model_type") != "pairwise_resume_committee_emulator":
            raise ValueError(f"Unsupported committee model type: {payload.get('model_type')!r}")
        if tuple(payload.get("feature_schema", ())) != COMMITTEE_FEATURE_SCHEMA:
            raise ValueError("Committee model feature schema does not match this version")
        return cls(
            feature_scales=dict(payload["feature_scales"]),
            coefficients=dict(payload["coefficients"]),
            head_to_head_coefficient=payload["head_to_head_coefficient"],
            common_opponent_coefficient=payload["common_opponent_coefficient"],
            comparable_window=payload["comparable_window"],
            provenance=payload["provenance"],
            evaluation=dict(payload.get("evaluation", {})),
        )

    def save(self, path: str | Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> CommitteeModel:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Expected a committee model object in {path}")
        return cls.from_dict(payload)


def resume_to_dict(resume: TeamResume) -> dict[str, Any]:
    """Return an audit-friendly JSON representation of a team resume."""

    payload = asdict(resume)
    payload["win_percentage"] = resume.win_percentage
    return payload
