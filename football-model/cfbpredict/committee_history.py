"""Assemble historical CFP polls into reproducible resume-training examples."""

from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cfbpredict.committee import (
    COMMITTEE_FEATURE_SCHEMA,
    CommitteeModel,
    ResumeGameResult,
    ResumeTeam,
    TeamResume,
    build_team_resumes,
    common_opponent_value,
    head_to_head_value,
)
from cfbpredict.committee_data import CommitteePoll
from cfbpredict.committee_training import CommitteeTrainingObservation
from cfbpredict.games import Game, completed_games
from cfbpredict.model import ModelConfig, PointRatingModel

_POLL_TEAM_ALIASES = {
    "appalachianstate": "appstate",
    "bayloruniversity": "baylor",
    "mississippi": "olemiss",
    "northwesternuniversity": "northwestern",
    "oklahomastateuniversity": "oklahomastate",
    "sanjosestateuniversity": "sanjosestate",
    "southerncalifornia": "usc",
}


def _team_token(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    token = "".join(
        character.casefold()
        for character in decomposed
        if not unicodedata.combining(character) and character.isalnum()
    )
    return _POLL_TEAM_ALIASES.get(token, token)


def _poll_cutoff(poll: CommitteePoll) -> datetime:
    return datetime.combine(poll.release_date, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)


def _is_fbs(value: str | None) -> bool:
    return value is not None and value.casefold() == "fbs"


def _is_fbs_championship(game: Game) -> bool:
    return bool(
        game.notes
        and "championship" in game.notes.casefold()
        and _is_fbs(game.home_classification)
        and _is_fbs(game.away_classification)
    )


@dataclass(frozen=True, slots=True)
class HistoricalCommitteeSnapshot:
    """One official poll aligned to every result and resume available that day."""

    poll: CommitteePoll
    resumes: Mapping[str, TeamResume]
    results: tuple[ResumeGameResult, ...]
    official_order: tuple[str, ...]


def build_resume_state(season_games, cutoff):
    """Build ranking inputs without receiving a target poll or its rankings."""
    season_games = list({game.id: game for game in season_games}.values())
    rating_config = ModelConfig(half_life_days=120.0, fbs_only=True, result_buffer_hours=4.0)
    rating_model = PointRatingModel(rating_config).fit(season_games, as_of=cutoff)
    usable = completed_games(
        season_games,
        as_of=cutoff,
        result_buffer=timedelta(hours=rating_config.result_buffer_hours),
    )

    latest_identity: dict[str, tuple[datetime, str, str | None]] = {}
    for game in usable:
        sides = (
            (
                game.home_key,
                game.home_team,
                game.home_classification,
                game.home_conference,
            ),
            (
                game.away_key,
                game.away_team,
                game.away_classification,
                game.away_conference,
            ),
        )
        for key, team, classification, conference in sides:
            if not _is_fbs(classification) or key not in rating_model.ratings:
                continue
            prior = latest_identity.get(key)
            if prior is None or game.start_date >= prior[0]:
                latest_identity[key] = (game.start_date, team, conference)
    teams = {
        key: ResumeTeam(key=key, team=value[1], conference=value[2])
        for key, value in latest_identity.items()
    }

    results = []
    champions: set[str] = set()
    runners_up: set[str] = set()
    for game in usable:
        if not game.has_score or game.margin == 0.0:
            continue
        if game.home_key not in teams and game.away_key not in teams:
            continue
        championship = _is_fbs_championship(game)
        result = ResumeGameResult(
            game_id=game.id,
            home_key=game.home_key,
            away_key=game.away_key,
            home_team=game.home_team,
            away_team=game.away_team,
            home_classification=game.home_classification or "other",
            away_classification=game.away_classification or "other",
            home_win=game.margin > 0.0,
            neutral_site=game.neutral_site,
            conference_game=bool(game.conference_game),
            championship_game=championship,
        )
        results.append(result)
        if championship:
            champions.add(result.winner_key)
            runners_up.add(result.loser_key)

    resumes = build_team_resumes(
        teams,
        results,
        rating_model.ratings,
        conference_champions=frozenset(champions & set(teams)),
        conference_runners_up=frozenset(runners_up & set(teams)),
    )
    return resumes, tuple(results)


def build_historical_committee_snapshots(
    polls: Sequence[CommitteePoll],
    games: Sequence[Game],
) -> tuple[HistoricalCommitteeSnapshot, ...]:
    """Reconstruct the information set behind each official weekly CFP poll."""

    if not polls:
        raise ValueError("At least one committee poll is required")
    if not games:
        raise ValueError("Historical games are required")
    games_by_season: dict[int, list[Game]] = defaultdict(list)
    for game in games:
        games_by_season[game.season].append(game)

    snapshots = []
    rating_config = ModelConfig(half_life_days=120.0, fbs_only=True, result_buffer_hours=4.0)
    for poll in sorted(polls, key=lambda row: row.release_date):
        season_games = games_by_season.get(poll.season, [])
        if not season_games:
            raise ValueError(f"No historical games are available for {poll.season}")
        cutoff = _poll_cutoff(poll)
        resumes, results = build_resume_state(season_games, cutoff)
        name_lookup: dict[str, str] = {}
        for key, resume in resumes.items():
            token = _team_token(resume.team)
            if token in name_lookup and name_lookup[token] != key:
                raise ValueError(
                    f"Historical team-name collision in {poll.season}: {resume.team}"
                )
            name_lookup[token] = key

        official_order = []
        for entry in poll.entries:
            key = name_lookup.get(_team_token(entry.team))
            if key is None:
                raise ValueError(
                    f"Cannot match official {poll.season} week {poll.week} team "
                    f"{entry.team!r} to the game data"
                )
            resume = resumes[key]
            reconstructed_record = f"{resume.wins}-{resume.losses}"
            if reconstructed_record != entry.record:
                raise ValueError(
                    f"Official record mismatch for {entry.team} in {poll.season} week "
                    f"{poll.week}: poll={entry.record}, games={reconstructed_record}"
                )
            official_order.append(key)
        snapshots.append(
            HistoricalCommitteeSnapshot(
                poll=poll,
                resumes=resumes,
                results=tuple(results),
                official_order=tuple(official_order),
            )
        )
    return tuple(snapshots)


def _feature_differences(first: TeamResume, second: TeamResume) -> dict[str, float]:
    first_values = first.feature_values
    second_values = second.feature_values
    return {
        name: first_values[name] - second_values[name]
        for name in COMMITTEE_FEATURE_SCHEMA
    }


def build_committee_training_observations(
    snapshots: Sequence[HistoricalCommitteeSnapshot],
    *,
    maximum_rank_gap: int = 8,
    hard_negative_count: int = 8,
    selection_day_weight: float = 2.0,
    season_half_life: float = 8.0,
) -> tuple[CommitteeTrainingObservation, ...]:
    """Create close-ranked and top-25-boundary comparisons from official polls."""

    if not snapshots:
        raise ValueError("At least one historical snapshot is required")
    if (
        not isinstance(maximum_rank_gap, int)
        or isinstance(maximum_rank_gap, bool)
        or maximum_rank_gap < 1
    ):
        raise ValueError("maximum_rank_gap must be a positive integer")
    if (
        not isinstance(hard_negative_count, int)
        or isinstance(hard_negative_count, bool)
        or hard_negative_count < 0
    ):
        raise ValueError("hard_negative_count must be a non-negative integer")
    if not math.isfinite(selection_day_weight) or selection_day_weight <= 0.0:
        raise ValueError("selection_day_weight must be finite and positive")
    if not math.isfinite(season_half_life) or season_half_life <= 0.0:
        raise ValueError("season_half_life must be finite and positive")

    latest_season = max(snapshot.poll.season for snapshot in snapshots)
    final_release = {
        season: max(
            snapshot.poll.release_date
            for snapshot in snapshots
            if snapshot.poll.season == season
        )
        for season in {snapshot.poll.season for snapshot in snapshots}
    }
    protocol_model = CommitteeModel.protocol_default()
    observations = []

    def add_pair(
        snapshot: HistoricalCommitteeSnapshot,
        higher_key: str,
        lower_key: str,
        weight: float,
    ) -> None:
        higher = snapshot.resumes[higher_key]
        lower = snapshot.resumes[lower_key]
        differences = _feature_differences(higher, lower)
        head_to_head = head_to_head_value(higher_key, lower_key, snapshot.results)
        common = common_opponent_value(higher_key, lower_key, snapshot.results)
        half_weight = 0.5 * weight
        observations.append(
            CommitteeTrainingObservation(
                season=snapshot.poll.season,
                feature_differences=differences,
                head_to_head_value=head_to_head,
                common_opponent_value=common,
                outcome=1.0,
                sample_weight=half_weight,
            )
        )
        observations.append(
            CommitteeTrainingObservation(
                season=snapshot.poll.season,
                feature_differences={name: -value for name, value in differences.items()},
                head_to_head_value=-head_to_head,
                common_opponent_value=-common,
                outcome=0.0,
                sample_weight=half_weight,
            )
        )

    for snapshot in snapshots:
        season_weight = 0.5 ** (
            (latest_season - snapshot.poll.season) / season_half_life
        )
        poll_weight = season_weight * (
            selection_day_weight
            if snapshot.poll.release_date == final_release[snapshot.poll.season]
            else 1.0
        )
        official = snapshot.official_order
        for first_index, higher_key in enumerate(official):
            stop = min(len(official), first_index + maximum_rank_gap + 1)
            for lower_index in range(first_index + 1, stop):
                rank_gap = lower_index - first_index
                add_pair(
                    snapshot,
                    higher_key,
                    official[lower_index],
                    poll_weight / math.sqrt(rank_gap),
                )

        if hard_negative_count:
            official_set = set(official)
            predicted = protocol_model.rank(snapshot.resumes, snapshot.results)
            hard_negatives = [
                row.key for row in predicted if row.key not in official_set
            ][:hard_negative_count]
            for higher_key in official[-min(6, len(official)) :]:
                for lower_key in hard_negatives:
                    add_pair(snapshot, higher_key, lower_key, 0.50 * poll_weight)
    return tuple(observations)


def evaluate_committee_model(
    model: CommitteeModel,
    snapshots: Sequence[HistoricalCommitteeSnapshot],
) -> dict[str, float]:
    """Measure full-ranking agreement against held-out official polls."""

    if not snapshots:
        raise ValueError("At least one evaluation snapshot is required")
    correct_pairs = 0
    total_pairs = 0
    absolute_rank_error = 0.0
    official_teams = 0
    top_25_overlap = 0
    top_12_overlap = 0
    selection_snapshots = 0
    selection_top_12_overlap = 0
    last_release = {
        season: max(
            snapshot.poll.release_date
            for snapshot in snapshots
            if snapshot.poll.season == season
        )
        for season in {snapshot.poll.season for snapshot in snapshots}
    }
    for snapshot in snapshots:
        predicted = model.rank(snapshot.resumes, snapshot.results)
        positions = {row.key: row.rank for row in predicted}
        predicted_top_25 = {row.key for row in predicted[:25]}
        official_top_25 = set(snapshot.official_order)
        top_25_overlap += len(predicted_top_25 & official_top_25)
        predicted_top_12 = {row.key for row in predicted[:12]}
        official_top_12 = set(snapshot.official_order[:12])
        overlap_12 = len(predicted_top_12 & official_top_12)
        top_12_overlap += overlap_12
        if snapshot.poll.release_date == last_release[snapshot.poll.season]:
            selection_snapshots += 1
            selection_top_12_overlap += overlap_12
        for official_rank, key in enumerate(snapshot.official_order, start=1):
            absolute_rank_error += abs(positions[key] - official_rank)
            official_teams += 1
        for first_index, higher_key in enumerate(snapshot.official_order):
            for lower_key in snapshot.official_order[first_index + 1 :]:
                correct_pairs += int(positions[higher_key] < positions[lower_key])
                total_pairs += 1
    return {
        "historical_poll_count": float(len(snapshots)),
        "historical_pairwise_accuracy": correct_pairs / total_pairs,
        "historical_mean_absolute_rank_error": absolute_rank_error / official_teams,
        "historical_top_25_recall": top_25_overlap / (25.0 * len(snapshots)),
        "historical_top_12_recall": top_12_overlap / (12.0 * len(snapshots)),
        "selection_day_top_12_recall": (
            selection_top_12_overlap / (12.0 * selection_snapshots)
        ),
    }
