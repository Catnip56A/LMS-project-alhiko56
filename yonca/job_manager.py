"""
Background job system for long-running tasks like content translation
"""
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
import json
from yonca.models import db, BackgroundJob as BackgroundJobModel

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

class JobManager:
    """Manages background jobs using database persistence"""

    def __init__(self):
        self.worker_thread = None
        self.running = False

    def start_worker(self, app):
        """Start the background worker thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.app = app
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("Background job worker started")

    def stop_worker(self):
        """Stop the background worker"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def queue_job(self, job_type: str, job_data: Dict[str, Any]) -> str:
        """Queue a new job and return its ID"""
        import uuid
        job_id = str(uuid.uuid4())
        
        # Create job in database
        job_model = BackgroundJobModel(
            id=job_id,
            type=job_type,
            status=JobStatus.QUEUED,
            message='',
            error=''
        )
        db.session.add(job_model)
        db.session.commit()

        # Store function reference for when job is executed
        # Note: This won't persist across app restarts, but for now we'll handle this
        # by having the worker know which functions to call based on job type
        print(f"Queued job {job_id} of type {job_type}")
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

    def _worker_loop(self):
        """Main worker loop that processes queued jobs from database"""
        with self.app.app_context():
            while self.running:
                try:
                    # Get next queued job from database
                    job_model = BackgroundJobModel.query.filter_by(status=JobStatus.QUEUED).order_by(BackgroundJobModel.created_at).first()
                    
                    if job_model:
                        job = BackgroundJob(job_model)
                        self._execute_job(job)
                    else:
                        # No jobs, wait before checking again
                        time.sleep(1)
                except Exception as e:
                    print(f"Error in worker loop: {e}")
                    time.sleep(5)  # Wait longer on error

    def _execute_job(self, job: BackgroundJob):
        """Execute a single job"""
        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            job.save()
            print(f"Starting job {job.id}")

            # Execute the job function based on type
            if job.type == 'translate_content':
                result = self._execute_translate_content_job(job)
            else:
                raise ValueError(f"Unknown job type: {job.type}")

            job.status = JobStatus.COMPLETED
            job.result = result
            job.progress = 100
            job.message = "Job completed successfully"
            job.completed_at = datetime.now()
            job.save()

            print(f"Completed job {job.id}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Failed job {job.id}: {error_details}")
            
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now()
            job.save()

    def _execute_translate_content_job(self, job):
        """Execute the translate content job"""
        try:
            from yonca.content_translator import (
                auto_translate_course,
                auto_translate_resource,
                auto_translate_home_content
            )
            from yonca.models import Course, Resource, HomeContent

            # Get total counts for progress calculation
            total_courses = Course.query.count()
            total_resources = Resource.query.count()
            total_home_content = HomeContent.query.count()
            
            total_items = total_courses + total_resources + total_home_content
            processed_items = 0

            # Initialize stats
            stats = {
                'courses': 0,
                'resources': 0,
                'home_content': 0,
                'total_processed': 0
            }

            # Process all content types sequentially
            job.message = "Starting translation process..."

            # Process courses
            job.message = "Translating courses..."
            courses = Course.query.all()
            for i, course in enumerate(courses):
                try:
                    auto_translate_course(course)
                    stats['courses'] += 1
                    stats['total_processed'] += 1
                    processed_items += 1
                    job.progress = int((processed_items / total_items) * 100)
                    job.message = f"Translated {stats['courses']} courses..."
                    job.save()
                except Exception as e:
                    print(f"Failed to translate course {course.id}: {e}")
                    continue

            # Process resources
            job.message = "Translating resources..."
            resources = Resource.query.all()
            for i, resource in enumerate(resources):
                try:
                    auto_translate_resource(resource)
                    stats['resources'] += 1
                    stats['total_processed'] += 1
                    processed_items += 1
                    job.progress = int((processed_items / total_items) * 100)
                    job.message = f"Translated {stats['resources']} resources..."
                    job.save()
                except Exception as e:
                    print(f"Failed to translate resource {resource.id}: {e}")
                    continue

            # Process home content
            job.message = "Translating home content..."
            home_contents = HomeContent.query.all()
            for i, home_content in enumerate(home_contents):
                try:
                    auto_translate_home_content(home_content)
                    stats['home_content'] += 1
                    stats['total_processed'] += 1
                    processed_items += 1
                    job.progress = int((processed_items / total_items) * 100)
                    job.message = f"Translated {stats['home_content']} home content items..."
                    job.save()
                except Exception as e:
                    print(f"Failed to translate home content {home_content.id}: {e}")
                    continue

            # Commit all changes
            db.session.commit()

            job.progress = 100
            job.message = f"Translation completed! Processed {stats['total_processed']} total items."
            job.save()

            return stats

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Translation job error: {error_details}")
            raise

# Global job manager instance
job_manager = JobManager()