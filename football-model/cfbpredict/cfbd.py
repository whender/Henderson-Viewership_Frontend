"""Small authenticated client for the official CollegeFootballData API."""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from cfbpredict.config import DEFAULT_BASE_URL
from cfbpredict.games import atomic_write_json, read_json


class CFBDConfigurationError(RuntimeError):
    """Raised when required CFBD configuration is missing."""


class CFBDAPIError(RuntimeError):
    """Raised for a non-retryable or exhausted CFBD API response."""


class CFBDClient:
    """HTTP client with Bearer authentication, retries, and a disk response cache."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: str | Path = "data/cache/cfbd",
        timeout: float = 30.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.max_retries = max_retries
        self.call_limit_remaining: int | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "cfbpredict/0.1",
            },
            transport=transport,
        )

    def __enter__(self) -> CFBDClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _require_key(self) -> None:
        if not self.api_key:
            raise CFBDConfigurationError(
                "CFBD_API_KEY is missing. Paste your key into .env, then retry."
            )

    def _cache_path(self, path: str, params: Mapping[str, Any]) -> Path:
        clean_path = path.strip("/").replace("/", "_") or "root"
        encoded = json.dumps(
            sorted((key, value) for key, value in params.items() if value is not None),
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(f"{path}?{encoded}".encode()).hexdigest()[:16]
        return self.cache_dir / f"{clean_path}-{digest}.json"

    def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        refresh: bool = False,
    ) -> Any:
        request_params = {key: value for key, value in (params or {}).items() if value is not None}
        cache_path = self._cache_path(path, request_params)
        if cache_path.exists() and not refresh:
            return read_json(cache_path)
        self._require_key()

        headers = {"Authorization": f"Bearer {self.api_key}"}
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(path, params=request_params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise CFBDAPIError(
                        f"CFBD request failed after {attempt + 1} attempts: {type(exc).__name__}"
                    ) from exc
                self._backoff(attempt, retry_after=None)
                continue

            if response.status_code < 400:
                remaining = response.headers.get("X-CallLimit-Remaining")
                if remaining is not None:
                    try:
                        self.call_limit_remaining = int(remaining)
                    except ValueError:
                        self.call_limit_remaining = None
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise CFBDAPIError("CFBD returned a non-JSON response") from exc
                atomic_write_json(cache_path, payload)
                return payload

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self.max_retries:
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            break

        assert response is not None
        if response.status_code in {401, 403}:
            detail = "Check that CFBD_API_KEY is valid and has access to this endpoint."
        elif response.status_code == 429:
            detail = "The CFBD rate limit was reached; try again after the reset window."
        else:
            detail = response.text.strip()[:300] or "No response body"
        raise CFBDAPIError(f"CFBD returned HTTP {response.status_code}. {detail}")

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                delay = max(0.0, min(float(retry_after), 30.0))
            except ValueError:
                delay = min(0.5 * (2**attempt), 10.0)
        else:
            delay = min(0.5 * (2**attempt) + random.uniform(0, 0.25), 10.0)
        time.sleep(delay)

    def get_games(
        self,
        year: int,
        *,
        classification: str | None = "fbs",
        season_type: str | None = "both",
        week: int | None = None,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        payload = self.get(
            "/games",
            params={
                "year": year,
                "classification": classification,
                "seasonType": season_type,
                "week": week,
            },
            refresh=refresh,
        )
        if not isinstance(payload, list):
            raise CFBDAPIError("CFBD /games returned an unexpected response shape")
        return payload

    def _get_list(
        self,
        path: str,
        *,
        params: Mapping[str, Any],
        refresh: bool,
    ) -> list[dict[str, Any]]:
        payload = self.get(path, params=params, refresh=refresh)
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise CFBDAPIError(f"CFBD {path} returned an unexpected response shape")
        return payload

    def get_advanced_game_stats(
        self,
        year: int,
        *,
        season_type: str = "both",
        exclude_garbage_time: bool = True,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return CFBD's team-game advanced offense and defense rows."""

        return self._get_list(
            "/stats/game/advanced",
            params={
                "year": year,
                "seasonType": season_type,
                "excludeGarbageTime": str(exclude_garbage_time).lower(),
            },
            refresh=refresh,
        )

    def get_fbs_teams(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/teams/fbs", params={"year": year}, refresh=refresh)

    def get_talent(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/talent", params={"year": year}, refresh=refresh)

    def get_team_recruiting(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/recruiting/teams", params={"year": year}, refresh=refresh)

    def get_returning_production(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/player/returning", params={"year": year}, refresh=refresh)

    def get_player_usage(
        self,
        year: int,
        *,
        position: str | None = None,
        exclude_garbage_time: bool = True,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        return self._get_list(
            "/player/usage",
            params={
                "year": year,
                "position": position,
                "excludeGarbageTime": str(exclude_garbage_time).lower(),
            },
            refresh=refresh,
        )

    def get_player_season_ppa(
        self,
        year: int,
        *,
        threshold: int = 0,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        return self._get_list(
            "/ppa/players/season",
            params={"year": year, "threshold": threshold},
            refresh=refresh,
        )

    def get_transfer_portal(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/player/portal", params={"year": year}, refresh=refresh)

    def get_draft_picks(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/draft/picks", params={"year": year}, refresh=refresh)

    def get_roster(
        self,
        year: int,
        *,
        classification: str = "fbs",
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        return self._get_list(
            "/roster",
            params={"year": year, "classification": classification},
            refresh=refresh,
        )

    def get_coaches(self, year: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return self._get_list("/coaches", params={"year": year}, refresh=refresh)
