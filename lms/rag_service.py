"""
RAG (retrieval-augmented generation) service for the AI personal guide (Phase 6).

Runtime layer — requires Flask app context and the database. Orchestrates:
  - extracting text from CourseContent items (plain text, PDF, or video transcription)
  - chunking + embedding that text (via gemini_client) and storing it in ContentEmbedding
  - answering student questions by retrieving relevant chunks and grounding a Gemini
    response in them, with citations back to the source CourseContent

See gemini_client.py for the underlying Gemini REST calls (no Flask/DB dependency there,
mirroring core_translator.py's split from translation_service.py).
"""
import logging
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timedelta

import requests
from docx import Document as DocxDocument
from pptx import Presentation
from pypdf import PdfReader

from lms import gemini_client
from lms.models import db, AiConversation, AiConversationMessage, ContentEmbedding, CourseContent

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Retrieval is two-stage: first rank whole files by their single best-matching chunk (from
# a wider candidate pool), then only pull context from the top few files. Mixing fragments
# from every vaguely-related file into one prompt gets noisy as a course accumulates more
# material — narrowing to the most relevant documents first keeps answers coherent.
CANDIDATE_POOL_SIZE = 30
MAX_SOURCE_FILES = 3
CHUNKS_PER_FILE = 4

# Conversation memory: keep this many raw turns (messages, not Q&A pairs) verbatim; older
# ones get folded into a rolling summary. A conversation the user hasn't consented to keep
# (AiConversation joined to a User with ai_history_consent True/False/None) is hard-deleted
# once inactive for this many days regardless of the above — see purge_stale_conversations.
MAX_VERBATIM_MESSAGES = 6
CONVERSATION_RETENTION_DAYS = 30

SYSTEM_INSTRUCTION = (
    "You are a study assistant answering questions about a specific course, using only the "
    "course material excerpts provided as context (plus prior conversation context, if any, "
    "purely to understand what the student is referring to). If the answer isn't contained "
    "in the provided excerpts, say you don't have that information in the course materials — "
    "do not use outside knowledge to fill gaps. Keep answers concise and mention which "
    "material(s) you drew from by name."
)


# ── Chunking ────────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Word-boundary-aware sliding-window chunking."""
    text = ' '.join(text.split())
    if not text:
        return []

    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            break_point = text.rfind(' ', start, end)
            if break_point > start:
                end = break_point
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


# ── Text extraction ──────────────────────────────────────────────────────────────

_DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.pptx'}


def extract_text_for_content(content: CourseContent) -> str | None:
    """Best-effort text extraction. Returns None if the content type isn't supported for
    indexing (e.g. links, images, or legacy Office formats like .doc/.ppt — Office *preview
    rendering* is separately Phase 8 scope, but raw text extraction from the modern .docx/
    .pptx XML formats is unrelated to that and cheap enough to do here)."""
    if content.content_type == 'text':
        return content.content_data
    if content.content_type == 'file' and content.drive_file_id:
        return _extract_drive_file_text(content)
    if content.content_type == 'video' and content.drive_file_id:
        return _transcribe_video(content)
    return None


def _download_public_drive_file(file_id: str, dest_path: str) -> bool:
    """Download a Drive file via its public share link, bypassing the OAuth-scoped Drive
    API entirely. Course files are made public-viewable at upload time (see
    google_drive_service.set_file_permissions) — the OAuth-scoped API (files.get/get_media)
    only works for files the querying identity itself created/opened (the drive.file scope's
    restriction), which 404s on anything created under a different identity than whichever
    the RAG pipeline authenticates as (e.g. content uploaded before the Phase 4 worker
    account existed). The public link has no such restriction, so this works uniformly."""
    session = requests.Session()
    url = 'https://drive.google.com/uc?export=download'
    try:
        resp = session.get(url, params={'id': file_id}, stream=True, timeout=60)

        # Large files get an HTML "can't scan for viruses" interstitial instead of the file
        # itself — needs a confirm token (from a cookie or the page body) to proceed.
        if 'text/html' in resp.headers.get('Content-Type', ''):
            token = next((v for k, v in resp.cookies.items() if k.startswith('download_warning')), None)
            if not token:
                match = re.search(r'confirm=([0-9A-Za-z_]+)', resp.text)
                token = match.group(1) if match else None
            if not token:
                logger.error(f"Could not extract confirm token for large Drive file {file_id}")
                return False
            resp = session.get(url, params={'id': file_id, 'confirm': token}, stream=True, timeout=300)

        if resp.status_code != 200:
            logger.error(f"Public Drive download for {file_id} returned {resp.status_code}")
            return False

        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"Public Drive download failed for {file_id}: {e}")
        return False


def _extract_drive_file_text(content: CourseContent) -> str | None:
    extension = os.path.splitext(content.title)[1].lower()
    if extension not in _DOCUMENT_EXTENSIONS:
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            tmp_path = tmp.name
        if not _download_public_drive_file(content.drive_file_id, tmp_path):
            return None

        if extension == '.pdf':
            reader = PdfReader(tmp_path)
            return '\n'.join(page.extract_text() or '' for page in reader.pages)
        if extension == '.docx':
            doc = DocxDocument(tmp_path)
            return '\n'.join(p.text for p in doc.paragraphs if p.text)
        if extension == '.pptx':
            prs = Presentation(tmp_path)
            lines = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text_frame.text:
                        lines.append(shape.text_frame.text)
            return '\n'.join(lines)
        return None
    except Exception as e:
        logger.error(f"Text extraction failed for content {content.id} ({extension}): {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _transcribe_video(content: CourseContent) -> str | None:
    extension = os.path.splitext(content.title)[1].lower()
    mime_type = mimetypes.guess_type(content.title)[0]
    if not mime_type or not (mime_type.startswith('video/') or mime_type.startswith('audio/')):
        return None

    tmp_path = None
    gemini_file_name = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            tmp_path = tmp.name
        if not _download_public_drive_file(content.drive_file_id, tmp_path):
            return None

        file_uri, gemini_file_name = gemini_client.upload_file(tmp_path, mime_type, display_name=content.title)
        if not file_uri or not gemini_client.wait_for_file_active(gemini_file_name):
            return None

        return gemini_client.generate_content_with_file(
            file_uri, mime_type,
            'Transcribe this lecture recording verbatim. Output only the transcript text — '
            'no timestamps, no speaker labels, no commentary.',
            timeout=300,
        )
    except Exception as e:
        logger.error(f"Video transcription failed for content {content.id}: {e}")
        return None
    finally:
        if gemini_file_name:
            gemini_client.delete_gemini_file(gemini_file_name)
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ── Indexing ────────────────────────────────────────────────────────────────────

def embed_content_item(content: CourseContent) -> int:
    """Extract, chunk, embed, and store one CourseContent item. Returns the number of
    chunks stored (0 if nothing was extracted, e.g. an unsupported file type)."""
    text = extract_text_for_content(content)

    ContentEmbedding.query.filter_by(course_content_id=content.id).delete()

    if not text or not text.strip():
        content.embedded_at = datetime.utcnow()
        db.session.commit()
        return 0

    chunks = chunk_text(text)
    if not chunks:
        content.embedded_at = datetime.utcnow()
        db.session.commit()
        return 0

    vectors = gemini_client.embed_batch(chunks, task_type='RETRIEVAL_DOCUMENT')

    stored = 0
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        if not vector:
            continue
        db.session.add(ContentEmbedding(
            course_content_id=content.id,
            chunk_index=idx,
            chunk_text=chunk,
            embedding=vector,
        ))
        stored += 1

    content.embedded_at = datetime.utcnow()
    db.session.commit()
    return stored


# ── Retrieval + answering ────────────────────────────────────────────────────────

def get_locked_content_ids(course, user) -> set[int]:
    """Content ids inside a currently-locked folder for this user — mirrors the lock check
    in course_page_enrolled.html (folder.locked_until_assignment_id/locked_until_quiz_id vs.
    the user's passed submissions/attempts) so the assistant can't answer from gated
    material. Locks cascade to subfolders of a locked folder."""
    from lms.models import CourseAssignmentSubmission, Quiz, QuizAttempt

    if user is None or not getattr(user, 'is_authenticated', False):
        passed_assignment_ids = set()
        passed_quiz_ids = set()
    else:
        passed_assignment_ids = {
            s.assignment_id for s in
            CourseAssignmentSubmission.query.filter_by(user_id=user.id, passed=True).all()
        }
        passed_quiz_ids = {
            a.quiz_id for a in
            QuizAttempt.query.join(Quiz)
                .filter(QuizAttempt.user_id == user.id, Quiz.course_id == course.id, QuizAttempt.passed.is_(True))
                .all()
        }

    folders = {f.id: f for f in course.content_folders.all()}

    def folder_locked(folder_id, seen=frozenset()):
        if folder_id in seen or folder_id not in folders:
            return False
        folder = folders[folder_id]
        if folder.locked_until_assignment_id and folder.locked_until_assignment_id not in passed_assignment_ids:
            return True
        if folder.locked_until_quiz_id and folder.locked_until_quiz_id not in passed_quiz_ids:
            return True
        if folder.parent_folder_id:
            return folder_locked(folder.parent_folder_id, seen | {folder_id})
        return False

    return {
        content.id for content in course.contents.all()
        if content.folder_id and folder_locked(content.folder_id)
    }


def _get_or_create_conversation(user, course) -> AiConversation:
    conversation = AiConversation.query.filter_by(user_id=user.id, course_id=course.id).first()
    if not conversation:
        conversation = AiConversation(user_id=user.id, course_id=course.id)
        db.session.add(conversation)
        db.session.commit()
    return conversation


def _build_history_context(conversation: AiConversation) -> str:
    """Rolling summary (if any) + the most recent verbatim turns, formatted for inclusion
    in a prompt. Empty string if this is a fresh conversation."""
    parts = []
    if conversation.summary:
        parts.append(f"Summary of earlier conversation:\n{conversation.summary}")

    recent = (
        conversation.messages.order_by(AiConversationMessage.created_at.desc())
        .limit(MAX_VERBATIM_MESSAGES)
        .all()
    )
    recent.reverse()
    if recent:
        speaker = {'user': 'Student', 'assistant': 'Assistant'}
        turns = [f"{speaker[m.role]}: {m.content}" for m in recent]
        parts.append("Recent conversation:\n" + '\n'.join(turns))

    return '\n\n'.join(parts)


def _rewrite_query_for_retrieval(question: str, history_context: str) -> str:
    """Follow-up questions ('what about the second one?') often don't embed anywhere near
    the chunks they actually need — rewrite into a standalone question using conversation
    context before embedding for retrieval. Falls back to the original question on failure."""
    if not history_context:
        return question

    prompt = (
        f"Conversation so far:\n{history_context}\n\n"
        f"Latest student message: {question}\n\n"
        "Rewrite the latest student message as a standalone question that makes sense "
        "without the conversation history, resolving pronouns/references. If it's already "
        "standalone, return it unchanged. Output only the rewritten question, nothing else."
    )
    rewritten = gemini_client.generate_content(prompt, temperature=0.0, timeout=20)
    return rewritten.strip() if rewritten else question


def _persist_turn(conversation: AiConversation, question: str, answer: str, sources: list) -> None:
    db.session.add(AiConversationMessage(conversation_id=conversation.id, role='user', content=question))
    db.session.add(AiConversationMessage(
        conversation_id=conversation.id, role='assistant', content=answer, sources=sources or None,
    ))
    conversation.last_activity_at = datetime.utcnow()
    db.session.commit()
    _compact_conversation_if_needed(conversation)


def _compact_conversation_if_needed(conversation: AiConversation) -> None:
    """Fold the oldest turns into the rolling summary once the raw count grows past
    MAX_VERBATIM_MESSAGES, so a long-running conversation's prompt size stays bounded."""
    messages = conversation.messages.order_by(AiConversationMessage.created_at).all()
    if len(messages) <= MAX_VERBATIM_MESSAGES:
        return

    excess = messages[:len(messages) - MAX_VERBATIM_MESSAGES]
    speaker = {'user': 'Student', 'assistant': 'Assistant'}
    excess_text = '\n'.join(f"{speaker[m.role]}: {m.content}" for m in excess)

    prompt = (
        (f"Existing summary of the conversation so far:\n{conversation.summary}\n\n" if conversation.summary else "")
        + f"New exchanges to fold into the summary:\n{excess_text}\n\n"
        "Write an updated, concise summary (a few sentences) of the entire conversation so "
        "far, preserving important facts/topics discussed. Output only the summary text."
    )
    new_summary = gemini_client.generate_content(prompt, temperature=0.2, timeout=30)
    if not new_summary:
        return  # leave the raw messages in place and try again next turn

    conversation.summary = new_summary.strip()
    for m in excess:
        db.session.delete(m)
    db.session.commit()


def get_conversation_history(user, course) -> dict:
    """For the frontend on page load: {'consent': True/False/None, 'messages': [...]}.
    `messages` is only populated if the user has actually consented — the caller doesn't
    need to re-check consent itself, but `consent` is always returned so the frontend knows
    whether to show the opt-in prompt."""
    conversation = AiConversation.query.filter_by(user_id=user.id, course_id=course.id).first()
    messages = []
    if conversation and user.ai_history_consent:
        messages = [
            {'role': m.role, 'content': m.content, 'sources': m.sources or []}
            for m in conversation.messages.order_by(AiConversationMessage.created_at).all()
        ]
    return {'consent': user.ai_history_consent, 'messages': messages}


def purge_stale_conversations() -> int:
    """Hard-delete conversations (cascading their messages) the user hasn't consented to
    keep, once inactive for CONVERSATION_RETENTION_DAYS. Consented conversations are never
    auto-purged by this. Returns the number of conversations deleted."""
    from lms.models import User

    cutoff = datetime.utcnow() - timedelta(days=CONVERSATION_RETENTION_DAYS)
    stale = (
        AiConversation.query
        .join(User, AiConversation.user_id == User.id)
        .filter(
            AiConversation.last_activity_at < cutoff,
            db.or_(User.ai_history_consent.is_(None), User.ai_history_consent.is_(False)),
        )
        .all()
    )
    count = len(stale)
    for conversation in stale:
        db.session.delete(conversation)
    db.session.commit()
    return count


def answer_question(
    course, question: str, user,
    max_files: int = MAX_SOURCE_FILES, chunks_per_file: int = CHUNKS_PER_FILE,
) -> dict | None:
    """Returns {'answer': str, 'sources': [{'content_id', 'title'}]}, or None if the
    question couldn't be processed (e.g. GEMINI_API_KEY missing/unreachable). Tracks
    multi-turn conversation memory per (user, course) when user is a real authenticated
    User — see _get_or_create_conversation / _persist_turn."""
    conversation = None
    history_context = ''
    if user is not None and getattr(user, 'is_authenticated', False):
        conversation = _get_or_create_conversation(user, course)
        history_context = _build_history_context(conversation)

    retrieval_query = _rewrite_query_for_retrieval(question, history_context)

    query_vector = gemini_client.embed_text(retrieval_query, task_type='RETRIEVAL_QUERY')
    if not query_vector:
        return None

    locked_ids = get_locked_content_ids(course, user)

    query = (
        db.session.query(ContentEmbedding, CourseContent)
        .join(CourseContent, ContentEmbedding.course_content_id == CourseContent.id)
        .filter(
            CourseContent.course_id == course.id,
            CourseContent.is_published.is_(True),
        )
    )
    if locked_ids:
        query = query.filter(~CourseContent.id.in_(locked_ids))

    candidates = (
        query.order_by(ContentEmbedding.embedding.cosine_distance(query_vector))
        .limit(CANDIDATE_POOL_SIZE)
        .all()
    )

    if not candidates:
        answer = "I don't have any indexed course material to answer that from yet."
        sources = []
    else:
        # Stage 1: pick which files to read. candidates is already ordered by ascending
        # distance (best match first), so each file's first appearance here is its best
        # chunk — ranking files by that and keeping only the top few is the "file
        # selection" step.
        ranked_content_ids = []
        seen = set()
        for _, content in candidates:
            if content.id not in seen:
                seen.add(content.id)
                ranked_content_ids.append(content.id)
        selected_content_ids = set(ranked_content_ids[:max_files])

        # Stage 2: within just those files, take each file's best few chunks.
        context_blocks = []
        sources = []
        seen_content_ids = set()
        chunks_used = {}
        for embedding, content in candidates:
            if content.id not in selected_content_ids:
                continue
            if chunks_used.get(content.id, 0) >= chunks_per_file:
                continue
            chunks_used[content.id] = chunks_used.get(content.id, 0) + 1
            context_blocks.append(f"[Source: {content.title}]\n{embedding.chunk_text}")
            if content.id not in seen_content_ids:
                seen_content_ids.add(content.id)
                sources.append({'content_id': content.id, 'title': content.title})

        context = '\n\n---\n\n'.join(context_blocks)
        prompt_parts = []
        if history_context:
            prompt_parts.append(history_context)
        prompt_parts.append(f"Course material excerpts:\n\n{context}")
        prompt_parts.append(f"Student question: {question}")
        prompt = '\n\n---\n\n'.join(prompt_parts)

        answer = gemini_client.generate_content(prompt, system_instruction=SYSTEM_INSTRUCTION, temperature=0.2)
        if not answer:
            return None

    if conversation:
        _persist_turn(conversation, question, answer, sources)

    return {'answer': answer, 'sources': sources}
