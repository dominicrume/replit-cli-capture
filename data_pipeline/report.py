"""Report: write a JSON run-summary after each pipeline execution."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def write_summary(
    output_dir: Path,
    run_id: str,
    start_time: datetime,
    end_time: datetime,
    ingested: int,
    valid: int,
    quarantined: int,
    loaded: int,
    files_read: list[str],
) -> Path:
    """Write a JSON run summary and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    duration_seconds = (end_time - start_time).total_seconds()

    summary = {
        "run_id": run_id,
        "started_at": start_time.isoformat(),
        "finished_at": end_time.isoformat(),
        "duration_seconds": round(duration_seconds, 3),
        "files_read": files_read,
        "rows": {
            "ingested": ingested,
            "valid": valid,
            "quarantined": quarantined,
            "loaded_to_sqlite": loaded,
        },
    }

    out_path = output_dir / f"summary_{run_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Run summary written to %s", out_path)
    return out_path
