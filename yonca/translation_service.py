"""
Runtime translation service — requires Flask app context and database.

Handles caching of translations in the Translation table.
For the underlying translation logic (no Flask/DB), see core_translator.py.
"""
import os
import re
from functools import lru_cache

from flask import current_app

from yonca import core_translator
from yonca.constants import SUPPORTED_LANGUAGES, LANGUAGE_NAMES
from yonca.models import Translation, db

# In-memory cache for translations to reduce database queries
# Key: (source_text, target_language), Value: translated_text
_TRANSLATION_CACHE = {}
_CACHE_ENABLED = os.getenv('TRANSLATION_CACHE_ENABLED', 'true').lower() in ('true', '1', 'yes')
_CACHE_MAX_SIZE = int(os.getenv('TRANSLATION_CACHE_SIZE', '10000'))


class TranslationService:
    """Translates and permanently caches content in the Translation DB table."""

    SUPPORTED_LANGUAGES = SUPPORTED_LANGUAGES

    def get_translation(self, text: str, target_language: str, source_language: str = None) -> str:
        """Return translation of text into target_language, using DB cache and in-memory cache.

        On a cache miss, translates to all supported languages at once and
        persists the results so future requests are instant.
        """
        if os.getenv('DISABLE_TRANSLATIONS', '').lower() in ('true', '1', 'yes'):
            return text
        if not text or len(text.strip()) < 2:
            return text

        # Check in-memory cache first (fastest)
        cache_key = (text, target_language)
        if _CACHE_ENABLED and cache_key in _TRANSLATION_CACHE:
            return _TRANSLATION_CACHE[cache_key]

        detected_source = core_translator.detect_language(text)
        if detected_source == target_language:
            return text

        # Check database cache
        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
        ).first()
        if cached:
            if _CACHE_ENABLED:
                self._add_to_cache(text, target_language, cached.translated_text)
            return cached.translated_text

        self._translate_and_cache_all(text, detected_source)

        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
        ).first()
        result = cached.translated_text if cached else text
        
        if _CACHE_ENABLED:
            self._add_to_cache(text, target_language, result)
        
        return result

    def _add_to_cache(self, text: str, target_language: str, translated_text: str) -> None:
        """Add translation to in-memory cache with LRU eviction."""
        cache_key = (text, target_language)
        if len(_TRANSLATION_CACHE) >= _CACHE_MAX_SIZE:
            # Remove oldest entry (FIFO - simple approach)
            _TRANSLATION_CACHE.pop(next(iter(_TRANSLATION_CACHE)), None)
        _TRANSLATION_CACHE[cache_key] = translated_text

    def _translate_and_cache_all(self, text: str, detected_source: str) -> None:
        """Translate text to every supported language and persist to DB."""
        libre_url = os.environ.get('LIBRETRANSLATE_URL') or None

        for target_lang in self.SUPPORTED_LANGUAGES:
            if target_lang == detected_source:
                continue

            already_cached = Translation.query.filter_by(
                source_text=text,
                target_language=target_lang,
            ).first()
            if already_cached:
                if _CACHE_ENABLED:
                    self._add_to_cache(text, target_lang, already_cached.translated_text)
                continue

            translated = core_translator.translate_text(
                text,
                target_lang,
                libretranslate_url=libre_url,
            )

            if translated == text:
                # Both backends failed — do not cache the untranslated original
                current_app.logger.warning(
                    f"Translation failed: {text[:60]!r} -> {target_lang}"
                )
                continue

            try:
                db.session.add(Translation(
                    source_text=text,
                    source_language=detected_source,
                    target_language=target_lang,
                    translated_text=translated,
                    translation_service='libretranslate',
                ))
                db.session.commit()
                
                if _CACHE_ENABLED:
                    self._add_to_cache(text, target_lang, translated)
            except Exception as exc:
                db.session.rollback()
                current_app.logger.error(f"Failed to cache translation: {exc}")

    def translate_html(self, html_content: str, target_language: str, source_language: str = 'auto') -> str:
        """Translate HTML content while preserving tag structure.
        
        Extracts text content only, translates it, and reconstructs HTML with translated text.
        This ensures the final stored translation contains proper HTML tags, not placeholders.
        """
        if not html_content or not html_content.strip():
            return html_content

        # Extract all tags and store them with their positions
        tags: dict[str, str] = {}
        tag_counter = [0]
        
        def replace_tag(match):
            # Use a placeholder format that's extremely unlikely to be modified by translation APIs
            # XLT = eXtract Language Tag (less likely to be translated than common English words)
            placeholder = f"XLT{tag_counter[0]}XLT"
            tags[placeholder] = match.group(0)
            tag_counter[0] += 1
            return placeholder

        # Replace all tags with unique placeholders
        protected = re.sub(r'<[^>]+>', replace_tag, html_content)
        
        # Translate the protected content (text + placeholders)
        if protected.strip():
            from yonca import core_translator
            import os
            
            # Use core_translator directly to avoid caching the placeholder version
            libre_url = os.environ.get('LIBRETRANSLATE_URL')
            detected_source = core_translator.detect_language(protected)
            
            if detected_source == target_language:
                translated_protected = protected
            else:
                translated_protected = core_translator.translate_text(
                    protected, 
                    target_language,
                    libretranslate_url=libre_url
                )
        else:
            translated_protected = protected

        # Restore tags in the translated content
        result = translated_protected
        for placeholder, tag in tags.items():
            # Try exact match first (most common case)
            if placeholder in result:
                result = result.replace(placeholder, tag)
            else:
                # Fallback: try matching with potential spacing variations
                # XLT0XLT → XLT 0 XLT → X L T 0 X L T (all variations)
                import re as regex_module
                tag_num = placeholder.replace("XLT", "")
                
                # Match with any amount of space or no space between parts
                # This handles: XLT0XLT, XLT 0 XLT, X L T 0 X L T, etc.
                pattern = f"X\\s*L\\s*T\\s*{tag_num}\\s*X\\s*L\\s*T"
                result = regex_module.sub(pattern, tag, result, flags=regex_module.IGNORECASE)
        
        return result

    def get_supported_languages(self) -> dict:
        return LANGUAGE_NAMES

    @classmethod
    def clear_cache(cls):
        """Clear the in-memory translation cache."""
        global _TRANSLATION_CACHE
        _TRANSLATION_CACHE = {}


# Global singleton used throughout the application
translation_service = TranslationService()
