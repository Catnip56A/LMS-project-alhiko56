"""
Standalone translation core — no Flask, no database.

Both the runtime TranslationService (lms/translation_service.py) and the
dev-time PO translation script (scripts/translations/auto_translate_po.py)
use this module. It can be imported without a Flask app context.

Translation backend: DeepL (https://www.deepl.com/pro-api), configured via
the DEEPL_API_KEY env var or passed explicitly to translate_text/translate_batch.
"""
import logging
import os
import re

import requests

try:
    from langdetect import detect, LangDetectException
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    LangDetectException = Exception

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ['en', 'ru']

# DeepL requires a regional variant for English as a *target* language (plain 'EN' is
# rejected) — source_lang doesn't need one, so this mapping is target-only.
_DEEPL_TARGET_CODES = {
    'en': 'EN-US',
    'ru': 'RU',
}

# Terms that must survive translation unchanged.
# Each entry is (pattern_to_match, placeholder, canonical_form).
# All-caps placeholder with no underscores/digits — translation engines treat
# these as opaque constants and leave them alone.
_PROTECTED_TERMS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r'\bLMS\b', re.IGNORECASE), '{LMS}', 'LMS'),
    (re.compile(r'Moxo', re.IGNORECASE), '{MOXO}', 'MOXO'),
]


# ── Term protection ────────────────────────────────────────────────────────────

def protect_terms(text: str) -> tuple[str, dict]:
    """Replace protected terms with placeholders before translation.

    Returns (protected_text, replacements) where replacements maps
    each placeholder back to its canonical form.
    """
    replacements: dict[str, str] = {}
    protected = text
    for pattern, placeholder, canonical in _PROTECTED_TERMS:
        if pattern.search(protected):
            replacements[placeholder] = canonical
            protected = pattern.sub(placeholder, protected)
    return protected, replacements


def restore_terms(text: str, replacements: dict) -> str:
    """Restore protected terms from placeholders after translation."""
    for placeholder, original in replacements.items():
        text = text.replace(placeholder, original)
    return text


# ── Language detection ─────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Detect the language of text. Returns an ISO 639-1 code, defaults to 'en'."""
    if not _LANGDETECT_AVAILABLE or not text or len(text.strip()) < 10:
        return 'en'
    try:
        detected = detect(text)
        return detected if detected in SUPPORTED_LANGUAGES else 'en'
    except Exception:
        return 'en'


# ── Translation ────────────────────────────────────────────────────────────────

def _deepl_endpoint(api_key: str) -> str:
    """Free-plan DeepL keys always end in ':fx' and must hit the api-free host —
    pointing one at api.deepl.com (or vice versa) fails auth entirely."""
    return 'https://api-free.deepl.com/v2/translate' if api_key.endswith(':fx') else 'https://api.deepl.com/v2/translate'


def translate_text(
    text: str,
    target_lang: str,
    *,
    deepl_api_key: str | None = None,
) -> str:
    """Translate text to target_lang via DeepL.

    Falls back to returning the original text if the request fails —
    never returns garbage.

    The DeepL API key is resolved in this order:
      1. deepl_api_key argument
      2. DEEPL_API_KEY environment variable
      3. No key → return original text unchanged

    Protected terms (_PROTECTED_TERMS) are preserved through translation.
    Source language is left to DeepL's auto-detection rather than passed
    explicitly, matching this module's prior 'auto' behavior.

    Args:
        text: Source text to translate.
        target_lang: ISO 639-1 target language code (e.g. 'ru').
        deepl_api_key: DeepL API key (free or pro plan).

    Returns:
        Translated string, or the original string on failure.
    """
    if not text or len(text.strip()) < 2:
        return text

    api_key = deepl_api_key or os.environ.get('DEEPL_API_KEY') or ''
    if not api_key:
        logger.warning(f"DEEPL_API_KEY not configured - cannot translate '{text[:60]}' to {target_lang}")
        return text

    deepl_target = _DEEPL_TARGET_CODES.get(target_lang, target_lang.upper())
    protected, replacements = protect_terms(text)

    try:
        resp = requests.post(
            _deepl_endpoint(api_key),
            headers={'Authorization': f'DeepL-Auth-Key {api_key}'},
            data={'text': protected, 'target_lang': deepl_target},
            timeout=10,
        )
        resp.raise_for_status()
        translations = resp.json().get('translations') or []
        if not translations:
            return text
        result = translations[0].get('text')
        if not result:
            return text
        return restore_terms(result, replacements)

    except Exception as e:
        logger.error(f"DeepL error translating to {target_lang}: {e}")
        return text


def translate_batch(
    texts: list[str],
    target_lang: str,
    *,
    deepl_api_key: str | None = None,
    chunk_size: int = 50,
) -> list[str]:
    """Translate a list of texts to target_lang via DeepL.

    Sends up to chunk_size strings per request. Returns a list of the same
    length as texts; falls back to the original string on any failure.
    """
    if not texts:
        return []

    api_key = deepl_api_key or os.environ.get('DEEPL_API_KEY') or ''
    if not api_key:
        logger.warning("DEEPL_API_KEY not configured — returning originals unchanged")
        return list(texts)

    deepl_target = _DEEPL_TARGET_CODES.get(target_lang, target_lang.upper())
    results: list[str] = []

    for start in range(0, len(texts), chunk_size):
        chunk = texts[start : start + chunk_size]
        protected_chunk: list[str] = []
        replacement_maps: list[dict] = []

        for text in chunk:
            if not text or len(text.strip()) < 2:
                protected_chunk.append(text)
                replacement_maps.append({})
            else:
                protected, replacements = protect_terms(text)
                protected_chunk.append(protected)
                replacement_maps.append(replacements)

        try:
            # DeepL takes repeated `text` form fields for a batch request.
            payload = [('text', t) for t in protected_chunk]
            payload.append(('target_lang', deepl_target))

            resp = requests.post(
                _deepl_endpoint(api_key),
                headers={'Authorization': f'DeepL-Auth-Key {api_key}'},
                data=payload,
                timeout=60,
            )
            resp.raise_for_status()
            translations = resp.json().get('translations') or []

            for orig, trans, repl in zip(chunk, translations, replacement_maps):
                translated_text = trans.get('text') if trans else None
                results.append(restore_terms(translated_text, repl) if translated_text else orig)

        except Exception as e:
            logger.error(f"DeepL batch error ({len(chunk)} texts → {target_lang}): {e}")
            results.extend(chunk)

    return results
