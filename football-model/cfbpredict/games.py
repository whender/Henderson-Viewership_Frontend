"""CFBD game normalization and local JSON storage."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class GameDataError(ValueError):
    """Raised when a CFBD game cannot be normalized."""


def _first(record: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return default


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        if not isinstance(value, str):
            raise GameDataError(f"Invalid game start date: {value!r}")
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise GameDataError(f"Invalid game start date: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_team_key(team_id: int | None, team_name: str) -> str:
    """Prefer stable CFBD IDs, with a normalized-name fallback for old records."""

    if team_id is not None:
        return f"id:{team_id}"
    normalized = " ".join(team_name.casefold().split())
    return f"name:{normalized}"


@dataclass(frozen=True, slots=True)
class Game:
    id: int
    season: int
    week: int
    season_type: str
    start_date: datetime
    completed: bool
    neutral_site: bool
    home_id: int | None
    home_team: str
    home_points: float | None
    home_classification: str | None
    away_id: int | None
    away_team: str
    away_points: float | None
    away_classification: str | None
    home_conference: str | None = None
    away_conference: str | None = None
    conference_game: bool | None = None
    notes: str | None = None
    playoff: Mapping[str, Any] | None = None

    @property
    def home_key(self) -> str:
        return canonical_team_key(self.home_id, self.home_team)

    @property
    def away_key(self) -> str:
        return canonical_team_key(self.away_id, self.away_team)

    @property
    def has_score(self) -> bool:
        return self.home_points is not None and self.away_points is not None

    @property
    def margin(self) -> float:
        if not self.has_score:
            raise GameDataError(f"Game {self.id} does not have a final score")
        return float(self.home_points) - float(self.away_points)

    @classmethod
    def from_cfbd(cls, record: Mapping[str, Any]) -> Game:
        try:
            game_id = int(record["id"])
            season = int(_first(record, "season", "year"))
            week = int(record["week"])
            start_value = _first(record, "startDate", "start_date")
            home_value = _first(record, "homeTeam", "home_team")
            away_value = _first(record, "awayTeam", "away_team")
            if start_value is None or home_value is None or away_value is None:
                raise KeyError("start date or team name")
            start_date = parse_datetime(start_value)
            home_team = str(home_value).strip()
            away_team = str(away_value).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise GameDataError(f"Malformed CFBD game record: {record!r}") from exc

        if not home_team or not away_team:
            raise GameDataError(f"Game {game_id} is missing a team name")

        def optional_int(value: Any, field: str) -> int | None:
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise GameDataError(f"Game {game_id} has invalid {field}: {value!r}") from exc

        def optional_float(value: Any, field: str) -> float | None:
            if value is None:
                return None
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                raise GameDataError(f"Game {game_id} has invalid {field}: {value!r}") from exc
            if not math.isfinite(parsed):
                raise GameDataError(f"Game {game_id} has non-finite {field}: {value!r}")
            return parsed

        conference_game_value = _first(record, "conferenceGame", "conference_game")
        playoff_value = _first(record, "playoff")
        if playoff_value is not None and not isinstance(playoff_value, Mapping):
            raise GameDataError(f"Game {game_id} has invalid playoff metadata")

        return cls(
            id=game_id,
            season=season,
            week=week,
            season_type=str(_first(record, "seasonType", "season_type", default="regular")),
            start_date=start_date,
            completed=bool(record.get("completed", False)),
            neutral_site=bool(_first(record, "neutralSite", "neutral_site", default=False)),
            home_id=optional_int(_first(record, "homeId", "home_id"), "homeId"),
            home_team=home_team,
            home_points=optional_float(_first(record, "homePoints", "home_points"), "homePoints"),
            home_classification=_first(record, "homeClassification", "home_classification"),
            away_id=optional_int(_first(record, "awayId", "away_id"), "awayId"),
            away_team=away_team,
            away_points=optional_float(_first(record, "awayPoints", "away_points"), "awayPoints"),
            away_classification=_first(record, "awayClassification", "away_classification"),
            home_conference=_first(record, "homeConference", "home_conference"),
            away_conference=_first(record, "awayConference", "away_conference"),
            conference_game=(
                None if conference_game_value is None else bool(conference_game_value)
            ),
            notes=_first(record, "notes"),
            playoff=None if playoff_value is None else dict(playoff_value),
        )


def normalize_games(records: Iterable[Mapping[str, Any]]) -> list[Game]:
    """Normalize and de-duplicate records, preferring the last copy of a game ID."""

    by_id: dict[int, Game] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise GameDataError(f"Expected a game object, received {type(record).__name__}")
        game = Game.from_cfbd(record)
        by_id[game.id] = game
    return sorted(by_id.values(), key=lambda game: (game.start_date, game.id))


def completed_games(
    games: Iterable[Game],
    *,
    as_of: datetime | None = None,
    result_buffer: timedelta = timedelta(0),
) -> list[Game]:
    if result_buffer < timedelta(0):
        raise ValueError("result_buffer must be non-negative")
    if as_of is None:
        cutoff = None
    elif as_of.tzinfo is None:
        cutoff = as_of.replace(tzinfo=UTC)
    else:
        cutoff = as_of.astimezone(UTC)
    return [
        game
        for game in games
        if game.completed
        and game.has_score
        and game.home_key != game.away_key
        and (cutoff is None or game.start_date + result_buffer < cutoff)
    ]


def read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise


def season_path(
    games_dir: str | Path,
    year: int,
    *,
    classification: str | None = None,
    season_type: str | None = None,
) -> Path:
    if classification is None and season_type is None:
        return Path(games_dir) / f"{year}.json"
    return Path(games_dir) / (f"{year}.{classification or 'all'}.{season_type or 'all'}.json")


def load_seasons(
    games_dir: str | Path,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[Game]:
    directory = Path(games_dir)
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise FileNotFoundError(
            f"No season files found in {directory}. Run `cfbpredict fetch` first."
        )

    records: list[Mapping[str, Any]] = []
    for path in paths:
        try:
            year = int(path.name.split(".", maxsplit=1)[0])
        except ValueError:
            continue
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        payload = read_json(path)
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise GameDataError(f"Expected an array of games in {path}")
        records.extend(payload)
    if not records:
        requested = f"{start_year or '*'}-{end_year or '*'}"
        raise FileNotFoundError(f"No locally cached games matched seasons {requested}")
    return normalize_games(records)
