"""
Thin REST client for the Gemini API — no Flask/DB dependency, mirrors core_translator.py's
role for the translation pipeline. Runtime orchestration (DB queries, chunking, retrieval)
lives in rag_service.py.

Built against the classic generateContent/embedContent REST surface (not the newer
Interactions API) — generateContent is still fully supported and far better documented.
Model names use Google's "-latest" aliases where available so this doesn't go stale as
new model generations ship.
"""
import base64
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'

GENERATION_MODEL = 'gemini-flash-latest'
EMBEDDING_MODEL = 'gemini-embedding-001'

# Free-tier quota is per-model, not shared — if GENERATION_MODEL's daily/per-minute limit is
# hit, these get tried in order before giving up. Discovered the hard way: `-latest` aliases
# can roll onto a new model generation with its own separate (and possibly much tighter)
# quota bucket with zero code change on our end, so a fallback chain matters more here than
# it would for a pinned model name. Candidates below were confirmed live to actually be
# reachable on this API key — several plausible-looking names (gemini-2.5-flash,
# gemini-2.5-flash-lite, gemini-pro-latest at the time) turned out 404 ("no longer available
# to new users") or already quota-exhausted themselves; don't add a model back to this list
# without confirming it responds first.
GENERATION_MODEL_FALLBACKS = ['gemini-3.5-flash', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite', 'gemini-3-flash-preview']


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
    max_output_tokens: int | None = None,
    thinking_budget: int | None = None,
    timeout: int = 60,
) -> str | None:
    """Plain text generation. Returns the model's text response, or None on failure.

    `thinking_budget`: this model is a "thinking" model — its reasoning tokens count against
    the same maxOutputTokens budget as the visible answer, silently, and a simple question
    was observed burning 400+ thinking tokens before writing anything. Pass 0 to disable
    thinking entirely (all of max_output_tokens then goes to visible text — use this whenever
    max_output_tokens is set to something modest); leave None to let the model think freely,
    but then max_output_tokens needs to be generous enough to leave room for both.
    """
    if not _api_key():
        logger.warning("GEMINI_API_KEY not configured")
        return None

    generation_config: dict = {'temperature': temperature}
    if max_output_tokens:
        generation_config['maxOutputTokens'] = max_output_tokens
    if thinking_budget is not None:
        generation_config['thinkingConfig'] = {'thinkingBudget': thinking_budget}

    payload: dict = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': generation_config,
    }
    if system_instruction:
        payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}

    return _call_generate_with_fallback(model, payload, timeout)


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
    return _call_generate_with_fallback(model, payload, timeout)


def generate_content_with_image(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str = GENERATION_MODEL,
    temperature: float = 0.2,
    max_output_tokens: int | None = None,
    thinking_budget: int | None = None,
    timeout: int = 60,
) -> str | None:
    """Generation grounded in a single still image, sent inline as base64.

    Deliberately not routed through the File API (upload_file / wait_for_file_active /
    generate_content_with_file): that path exists for large async media and costs three HTTP
    round-trips plus a polling loop with a ~3s floor per file, all to hand over a ~60KB JPEG.
    Inline bytes make it one request — Gemini's inline limit is on total request size
    (~20MB), which a downscaled video frame is nowhere near.

    Note: not every model in GENERATION_MODEL_FALLBACKS is guaranteed multimodal — a
    text-only fallback will 400 on inlineData and _call_generate_with_fallback will log and
    move to the next candidate, which is correct but can be noisy in logs for this call
    specifically.
    """
    if not _api_key():
        logger.warning("GEMINI_API_KEY not configured")
        return None

    generation_config: dict = {'temperature': temperature}
    if max_output_tokens:
        generation_config['maxOutputTokens'] = max_output_tokens
    if thinking_budget is not None:
        generation_config['thinkingConfig'] = {'thinkingBudget': thinking_budget}

    payload: dict = {
        'contents': [{'parts': [
            {'inlineData': {'mimeType': mime_type, 'data': base64.b64encode(image_bytes).decode('ascii')}},
            {'text': prompt},
        ]}],
        'generationConfig': generation_config,
    }
    if system_instruction:
        payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}

    return _call_generate_with_fallback(model, payload, timeout)


def _call_generate_with_fallback(model: str, payload: dict, timeout: int) -> str | None:
    """Tries `model` first, then GENERATION_MODEL_FALLBACKS in order, stopping at the first
    one that returns text. Falls through on *any* failure (quota, model unavailable, etc.) —
    the goal is "something answers", not distinguishing failure modes, so a bad model name in
    the fallback list just gets skipped rather than aborting the chain.

    Fallback attempts strip thinkingConfig/maxOutputTokens from the payload rather than
    reusing it verbatim — confirmed live that gemini-flash-lite-latest 400s on thinkingConfig
    (it doesn't support thinking at all), and reusing a small maxOutputTokens on a model whose
    thinking behavior we don't know risks the exact silent-truncation bug this budget was
    added to prevent in the first place. A fallback answer without the length/thinking tuning
    is far better than a broken one."""
    candidates = [model] + [m for m in GENERATION_MODEL_FALLBACKS if m != model]
    for i, candidate_model in enumerate(candidates):
        candidate_payload = payload
        if i > 0:
            candidate_payload = dict(payload)
            generation_config = dict(payload.get('generationConfig') or {})
            generation_config.pop('thinkingConfig', None)
            generation_config.pop('maxOutputTokens', None)
            candidate_payload['generationConfig'] = generation_config

        text = _call_generate(candidate_model, candidate_payload, timeout)
        if text is not None:
            if i > 0:
                logger.warning(f"Gemini fallback: {model} unavailable, served by {candidate_model} instead")
            return text
    return None


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
        logger.warning(f"Gemini generateContent error on {model}: {e}")
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
