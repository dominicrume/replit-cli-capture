"""Transform: lowercase string columns, round numeric columns to 2dp."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from .config import ColumnSchema

logger = logging.getLogger(__name__)


def normalise_rows(
    rows: list[dict],
    columns: list[ColumnSchema],
) -> list[dict]:
    """Return a new list of rows with normalised values."""
    normalised: list[dict] = []
    for row in rows:
        new_row = dict(row)
        for col in columns:
            raw = row.get(col.name)
            if raw is None or str(raw).strip() == "":
                new_row[col.name] = None
                continue

            if col.type == "string":
                new_row[col.name] = str(raw).lower().strip()
            elif col.type == "numeric":
                try:
                    rounded = (
                        Decimal(str(raw))
                        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    )
                    new_row[col.name] = float(rounded)
                except Exception:
                    new_row[col.name] = raw
        normalised.append(new_row)

    logger.info("Normalised %d rows", len(normalised))
    return normalised
