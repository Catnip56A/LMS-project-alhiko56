"""
Content translation helper for automatic translation of dynamic content
"""
import re
from lms.models import ContentTranslation, db
from lms.translation_service import translation_service

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("Warning: langdetect not available. Install with: pip install langdetect")

# Import centralized language constants

# Languages to automatically translate to
TARGET_LANGUAGES = ['az', 'ru']

# Fields to translate for each content type
TRANSLATABLE_FIELDS = {
    'course': ['title', 'description', 'tags'],
    'resource': ['title', 'description'],
}


def detect_language(text):
    """
    Detect the language of the given text.
    Returns language code or 'en' as default.
    """
    if not LANGDETECT_AVAILABLE:
        return 'en'  # Default to English if langdetect not available
    
    if not text or len(text.strip()) < 10:
        return 'en'  # Default to English for very short text
    
    try:
        detected = detect(text)
        # Map common language codes
        lang_map = {
            'ru': 'ru',  # Russian
            'en': 'en',  # English
        }
        return lang_map.get(detected, detected)
    except (LangDetectException, Exception):
        return 'en'  # Default to English if detection fails

def translate_content(content_type, content_id, field_name, text, source_language=None, session=None):
    """
    Translate a piece of content into all target languages and store in database.
    Auto-detects source language if not provided.
    Returns the number of languages successfully translated.

    Args:
        content_type: Type of content ('course', 'resource', etc.)
        content_id: ID of the content item
        field_name: Name of the field being translated
        text: Text to translate
        source_language: Source language code (if None, auto-detects)
        session: SQLAlchemy session to use (if None, uses db.session)
    """
    if not text or not text.strip():
        return 0

    # Auto-detect source language if not provided
    if source_language is None:
        source_language = detect_language(text)
        print(f"   Detected language: {source_language} for {content_type}:{content_id}.{field_name}")

    # Use provided session or fall back to db.session
    if session is None:
        session = db.session

    # Determine which languages to translate to
    # Include English if source is not English
    target_langs = TARGET_LANGUAGES.copy()
    if source_language != 'en' and 'en' not in target_langs:
        target_langs.append('en')

    saved = 0
    for target_lang in target_langs:
        if target_lang == source_language:
            continue

        try:
            # Check if content contains HTML (both actual tags and entities)
            is_html = bool(re.search(r'<[^>]+>|&lt;|&gt;|&amp;', text))

            if is_html:
                translated = translation_service.translate_html(text, target_lang, source_language)
                print(f"   Translated HTML content for {content_type}:{content_id}.{field_name} -> {target_lang}")
            else:
                translated = translation_service.get_translation(text, target_lang, source_language)

            # Skip if translation is empty or unchanged (LibreTranslate unavailable)
            if not translated or translated == text:
                print(f"Warning: Translation unchanged/failed for {content_type}:{content_id}.{field_name} -> {target_lang}")
                continue

            # Check if translation already exists
            existing = session.query(ContentTranslation).filter_by(
                content_type=content_type,
                content_id=content_id,
                field_name=field_name,
                target_language=target_lang
            ).first()

            if existing:
                existing.translated_text = translated
                existing.source_language = source_language
            else:
                new_translation = ContentTranslation(
                    content_type=content_type,
                    content_id=content_id,
                    field_name=field_name,
                    source_language=source_language,
                    target_language=target_lang,
                    translated_text=translated
                )
                session.add(new_translation)

            saved += 1
            print(f"✓ Translated {content_type}:{content_id}.{field_name} -> {target_lang}")

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error translating {content_type}:{content_id}.{field_name} -> {target_lang}: {e}")
            print(f"ERROR: Translation failed for {content_type}:{content_id}.{field_name} -> {target_lang}: {e}")

    # Flush translations to database
    try:
        session.flush()
    except Exception as e:
        print(f"Error flushing translations: {e}")

    return saved


def translate_json_array(content_type, content_id, field_name, json_array, text_field='description', source_language=None, session=None):
    """
    Translate text fields within a JSON array (e.g., features list, gallery captions).
    Auto-detects source language from first item if not provided.
    
    Args:
        content_type: Type of content
        content_id: ID of the content item
        field_name: Name of the JSON field
        json_array: List of dictionaries containing text to translate
        text_field: Which field within each dict to translate (default 'description')
        source_language: Source language code (if None, auto-detects)
        session: SQLAlchemy session to use (if None, uses db.session)
    """
    if not json_array or not isinstance(json_array, list):
        return
    
    # Auto-detect language from first item if not provided
    if source_language is None and len(json_array) > 0:
        first_item = json_array[0]
        detect_text = first_item.get('description') or first_item.get('title') or first_item.get('text') or ''
        if detect_text:
            source_language = detect_language(detect_text)
            print(f"   Detected language for {field_name}: {source_language}")
        else:
            source_language = 'en'
    elif source_language is None:
        source_language = 'en'
    
    for index, item in enumerate(json_array):
        if not isinstance(item, dict):
            continue
            
        # Translate title if present
        if 'title' in item and item['title']:
            sub_field_name = f"{field_name}[{index}].title"
            translate_content(content_type, content_id, sub_field_name, item['title'], source_language, session)
        
        # Translate description if present
        if 'description' in item and item['description']:
            sub_field_name = f"{field_name}[{index}].description"
            translate_content(content_type, content_id, sub_field_name, item['description'], source_language, session)
        
        # Translate caption if present (for gallery images)
        if 'caption' in item and item['caption']:
            sub_field_name = f"{field_name}[{index}].caption"
            translate_content(content_type, content_id, sub_field_name, item['caption'], source_language, session)
        
        # Translate text if present
        if 'text' in item and item['text']:
            sub_field_name = f"{field_name}[{index}].text"
            translate_content(content_type, content_id, sub_field_name, item['text'], source_language, session)
        
        # Translate button_text if present (for features)
        if 'button_text' in item and item['button_text']:
            sub_field_name = f"{field_name}[{index}].button_text"
            translate_content(content_type, content_id, sub_field_name, item['button_text'], source_language, session)

        # Translate caption if present (for gallery items)
        if 'caption' in item and item['caption']:
            sub_field_name = f"{field_name}[{index}].caption"
            translate_content(content_type, content_id, sub_field_name, item['caption'], source_language, session)
        
        # Translate tags if present (for carousel items or other content)
        if 'tags' in item and item['tags']:
            if isinstance(item['tags'], list):
                # If tags is an array of strings, translate each tag
                translate_string_array(content_type, content_id, f"{field_name}[{index}].tags", item['tags'], source_language, session)
            elif isinstance(item['tags'], str):
                # If tags is a string (comma or space separated), translate it as text
                sub_field_name = f"{field_name}[{index}].tags"
                translate_content(content_type, content_id, sub_field_name, item['tags'], source_language, session)


def translate_string_array(content_type, content_id, field_name, string_array, source_language=None, session=None):
    """
    Translate an array of strings, where each string is translated individually.
    
    Args:
        content_type: Type of content
        content_id: ID of the content item
        field_name: Name of the field
        string_array: List of strings to translate
        source_language: Source language code (if None, auto-detects from first string)
        session: SQLAlchemy session to use
    """
    if not string_array or not isinstance(string_array, list):
        return
    
    # Auto-detect language from first non-empty string if not provided
    if source_language is None:
        for item in string_array:
            if isinstance(item, str) and item.strip():
                source_language = detect_language(item)
                print(f"   Detected language for {field_name}: {source_language}")
                break
        if source_language is None:
            source_language = 'en'
    
    for index, item in enumerate(string_array):
        if isinstance(item, str) and item.strip():
            sub_field_name = f"{field_name}[{index}]"
            translate_content(content_type, content_id, sub_field_name, item, source_language, session)


def auto_translate_course(course, session=None):
    """Automatically translate all translatable fields of a course."""
    fields = TRANSLATABLE_FIELDS.get('course', [])

    for field in fields:
        text = getattr(course, field, None)
        if text:
            if field == 'tags' and isinstance(text, list):
                # Handle tags as array of strings
                translate_string_array('course', course.id, field, text, session=session)
            else:
                translate_content('course', course.id, field, text, session=session)

    # DO NOT translate course content or folders when translating course from admin panel
    # (Intentionally left blank)

def auto_translate_course_content(content, session=None):
    """Automatically translate course content (lessons, materials, etc.)."""
    fields = TRANSLATABLE_FIELDS.get('course_content', [])
    
    for field in fields:
        text = getattr(content, field, None)
        if text:
            translate_content('course_content', content.id, field, text, session=session)


def auto_translate_course_content_folder(folder, session=None):
    """Automatically translate course content folder."""
    fields = TRANSLATABLE_FIELDS.get('course_content_folder', [])
    
    for field in fields:
        text = getattr(folder, field, None)
        if text:
            translate_content('course_content_folder', folder.id, field, text, session=session)


def auto_translate_resource(resource, session=None):
    """Automatically translate all translatable fields of a resource."""
    fields = TRANSLATABLE_FIELDS.get('resource', [])
    
    for field in fields:
        text = getattr(resource, field, None)
        if text:
            translate_content('resource', resource.id, field, text, session=session)



def get_translated_content(content_type, content_id, field_name, original_text, target_language):
    """
    Get translated content for a specific field.
    
    Args:
        content_type: Type of content
        content_id: ID of the content item
        field_name: Name of the field
        original_text: Original text (fallback if translation not found)
        target_language: Target language code
    
    Returns:
        Translated text or original text if translation not found
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not target_language:
        return original_text
    
    # Skip English
    if target_language == 'en':
        return original_text
    
    try:
        translation = ContentTranslation.query.filter_by(
            content_type=content_type,
            content_id=content_id,
            field_name=field_name,
            target_language=target_language
        ).first()
        
        if translation:
            logger.warning(f"  🔍 FOUND: {field_name} -> {target_language}")
            return translation.translated_text
        else:
            logger.warning(f"  ✗ NOT FOUND: {field_name} -> {target_language}")
            return original_text
    except Exception as e:
        logger.error(f"  ✗ ERROR querying translations: {str(e)}")
        return original_text


def get_translated_json_array(content_type, content_id, field_name, json_array, target_language):
    """
    Get translated JSON array with text fields translated.
    Uses batched queries to reduce database hits.
    
    Args:
        content_type: Type of content
        content_id: ID of the content item
        field_name: Name of the JSON field
        json_array: Original JSON array
        target_language: Target language code
    
    Returns:
        JSON array with translated text fields
    """
    if not target_language or target_language == 'en' or not json_array:
        return json_array
    
    # Batch query all translations at once to reduce DB hits
    # Build list of all sub-field names we need to query
    sub_fields = []
    for index, item in enumerate(json_array):
        if not isinstance(item, dict):
            continue
        if 'title' in item:
            sub_fields.append(f"{field_name}[{index}].title")
        if 'description' in item:
            sub_fields.append(f"{field_name}[{index}].description")
        if 'caption' in item:
            sub_fields.append(f"{field_name}[{index}].caption")
        if 'text' in item:
            sub_fields.append(f"{field_name}[{index}].text")
        if 'button_text' in item:
            sub_fields.append(f"{field_name}[{index}].button_text")
        if 'tags' in item and isinstance(item['tags'], str) and item['tags'].strip():
            sub_fields.append(f"{field_name}[{index}].tags")
    
    # Single query to get all translations
    translations = {}
    if sub_fields:
        from lms.models import ContentTranslation
        results = ContentTranslation.query.filter(
            ContentTranslation.content_type == content_type,
            ContentTranslation.content_id == content_id,
            ContentTranslation.target_language == target_language,
            ContentTranslation.field_name.in_(sub_fields)
        ).all()
        translations = {t.field_name: t.translated_text for t in results}
    
    translated_array = []
    for index, item in enumerate(json_array):
        if not isinstance(item, dict):
            translated_array.append(item)
            continue
        
        translated_item = item.copy()
        
        # Translate title if present
        if 'title' in item:
            sub_field_name = f"{field_name}[{index}].title"
            translated_item['title'] = translations.get(sub_field_name, item['title'])
        
        # Translate description if present
        if 'description' in item:
            sub_field_name = f"{field_name}[{index}].description"
            translated_item['description'] = translations.get(sub_field_name, item['description'])
        
        # Translate caption if present (for gallery items)
        if 'caption' in item:
            sub_field_name = f"{field_name}[{index}].caption"
            translated_item['caption'] = translations.get(sub_field_name, item['caption'])
        
        # Translate text if present (for dropdown menus)
        if 'text' in item:
            sub_field_name = f"{field_name}[{index}].text"
            translated_item['text'] = translations.get(sub_field_name, item['text'])
        
        # Translate button_text if present (for features)
        if 'button_text' in item:
            sub_field_name = f"{field_name}[{index}].button_text"
            translated_item['button_text'] = translations.get(
                sub_field_name, 
                item.get('button_text', '')
            )
        
        # Translate tags if present
        if 'tags' in item:
            if isinstance(item['tags'], list):
                # If tags is an array of strings, translate each tag
                sub_field_name = f"{field_name}[{index}].tags"
                translated_item['tags'] = get_translated_string_array(
                    content_type, content_id, sub_field_name, item['tags'], target_language
                )
            elif isinstance(item['tags'], str) and item['tags'].strip():
                # If tags is a string, translate it as text
                sub_field_name = f"{field_name}[{index}].tags"
                translated_item['tags'] = translations.get(sub_field_name, item['tags'])
        
        translated_array.append(translated_item)
    
    return translated_array


def get_translated_string_array(content_type, content_id, field_name, string_array, target_language):
    """
    Get translated string array where each string is translated individually.
    Uses batched queries to reduce database hits.
    
    Args:
        content_type: Type of content
        content_id: ID of the content item
        field_name: Name of the field
        string_array: Original array of strings
        target_language: Target language code
    
    Returns:
        Array of translated strings
    """
    if not target_language or target_language == 'en' or not string_array:
        return string_array
    
    # Batch query all translations at once
    sub_fields = [f"{field_name}[{index}]" for index in range(len(string_array))]
    translations = {}
    if sub_fields:
        from lms.models import ContentTranslation
        results = ContentTranslation.query.filter(
            ContentTranslation.content_type == content_type,
            ContentTranslation.content_id == content_id,
            ContentTranslation.target_language == target_language,
            ContentTranslation.field_name.in_(sub_fields)
        ).all()
        translations = {t.field_name: t.translated_text for t in results}
    
    translated_array = []
    for index, item in enumerate(string_array):
        if isinstance(item, str) and item.strip():
            sub_field_name = f"{field_name}[{index}]"
            translated_item = translations.get(sub_field_name, item)
            translated_array.append(translated_item)
        else:
            translated_array.append(item)
    
