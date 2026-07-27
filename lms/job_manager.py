"""
Background job system for long-running tasks like content translation.

Jobs are enqueued onto Redis via RQ (see lms/queue.py) and picked up by a separate worker
process (lms/worker.py) — not a thread inside the Flask process. Job status/progress is
still tracked in the BackgroundJob DB table so the existing polling API (admin panel's
job-status endpoint) and BackgroundJob.to_dict() contract are unchanged.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from lms.models import db, BackgroundJob as BackgroundJobModel

logger = logging.getLogger(__name__)

# Recurring full-catalog translation sweep — the "interval" side of the translation
# trigger (see run_scheduled_translation_sweep / ensure_translation_sweep_scheduled below).
# The "threshold" side is per-course jobs queued right after a create/edit (admin/__init__.py).
TRANSLATION_SWEEP_JOB_ID = 'translation-sweep-recurring'
TRANSLATION_SWEEP_INTERVAL_HOURS = 24


class JobStatus:
    """Job status constants"""
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

class BackgroundJob:
    """Represents a background job"""

    def __init__(self, job_model):
        self.model = job_model

    @property
    def id(self):
        return self.model.id

    @property
    def type(self):
        return self.model.type

    @property
    def status(self):
        return self.model.status

    @status.setter
    def status(self, value):
        self.model.status = value

    @property
    def progress(self):
        return self.model.progress

    @progress.setter
    def progress(self, value):
        self.model.progress = value

    @property
    def message(self):
        return self.model.message

    @message.setter
    def message(self, value):
        self.model.message = value

    @property
    def data(self):
        return self.model.data

    @property
    def result(self):
        return self.model.result

    @result.setter
    def result(self, value):
        self.model.result = value

    @property
    def error(self):
        return self.model.error

    @error.setter
    def error(self, value):
        self.model.error = value

    @property
    def created_at(self):
        return self.model.created_at

    @property
    def started_at(self):
        return self.model.started_at

    @started_at.setter
    def started_at(self, value):
        self.model.started_at = value

    @property
    def completed_at(self):
        return self.model.completed_at

    @completed_at.setter
    def completed_at(self, value):
        self.model.completed_at = value

    def to_dict(self):
        """Convert job to dictionary for JSON serialization"""
        return self.model.to_dict()

    def save(self):
        """Save job to database"""
        db.session.add(self.model)
        db.session.commit()


def _execute_job(job: 'BackgroundJob'):
    """Run one job's handler, tracking status/progress on the DB row throughout."""
    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        job.save()
        logger.info(f"Starting job {job.id}")

        if job.type == 'translate_content':
            result = _execute_translate_content_job(job)
        elif job.type == 'translate_course':
            result = _execute_translate_course_job(job)
        else:
            raise ValueError(f"Unknown job type: {job.type}")

        job.status = JobStatus.COMPLETED
        job.result = result
        job.progress = 100
        job.message = "Job completed successfully"
        job.completed_at = datetime.now()
        job.save()

        logger.info(f"Completed job {job.id}")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Failed job {job.id}: {error_details}")

        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now()
        job.save()


def _execute_translate_content_job(job):
    """Execute the full-catalog translate content job (manual admin trigger or the
    recurring sweep — see run_scheduled_translation_sweep)."""
    try:
        from lms.content_translator import auto_translate_course, spot_check_translations
        from lms.models import Course

        # Get total counts for progress calculation
        total_items = Course.query.count()
        processed_items = 0

        # Initialize stats
        stats = {
            'courses': 0,
            'total_processed': 0
        }

        job.message = "Starting translation process..."
        logger.info("🔄 Translation job started")

        # Process courses
        job.message = "Translating courses..."
        courses = Course.query.all()
        for i, course in enumerate(courses):
            try:
                auto_translate_course(course)
                stats['courses'] += 1
                stats['total_processed'] += 1
                processed_items += 1
                job.progress = int((processed_items / total_items) * 100) if total_items else 100
                job.message = f"Translated {stats['courses']} courses..."
                job.save()
            except Exception as e:
                logger.error(f"Failed to translate course {course.id}: {e}")
                continue

        # Commit all changes
        db.session.commit()

        stats['spot_check'] = spot_check_translations()

        job.progress = 100
        job.message = f"Translation completed! Processed {stats['total_processed']} total items."
        job.save()

        return stats

    except Exception:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Translation job error: {error_details}")
        raise


def _execute_translate_course_job(job):
    """Execute a single-course translate job — the "threshold" trigger, queued right
    after a course is created/edited in the admin panel (admin/__init__.py) so new/changed
    content gets translated within seconds instead of waiting for the nightly sweep."""
    from lms.content_translator import auto_translate_course
    from lms.models import Course

    course_id = (job.data or {}).get('course_id')
    course = Course.query.get(course_id) if course_id else None
    if not course:
        raise ValueError(f"translate_course job {job.id}: course {course_id!r} not found")

    job.message = f"Translating course {course.title!r}..."
    job.save()

    auto_translate_course(course)
    db.session.commit()

    job.progress = 100
    job.message = f"Translated course {course.title!r}."
    job.save()

    return {'course_id': course.id}


def run_queued_job(job_id: str):
    """RQ entrypoint — runs in the worker process (lms/worker.py), which has already
    pushed a Flask app context for its whole lifetime, so this can use the DB directly."""
    job_model = BackgroundJobModel.query.get(job_id)
    if not job_model:
        logger.error(f"Job {job_id} not found in database")
        return
    _execute_job(BackgroundJob(job_model))


def run_scheduled_translation_sweep():
    """RQ scheduler entrypoint for the recurring full-catalog translation sweep (the
    "interval" trigger). Re-enqueues itself under the same job_id for the next interval
    when done, so once bootstrapped (see ensure_translation_sweep_scheduled) this repeats
    indefinitely using only the existing worker (with_scheduler=True) — no separate cron
    process or rq-scheduler dependency needed."""
    import uuid
    from lms.queue import job_queue

    job_id = str(uuid.uuid4())
    job_model = BackgroundJobModel(id=job_id, type='translate_content', status=JobStatus.QUEUED, message='', error='')
    db.session.add(job_model)
    db.session.commit()

    try:
        _execute_job(BackgroundJob(job_model))
    finally:
        job_queue.enqueue_in(
            timedelta(hours=TRANSLATION_SWEEP_INTERVAL_HOURS),
            run_scheduled_translation_sweep,
            job_id=TRANSLATION_SWEEP_JOB_ID,
        )
        logger.info(f"Rescheduled translation sweep for {TRANSLATION_SWEEP_INTERVAL_HOURS}h from now")


def ensure_translation_sweep_scheduled():
    """Bootstrap the recurring translation sweep. Idempotent and safe to call on every
    worker startup — no-ops if a sweep is already scheduled, so restarting the worker
    process (e.g. `just worker` during dev) doesn't spawn duplicate recurring chains."""
    from rq.registry import ScheduledJobRegistry
    from lms.queue import job_queue

    registry = ScheduledJobRegistry(queue=job_queue)
    if TRANSLATION_SWEEP_JOB_ID in registry.get_job_ids():
        logger.info("Translation sweep already scheduled, skipping bootstrap")
        return

    job_queue.enqueue_in(
        timedelta(minutes=1),
        run_scheduled_translation_sweep,
        job_id=TRANSLATION_SWEEP_JOB_ID,
    )
    logger.info(f"Bootstrapped recurring translation sweep (every {TRANSLATION_SWEEP_INTERVAL_HOURS}h)")


class JobManager:
    """Enqueues jobs onto Redis (RQ) and reads their status back from the DB."""

    def queue_job(self, job_type: str, job_data: Dict[str, Any]) -> str:
        """Queue a new job and return its ID"""
        import uuid
        from lms.queue import job_queue

        job_id = str(uuid.uuid4())

        # Create job in database
        job_model = BackgroundJobModel(
            id=job_id,
            type=job_type,
            status=JobStatus.QUEUED,
            message='',
            data=job_data or None,
            error=''
        )
        db.session.add(job_model)
        db.session.commit()

        job_queue.enqueue(run_queued_job, job_id)
        logger.info(f"Queued job {job_id} of type {job_type} onto Redis")
        return job_id

    def get_job(self, job_id: str) -> Optional[BackgroundJob]:
        """Get job by ID from database"""
        job_model = BackgroundJobModel.query.get(job_id)
        if job_model:
            return BackgroundJob(job_model)
        return None

    def get_all_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all jobs as dictionaries"""
        jobs = BackgroundJobModel.query.order_by(BackgroundJobModel.created_at.desc()).limit(50).all()
        return {job.id: BackgroundJob(job).to_dict() for job in jobs}


# Global job manager instance
job_manager = JobManager()
