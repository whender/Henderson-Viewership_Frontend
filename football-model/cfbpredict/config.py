"""Environment and path configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.collegefootballdata.com"
DEFAULT_PICKS_BASE_URL = "https://predictionsapi.collegefootballdata.com"
DEFAULT_GAMES_DIR = Path("data/raw/games")
DEFAULT_ENRICHMENT_DIR = Path("data/raw/enrichment")
DEFAULT_CACHE_DIR = Path("data/cache/cfbd")
DEFAULT_MODEL_PATH = Path("models/cfbpredict.json")
DEFAULT_V2_MODEL_PATH = Path("models/cfbpredict-v2.json")
DEFAULT_V2_CHALLENGER_PATH = Path("models/cfbpredict-v2-challenger.json")
DEFAULT_COMMITTEE_MODEL_PATH = Path("models/cfbpredict-committee.json")
DEFAULT_COMMITTEE_POLLS_PATH = Path("data/processed/cfp_committee_polls_2014_2025.json")
DEFAULT_V2_FEATURES_PATH = Path("data/processed/v2_historical_features_2016_2025.json")
DEFAULT_V2_FCS_FEATURES_PATH = Path(
    "data/processed/v2_fcs_historical_features_2016_2025.json"
)
DEFAULT_PLAYER_AVAILABILITY_PATH = Path("data/overrides/player_availability.json")
DEFAULT_TEAM_CONTINUITY_PATH = Path("data/overrides/team_continuity.json")


def load_environment(dotenv_path: str | Path | None = None) -> None:
    """Load local configuration without replacing explicitly exported variables."""

    path = Path(dotenv_path) if dotenv_path is not None else Path.cwd() / ".env"
    load_dotenv(dotenv_path=path, override=False)


def cfbd_api_key() -> str | None:
    value = os.getenv("CFBD_API_KEY", "").strip()
    return value or None


def cfbd_base_url() -> str:
    return os.getenv("CFBD_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")


def cfbd_picks_api_key() -> str | None:
    """Return the dedicated Model Pick'em credential, never the CFBD data key."""

    value = os.getenv("CFBD_PICKS_API_KEY", "").strip()
    return value or None


def cfbd_picks_base_url() -> str:
    return os.getenv("CFBD_PICKS_BASE_URL", DEFAULT_PICKS_BASE_URL).strip().rstrip("/")
