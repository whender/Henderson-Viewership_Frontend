"""Normalized, local representations of official CFP committee polls."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cfbpredict.games import atomic_write_json, read_json

COMMITTEE_POLL_SCHEMA_VERSION = 1
_FIRST_CFP_SEASON = 2014
_MAX_SEASON = 2200
_MAX_WEEK = 25
_RELEASE_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_RECORD_PATTERN = re.compile(r"\d+-\d+\Z")
_EXPECTED_RANKS = frozenset(range(1, 26))


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalized_team(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Committee poll team must be a string")
    team = " ".join(value.split())
    if not team:
        raise ValueError("Committee poll team must not be empty")
    return team


def _normalized_record(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Committee poll record must be a string")
    record = value.strip()
    if _RECORD_PATTERN.fullmatch(record) is None:
        raise ValueError(f"Invalid committee poll record: {value!r}")
    return record


def _parse_release_date(value: object) -> date:
    if not isinstance(value, str) or _RELEASE_DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Invalid committee poll release date: {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid committee poll release date: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class CommitteePollEntry:
    """One team in an official top-25 committee poll."""

    rank: int
    team: str
    record: str

    def __post_init__(self) -> None:
        if not _is_integer(self.rank) or self.rank not in _EXPECTED_RANKS:
            raise ValueError("Committee poll rank must be an integer from 1 through 25")
        object.__setattr__(self, "team", _normalized_team(self.team))
        object.__setattr__(self, "record", _normalized_record(self.record))

    def to_dict(self) -> dict[str, object]:
        return {"rank": self.rank, "team": self.team, "record": self.record}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CommitteePollEntry:
        if not isinstance(payload, Mapping):
            raise ValueError("Committee poll entry must be an object")
        return cls(
            rank=payload.get("rank"),  # type: ignore[arg-type]
            team=payload.get("team"),  # type: ignore[arg-type]
            record=payload.get("record"),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class CommitteePoll:
    """One complete official CFP top-25 release."""

    season: int
    week: int
    release_date: date
    entries: tuple[CommitteePollEntry, ...]

    def __post_init__(self) -> None:
        if (
            not _is_integer(self.season)
            or self.season < _FIRST_CFP_SEASON
            or self.season > _MAX_SEASON
        ):
            raise ValueError(
                f"Committee poll season must be between {_FIRST_CFP_SEASON} and {_MAX_SEASON}"
            )
        if not _is_integer(self.week) or not 1 <= self.week <= _MAX_WEEK:
            raise ValueError(f"Committee poll week must be an integer from 1 through {_MAX_WEEK}")
        if not isinstance(self.release_date, date):
            raise ValueError("Committee poll release_date must be a date")
        if self.release_date.year != self.season:
            raise ValueError("Committee poll release date must fall in its season year")

        entries = tuple(self.entries)
        if not all(isinstance(entry, CommitteePollEntry) for entry in entries):
            raise ValueError("Committee poll entries must contain CommitteePollEntry values")
        ranks = [entry.rank for entry in entries]
        if len(entries) != 25 or frozenset(ranks) != _EXPECTED_RANKS:
            raise ValueError("Committee poll must contain each rank from 1 through 25 exactly once")
        normalized_teams = [entry.team.casefold() for entry in entries]
        if len(set(normalized_teams)) != len(normalized_teams):
            raise ValueError("Committee poll contains a duplicate team")
        object.__setattr__(self, "entries", tuple(sorted(entries, key=lambda entry: entry.rank)))

    def to_dict(self) -> dict[str, object]:
        return {
            "season": self.season,
            "week": self.week,
            "release_date": self.release_date.isoformat(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CommitteePoll:
        if not isinstance(payload, Mapping):
            raise ValueError("Committee poll must be an object")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
            raise ValueError("Committee poll entries must be an array")
        return cls(
            season=payload.get("season"),  # type: ignore[arg-type]
            week=payload.get("week"),  # type: ignore[arg-type]
            release_date=_parse_release_date(payload.get("release_date")),
            entries=tuple(CommitteePollEntry.from_dict(entry) for entry in raw_entries),
        )


def _normalized_polls(polls: Sequence[CommitteePoll]) -> tuple[CommitteePoll, ...]:
    if not all(isinstance(poll, CommitteePoll) for poll in polls):
        raise ValueError("Committee polls must contain CommitteePoll values")
    normalized = tuple(sorted(polls, key=lambda poll: (poll.release_date, poll.season, poll.week)))
    season_weeks = [(poll.season, poll.week) for poll in normalized]
    if len(set(season_weeks)) != len(season_weeks):
        raise ValueError("Committee poll data contains a duplicate season and week")
    release_dates = [poll.release_date for poll in normalized]
    if len(set(release_dates)) != len(release_dates):
        raise ValueError("Committee poll data contains a duplicate release date")
    return normalized


def parse_committee_rankings_payload(payload: object) -> tuple[CommitteePoll, ...]:
    """Parse the official CFP ``/services/rankings.ashx`` response."""

    if not isinstance(payload, Mapping):
        raise ValueError("Official committee rankings payload must be an object")
    raw_weeks = payload.get("weeks")
    if not isinstance(raw_weeks, Sequence) or isinstance(raw_weeks, (str, bytes)):
        raise ValueError("Official committee rankings payload must contain a weeks array")

    polls: list[CommitteePoll] = []
    for index, raw_poll in enumerate(raw_weeks):
        if not isinstance(raw_poll, Mapping):
            raise ValueError(f"Committee rankings week {index} must be an object")
        season = raw_poll.get("year")
        raw_week = raw_poll.get("week")
        if not _is_integer(season):
            raise ValueError(f"Committee rankings week {index} has an invalid year")
        if not isinstance(raw_week, str) or not raw_week.isascii() or not raw_week.isdigit():
            raise ValueError(f"Committee rankings week {index} has an invalid week")
        week = int(raw_week)
        raw_entries = raw_poll.get("rankings")
        if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
            raise ValueError(f"Committee rankings week {index} must contain a rankings array")
        polls.append(
            CommitteePoll(
                season=season,
                week=week,
                release_date=_parse_release_date(raw_poll.get("release_date")),
                entries=tuple(CommitteePollEntry.from_dict(entry) for entry in raw_entries),
            )
        )
    return _normalized_polls(polls)


def save_committee_polls(path: str | Path, polls: Sequence[CommitteePoll]) -> None:
    """Atomically save normalized committee polls to a versioned local artifact."""

    normalized = _normalized_polls(polls)
    atomic_write_json(
        path,
        {
            "schema_version": COMMITTEE_POLL_SCHEMA_VERSION,
            "polls": [poll.to_dict() for poll in normalized],
        },
    )


def load_committee_polls(path: str | Path) -> tuple[CommitteePoll, ...]:
    """Load a versioned local committee-poll artifact."""

    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a committee-poll object in {path}")
    if payload.get("schema_version") != COMMITTEE_POLL_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported committee-poll schema version in {path}: "
            f"{payload.get('schema_version')!r}"
        )
    raw_polls = payload.get("polls")
    if not isinstance(raw_polls, Sequence) or isinstance(raw_polls, (str, bytes)):
        raise ValueError(f"Expected a polls array in {path}")
    return _normalized_polls(tuple(CommitteePoll.from_dict(poll) for poll in raw_polls))
