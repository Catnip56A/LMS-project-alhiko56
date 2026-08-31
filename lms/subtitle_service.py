"""
Subtitle generation from persisted Whisper transcript segments (lms.models.TranscriptSegment).

Runtime layer — requires Flask app context and the database, same split as rag_service.py.
record_transcript_segments() is called from rag_service.embed_content_item() as a side effect
of transcription; generate_vtt() is called from the subtitle-serving route in
lms/routes/api.py to build a WebVTT file on the fly from those stored segments — no caching,
since the query is a single indexed lookup and WebVTT generation is trivial string work.
"""
import logging

from lms.models import db, CourseContent, TranscriptSegment

logger = logging.getLogger(__name__)


def record_transcript_segments(content: CourseContent, segments: list[dict]) -> int:
    """Delete existing segments for this content, re-insert from the raw (pre-chunking)
    Whisper segment list. Does not commit — the caller's commit covers it (matches how
    embed_content_item already handles ContentEmbedding's delete-and-reinsert)."""
    TranscriptSegment.query.filter_by(course_content_id=content.id).delete()
    stored = 0
    for idx, seg in enumerate(segments):
        start, end, text = seg.get('start'), seg.get('end'), (seg.get('text') or '').strip()
        if start is None or end is None or not text:
            continue
        db.session.add(TranscriptSegment(
            course_content_id=content.id,
            segment_index=idx,
            start_seconds=start,
            end_seconds=end,
            text=text,
        ))
        stored += 1
    return stored


def _vtt_timestamp(seconds: float) -> str:
    """WebVTT requires HH:MM:SS.mmm — unlike _format_timestamp's student-facing M:SS, every
    component here is fixed-width and zero-padded, including hours, since the spec doesn't
    allow the shorthand omission a citation chip can get away with."""
    total_ms = max(0, round(seconds * 1000))
    hours, rem_ms = divmod(total_ms, 3600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}'


def has_subtitles(content_id: int) -> bool:
    return db.session.query(TranscriptSegment.id).filter_by(course_content_id=content_id).first() is not None


def generate_vtt(content: CourseContent) -> str | None:
    """Builds a WebVTT string from this content's stored TranscriptSegment rows, or None if
    there are none (not yet transcribed, or a non-video/audio item)."""
    segments = (
        TranscriptSegment.query
        .filter_by(course_content_id=content.id)
        .order_by(TranscriptSegment.segment_index)
        .all()
    )
    if not segments:
        return None

    lines = ['WEBVTT', '']
    for i, seg in enumerate(segments, start=1):
        # WebVTT requires end > start and monotonically non-decreasing cues; Whisper segments
        # already satisfy this, but guard against a degenerate zero-length segment (e.g. a
        # VAD edge case) rendering an invisible cue that still eats a line in some players.
        end = seg.end_seconds if seg.end_seconds > seg.start_seconds else seg.start_seconds + 0.5
        lines.append(str(i))
        lines.append(f'{_vtt_timestamp(seg.start_seconds)} --> {_vtt_timestamp(end)}')
        lines.append(seg.text)
        lines.append('')

    return '\n'.join(lines)
