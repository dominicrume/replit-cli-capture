"""Core pipeline orchestration: ingest → validate → transform → load → report."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import PipelineConfig
from .ingest import read_csv_files
from .load import load_rows
from .report import write_summary
from .transform import normalise_rows
from .validate import validate_rows, write_quarantine

logger = logging.getLogger(__name__)


def run(config: PipelineConfig) -> dict:
    """Execute one full pipeline run. Returns the summary dict."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    start_time = datetime.now(timezone.utc)
    logger.info("=== Pipeline run started: %s ===", run_id)

    raw_rows, files_read = read_csv_files(config.input_dir)
    ingested = len(raw_rows)

    result = validate_rows(raw_rows, config.columns)
    write_quarantine(
        result.quarantine_rows,
        result.quarantine_reasons,
        config.quarantine_dir,
        run_id,
    )

    normalised = normalise_rows(result.valid_rows, config.columns)

    loaded = load_rows(
        normalised,
        config.db_path,
        config.table_name,
        config.columns,
        config.primary_key_columns,
    )

    end_time = datetime.now(timezone.utc)

    summary_path = write_summary(
        output_dir=config.output_dir,
        run_id=run_id,
        start_time=start_time,
        end_time=end_time,
        ingested=ingested,
        valid=len(result.valid_rows),
        quarantined=len(result.quarantine_rows),
        loaded=loaded,
        files_read=[str(f) for f in files_read],
    )

    logger.info(
        "=== Run %s complete — ingested=%d valid=%d quarantined=%d loaded=%d (%.3fs) ===",
        run_id,
        ingested,
        len(result.valid_rows),
        len(result.quarantine_rows),
        loaded,
        (end_time - start_time).total_seconds(),
    )

    with open(summary_path) as f:
        import json
        return json.load(f)
