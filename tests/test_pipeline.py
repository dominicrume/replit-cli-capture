"""Tests for each pipeline feature and governance rule."""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_pipeline.config import ColumnSchema, PipelineConfig
from data_pipeline.ingest import read_csv_files
from data_pipeline.load import load_rows
from data_pipeline.report import write_summary
from data_pipeline.transform import normalise_rows
from data_pipeline.validate import validate_rows, write_quarantine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COLUMNS = [
    ColumnSchema(name="id", type="string", nullable=False, primary_key=True),
    ColumnSchema(name="category", type="string", nullable=False),
    ColumnSchema(name="amount", type="numeric", nullable=False),
    ColumnSchema(name="notes", type="string", nullable=True),
]

SAMPLE_ROWS = [
    {"id": "A1", "category": "Books", "amount": "12.567", "notes": "Good"},
    {"id": "A2", "category": "Electronics", "amount": "199.999", "notes": ""},
]


# ---------------------------------------------------------------------------
# ingest.csv
# ---------------------------------------------------------------------------

class TestIngest:
    def test_reads_csv_from_directory(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("id,category,amount,notes\nR1,Toys,9.99,Fun\n")
        rows, files = read_csv_files(tmp_path)
        assert len(rows) == 1
        assert rows[0]["id"] == "R1"
        assert len(files) == 1

    def test_reads_multiple_csv_files(self, tmp_path):
        (tmp_path / "a.csv").write_text("id,val\n1,x\n")
        (tmp_path / "b.csv").write_text("id,val\n2,y\n")
        rows, files = read_csv_files(tmp_path)
        assert len(rows) == 2
        assert len(files) == 2

    def test_empty_directory_returns_empty(self, tmp_path):
        rows, files = read_csv_files(tmp_path)
        assert rows == []
        assert files == []

    def test_non_csv_files_ignored(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a csv")
        rows, _ = read_csv_files(tmp_path)
        assert rows == []


# ---------------------------------------------------------------------------
# validate.schema
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_rows_pass(self):
        result = validate_rows(SAMPLE_ROWS, COLUMNS)
        assert len(result.valid_rows) == 2
        assert result.quarantine_rows == []

    def test_missing_required_field_quarantined(self):
        bad = [{"id": "X1", "category": "", "amount": "5.0", "notes": ""}]
        result = validate_rows(bad, COLUMNS)
        assert len(result.quarantine_rows) == 1
        assert "category" in result.quarantine_reasons[0]

    def test_bad_numeric_quarantined(self):
        bad = [{"id": "X2", "category": "Tools", "amount": "abc", "notes": ""}]
        result = validate_rows(bad, COLUMNS)
        assert len(result.quarantine_rows) == 1
        assert "numeric" in result.quarantine_reasons[0]

    def test_nullable_field_allowed_empty(self):
        row = [{"id": "X3", "category": "Tools", "amount": "5.0", "notes": ""}]
        result = validate_rows(row, COLUMNS)
        assert len(result.valid_rows) == 1

    def test_quarantine_file_written(self, tmp_path):
        bad = [{"id": "", "category": "", "amount": "x", "notes": ""}]
        result = validate_rows(bad, COLUMNS)
        out = write_quarantine(result.quarantine_rows, result.quarantine_reasons, tmp_path, "run1")
        assert out is not None and out.exists()
        with out.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert "_quarantine_reason" in rows[0]

    def test_quarantine_file_not_written_when_empty(self, tmp_path):
        result = validate_rows(SAMPLE_ROWS, COLUMNS)
        out = write_quarantine(result.quarantine_rows, result.quarantine_reasons, tmp_path, "run2")
        assert out is None


# ---------------------------------------------------------------------------
# transform.normalise
# ---------------------------------------------------------------------------

class TestTransform:
    def test_string_columns_lowercased(self):
        rows = [{"id": "A1", "category": "BOOKS", "amount": "10.0", "notes": "Hello World"}]
        normalised = normalise_rows(rows, COLUMNS)
        assert normalised[0]["category"] == "books"
        assert normalised[0]["notes"] == "hello world"

    def test_numeric_rounded_to_2dp(self):
        rows = [{"id": "A1", "category": "x", "amount": "12.567", "notes": ""}]
        normalised = normalise_rows(rows, COLUMNS)
        assert normalised[0]["amount"] == 12.57

    def test_numeric_rounded_half_up(self):
        rows = [{"id": "A1", "category": "x", "amount": "2.555", "notes": ""}]
        normalised = normalise_rows(rows, COLUMNS)
        assert normalised[0]["amount"] == 2.56

    def test_nullable_empty_becomes_none(self):
        rows = [{"id": "A1", "category": "x", "amount": "5.0", "notes": ""}]
        normalised = normalise_rows(rows, COLUMNS)
        assert normalised[0]["notes"] is None

    def test_string_stripped(self):
        rows = [{"id": "  A1  ", "category": "  Books  ", "amount": "5.0", "notes": ""}]
        normalised = normalise_rows(rows, COLUMNS)
        assert normalised[0]["id"] == "a1"
        assert normalised[0]["category"] == "books"


# ---------------------------------------------------------------------------
# load.sqlite — including governance: idempotent_loads
# ---------------------------------------------------------------------------

class TestLoad:
    def _make_db(self, tmp_path):
        return tmp_path / "test.db"

    def test_rows_inserted(self, tmp_path):
        rows = [{"id": "A1", "category": "books", "amount": 12.5, "notes": None}]
        n = load_rows(rows, self._make_db(tmp_path), "records", COLUMNS, ["id"])
        assert n == 1

    def test_idempotent_no_duplicates_on_rerun(self, tmp_path):
        """Governance: re-running on same input must not duplicate rows."""
        rows = [{"id": "A1", "category": "books", "amount": 12.5, "notes": None}]
        db = self._make_db(tmp_path)
        load_rows(rows, db, "records", COLUMNS, ["id"])
        n2 = load_rows(rows, db, "records", COLUMNS, ["id"])
        assert n2 == 0
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        conn.close()
        assert count == 1

    def test_idempotent_hash_based_without_pk(self, tmp_path):
        """Idempotency via row hash when no primary key is declared."""
        rows = [{"id": "A1", "category": "books", "amount": 12.5, "notes": None}]
        db = self._make_db(tmp_path)
        cols_no_pk = [ColumnSchema(name=c.name, type=c.type, nullable=c.nullable, primary_key=False) for c in COLUMNS]
        load_rows(rows, db, "records", cols_no_pk, [])
        n2 = load_rows(rows, db, "records", cols_no_pk, [])
        assert n2 == 0

    def test_different_rows_all_inserted(self, tmp_path):
        rows = [
            {"id": "A1", "category": "books", "amount": 10.0, "notes": None},
            {"id": "A2", "category": "food", "amount": 5.0, "notes": None},
        ]
        db = self._make_db(tmp_path)
        n = load_rows(rows, db, "records", COLUMNS, ["id"])
        assert n == 2


# ---------------------------------------------------------------------------
# report.run_summary
# ---------------------------------------------------------------------------

class TestReport:
    def test_summary_json_written(self, tmp_path):
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
        out = write_summary(tmp_path, "run123", start, end, 10, 8, 2, 7, ["input/a.csv"])
        assert out.exists()
        with out.open() as f:
            data = json.load(f)
        assert data["run_id"] == "run123"
        assert data["duration_seconds"] == 5.0
        assert data["rows"]["ingested"] == 10
        assert data["rows"]["quarantined"] == 2
        assert data["rows"]["loaded_to_sqlite"] == 7
        assert "input/a.csv" in data["files_read"]

    def test_summary_filename_includes_run_id(self, tmp_path):
        start = end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = write_summary(tmp_path, "myrun", start, end, 0, 0, 0, 0, [])
        assert "myrun" in out.name


# ---------------------------------------------------------------------------
# Governance: no_external_calls_without_allowlist
# ---------------------------------------------------------------------------

class TestNoExternalCalls:
    """Verify no network-calling imports are present in the pipeline modules."""

    PIPELINE_MODULES = [
        "data_pipeline/ingest.py",
        "data_pipeline/validate.py",
        "data_pipeline/transform.py",
        "data_pipeline/load.py",
        "data_pipeline/report.py",
        "data_pipeline/pipeline.py",
        "data_pipeline/config.py",
    ]
    BANNED = ["requests", "httpx", "urllib.request", "aiohttp", "boto3", "urllib3"]

    def test_no_banned_network_imports(self):
        for mod_path in self.PIPELINE_MODULES:
            source = Path(mod_path).read_text()
            for lib in self.BANNED:
                assert lib not in source, (
                    f"Banned network import '{lib}' found in {mod_path}"
                )
