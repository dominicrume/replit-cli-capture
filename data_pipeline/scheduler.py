"""Scheduler entrypoint: runs the pipeline once per day via APScheduler."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import load_config, PipelineConfig
from .pipeline import run as run_pipeline

logger = logging.getLogger(__name__)


def _make_job(config: PipelineConfig):
    def job():
        logger.info("Scheduled pipeline run triggered")
        try:
            run_pipeline(config)
        except Exception:
            logger.exception("Pipeline run failed")

    return job


def start_scheduler(config_path: str | Path = "config.yaml") -> None:
    """Start the blocking APScheduler using the cron_string from config."""
    config = load_config(config_path)
    scheduler = BlockingScheduler(timezone="UTC")

    trigger = CronTrigger.from_crontab(config.cron_string, timezone="UTC")
    scheduler.add_job(_make_job(config), trigger, id="daily_pipeline")

    logger.info(
        "Scheduler started — pipeline will run on cron '%s' (UTC)",
        config.cron_string,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler (signal %s)", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
