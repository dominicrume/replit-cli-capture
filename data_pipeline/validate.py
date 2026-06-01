"""Validate rows against the declared column schema; quarantine invalid rows."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import ColumnSchema

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid_rows: list[dict]
    quarantine_rows: list[dict]
    quarantine_reasons: list[str]


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def validate_rows(
    rows: list[dict],
    columns: list[ColumnSchema],
) -> ValidationResult:
    """Split *rows* into valid and quarantine lists based on *columns* schema."""
    declared_names = {c.name for c in columns}
    valid: list[dict] = []
    quarantine: list[dict] = []
    reasons: list[str] = []

    for row in rows:
        errors: list[str] = []

        missing_keys = declared_names - set(row.keys())
        if missing_keys:
            errors.append(f"Missing columns: {missing_keys}")

        for col in columns:
            raw = row.get(col.name, "")
            is_empty = raw is None or str(raw).strip() == ""

            if is_empty:
                if not col.nullable:
                    errors.append(f"Column '{col.name}' is required but empty")
                continue

            if col.type == "numeric" and not _is_numeric(raw):
                errors.append(
                    f"Column '{col.name}' expected numeric, got {raw!r}"
                )

        if errors:
            quarantine.append(row)
            reasons.append("; ".join(errors))
            logger.debug("Quarantined row %s — %s", row, errors)
        else:
            valid.append(row)

    return ValidationResult(
        valid_rows=valid,
        quarantine_rows=quarantine,
        quarantine_reasons=reasons,
    )


def write_quarantine(
    quarantine_rows: list[dict],
    quarantine_reasons: list[str],
    quarantine_dir: Path,
    run_id: str,
) -> Path | None:
    """Write quarantined rows to a CSV file; return the path or None if empty."""
    if not quarantine_rows:
        return None

    quarantine_dir.mkdir(parents=True, exist_ok=True)
    out_path = quarantine_dir / f"quarantine_{run_id}.csv"

    fieldnames = list(quarantine_rows[0].keys()) + ["_quarantine_reason"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row, reason in zip(quarantine_rows, quarantine_reasons):
            writer.writerow({**row, "_quarantine_reason": reason})

    logger.info(
        "Wrote %d quarantined rows to %s", len(quarantine_rows), out_path
    )
    return out_path
