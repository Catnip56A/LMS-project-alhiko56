"""
AI Translation service for real-time content translation with protected terms
"""
import hashlib
import os
import re
import requests
import signal
import platform
import threading
from yonca.models import Translation, db
from flask import current_app

try:
    from deep_translator import GoogleTranslator
    DEEP_TRANS_AVAILABLE = True
except ImportError:
    DEEP_TRANS_AVAILABLE = False
    print("Warning: deep-translator not available, using LibreTranslate only")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("Warning: beautifulsoup4 not available, HTML translation will be limited")

try:
    from langdetect import LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    LangDetectException = Exception  # Fallback to catch all exceptions

# Protected terms that should never be translated
PROTECTED_TERMS = [
    'Yonca',
    'YONCA',
    'yonca'
]

class TranslationService:
    """Service for handling AI-powered translations with caching and protected terms"""

    # Supported languages for automatic translation
    SUPPORTED_LANGUAGES = ['az', 'ru', 'en']

    def __init__(self):
        if DEEP_TRANS_AVAILABLE:
            print("Deep Translator available")
        else:
            print("Using LibreTranslate only")
        
        if BS4_AVAILABLE:
            print("BeautifulSoup available for HTML translation")
        else:
            print("BeautifulSoup not available - HTML translation limited")
        
        if LANGDETECT_AVAILABLE:
            print("Langdetect available for language detection")
        else:
            print("Langdetect not available - defaulting to English")
            
        self.protected_terms = PROTECTED_TERMS
    
    def _detect_source_language(self, text):
        """
        Detect the source language of the text.
        Returns language code or 'en' as default.
        """
        if not LANGDETECT_AVAILABLE:
            return 'en'
        try:
            from langdetect import detect
            if not text or len(text.strip()) < 10:
                return 'en'
            detected = detect(text)
            # Map to supported languages
            lang_map = {
                'az': 'az',
                'ru': 'ru', 
                'en': 'en'
            }
            return lang_map.get(detected, 'en')
        except LangDetectException:
            return 'en'
        except Exception:
            return 'en'
    
    def _protect_terms(self, text):
        """
        Replace protected terms with placeholders before translation.
        Returns tuple of (protected_text, replacements_dict)
        """
        replacements = {}
        protected_text = text
        
        for i, term in enumerate(self.protected_terms):
            placeholder = f"{{PROTECTED_{i}}}"
            # Case-insensitive replacement that preserves original case
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            matches = pattern.finditer(protected_text)
            
            for match in matches:
                original_term = match.group()
                if placeholder not in replacements:
                    replacements[placeholder] = original_term
                    protected_text = protected_text.replace(original_term, placeholder, 1)
        
        return protected_text, replacements
    
    def _restore_terms(self, text, replacements):
        """Restore protected terms from placeholders after translation."""
        restored_text = text
        for placeholder, original_term in replacements.items():
            restored_text = restored_text.replace(placeholder, original_term)
        return restored_text

    def _translate_with_libretranslate(self, text, source_language, target_language):
        """
        Translate text using LibreTranslate API.

        Args:
            text (str): Text to translate
            source_language (str): Source language code or 'auto'
            target_language (str): Target language code

        Returns:
            str: Translated text or original text if translation fails
        """
        # Detect environment via ENV variable
        env = os.getenv('ENV', 'local')  # Default to local if not set

        # Set the LibreTranslate endpoint based on environment
        if env == 'local':
            url = 'http://127.0.0.1:5000/translate'
        elif env == 'server':
            url = 'http://127.0.0.1:5001/translate'
        else:
            # Fallback to local if unknown env
            url = 'http://127.0.0.1:5000/translate'

        # Prepare the payload
        payload = {
            'q': text,
            'source': source_language,
            'target': target_language,
            'format': 'text'
        }

        try:
            # Send POST request to LibreTranslate API with shorter timeout
            response = requests.post(url, json=payload, timeout=5)  # Reduced from 10 to 5 seconds
            response.raise_for_status()  # Raise exception for bad status codes

            # Parse the response
            data = response.json()
            translated_text = data.get('translatedText', text)

            return translated_text

        except requests.exceptions.Timeout:
            current_app.logger.error("LibreTranslate request timed out after 5 seconds")
            raise Exception("LibreTranslate timeout")
        except requests.exceptions.RequestException as e:
            # Log the error
            current_app.logger.error(f"LibreTranslate request failed: {str(e)}")
            raise e
        except Exception as e:
            # Catch any other errors
            current_app.logger.error(f"LibreTranslate translation error: {str(e)}")
            raise e

    def translate_with_libretranslate(text, source_language, target_language):
        """
        Standalone function to translate text using LibreTranslate API.
        This function can be used independently of the TranslationService class.

        Args:
            text (str): Text to translate
            source_language (str): Source language code or 'auto'
            target_language (str): Target language code

        Returns:
            str: Translated text or original text if translation fails
        """
        import os
        import requests

        # Detect environment via ENV variable
        env = os.getenv('ENV', 'local')  # Default to local if not set

        # Set the LibreTranslate endpoint based on environment
        if env == 'local':
            url = 'http://127.0.0.1:5000/translate'
        elif env == 'server':
            url = 'http://127.0.0.1:5001/translate'
        else:
            # Fallback to local if unknown env
            url = 'http://127.0.0.1:5000/translate'

        # Prepare the payload
        payload = {
            'q': text,
            'source': source_language,
            'target': target_language,
            'format': 'text'
        }

        try:
            # Send POST request to LibreTranslate API
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes

            # Parse the response
            data = response.json()
            translated_text = data.get('translatedText', text)

            return translated_text

        except requests.exceptions.RequestException as e:
            # Log the error (if logger available, otherwise print)
            print(f"LibreTranslate request failed: {str(e)}")
            # Return original text if translation fails
            return text
        except Exception as e:
            # Catch any other errors
            print(f"LibreTranslate translation error: {str(e)}")
            return text

    def get_translation(self, text, target_language, source_language=None):
        """
        Get translation for text, using cache if available.
        Protects specified terms from translation.
        Detects source language automatically and pre-translates to all supported languages.

        Args:
            text (str): Text to translate
            target_language (str): Target language code (e.g., 'az', 'ru')
            source_language (str): Ignored - always detects automatically

        Returns:
            str: Translated text or original text if translation fails/disabled
        """
        # Check if translations are disabled via environment variable
        if os.getenv('DISABLE_TRANSLATIONS', '').lower() in ('true', '1', 'yes'):
            current_app.logger.info("Translations disabled via DISABLE_TRANSLATIONS environment variable")
            return text
            
        # Skip translation if text is too short
        if not text or len(text.strip()) < 2:
            return text
            
        # Skip translation if source and target languages are the same
        if source_language and source_language == target_language:
            return text
            
        # Detect the actual source language
        detected_source = self._detect_source_language(text)
        source_language = 'auto'  # Keep 'auto' for translation services
        
        # Skip if detected source is the same as target
        if detected_source == target_language:
            return text

        # Check cache first for the requested translation
        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
            source_language=source_language
        ).first()

        if cached:
            current_app.logger.debug(f"Translation cache hit for: {text[:50]}...")
            return cached.translated_text

        # If not cached, translate to all supported languages
        self._translate_to_all_languages(text, detected_source)
        
        # Now check cache again for the requested translation
        cached = Translation.query.filter_by(
            source_text=text,
            target_language=target_language,
            source_language=source_language
        ).first()

        if cached:
            return cached.translated_text
        
        # If still not found, return original text
        current_app.logger.warning(f"Translation failed for {detected_source} -> {target_language}")
        return text
    
    def _translate_to_all_languages(self, text, detected_source):
        """
        Translate text to all supported languages and cache the results.
        This is called when a translation is requested but not cached.
        """
        # Protect terms before translation
        protected_text, replacements = self._protect_terms(text)
        
        for target_lang in self.SUPPORTED_LANGUAGES:
            if target_lang == detected_source:
                continue
                
            # Check if already cached
            existing = Translation.query.filter_by(
                source_text=text,
                target_language=target_lang,
                source_language='auto'
            ).first()
            
            if existing:
                continue
                
            try:
                translated_text = None
                service_used = None
                
                # Use GoogleTranslator if available
                if DEEP_TRANS_AVAILABLE:
                    try:
                        flask_env = os.getenv('FLASK_ENV', 'development')
                        timeout_seconds = 10 if flask_env == 'production' else 30
                        
                        result = [None]
                        exception = [None]
                        
                        def translate_with_timeout():
                            try:
                                result[0] = GoogleTranslator(source='auto', target=target_lang).translate(protected_text)
                            except Exception as e:
                                exception[0] = e
                        
                        translate_thread = threading.Thread(target=translate_with_timeout)
                        translate_thread.daemon = True
                        translate_thread.start()
                        translate_thread.join(timeout_seconds)
                        
                        if not translate_thread.is_alive() and not exception[0]:
                            translated_text = result[0]
                            service_used = 'deep_translator'
                            
                    except Exception as e:
                        pass
                        
                # Fallback to LibreTranslate if needed
                if translated_text is None:
                    env = os.getenv('ENV', 'local')
                    flask_env = os.getenv('FLASK_ENV', 'development')
                    
                    if env in ['local', 'server'] and flask_env != 'production':
                        try:
                            translated_text = self._translate_with_libretranslate(protected_text, 'auto', target_lang)
                            service_used = 'libretranslate'
                        except Exception as e:
                            pass
                
                # Use mock translation as final fallback
                if translated_text is None:
                    try:
                        translated_text = self._mock_translate(protected_text, target_lang)
                        service_used = 'mock'
                    except Exception as e:
                        continue
                
                # Restore protected terms
                translated_text = self._restore_terms(translated_text, replacements)
                
                # Cache the translation
                if service_used != 'mock':
                    try:
                        new_translation = Translation(
                            source_text=text,
                            source_language='auto',
                            target_language=target_lang,
                            translated_text=translated_text,
                            translation_service=service_used
                        )
                        db.session.add(new_translation)
                        db.session.commit()
                        current_app.logger.debug(f"Pre-translated and cached: {text[:30]}... -> {target_lang}")
                    except Exception as e:
                        current_app.logger.error(f"Failed to cache pre-translation: {str(e)}")
                        
            except Exception as e:
                current_app.logger.error(f"Failed to pre-translate to {target_lang}: {str(e)}")
                continue

    def translate_html(self, html_content, target_language, source_language='auto'):
        """
        Translate HTML content while preserving HTML structure.
        
        Args:
            html_content (str): HTML content to translate
            target_language (str): Target language code
            source_language (str): Source language code (default: auto-detect)
            
        Returns:
            str: Translated HTML content
        """
        if not html_content or not html_content.strip():
            return html_content
        
        try:
            # Use a placeholder approach: protect HTML tags, translate content, then restore tags
            import re as re_module
            
            # Step 1: Find all HTML tags and replace with placeholders
            tags = []
            def protect_tags(match):
                tag = match.group(0)
                placeholder = f"{{TAG_{len(tags)}}}"
                tags.append(tag)
                return placeholder
            
            # Protect all HTML tags (both opening and closing, including self-closing)
            protected_content = re_module.sub(r'<[^>]+>', protect_tags, html_content)
            
            current_app.logger.warning(f"HTML TRANSLATION - After tag protection: {protected_content[:100]}")
            current_app.logger.warning(f"HTML TRANSLATION - Extracted {len(tags)} tags")
            
            # Step 2: Translate the content without tags
            if protected_content.strip():
                translated_content = self.get_translation(protected_content, target_language, source_language)
                current_app.logger.warning(f"HTML TRANSLATION - After translation: {translated_content[:100]}")
            else:
                translated_content = protected_content
            
            # Step 3: Restore the HTML tags
            for i, tag in enumerate(tags):
                placeholder = f"{{TAG_{i}}}"
                translated_content = translated_content.replace(placeholder, tag)
            
            current_app.logger.warning(f"HTML TRANSLATION - After tag restoration: {translated_content[:100]}")
            
            return translated_content
            
        except Exception as e:
            current_app.logger.error(f"HTML translation failed: {str(e)}")
            # Fall back to plain text translation
            return self.get_translation(html_content, target_language, source_language)

    def extract_text_from_html(self, html_content):
        """
        Extract plain text from HTML content.
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: Plain text extracted from HTML
        """
        if not html_content:
            return ""
            
        if BS4_AVAILABLE:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                # Extract text while preserving some structure
                return soup.get_text(separator=' ', strip=True)
            except Exception as e:
                current_app.logger.warning(f"Failed to parse HTML: {str(e)}")
        
        # Fallback: simple regex-based text extraction
        import re
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        import html
        text = html.unescape(text)
        return text.strip()

    def _mock_translate(self, text, target_language):
        """Mock translation for development"""
        # Simple mock translations for common phrases
        mock_translations = {
            'en': {
                'es': {
                    'Hello': 'Hola',
                    'Welcome': 'Bienvenido',
                    'Thank you': 'Gracias',
                    'Please': 'Por favor',
                    'Yes': 'Sí',
                    'No': 'No',
                    'Good morning': 'Buenos días',
                    'Good evening': 'Buenas noches',
                    'How are you?': '¿Cómo estás?',
                    'I am fine': 'Estoy bien',
                    'What is your name?': '¿Cuál es tu nombre?',
                    'My name is': 'Mi nombre es',
                    'I need help': 'Necesito ayuda',
                    'Can you help me?': '¿Puedes ayudarme?',
                    'I understand': 'Entiendo',
                    'I do not understand': 'No entiendo',
                    'Please speak slowly': 'Por favor habla despacio',
                    'Where is...?': '¿Dónde está...?',
                    'How much does it cost?': '¿Cuánto cuesta?',
                    'I would like...': 'Me gustaría...',
                    'Do you speak English?': '¿Hablas inglés?',
                    'I speak a little Spanish': 'Hablo un poco de español'
                },
                'fr': {
                    'Hello': 'Bonjour',
                    'Welcome': 'Bienvenue',
                    'Thank you': 'Merci',
                    'Please': 'S\'il vous plaît',
                    'Yes': 'Oui',
                    'No': 'Non',
                    'Good morning': 'Bonjour',
                    'Good evening': 'Bonsoir',
                    'How are you?': 'Comment allez-vous?',
                    'I am fine': 'Je vais bien',
                    'What is your name?': 'Quel est votre nom?',
                    'My name is': 'Je m\'appelle',
                    'I need help': 'J\'ai besoin d\'aide',
                    'Can you help me?': 'Pouvez-vous m\'aider?',
                    'I understand': 'Je comprends',
                    'I do not understand': 'Je ne comprends pas',
                    'Please speak slowly': 'Parlez lentement s\'il vous plaît',
                    'Where is...?': 'Où est...?',
                    'How much does it cost?': 'Combien ça coûte?',
                    'I would like...': 'Je voudrais...',
                    'Do you speak English?': 'Parlez-vous anglais?',
                    'I speak a little French': 'Je parle un peu français'
                },
                'de': {
                    'Hello': 'Hallo',
                    'Welcome': 'Willkommen',
                    'Thank you': 'Danke',
                    'Please': 'Bitte',
                    'Yes': 'Ja',
                    'No': 'Nein',
                    'Good morning': 'Guten Morgen',
                    'Good evening': 'Guten Abend',
                    'How are you?': 'Wie geht es Ihnen?',
                    'I am fine': 'Mir geht es gut',
                    'What is your name?': 'Wie heißen Sie?',
                    'My name is': 'Ich heiße',
                    'I need help': 'Ich brauche Hilfe',
                    'Can you help me?': 'Können Sie mir helfen?',
                    'I understand': 'Ich verstehe',
                    'I do not understand': 'Ich verstehe nicht',
                    'Please speak slowly': 'Bitte sprechen Sie langsam',
                    'Where is...?': 'Wo ist...?',
                    'How much does it cost?': 'Wie viel kostet es?',
                    'I would like...': 'Ich möchte...',
                    'Do you speak English?': 'Sprechen Sie Englisch?',
                    'I speak a little German': 'Ich spreche ein bisschen Deutsch'
                },
                'az': {
                    'Hello': 'Salam',
                    'Welcome': 'Xoş gəlmisiniz',
                    'Thank you': 'Təşəkkür edirəm',
                    'Please': 'Zəhmət olmasa',
                    'Yes': 'Bəli',
                    'No': 'Xeyr',
                    'Good morning': 'Sabahınız xeyir',
                    'Good evening': 'Axşamınız xeyir',
                    'How are you?': 'Necəsiniz?',
                    'I am fine': 'Yaxşıyam',
                    'What is your name?': 'Adınız nədir?',
                    'My name is': 'Mənim adım',
                    'I need help': 'Köməyə ehtiyacım var',
                    'Can you help me?': 'Mənə kömək edə bilərsiniz?',
                    'I understand': 'Başadüşürəm',
                    'I do not understand': 'Başadüşmürəm',
                    'Please speak slowly': 'Zəhmət olmasa yavaş danışın',
                    'Where is...?': 'Haradadır...?',
                    'How much does it cost?': 'Neçəyə başa gəlir?',
                    'I would like...': 'İstərdim...',
                    'Do you speak English?': 'İngiliscə danışırsınız?',
                    'I speak a little Azeri': 'Azərbaycanca bir az danışıram'
                },
                'ru': {
                    'Hello': 'Привет',
                    'Welcome': 'Добро пожаловать',
                    'Thank you': 'Спасибо',
                    'Please': 'Пожалуйста',
                    'Yes': 'Да',
                    'No': 'Нет',
                    'Good morning': 'Доброе утро',
                    'Good evening': 'Добрый вечер',
                    'How are you?': 'Как дела?',
                    'I am fine': 'У меня всё хорошо',
                    'What is your name?': 'Как ваше имя?',
                    'My name is': 'Меня зовут',
                    'I need help': 'Мне нужна помощь',
                    'Can you help me?': 'Вы можете мне помочь?',
                    'I understand': 'Я понимаю',
                    'I do not understand': 'Я не понимаю',
                    'Please speak slowly': 'Пожалуйста, говорите медленно',
                    'Where is...?': 'Где...?',
                    'How much does it cost?': 'Сколько это стоит?',
                    'I would like...': 'Я бы хотел...',
                    'Do you speak English?': 'Вы говорите по-английски?',
                    'I speak a little Russian': 'Я говорю немного по-русски'
                }
            }
        }

        # Check if we have a mock translation
        if target_language in mock_translations.get('en', {}):
            lang_translations = mock_translations['en'][target_language]
            for key, value in lang_translations.items():
                if key.lower() in text.lower():
                    return text.replace(key, value)

        # If no mock translation found, add a marker
        return f"[Translated to {target_language}] {text}"

    def get_supported_languages(self):
        """Get list of supported languages"""
        return {
            'en': 'English',
            'ru': 'Russian',
            'az': 'Azerbaijani'
        }

# Global translation service instance
translation_service = TranslationService()