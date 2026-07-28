"""
Thin REST client for the Gemini API — no Flask/DB dependency, mirrors core_translator.py's
role for the translation pipeline. Runtime orchestration (DB queries, chunking, retrieval)
lives in rag_service.py.

Built against the classic generateContent/embedContent REST surface (not the newer
Interactions API) — generateContent is still fully supported and far better documented.
Model names use Google's "-latest" aliases where available so this doesn't go stale as
new model generations ship.
"""
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'

GENERATION_MODEL = 'gemini-flash-latest'
EMBEDDING_MODEL = 'gemini-embedding-001'


def _api_key() -> str:
    return os.environ.get('GEMINI_API_KEY') or ''


def _headers(**extra) -> dict:
    return {'x-goog-api-key': _api_key(), 'Content-Type': 'application/json', **extra}


# ── Embeddings ──────────────────────────────────────────────────────────────────

def embed_text(text: str, *, task_type: str = 'RETRIEVAL_DOCUMENT', dimensions: int = 768) -> list[float] | None:
    """Embed a single string. task_type should be RETRIEVAL_DOCUMENT for content being
    indexed, RETRIEVAL_QUERY for a search query — Gemini's embeddings are tuned per side.

    Truncating below the model's native 3072-dim output requires re-normalizing the vector
    afterward (Google's own documented requirement) — done here so callers always get a
    unit vector suitable for cosine similarity.
    """
    if not _api_key() or not text or not text.strip():
        return None
    try:
        resp = requests.post(
            f'{_API_BASE}/models/{EMBEDDING_MODEL}:embedContent',
            headers=_headers(),
            json={
                'content': {'parts': [{'text': text}]},
                'taskType': task_type,
                'outputDimensionality': dimensions,
            },
            timeout=30,
        )
        resp.raise_for_status()
        values = resp.json()['embedding']['values']
        norm = sum(v * v for v in values) ** 0.5
        return [v / norm for v in values] if norm else values
    except Exception as e:
        logger.error(f"Gemini embedContent error: {e}")
        return None


def embed_batch(texts: list[str], *, task_type: str = 'RETRIEVAL_DOCUMENT', dimensions: int = 768) -> list[list[float] | None]:
    """Embed multiple strings in one request via batchEmbedContents. Returns a list the
    same length as texts; entries are None for empty/whitespace-only inputs or on failure."""
    if not _api_key() or not texts:
        return [None] * len(texts)

    indices = [i for i, t in enumerate(texts) if t and t.strip()]
    if not indices:
        return [None] * len(texts)

    requests_payload = [
        {
            'model': f'models/{EMBEDDING_MODEL}',
            'content': {'parts': [{'text': texts[i]}]},
            'taskType': task_type,
            'outputDimensionality': dimensions,
        }
        for i in indices
    ]

    results: list[list[float] | None] = [None] * len(texts)
    try:
        resp = requests.post(
            f'{_API_BASE}/models/{EMBEDDING_MODEL}:batchEmbedContents',
            headers=_headers(),
            json={'requests': requests_payload},
            timeout=60,
        )
        resp.raise_for_status()
        embeddings = resp.json().get('embeddings', [])
        for idx, emb in zip(indices, embeddings):
            values = emb.get('values')
            if not values:
                continue
            norm = sum(v * v for v in values) ** 0.5
            results[idx] = [v / norm for v in values] if norm else values
    except Exception as e:
        logger.error(f"Gemini batchEmbedContents error ({len(indices)} texts): {e}")

    return results


# ── Text generation ─────────────────────────────────────────────────────────────

def generate_content(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str = GENERATION_MODEL,
    temperature: float = 0.3,
    timeout: int = 60,
) -> str | None:
    """Plain text generation. Returns the model's text response, or None on failure."""
    if not _api_key():
        logger.warning("GEMINI_API_KEY not configured")
        return None

    payload: dict = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': temperature},
    }
    if system_instruction:
        payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}

    return _call_generate(model, payload, timeout)


def generate_content_with_file(
    file_uri: str,
    mime_type: str,
    prompt: str,
    *,
    model: str = GENERATION_MODEL,
    timeout: int = 180,
) -> str | None:
    """Generation grounded in a previously-uploaded file (see upload_file below) — used for
    video/audio transcription."""
    if not _api_key():
        return None

    payload = {
        'contents': [{
            'parts': [
                {'fileData': {'fileUri': file_uri, 'mimeType': mime_type}},
                {'text': prompt},
            ]
        }],
    }
    return _call_generate(model, payload, timeout)


def _call_generate(model: str, payload: dict, timeout: int) -> str | None:
    try:
        resp = requests.post(
            f'{_API_BASE}/models/{model}:generateContent',
            headers=_headers(),
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        candidates = resp.json().get('candidates') or []
        if not candidates:
            return None
        parts = candidates[0].get('content', {}).get('parts', [])
        text = ''.join(p.get('text', '') for p in parts if 'text' in p)
        return text or None
    except Exception as e:
        logger.error(f"Gemini generateContent error: {e}")
        return None


# ── File API (video/audio transcription) ────────────────────────────────────────

def upload_file(file_path: str, mime_type: str, display_name: str | None = None) -> tuple[str, str] | tuple[None, None]:
    """Upload a local file to Gemini's File API (resumable protocol). Returns (file_uri,
    file_name) — file_name is the 'files/xyz' resource id, needed to poll status/delete."""
    if not _api_key():
        return None, None

    import os as _os
    num_bytes = _os.path.getsize(file_path)

    try:
        start_resp = requests.post(
            f'{_API_BASE}/files',
            headers={
                'x-goog-api-key': _api_key(),
                'X-Goog-Upload-Protocol': 'resumable',
                'X-Goog-Upload-Command': 'start',
                'X-Goog-Upload-Header-Content-Length': str(num_bytes),
                'X-Goog-Upload-Header-Content-Type': mime_type,
                'Content-Type': 'application/json',
            },
            json={'file': {'display_name': display_name or _os.path.basename(file_path)}},
            timeout=30,
        )
        start_resp.raise_for_status()
        upload_url = start_resp.headers.get('X-Goog-Upload-URL') or start_resp.headers.get('x-goog-upload-url')
        if not upload_url:
            logger.error("Gemini file upload: no upload URL in response headers")
            return None, None

        with open(file_path, 'rb') as f:
            upload_resp = requests.post(
                upload_url,
                headers={
                    'Content-Length': str(num_bytes),
                    'X-Goog-Upload-Offset': '0',
                    'X-Goog-Upload-Command': 'upload, finalize',
                },
                data=f,
                timeout=900,
            )
        upload_resp.raise_for_status()
        file_info = upload_resp.json().get('file', {})
        return file_info.get('uri'), file_info.get('name')
    except Exception as e:
        logger.error(f"Gemini file upload error: {e}")
        return None, None


def wait_for_file_active(file_name: str, *, max_wait: int = 180, poll_interval: int = 3) -> bool:
    """Poll an uploaded file until Gemini finishes processing it (state ACTIVE) — required
    before referencing it in generateContent. Video files can take tens of seconds."""
    if not _api_key():
        return False
    waited = 0
    while waited < max_wait:
        try:
            resp = requests.get(f'{_API_BASE}/{file_name}', headers=_headers(), timeout=15)
            resp.raise_for_status()
            state = resp.json().get('state')
            if state == 'ACTIVE':
                return True
            if state == 'FAILED':
                logger.error(f"Gemini file {file_name} failed processing")
                return False
        except Exception as e:
            logger.error(f"Gemini file status check error: {e}")
            return False
        time.sleep(poll_interval)
        waited += poll_interval
    logger.error(f"Gemini file {file_name} did not become ACTIVE within {max_wait}s")
    return False


def delete_gemini_file(file_name: str) -> None:
    """Best-effort cleanup of an uploaded Gemini file. Not fatal if it fails — Gemini
    auto-expires uploaded files after 48h regardless."""
    try:
        requests.delete(f'{_API_BASE}/{file_name}', headers=_headers(), timeout=15)
    except Exception as e:
        logger.warning(f"Gemini file delete error (non-fatal): {e}")
