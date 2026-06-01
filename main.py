"""CLI entrypoint for data_pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="data_pipeline — ETL pipeline with validation, transformation, and SQLite loading"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Execute the pipeline once immediately")
    sub.add_parser("schedule", help="Start the daily scheduler (blocking)")

    args = parser.parse_args()
    _configure_logging(args.log_level)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    if args.command == "run":
        from data_pipeline.config import load_config
        from data_pipeline.pipeline import run as run_pipeline

        config = load_config(config_path)
        summary = run_pipeline(config)
        print(json.dumps(summary, indent=2))

    elif args.command == "schedule":
        from data_pipeline.scheduler import start_scheduler

        start_scheduler(config_path)


if __name__ == "__main__":
    main()
