"""Configuration loader for data_pipeline."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ColumnSchema:
    name: str
    type: Literal["string", "numeric"]
    nullable: bool = False
    primary_key: bool = False


@dataclass
class PipelineConfig:
    input_dir: Path
    quarantine_dir: Path
    output_dir: Path
    db_name: str
    table_name: str
    columns: list[ColumnSchema]
    cron_string: str = "0 2 * * *"

    @property
    def db_path(self) -> Path:
        return self.output_dir / self.db_name

    @property
    def primary_key_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.primary_key]


def load_config(path: str | Path = "config.yaml") -> PipelineConfig:
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    pipeline = raw.get("pipeline", {})
    columns = [
        ColumnSchema(
            name=col["name"],
            type=col["type"],
            nullable=col.get("nullable", False),
            primary_key=col.get("primary_key", False),
        )
        for col in raw.get("columns", [])
    ]

    return PipelineConfig(
        input_dir=Path(pipeline.get("input_dir", "input")),
        quarantine_dir=Path(pipeline.get("quarantine_dir", "quarantine")),
        output_dir=Path(pipeline.get("output_dir", "output")),
        db_name=pipeline.get("db_name", "pipeline.db"),
        table_name=pipeline.get("table_name", "records"),
        columns=columns,
        cron_string=pipeline.get("cron_string", "0 2 * * *"),
    )
