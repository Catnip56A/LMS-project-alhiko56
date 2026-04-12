"""
Standalone translation core — no Flask, no database.

Both the runtime TranslationService (yonca/translation_service.py) and the
dev-time PO translation script (scripts/translations/auto_translate_po.py)
use this module. It can be imported without a Flask app context.

Translation backend: LibreTranslate (self-hosted, configured via
LIBRETRANSLATE_URL env var or passed explicitly to translate_text).
"""
import os
import re

import requests

try:
    from langdetect import detect, LangDetectException
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    LangDetectException = Exception

SUPPORTED_LANGUAGES = ['en', 'az', 'ru']

# Terms that must survive translation unchanged
PROTECTED_TERMS = ['Yonca', 'YONCA', 'yonca']


# ── Term protection ────────────────────────────────────────────────────────────

def protect_terms(text: str) -> tuple[str, dict]:
    """Replace protected terms with placeholders before translation.

    Returns (protected_text, replacements) where replacements maps
    each placeholder back to the original token.
    """
    replacements: dict[str, str] = {}
    protected = text
    for i, term in enumerate(PROTECTED_TERMS):
        placeholder = f"{{PROTECTED_{i}}}"
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(protected):
            original = match.group()
            if placeholder not in replacements:
                replacements[placeholder] = original
                protected = protected.replace(original, placeholder, 1)
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

def translate_text(
    text: str,
    target_lang: str,
    *,
    libretranslate_url: str | None = None,
    libretranslate_api_key: str = '',
) -> str:
    """Translate text to target_lang via LibreTranslate.

    Falls back to returning the original text if the request fails —
    never returns garbage.

    The LibreTranslate URL is resolved in this order:
      1. libretranslate_url argument
      2. LIBRETRANSLATE_URL environment variable
      3. No URL → return original text unchanged

    Protected terms (PROTECTED_TERMS) are preserved through translation.

    Args:
        text: Source text to translate.
        target_lang: ISO 639-1 target language code (e.g. 'az', 'ru').
        libretranslate_url: Base URL of a LibreTranslate instance.
        libretranslate_api_key: Optional API key for the instance.

    Returns:
        Translated string, or the original string on failure.
    """
    if not text or len(text.strip()) < 2:
        return text

    url = libretranslate_url or os.environ.get('LIBRETRANSLATE_URL') or ''
    if not url:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"LIBRETRANSLATE_URL not configured - cannot translate '{text[:60]}' to {target_lang}")
        return text

    protected, replacements = protect_terms(text)

    try:
        payload: dict = {
            'q': protected,
            'source': 'auto',
            'target': target_lang,
            'format': 'text',
        }
        if libretranslate_api_key:
            payload['api_key'] = libretranslate_api_key

        resp = requests.post(
            f"{url.rstrip('/')}/translate",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get('translatedText')
        if not result:
            return text
        return restore_terms(result, replacements)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"LibreTranslate error translating to {target_lang}: {e} (URL: {url})")
        return text
