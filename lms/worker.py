"""
RQ worker entrypoint. Runs as its own process, separate from the Flask app
(see docker-compose.yml's worker-dev service / `just worker`).

Jobs need Flask app context (DB session, config, etc.), so this creates the app once and
pushes its context for the worker's whole lifetime, rather than per job.

Run directly: `python -m lms.worker`
"""
import logging
from rq import Worker
from lms.queue import get_redis_connection, QUEUE_NAME
from lms import create_app

logger = logging.getLogger(__name__)


def main():
    app = create_app()
    with app.app_context():
        from lms.job_manager import ensure_translation_sweep_scheduled
        ensure_translation_sweep_scheduled()

        logger.info("RQ worker starting, listening on queue '%s'", QUEUE_NAME)
        worker = Worker([QUEUE_NAME], connection=get_redis_connection())
        worker.work(with_scheduler=True)


if __name__ == '__main__':
    main()
