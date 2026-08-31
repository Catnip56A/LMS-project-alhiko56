#!/usr/bin/env python3
"""
One-time backfill: populate TranscriptSegment (subtitle data) for every video/audio
CourseContent that was transcribed before the subtitles feature existed.

Not needed for new uploads or any future reindex — embed_content_item now persists segments
as a side effect of transcription automatically. This is only for content that was already
embedded (embedded_at IS NOT NULL) before that hook existed, whose raw per-segment transcript
was discarded after being collapsed into 45s RAG chunks.

Real cost: every selected item is re-run through Whisper from scratch (local CPU, no API
cost) via the ordinary embed_content_item() pipeline — same as a manual reindex, and it also
refreshes the RAG embeddings and Stage-1 auto-detected moments as a side effect, not just
subtitles.

Usage:
  python scripts/migration/backfill_transcript_segments.py [--dry-run] [--limit N]
      [--course-id N] [--content-id N]

Via just (dev):
  just backfill-subtitles --dry-run
  just backfill-subtitles --limit 1
  just backfill-subtitles

Via Docker directly (e.g. production):
  docker compose -f <production compose file> run --rm app \
      python scripts/migration/backfill_transcript_segments.py [flags]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lms import create_app
from lms.models import CourseContent, TranscriptSegment
from lms.rag_service import embed_content_item


def _select_rows(args):
    # CourseContent.has_bytes is a Python-side property (checks r2_key/drive_file_id), not a
    # queryable column, so that part of the filter is applied in Python below rather than in SQL.
    query = (
        CourseContent.query
        .outerjoin(TranscriptSegment, TranscriptSegment.course_content_id == CourseContent.id)
        .filter(CourseContent.content_type == 'video', TranscriptSegment.id.is_(None))
        .distinct()
    )
    if args.course_id:
        query = query.filter(CourseContent.course_id == args.course_id)
    if args.content_id:
        query = query.filter(CourseContent.id == args.content_id)
    rows = [c for c in query.order_by(CourseContent.id).all() if c.has_bytes]
    if args.limit:
        rows = rows[:args.limit]
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--course-id', type=int, default=None)
    parser.add_argument('--content-id', type=int, default=None)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        rows = _select_rows(args)
        print(f'{len(rows)} row(s) missing subtitles.')
        if args.dry_run:
            for content in rows:
                print(f'  [dry-run] id={content.id} course_id={content.course_id} title={content.title!r}')
            return

        ok = failed = 0
        for content in rows:
            try:
                chunks = embed_content_item(content)
                segment_count = TranscriptSegment.query.filter_by(course_content_id=content.id).count()
                ok += 1
                print(f'  OK   id={content.id} ({content.title!r}) -> {chunks} RAG chunk(s), {segment_count} subtitle segment(s)')
            except Exception as e:
                failed += 1
                print(f'  FAIL id={content.id} ({content.title!r}): {e}')

        print(f'\nDone: {ok} processed, {failed} failed.')
        if failed:
            sys.exit(1)


if __name__ == '__main__':
    main()
