"""
Video moment highlighting (Phase 6 addendum) — Flask/DB layer, the counterpart to
frame_extraction.py (no Flask/DB dependency there, mirroring the rag_service.py/
transcription.py split already used in this codebase).

Two signals feed a shared pipeline: an automatic keyword/regex pass over a video's
transcript (detect_auto_moments / record_auto_moments), and students clicking "flag this
moment" in the viewer (see routes/api.py's flag_video_moment). Both land as VideoMomentFlag
rows; candidate_buckets() computes which timestamp buckets have crossed their course's
adaptive weighting threshold; promote_pending_moments() is the recurring sweep (see
job_manager.run_scheduled_moment_promotion) that turns a promoted bucket into a captioned,
citable VideoMoment — which caption_chunks_for_content() re-embeds into ContentEmbedding on
every reindex, so answer_question() picks it up with no changes of its own.
"""
import logging
import math
import os
import re
import statistics
import tempfile
from datetime import datetime, timedelta

from lms.models import db, ContentEmbedding, CourseContent, Enrollment, VideoMoment, VideoMomentFlag

logger = logging.getLogger(__name__)

# ── Stage 1: automatic keyword/regex detection ──────────────────────────────────

MOMENT_TRIGGER_PHRASES_EN = [
    'as you can see', 'as you see', 'as shown', 'as depicted',
    'look at', 'take a look', 'if you look at', 'if we look at',
    'on the screen', 'on this slide', 'on the slide', 'on the board',
    'shown here', 'shown below', 'here we have', 'here you have',
    'this diagram', 'this graph', 'this chart', 'this figure', 'this table',
    'this slide', 'this image', 'this picture', 'this equation', 'this formula',
    'this example', 'this drawing', 'the diagram', 'the graph', 'the chart',
    'notice that', 'note here', 'pay attention to', 'right here', 'over here',
    'let me show you', 'i will show you', "i'll show you", 'watch this',
]
MOMENT_TRIGGER_PHRASES_RU = [
    'как вы видите', 'как видите', 'посмотрите', 'посмотрим',
    'на этом слайде', 'на слайде', 'на экране', 'на доске',
    'вот здесь', 'здесь вы видите', 'эта диаграмма', 'этот график',
    'эта схема', 'эта таблица', 'эта формула', 'обратите внимание',
    'как показано', 'покажу вам',
]
_ALL_TRIGGER_PHRASES = MOMENT_TRIGGER_PHRASES_EN + MOMENT_TRIGGER_PHRASES_RU
_TRIGGER_RE = re.compile(
    r'(?<!\w)(?:' + '|'.join(re.escape(p) for p in _ALL_TRIGGER_PHRASES) + r')(?!\w)',
    re.IGNORECASE,
)

MAX_AUTO_MOMENTS_PER_VIDEO = 40


def bucket_for(timestamp_seconds: float) -> int:
    from lms.rag_service import SEGMENT_CHUNK_WINDOW_SECONDS
    return int(timestamp_seconds // SEGMENT_CHUNK_WINDOW_SECONDS)


def detect_auto_moments(segments: list[dict]) -> list[dict]:
    """Pure function, no DB. Returns [{'timestamp_seconds', 'bucket_index'}, ...], at most
    one per bucket (earliest kept), ordered by time, capped at MAX_AUTO_MOMENTS_PER_VIDEO."""
    seen_buckets = set()
    out = []
    for seg in segments:
        start, end = seg.get('start'), seg.get('end')
        if start is None:
            continue
        # The Gemini-fallback shape (rag_service._transcribe_via_gemini) is one segment
        # spanning the whole file with start=end=0.0 — a placeholder, not a real timestamp.
        # Detecting a "moment" there would point every citation at the start of the video.
        if start == 0.0 and end == 0.0:
            continue
        text = ' '.join((seg.get('text') or '').split())
        if not text or not _TRIGGER_RE.search(text):
            continue
        bucket = bucket_for(start)
        if bucket in seen_buckets:
            continue
        seen_buckets.add(bucket)
        out.append({'timestamp_seconds': start, 'bucket_index': bucket})

    out.sort(key=lambda m: m['timestamp_seconds'])
    return out[:MAX_AUTO_MOMENTS_PER_VIDEO]


def record_auto_moments(content: CourseContent, segments: list[dict]) -> int:
    """Delete existing source='auto' flags for this content, re-insert from
    detect_auto_moments(). Does not commit — the caller's commit covers it (matches how
    embed_content_item already handles ContentEmbedding's delete-and-reinsert)."""
    VideoMomentFlag.query.filter_by(course_content_id=content.id, source='auto').delete()
    moments = detect_auto_moments(segments)
    for m in moments:
        db.session.add(VideoMomentFlag(
            course_content_id=content.id,
            timestamp_seconds=m['timestamp_seconds'],
            bucket_index=m['bucket_index'],
            source='auto',
            added_by=None,
        ))
    return len(moments)


# ── Weighting, bucketing, adaptive threshold ────────────────────────────────────

AUTO_MOMENT_BASE_WEIGHT = 1
MOMENT_THRESHOLD_FRACTION = 0.10
MOMENT_THRESHOLD_MIN = 2
MOMENT_THRESHOLD_MAX = 12
MOMENT_FLAG_LEAD_SECONDS = 3.0  # a student reacts *after* seeing something; back-date their click


def threshold_for_course(course) -> int:
    """Adaptive promotion threshold: roughly 10% of enrolled (non-teacher) students, floored
    so a tiny class isn't stuck at an unreachable bar, capped so a huge course doesn't need
    unreasonable consensus."""
    student_count = Enrollment.query.filter_by(course_id=course.id, is_teacher=False).count()
    return min(MOMENT_THRESHOLD_MAX, max(MOMENT_THRESHOLD_MIN, math.ceil(student_count * MOMENT_THRESHOLD_FRACTION)))


def candidate_buckets(course_id: int | None = None) -> list[dict]:
    """Live weight computation, across all courses by default or scoped to one (course_id) —
    the latter used by the manual per-course "Promote flagged moments" trigger. Returns
    groups that meet their course's adaptive threshold and aren't already claimed by an
    existing VideoMoment (any status), each as {'course_content_id', 'bucket_index', 'weight',
    'timestamp_seconds', 'has_auto'}.

    Computed live, not materialized: the sweep is the only consumer, and weight must be
    retroactively correct the instant a teacher blocks a student — a live query achieves that
    with zero backfill, which a cached counter could not.
    """
    from lms.rag_service import SEGMENT_CHUNK_WINDOW_SECONDS

    query = (
        db.session.query(VideoMomentFlag, CourseContent.course_id)
        .join(CourseContent, VideoMomentFlag.course_content_id == CourseContent.id)
        .filter(CourseContent.content_type == 'video', CourseContent.is_published.is_(True))
    )
    if course_id is not None:
        query = query.filter(CourseContent.course_id == course_id)
    flags = query.all()
    if not flags:
        return []

    blocked_pairs = {
        (e.user_id, e.course_id)
        for e in Enrollment.query.filter_by(moment_flags_blocked=True).all()
    }

    already_claimed = {
        (vm.course_content_id, vm.bucket_index)
        for vm in VideoMoment.query.all()
    }

    # Group raw flags by (course_content_id, bucket_index), excluding blocked students' flags.
    groups = {}
    course_by_content = {}
    for flag, course_id in flags:
        course_by_content[flag.course_content_id] = course_id
        if flag.source == 'student' and (flag.added_by, course_id) in blocked_pairs:
            continue
        key = (flag.course_content_id, flag.bucket_index)
        g = groups.setdefault(key, {'student_ids': set(), 'has_auto': False, 'timestamps': [], 'student_timestamps': []})
        g['timestamps'].append(flag.timestamp_seconds)
        if flag.source == 'auto':
            g['has_auto'] = True
        else:
            g['student_ids'].add(flag.added_by)
            g['student_timestamps'].append(flag.timestamp_seconds)

    # Adjacent-bucket merge: two flags on either side of a 45s boundary should count as one
    # moment. Merge bucket n into n+1 when n's latest timestamp is within one window of n+1's
    # earliest — union student ids (a student flagging both sides counts once).
    by_content = {}
    for (content_id, bucket), g in groups.items():
        by_content.setdefault(content_id, {})[bucket] = g

    merged = {}  # (content_id, representative_bucket) -> {'buckets': set, 'student_ids', 'has_auto', 'timestamps'}
    for content_id, buckets in by_content.items():
        for bucket in sorted(buckets):
            g = buckets[bucket]
            prev_key = next((k for k in merged if k[0] == content_id and bucket - 1 in merged[k]['buckets']), None)
            if prev_key is not None:
                prev = merged[prev_key]
                if max(prev['timestamps']) >= min(g['timestamps']) - SEGMENT_CHUNK_WINDOW_SECONDS:
                    prev['buckets'].add(bucket)
                    prev['student_ids'] |= g['student_ids']
                    prev['has_auto'] = prev['has_auto'] or g['has_auto']
                    prev['timestamps'].extend(g['timestamps'])
                    prev['student_timestamps'].extend(g['student_timestamps'])
                    continue
            merged[(content_id, bucket)] = {
                'buckets': {bucket}, 'student_ids': set(g['student_ids']),
                'has_auto': g['has_auto'], 'timestamps': list(g['timestamps']),
                'student_timestamps': list(g['student_timestamps']),
            }

    threshold_cache = {}
    out = []
    for (content_id, rep_bucket), g in merged.items():
        if any((content_id, b) in already_claimed for b in g['buckets']):
            continue
        weight = len(g['student_ids']) + (AUTO_MOMENT_BASE_WEIGHT if g['has_auto'] else 0)
        course_id = course_by_content[content_id]
        if course_id not in threshold_cache:
            course = CourseContent.query.get(content_id).course
            threshold_cache[course_id] = threshold_for_course(course)
        if weight < threshold_cache[course_id]:
            continue

        if g['student_timestamps']:
            rep_timestamp = max(0.0, statistics.median(g['student_timestamps']) - MOMENT_FLAG_LEAD_SECONDS)
        else:
            rep_timestamp = min(g['timestamps'])  # auto-only group: use the trigger's own timestamp, unchanged

        out.append({
            'course_content_id': content_id,
            'bucket_index': rep_bucket,
            'weight': weight,
            'timestamp_seconds': rep_timestamp,
            'has_auto': g['has_auto'],
        })

    out.sort(key=lambda c: (-c['weight'], c['course_content_id'], c['bucket_index']))
    return out


# ── Frame extraction / captioning orchestration ─────────────────────────────────

VISION_MOMENT_WINDOW_SECONDS = 10.0
VISION_CHUNK_PREFIX = '[On-screen visual] '
MOMENT_PROMOTION_MAX_ATTEMPTS = 3


def _caption_prompt(content: CourseContent, timestamp_seconds: float) -> str:
    """Builds the vision-captioning prompt, including nearby transcript text as context (not
    duplicated into the stored caption — that text is already its own embedded chunk)."""
    window = 30.0
    nearby = (
        ContentEmbedding.query
        .filter(
            ContentEmbedding.course_content_id == content.id,
            ContentEmbedding.start_seconds.isnot(None),
            ContentEmbedding.start_seconds >= timestamp_seconds - window,
            ContentEmbedding.start_seconds <= timestamp_seconds + window,
        )
        .order_by(ContentEmbedding.start_seconds)
        .all()
    )
    context = ' '.join(c.chunk_text for c in nearby)[:1500]
    from lms.rag_service import _format_timestamp
    ts = _format_timestamp(timestamp_seconds)
    context_line = f'\nThe lecturer is saying, around this moment: "{context}"\n' if context else ''
    return (
        f'This is a still frame from a lecture recording titled "{content.title}", at {ts}.'
        f'{context_line}\n'
        'Describe what is visible on screen so it can be found later by a text search. '
        'Transcribe any visible text, labels, equations, or code verbatim. If it is a diagram '
        'or chart, describe its structure and what it shows. Output plain prose, under 120 '
        'words, no preamble, no markdown.'
    )


def _store_caption_embedding(content: CourseContent, moment: VideoMoment) -> bool:
    from lms import gemini_client
    chunk_text = f'{VISION_CHUNK_PREFIX}{moment.caption}'
    vector = gemini_client.embed_text(chunk_text, task_type='RETRIEVAL_DOCUMENT')
    if not vector:
        return False
    next_index = (
        db.session.query(db.func.max(ContentEmbedding.chunk_index))
        .filter_by(course_content_id=content.id).scalar() or -1
    ) + 1
    db.session.add(ContentEmbedding(
        course_content_id=content.id,
        chunk_index=next_index,
        chunk_text=chunk_text,
        start_seconds=moment.timestamp_seconds,
        end_seconds=moment.timestamp_seconds + VISION_MOMENT_WINDOW_SECONDS,
        embedding=vector,
    ))
    return True


def caption_chunks_for_content(content: CourseContent) -> list[dict]:
    """Rebuilds embeddable {'text','start','end'} chunks from already-captioned VideoMoment
    rows — no vision API call, since the caption text is the durable artifact stored
    precisely so re-embedding on reindex is free. Excludes 'blocked' (and 'pending'/'failed')
    rows automatically via the status filter."""
    moments = VideoMoment.query.filter_by(course_content_id=content.id, status='captioned').all()
    return [
        {
            'text': f'{VISION_CHUNK_PREFIX}{m.caption}',
            'start': m.timestamp_seconds,
            'end': m.timestamp_seconds + VISION_MOMENT_WINDOW_SECONDS,
        }
        for m in moments if m.caption
    ]


def find_matching_caption(content_id: int, phash_hex: str) -> str | None:
    """If a frame near-duplicate to `phash_hex` was already captioned on this content (e.g.
    the lecturer returned to a slide shown earlier), return its caption text so the caller can
    skip a redundant vision API call — the single highest-leverage cost saving for slide-heavy
    lectures. A new ContentEmbedding row still gets created at the new timestamp so both
    moments remain independently citable."""
    from lms import frame_extraction
    captioned = VideoMoment.query.filter_by(
        course_content_id=content_id, status='captioned',
    ).filter(VideoMoment.frame_phash.isnot(None)).all()
    for m in captioned:
        if frame_extraction.phash_distance(phash_hex, m.frame_phash) <= frame_extraction.PHASH_NEAR_DUPLICATE_DISTANCE:
            return m.caption
    return None


def promote_pending_moments(limit: int, course_id: int | None = None) -> dict:
    """The promotion sweep's actual work — called from
    job_manager.run_scheduled_moment_promotion (global, recurring) and
    job_manager._execute_promote_moments_job (course_id set, the manual admin "Promote
    flagged moments" trigger next to "Reindex course content"). Claims new
    threshold-crossing buckets (and picks up retryable 'pending' rows, which also covers
    teacher-fast-path moments — see routes/api.py's flag_video_moment), then for each video
    with pending moments: downloads it once, samples/analyzes frames per moment, captions,
    and embeds.
    """
    from lms import frame_extraction, gemini_client
    from lms.rag_service import _download_content_bytes

    result = {'promoted': 0, 'captioned': 0, 'failed': 0, 'videos_downloaded': 0, 'vision_calls': 0}

    # Claim new candidates immediately (before any download/API call) so a worker crash
    # mid-caption leaves a resumable 'pending' row rather than re-promoting from scratch.
    for cand in candidate_buckets(course_id=course_id):
        if result['promoted'] >= limit:
            break
        moment = VideoMoment(
            course_content_id=cand['course_content_id'],
            bucket_index=cand['bucket_index'],
            timestamp_seconds=cand['timestamp_seconds'],
            weight_at_promotion=cand['weight'],
            status='pending',
        )
        db.session.add(moment)
        try:
            db.session.commit()
            result['promoted'] += 1
        except Exception:
            db.session.rollback()  # lost the race with another promotion path (e.g. teacher fast-path)

    retry_cutoff = datetime.utcnow() - timedelta(hours=1)
    pending_query = (
        VideoMoment.query
        .filter(
            VideoMoment.status == 'pending',
            VideoMoment.attempts < MOMENT_PROMOTION_MAX_ATTEMPTS,
            db.or_(VideoMoment.last_attempt_at.is_(None), VideoMoment.last_attempt_at < retry_cutoff),
        )
    )
    if course_id is not None:
        pending_query = pending_query.join(CourseContent, VideoMoment.course_content_id == CourseContent.id) \
            .filter(CourseContent.course_id == course_id)
    pending = (
        pending_query
        .order_by(VideoMoment.weight_at_promotion.desc(), VideoMoment.created_at)
        .limit(max(limit, 1) * 5)  # a few videos' worth, since we group+dedupe by content below
        .all()
    )

    by_content: dict[int, list[VideoMoment]] = {}
    for m in pending:
        by_content.setdefault(m.course_content_id, []).append(m)

    for content_id, moments in by_content.items():
        content = CourseContent.query.get(content_id)
        if not content or not content.has_bytes:
            for m in moments:
                m.status = 'failed'
            db.session.commit()
            result['failed'] += len(moments)
            continue

        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            if not _download_content_bytes(content, tmp_path):
                for m in moments:
                    m.attempts += 1
                    m.last_attempt_at = datetime.utcnow()
                db.session.commit()
                continue
            result['videos_downloaded'] += 1

            for moment in moments:
                moment.attempts += 1
                moment.last_attempt_at = datetime.utcnow()
                db.session.commit()

                frames = frame_extraction.sample_frames(tmp_path, moment.timestamp_seconds)
                chosen = frame_extraction.analyze_frames(frames)
                if not chosen:
                    moment.status = 'failed'
                    db.session.commit()
                    result['failed'] += 1
                    continue

                for i, (t, img, phash) in enumerate(chosen):
                    target = moment
                    if i > 0:
                        new_bucket = bucket_for(t)
                        if new_bucket != moment.bucket_index and not VideoMoment.query.filter_by(
                            course_content_id=content_id, bucket_index=new_bucket,
                        ).first():
                            target = VideoMoment(
                                course_content_id=content_id, bucket_index=new_bucket,
                                timestamp_seconds=t, weight_at_promotion=moment.weight_at_promotion,
                                status='pending', attempts=1, last_attempt_at=datetime.utcnow(),
                            )
                            db.session.add(target)
                        else:
                            continue  # collision — drop the split, keep just the first moment

                    # Reuse an existing caption if this frame matches an already-captioned one
                    # (e.g. the lecturer returned to a slide shown earlier) — no API call.
                    reused = find_matching_caption(content_id, phash)
                    if reused:
                        target.caption = reused
                    else:
                        caption = gemini_client.generate_content_with_image(
                            frame_extraction.image_to_jpeg_bytes(img), 'image/jpeg',
                            _caption_prompt(content, t),
                        )
                        result['vision_calls'] += 1
                        if not caption:
                            # Leave target 'pending' for retry (moment itself was already
                            # marked attempted above; a split-off target just stays pending).
                            db.session.commit()
                            continue
                        target.caption = caption

                    target.frame_phash = phash
                    target.timestamp_seconds = t
                    target.status = 'captioned'
                    target.captioned_at = datetime.utcnow()
                    if _store_caption_embedding(content, target):
                        result['captioned'] += 1
                    db.session.commit()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return result
