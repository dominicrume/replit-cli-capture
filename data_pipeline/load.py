"""Load: write normalised rows into SQLite with idempotent inserts."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from .config import ColumnSchema

logger = logging.getLogger(__name__)

_ROW_HASH_COL = "_row_hash"


def _row_hash(row: dict) -> str:
    """Deterministic SHA-256 hash of a row's serialised content."""
    serialised = json.dumps(row, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()


def _col_sql_type(col_type: str) -> str:
    return "REAL" if col_type == "numeric" else "TEXT"


def _ensure_table(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[ColumnSchema],
    pk_columns: list[str],
) -> None:
    col_defs = [
        f'"{col.name}" {_col_sql_type(col.type)}'
        for col in columns
    ]
    col_defs.append(f'"{_ROW_HASH_COL}" TEXT NOT NULL')

    if pk_columns:
        pk_clause = ", ".join(f'"{c}"' for c in pk_columns)
        col_defs.append(f"PRIMARY KEY ({pk_clause})")
    else:
        col_defs.append(f'UNIQUE ("{_ROW_HASH_COL}")')

    ddl = (
        f'CREATE TABLE IF NOT EXISTS "{table_name}" '
        f"({', '.join(col_defs)})"
    )
    conn.execute(ddl)
    conn.commit()
    logger.debug("Ensured table '%s' exists", table_name)


def load_rows(
    rows: list[dict],
    db_path: Path,
    table_name: str,
    columns: list[ColumnSchema],
    pk_columns: list[str],
) -> int:
    """Insert *rows* into *table_name*; skip duplicates. Returns inserted count."""
    if not rows:
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))

    try:
        _ensure_table(conn, table_name, columns, pk_columns)

        col_names = [col.name for col in columns] + [_ROW_HASH_COL]
        placeholders = ", ".join("?" for _ in col_names)
        quoted_cols = ", ".join(f'"{c}"' for c in col_names)

        insert_sql = (
            f'INSERT OR IGNORE INTO "{table_name}" '
            f"({quoted_cols}) VALUES ({placeholders})"
        )

        inserted = 0
        for row in rows:
            h = _row_hash(row)
            values = [row.get(col.name) for col in columns] + [h]
            cursor = conn.execute(insert_sql, values)
            if cursor.rowcount:
                inserted += 1

        conn.commit()
        logger.info(
            "Loaded %d new rows into '%s' (skipped %d duplicates)",
            inserted,
            table_name,
            len(rows) - inserted,
        )
        return inserted
    finally:
        conn.close()
