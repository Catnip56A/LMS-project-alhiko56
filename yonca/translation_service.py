"""
Runtime translation service — requires Flask app context and database.

Handles caching of translations in the Translation table.
For the underlying translation logic (no Flask/DB), see core_translator.py.
"""
import os
import re

from flask import current_app

from yonca import core_translator
from yonca.models import Translation, db


class TranslationService:
    """Translates and permanently caches content in the Translation DB table."""

    SUPPORTED_LANGUAGES = ['az', 'ru', 'en']

    def get_translation(self, text: str, target_language: str, source_language: str = None) -> str:
        """Return translation of text into target_language, using DB cache.

        On a cache miss, translates to all supported languages at once and
        persists the results so future requests are instant.
        """
        if os.getenv('DISABLE_TRANSLATIONS', '').lower() in ('true', '1', 'yes'):
            return text
        if not text or len(text.strip()) < 2:
            return text

        detected_source = core_translator.detect_language(text)
        if detected_source == target_language:
            return text

        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
        ).first()
        if cached:
            return cached.translated_text

        self._translate_and_cache_all(text, detected_source)

        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
        ).first()
        return cached.translated_text if cached else text

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
            except Exception as exc:
                db.session.rollback()
                current_app.logger.error(f"Failed to cache translation: {exc}")

    def translate_html(self, html_content: str, target_language: str, source_language: str = 'auto') -> str:
        """Translate HTML content while preserving tag structure."""
        if not html_content or not html_content.strip():
            return html_content

        tags: list[str] = []

        def protect_tag(match):
            tags.append(match.group(0))
            return f"{{TAG_{len(tags) - 1}}}"

        protected = re.sub(r'<[^>]+>', protect_tag, html_content)
        translated = self.get_translation(protected, target_language, source_language) if protected.strip() else protected

        for i, tag in enumerate(tags):
            translated = translated.replace(f"{{TAG_{i}}}", tag)

        return translated

    def get_supported_languages(self) -> dict:
        return {'en': 'English', 'ru': 'Russian', 'az': 'Azerbaijani'}


# Global singleton used throughout the application
translation_service = TranslationService()
