"""Outbox worker: delivers domain events (notifications today; workflows/webhooks later).

    python -m app.workers.outbox            # run forever
    python -m app.workers.outbox --once     # deliver what's pending and exit (cron / tests)

Run it alongside the API with EVENT_DISPATCH_MODE=worker. Several workers can run
at once; handlers are idempotent.
"""
import logging
import signal
import sys
import time

from app.core.logging import configure_logging
from app.events import dispatch_pending

logger = logging.getLogger("talentmatch.worker.outbox")

POLL_SECONDS = 2.0
_running = True


def _stop(*_):
    global _running
    _running = False


def main(once: bool = False) -> None:
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Outbox worker started")
    while _running:
        try:
            delivered = dispatch_pending(limit=200)
        except Exception:  # database blip: log and keep going
            logger.exception("Outbox dispatch failed")
            delivered = 0
        if once:
            break
        if delivered == 0:
            time.sleep(POLL_SECONDS)
    logger.info("Outbox worker stopped")


if __name__ == "__main__":
    main(once="--once" in sys.argv)
