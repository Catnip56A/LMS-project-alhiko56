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

# Recurring RAG-embedding sweep (Phase 6) — catches CourseContent items that were created
# through any of the app's many content-creation paths (uploads, Drive imports, picker
# import, etc.). Runs far more often than the translation sweep since new material should
# become askable quickly, but processes in small batches so one run can't monopolize the
# worker or blow through the Gemini free-tier rate limit.
#
# Two triggers, whichever comes first — the same "threshold + interval" split already used
# for the translation pipeline: the interval below is the ceiling on latency when nothing's
# happening; record_content_update() (called from every content-creation call site) is the
# "threshold" side, immediately jumping the recurring job's next run to now once
# CONTENT_UPDATE_TRIGGER_COUNT items have accumulated, instead of making a teacher wait out
# the full interval after a batch of uploads.
EMBEDDING_SWEEP_JOB_ID = 'embedding-sweep-recurring'
EMBEDDING_SWEEP_INTERVAL_MINUTES = 30
EMBEDDING_SWEEP_BATCH_SIZE = 20
CONTENT_UPDATE_TRIGGER_COUNT = 3
CONTENT_UPDATE_COUNTER_KEY = 'embedding_sweep_pending_update_count'

# Recurring purge of "Ask AI" conversations the user hasn't consented to keep (see
# rag_service.purge_stale_conversations) — daily is plenty since the retention window is 30
# days; nothing time-sensitive about exactly when within a day it runs.
CONVERSATION_PURGE_JOB_ID = 'conversation-purge-recurring'
CONVERSATION_PURGE_INTERVAL_HOURS = 24

# Recurring promotion of flagged video moments (Phase 6 addendum, video moment
# highlighting) — see moment_service.promote_pending_moments. Deliberately slower and
# smaller-batched than the embedding sweep: each promotion downloads a whole video to
# extract a frame and spends a Gemini vision call, and this shares the single worker with
# Whisper transcription (which can run 10+ minutes on one lecture).
MOMENT_PROMOTION_JOB_ID = 'moment-promotion-recurring'
MOMENT_PROMOTION_INTERVAL_MINUTES = 30
MOMENT_PROMOTION_BATCH_SIZE = 5


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
        elif job.type == 'embed_course_content':
            result = _execute_embed_course_content_job(job)
        elif job.type == 'embed_course':
            result = _execute_embed_course_job(job)
        elif job.type == 'promote_moments':
            result = _execute_promote_moments_job(job)
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


def _execute_embed_course_content_job(job):
    """Embed a single CourseContent item — used both by the manual per-item path and as the
    unit of work inside the recurring sweep below."""
    from lms.models import CourseContent
    from lms.rag_service import embed_content_item

    content_id = (job.data or {}).get('content_id')
    content = CourseContent.query.get(content_id) if content_id else None
    if not content:
        raise ValueError(f"embed_course_content job {job.id}: content {content_id!r} not found")

    job.message = f"Indexing {content.title!r}..."
    job.save()

    chunks = embed_content_item(content)

    job.progress = 100
    job.message = f"Indexed {content.title!r} ({chunks} chunk(s))."
    job.save()

    return {'content_id': content.id, 'chunks': chunks}


def _execute_embed_course_job(job):
    """Re-index every content item in one course — the manual "Reindex course" trigger."""
    from lms.models import Course
    from lms.rag_service import embed_content_item

    course_id = (job.data or {}).get('course_id')
    course = Course.query.get(course_id) if course_id else None
    if not course:
        raise ValueError(f"embed_course job {job.id}: course {course_id!r} not found")

    contents = course.contents.all()
    stats = {'items': 0, 'chunks': 0}

    for i, content in enumerate(contents):
        try:
            stats['chunks'] += embed_content_item(content)
            stats['items'] += 1
        except Exception as e:
            logger.error(f"Failed to embed content {content.id}: {e}")
            continue
        job.progress = int(((i + 1) / len(contents)) * 100) if contents else 100
        job.message = f"Indexed {stats['items']}/{len(contents)} items..."
        job.save()

    job.progress = 100
    job.message = f"Reindexed {course.title!r}: {stats['items']} item(s), {stats['chunks']} chunk(s)."
    job.save()

    return stats


def _execute_promote_moments_job(job):
    """Promote and caption this course's flagged video moments right now, instead of waiting
    up to MOMENT_PROMOTION_INTERVAL_MINUTES for the recurring sweep — the manual admin
    "Promote flagged moments" trigger next to "Reindex course content"."""
    from lms.models import Course
    from lms.moment_service import promote_pending_moments

    course_id = (job.data or {}).get('course_id')
    course = Course.query.get(course_id) if course_id else None
    if not course:
        raise ValueError(f"promote_moments job {job.id}: course {course_id!r} not found")

    stats = promote_pending_moments(limit=MOMENT_PROMOTION_BATCH_SIZE, course_id=course.id)
    job.message = (
        f"Promoted {stats['promoted']}, captioned {stats['captioned']}, "
        f"failed {stats['failed']} ({stats['vision_calls']} vision call(s))."
    )
    job.save()
    return stats


def record_content_update():
    """Call this right after a CourseContent row is created (upload, Picker import — not the
    one-off backfill script). This is the "threshold" trigger for the embedding sweep: once
    CONTENT_UPDATE_TRIGGER_COUNT items have accumulated since the last sweep run, immediately
    reschedule the recurring sweep's next run to now, rather than making new material wait
    out the full interval. Reset in run_scheduled_embedding_sweep, at the start of a run (not
    in `finally`) so updates landing while a sweep is in flight still count toward the next
    batch instead of being silently dropped.
    """
    from lms.models import AppSetting

    setting = AppSetting.query.filter_by(key=CONTENT_UPDATE_COUNTER_KEY).first()
    count = (int(setting.value) if setting else 0) + 1
    if setting:
        setting.value = str(count)
    else:
        db.session.add(AppSetting(key=CONTENT_UPDATE_COUNTER_KEY, value=str(count)))
    db.session.commit()

    if count >= CONTENT_UPDATE_TRIGGER_COUNT:
        from lms.queue import job_queue
        job_queue.enqueue_in(timedelta(seconds=0), run_scheduled_embedding_sweep, job_id=EMBEDDING_SWEEP_JOB_ID)
        logger.info(f"Embedding sweep triggered early: {count} content update(s) accumulated")


def run_scheduled_embedding_sweep():
    """RQ scheduler entrypoint for the recurring embedding sweep — the "interval" trigger; see
    the module-level comment above EMBEDDING_SWEEP_JOB_ID for the threshold-trigger half
    (record_content_update). Re-enqueues itself under the same job_id when done — the fixed
    job_id is also what lets record_content_update's early trigger simply reschedule this
    same chain to fire now, rather than spawning a parallel one."""
    import uuid
    from lms.models import AppSetting, CourseContent
    from lms.queue import job_queue
    from lms.rag_service import embed_content_item

    job_id = str(uuid.uuid4())
    job_model = BackgroundJobModel(id=job_id, type='embed_course', status=JobStatus.RUNNING, message='', error='')
    job_model.started_at = datetime.now()
    db.session.add(job_model)
    db.session.commit()
    job = BackgroundJob(job_model)

    counter = AppSetting.query.filter_by(key=CONTENT_UPDATE_COUNTER_KEY).first()
    if counter and counter.value != '0':
        counter.value = '0'
        db.session.commit()

    stats = {'items': 0, 'chunks': 0}
    try:
        pending = (
            CourseContent.query
            .filter(CourseContent.embedded_at.is_(None))
            .order_by(CourseContent.created_at)
            .limit(EMBEDDING_SWEEP_BATCH_SIZE)
            .all()
        )
        for content in pending:
            try:
                stats['chunks'] += embed_content_item(content)
                stats['items'] += 1
            except Exception as e:
                logger.error(f"Embedding sweep: failed to embed content {content.id}: {e}")
                continue

        job.status = JobStatus.COMPLETED
        job.result = stats
        job.progress = 100
        job.message = f"Sweep indexed {stats['items']} item(s), {stats['chunks']} chunk(s)."
        job.completed_at = datetime.now()
        job.save()
    except Exception as e:
        logger.error(f"Embedding sweep failed: {e}")
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now()
        job.save()
    finally:
        job_queue.enqueue_in(
            timedelta(minutes=EMBEDDING_SWEEP_INTERVAL_MINUTES),
            run_scheduled_embedding_sweep,
            job_id=EMBEDDING_SWEEP_JOB_ID,
        )


def ensure_embedding_sweep_scheduled():
    """Bootstrap the recurring embedding sweep. Idempotent — safe to call on every worker
    startup, same pattern as ensure_translation_sweep_scheduled."""
    from rq.registry import ScheduledJobRegistry
    from lms.queue import job_queue

    registry = ScheduledJobRegistry(queue=job_queue)
    if EMBEDDING_SWEEP_JOB_ID in registry.get_job_ids():
        logger.info("Embedding sweep already scheduled, skipping bootstrap")
        return

    job_queue.enqueue_in(
        timedelta(minutes=1),
        run_scheduled_embedding_sweep,
        job_id=EMBEDDING_SWEEP_JOB_ID,
    )
    logger.info(f"Bootstrapped recurring embedding sweep (every {EMBEDDING_SWEEP_INTERVAL_MINUTES}m)")


def run_scheduled_moment_promotion():
    """RQ scheduler entrypoint for the recurring video-moment promotion sweep — see
    moment_service.promote_pending_moments. Re-enqueues itself under the same job_id when
    done, same pattern as run_scheduled_embedding_sweep."""
    import uuid
    from lms.queue import job_queue
    from lms.moment_service import promote_pending_moments

    job_id = str(uuid.uuid4())
    job_model = BackgroundJobModel(id=job_id, type='promote_video_moments', status=JobStatus.RUNNING, message='', error='')
    job_model.started_at = datetime.now()
    db.session.add(job_model)
    db.session.commit()
    job = BackgroundJob(job_model)

    try:
        stats = promote_pending_moments(limit=MOMENT_PROMOTION_BATCH_SIZE)
        job.status = JobStatus.COMPLETED
        job.result = stats
        job.progress = 100
        job.message = (
            f"Promoted {stats['promoted']}, captioned {stats['captioned']}, "
            f"failed {stats['failed']} ({stats['vision_calls']} vision call(s), "
            f"{stats['videos_downloaded']} video(s) downloaded)."
        )
        job.completed_at = datetime.now()
        job.save()
    except Exception as e:
        logger.error(f"Moment promotion sweep failed: {e}")
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now()
        job.save()
    finally:
        job_queue.enqueue_in(
            timedelta(minutes=MOMENT_PROMOTION_INTERVAL_MINUTES),
            run_scheduled_moment_promotion,
            job_id=MOMENT_PROMOTION_JOB_ID,
        )


def ensure_moment_promotion_scheduled():
    """Bootstrap the recurring moment-promotion sweep. Idempotent — safe to call on every
    worker startup, same pattern as ensure_embedding_sweep_scheduled."""
    from rq.registry import ScheduledJobRegistry
    from lms.queue import job_queue

    registry = ScheduledJobRegistry(queue=job_queue)
    if MOMENT_PROMOTION_JOB_ID in registry.get_job_ids():
        logger.info("Moment promotion sweep already scheduled, skipping bootstrap")
        return

    job_queue.enqueue_in(
        timedelta(minutes=1),
        run_scheduled_moment_promotion,
        job_id=MOMENT_PROMOTION_JOB_ID,
    )
    logger.info(f"Bootstrapped recurring moment promotion sweep (every {MOMENT_PROMOTION_INTERVAL_MINUTES}m)")


def run_scheduled_conversation_purge():
    """RQ scheduler entrypoint for the recurring Ask-AI conversation purge — deletes
    conversations the user hasn't consented to keep once inactive for 30 days (see
    rag_service.purge_stale_conversations). Re-enqueues itself under the same job_id."""
    import uuid
    from lms.queue import job_queue
    from lms.rag_service import purge_stale_conversations

    job_id = str(uuid.uuid4())
    job_model = BackgroundJobModel(id=job_id, type='conversation_purge', status=JobStatus.RUNNING, message='', error='')
    job_model.started_at = datetime.now()
    db.session.add(job_model)
    db.session.commit()
    job = BackgroundJob(job_model)

    try:
        count = purge_stale_conversations()
        job.status = JobStatus.COMPLETED
        job.result = {'purged': count}
        job.progress = 100
        job.message = f"Purged {count} stale conversation(s)."
        job.completed_at = datetime.now()
        job.save()
    except Exception as e:
        logger.error(f"Conversation purge failed: {e}")
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.completed_at = datetime.now()
        job.save()
    finally:
        job_queue.enqueue_in(
            timedelta(hours=CONVERSATION_PURGE_INTERVAL_HOURS),
            run_scheduled_conversation_purge,
            job_id=CONVERSATION_PURGE_JOB_ID,
        )


def ensure_conversation_purge_scheduled():
    """Bootstrap the recurring conversation purge. Idempotent, same pattern as the other
    sweeps' bootstrap functions."""
    from rq.registry import ScheduledJobRegistry
    from lms.queue import job_queue

    registry = ScheduledJobRegistry(queue=job_queue)
    if CONVERSATION_PURGE_JOB_ID in registry.get_job_ids():
        logger.info("Conversation purge already scheduled, skipping bootstrap")
        return

    job_queue.enqueue_in(
        timedelta(minutes=1),
        run_scheduled_conversation_purge,
        job_id=CONVERSATION_PURGE_JOB_ID,
    )
    logger.info(f"Bootstrapped recurring conversation purge (every {CONVERSATION_PURGE_INTERVAL_HOURS}h)")


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
