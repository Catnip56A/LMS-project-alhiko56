"""Speech-to-text with segment/word timestamps.

No Flask or DB dependency (mirrors `core_translator.py`'s role) so dev scripts and the
RQ worker can both use it directly.

Engine is faster-whisper (CTranslate2). Chosen over Gemini for this job because it emits
native timestamps and has no per-day quota — see the Phase 6 addendum in
`Docs/rework docs/development_checklist.md` for the full comparison. PyAV bundles the
FFmpeg libraries, so no system ffmpeg install is required for transcription.
"""
import logging
import os
import threading

logger = logging.getLogger(__name__)

# `small` balances accuracy on lecture speech against CPU time; int8 keeps CPU inference
# viable without a GPU. Both overridable via env.
DEFAULT_MODEL_SIZE = os.environ.get('WHISPER_MODEL_SIZE', 'small')
DEFAULT_COMPUTE_TYPE = os.environ.get('WHISPER_COMPUTE_TYPE', 'int8')
# Deliberately a runtime download into a mounted volume, not baked into the image —
# models run 75MB-3GB and the image ships through GHCR on every deploy.
# Defaults to a repo-relative path so `just dev` (which runs outside Docker) works; the
# compose files override it to the container path, mirroring CERT_TEMPLATE_DIR's pattern.
MODEL_CACHE_DIR = os.environ.get(
    'WHISPER_CACHE_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'whisper-models'),
)

# The loaded model holds ~1.5GB resident (small/int8). Keeping it warm only pays off under
# continuous transcription; here videos arrive occasionally, so the default is to release it
# after each job — reloading from the local volume costs ~5-15s against a job that runs for
# minutes. Set WHISPER_KEEP_MODEL_LOADED=1 on a RAM-rich host to keep it warm instead.
KEEP_MODEL_LOADED = os.environ.get('WHISPER_KEEP_MODEL_LOADED', '0').lower() in ('1', 'true', 'yes')

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Load the model once per process. First call downloads it into MODEL_CACHE_DIR."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
        logger.info(
            f"Loading Whisper model '{DEFAULT_MODEL_SIZE}' ({DEFAULT_COMPUTE_TYPE}) "
            f"from {MODEL_CACHE_DIR} — first run downloads it"
        )
        _model = WhisperModel(
            DEFAULT_MODEL_SIZE,
            device='cpu',
            compute_type=DEFAULT_COMPUTE_TYPE,
            download_root=MODEL_CACHE_DIR,
        )
        logger.info(f"Whisper model '{DEFAULT_MODEL_SIZE}' ready")
    return _model


def unload_model() -> None:
    """Release the loaded model and its ~1.5GB of resident memory."""
    global _model
    with _model_lock:
        if _model is not None:
            _model = None
            import gc
            gc.collect()
            logger.info('Whisper model unloaded')


def transcribe_with_timestamps(file_path: str, language: str | None = None) -> list[dict] | None:
    """Transcribe an audio/video file into timestamped segments.

    Returns a list of {'start': float_seconds, 'end': float_seconds, 'text': str},
    or None if transcription failed. Only the audio stream is decoded — video frames
    are never touched.
    """
    try:
        model = _get_model()
        segments, info = model.transcribe(
            file_path,
            language=language,
            vad_filter=True,          # drops silence, cuts CPU time and stray hallucinations
            beam_size=5,
        )
        # `segments` is a generator — consuming it is what actually runs inference.
        result = [
            {'start': float(s.start), 'end': float(s.end), 'text': s.text.strip()}
            for s in segments
            if s.text and s.text.strip()
        ]
        logger.info(
            f"Transcribed {file_path}: {len(result)} segments, "
            f"detected language={getattr(info, 'language', '?')}"
        )
        return result
    except Exception as e:
        logger.error(f"Whisper transcription failed for {file_path}: {e}")
        return None
    finally:
        if not KEEP_MODEL_LOADED:
            unload_model()


def segments_to_text(segments: list[dict]) -> str:
    """Flatten timestamped segments into a plain transcript string."""
    return ' '.join(s['text'] for s in segments if s.get('text'))
