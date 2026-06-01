"""Ingest: read CSV files from the configured input directory."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_csv_files(input_dir: Path) -> tuple[list[dict], list[Path]]:
    """Return all rows from every CSV in *input_dir* and the list of files read."""
    input_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(input_dir.glob("*.csv"))
    if not files:
        logger.info("No CSV files found in %s", input_dir)
        return [], []

    all_rows: list[dict] = []
    for csv_file in files:
        logger.info("Ingesting file: %s", csv_file.name)
        with csv_file.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        logger.info("  Read %d rows from %s", len(rows), csv_file.name)
        all_rows.extend(rows)

    return all_rows, files
