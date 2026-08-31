#!/usr/bin/env python3
"""
One-time backfill: copy every CourseContent item's bytes from Google Drive into Cloudflare
R2, across all content types (not just video).

Not an Alembic data migration deliberately — `migrate-prod` runs `flask db upgrade`
automatically on every deploy, and this does bulk network I/O (potentially many GB) that
can't be resumed, rate-limited, or partially run the way a schema change can. See
Docs/rework docs/development_checklist.md's R2 migration notes for the full reasoning.

Idempotent and resumable by construction: each row is committed individually, so a
re-run's selection query (drive_file_id set, r2_key not yet set) naturally skips whatever
already succeeded. Never clears drive_file_id — see CourseContent.storage_backend's
docstring for why Drive provenance is kept even after a row is migrated.

Usage:
  python scripts/migration/backfill_drive_to_r2.py [--dry-run] [--limit N]
      [--course-id N] [--content-id N] [--skip-verify]

Via just (dev):
  just backfill-r2 --dry-run
  just backfill-r2 --limit 1
  just backfill-r2

Via Docker directly (e.g. production):
  docker compose -f <production compose file> run --rm app \
      python scripts/migration/backfill_drive_to_r2.py [flags]
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import filetype

from lms import create_app, office_preview, r2_client
from lms.models import db, CourseContent
from lms.rag_service import _download_public_drive_file


def _select_rows(args):
    query = CourseContent.query.filter(
        CourseContent.drive_file_id.isnot(None),
        CourseContent.r2_key.is_(None),
    ).order_by(CourseContent.id)
    if args.course_id:
        query = query.filter(CourseContent.course_id == args.course_id)
    if args.content_id:
        query = query.filter(CourseContent.id == args.content_id)
    if args.limit:
        query = query.limit(args.limit)
    return query.all()


def _backfill_one(content, staging_dir, skip_verify) -> tuple[bool, str]:
    fd, tmp_path = tempfile.mkstemp(dir=staging_dir)
    os.close(fd)
    try:
        if not _download_public_drive_file(content.drive_file_id, tmp_path):
            return False, 'download failed'

        kind = filetype.guess(tmp_path)
        mime = kind.mime if kind else None
        name = content.title or f'content-{content.id}'
        key = r2_client.build_content_key(content.course_id, name, when=content.created_at)

        if not r2_client.upload_file(tmp_path, key, content_type=mime, filename=name):
            return False, 'upload failed'

        if not skip_verify:
            remote_size = r2_client.get_object_size(key)
            local_size = os.path.getsize(tmp_path)
            if remote_size is None:
                return False, 'verify failed: object not found after upload'
            if remote_size != local_size:
                return False, f'verify failed: size mismatch (local={local_size}, remote={remote_size})'

        content.r2_key = key
        content.r2_preview_key = office_preview.generate_and_upload_preview(tmp_path, mime, key)
        content.file_mime_type = mime

        # Self-heal: a legacy row mis-typed as 'file' that actually sniffs as video/audio
        # never got transcribed — correct its type and let the sweep re-index it (mirrors
        # the same self-healing logic in rag_service._extract_drive_file_text).
        if content.content_type == 'file' and mime and (mime.startswith('video/') or mime.startswith('audio/')):
            content.content_type = 'video'
            content.embedded_at = None

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
    parser.add_argument('--course-id', type=int, default=None)
    parser.add_argument('--content-id', type=int, default=None)
    parser.add_argument('--skip-verify', action='store_true', help='Skip the post-upload object_exists check')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if not r2_client.is_configured():
            print('Error: R2 is not configured (R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME).')
            sys.exit(1)

        from lms.routes import UPLOAD_STAGING_DIR
        os.makedirs(UPLOAD_STAGING_DIR, exist_ok=True)

        rows = _select_rows(args)
        print(f'{len(rows)} row(s) to migrate.')
        if args.dry_run:
            for content in rows:
                print(f'  [dry-run] id={content.id} course_id={content.course_id} '
                      f'type={content.content_type} title={content.title!r}')
            return

        ok = failed = 0
        for content in rows:
            success, detail = _backfill_one(content, UPLOAD_STAGING_DIR, args.skip_verify)
            if success:
                ok += 1
                print(f'  OK   id={content.id} -> {detail}')
            else:
                failed += 1
                print(f'  FAIL id={content.id} ({content.title!r}): {detail}')

        print(f'\nDone: {ok} migrated, {failed} failed.')
        if failed:
            sys.exit(1)


if __name__ == '__main__':
    main()
