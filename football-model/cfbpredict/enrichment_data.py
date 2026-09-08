"""Versioned local snapshots for CFBD model-enrichment endpoints."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cfbpredict.games import atomic_write_json, parse_datetime, read_json

ENRICHMENT_SCHEMA_VERSION = 1
ENRICHMENT_DATASETS = (
    "advanced",
    "teams",
    "talent",
    "recruiting",
    "returning",
    "usage",
    "player_ppa",
    "draft",
    "portal",
    "roster",
    "coaches",
)


def enrichment_path(root: str | Path, dataset: str, year: int) -> Path:
    if dataset not in ENRICHMENT_DATASETS:
        raise ValueError(f"Unknown enrichment dataset: {dataset}")
    if year < 1869 or year > 2200:
        raise ValueError("year must be between 1869 and 2200")
    return Path(root) / dataset / f"{year}.json"


def write_enrichment_snapshot(
    root: str | Path,
    *,
    dataset: str,
    year: int,
    endpoint: str,
    params: Mapping[str, Any],
    records: Iterable[Mapping[str, Any]],
    captured_at: datetime | None = None,
) -> Path:
    rows = [dict(row) for row in records]
    timestamp = captured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    payload = {
        "schema_version": ENRICHMENT_SCHEMA_VERSION,
        "dataset": dataset,
        "requested_year": year,
        "endpoint": endpoint,
        "params": dict(params),
        "captured_at": timestamp.astimezone(UTC).isoformat(),
        "records": rows,
    }
    destination = enrichment_path(root, dataset, year)
    atomic_write_json(destination, payload)
    return destination


def read_enrichment_snapshot(
    path: str | Path,
    *,
    expected_dataset: str | None = None,
    expected_year: int | None = None,
) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected an enrichment object in {path}")
    if payload.get("schema_version") != ENRICHMENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported enrichment schema version in {path}: {payload.get('schema_version')!r}"
        )
    dataset = payload.get("dataset")
    year = payload.get("requested_year")
    records = payload.get("records")
    if dataset not in ENRICHMENT_DATASETS:
        raise ValueError(f"Unknown enrichment dataset in {path}: {dataset!r}")
    if expected_dataset is not None and dataset != expected_dataset:
        raise ValueError(f"Expected {expected_dataset} data in {path}, found {dataset}")
    if not isinstance(year, int):
        raise ValueError(f"Invalid requested_year in {path}")
    if expected_year is not None and year != expected_year:
        raise ValueError(f"Expected year {expected_year} in {path}, found {year}")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError(f"Expected a records array in {path}")
    if not all(isinstance(row, Mapping) for row in records):
        raise ValueError(f"Expected record objects in {path}")
    parse_datetime(payload.get("captured_at"))
    return dict(payload)


def load_enrichment_year(
    root: str | Path, dataset: str, year: int, *, required: bool = True
) -> list[dict[str, Any]]:
    path = enrichment_path(root, dataset, year)
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"No local {dataset} snapshot for {year} at {path}. Run `cfbpredict enrich` first."
            )
        return []
    payload = read_enrichment_snapshot(path, expected_dataset=dataset, expected_year=year)
    return [dict(row) for row in payload["records"]]


def enrichment_inventory(root: str | Path) -> dict[str, list[int]]:
    inventory: dict[str, list[int]] = {}
    base = Path(root)
    for dataset in ENRICHMENT_DATASETS:
        years: list[int] = []
        for path in (base / dataset).glob("*.json"):
            try:
                years.append(int(path.stem))
            except ValueError:
                continue
        inventory[dataset] = sorted(set(years))
    return inventory
