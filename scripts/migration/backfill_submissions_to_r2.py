#!/usr/bin/env python3
"""
One-time backfill: copy CourseAssignmentSubmission bytes from Google Drive into Cloudflare R2
— the same treatment scripts/migration/backfill_drive_to_r2.py already gave CourseContent (see
the "R2/Drive removal" addendum in Docs/rework docs/development_checklist.md).

Originally covered PDFDocument too, alongside CourseAssignmentSubmission — PDFDocument was
removed outright shortly after (it turned out to have zero reachable UI anywhere in the app;
see the checklist's "PDFDocument removal" entry), so this script is submission-only now.

Not an Alembic data migration, for the same reasons as backfill_drive_to_r2.py: bulk,
potentially-large network I/O that can't run as part of an automatic `flask db upgrade`.
Idempotent and resumable — each row commits individually, so a re-run's selection query
(drive_file_id set, r2_key not yet set) naturally skips whatever already succeeded. Never
clears drive_file_id, kept as provenance like every other R2-migrated row in this app.

Submissions are always public — submit_assignment always called set_file_permissions(...,
make_public=True) — so, like CourseContent, they download over the unauthenticated public link
(rag_service._download_public_drive_file), not an authenticated Drive session.

Usage:
  python scripts/migration/backfill_submissions_to_r2.py [--dry-run] [--limit N]
      [--skip-verify]

Via just (dev):
  just backfill-submissions --dry-run
  just backfill-submissions

Via Docker directly (e.g. production):
  docker compose -f <production compose file> run --rm app \
      python scripts/migration/backfill_submissions_to_r2.py [flags]
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import filetype

from lms import create_app, office_preview, r2_client
from lms.models import db, CourseAssignmentSubmission
from lms.rag_service import _download_public_drive_file


def _select_submissions(args):
    query = CourseAssignmentSubmission.query.filter(
        CourseAssignmentSubmission.drive_file_id.isnot(None),
        CourseAssignmentSubmission.r2_key.is_(None),
    ).order_by(CourseAssignmentSubmission.id)
    if args.limit:
        query = query.limit(args.limit)
    return query.all()


def _backfill_submission(submission, staging_dir, skip_verify) -> tuple[bool, str]:
    fd, tmp_path = tempfile.mkstemp(dir=staging_dir)
    os.close(fd)
    try:
        if not _download_public_drive_file(submission.drive_file_id, tmp_path):
            return False, 'download failed (submission not publicly accessible)'

        kind = filetype.guess(tmp_path)
        mime = kind.mime if kind else None
        name = f'submission-{submission.id}'
        course_id = submission.assignment.course_id if submission.assignment else 'submissions'
        key = r2_client.build_content_key(course_id, name, when=submission.submitted_at)

        if not r2_client.upload_file(tmp_path, key, content_type=mime, filename=name):
            return False, 'upload failed'
        if not skip_verify:
            remote_size = r2_client.get_object_size(key)
            local_size = os.path.getsize(tmp_path)
            if remote_size is None:
                return False, 'verify failed: object not found after upload'
            if remote_size != local_size:
                return False, f'verify failed: size mismatch (local={local_size}, remote={remote_size})'

        submission.r2_key = key
        submission.r2_preview_key = office_preview.generate_and_upload_preview(tmp_path, mime, key)
        submission.file_mime_type = mime
        db.session.commit()
        return True, key
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='List what would be migrated without doing it')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--skip-verify', action='store_true', help='Skip the post-upload object_exists check')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if not r2_client.is_configured():
            print('Error: R2 is not configured (R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME).')
            sys.exit(1)

        from lms.routes import UPLOAD_STAGING_DIR
        os.makedirs(UPLOAD_STAGING_DIR, exist_ok=True)

        submissions = _select_submissions(args)
        print(f'{len(submissions)} submission(s) to migrate.')
        if args.dry_run:
            for s in submissions:
                print(f'  [dry-run] submission id={s.id} assignment_id={s.assignment_id} user_id={s.user_id}')
            return

        ok = failed = 0
        for s in submissions:
            success, detail = _backfill_submission(s, UPLOAD_STAGING_DIR, args.skip_verify)
            if success:
                ok += 1
                print(f'  OK   submission id={s.id} -> {detail}')
            else:
                failed += 1
                print(f'  FAIL submission id={s.id}: {detail}')

        print(f'\nDone: {ok} migrated, {failed} failed.')
        if failed:
            sys.exit(1)


if __name__ == '__main__':
    main()
