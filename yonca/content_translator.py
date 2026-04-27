"""
Content translation helper for automatic translation of dynamic content
"""
import re
from yonca.models import ContentTranslation, db
from yonca.translation_service import translation_service

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("Warning: langdetect not available. Install with: pip install langdetect")

# Import centralized language constants
from yonca.constants import SUPPORTED_LANGUAGES

# Languages to automatically translate to
TARGET_LANGUAGES = ['az', 'ru']

# Fields to translate for each content type
TRANSLATABLE_FIELDS = {
    'course': ['title', 'description', 'page_welcome_title', 'page_subtitle', 'page_description', 'page_features', 'tags'],
    'resource': ['title', 'description'],
    'home_content': [
        'welcome_title', 'subtitle', 'get_started_text',
        'logged_out_welcome_title', 'logged_out_subtitle', 'logged_out_get_started_text',
        'courses_section_title', 'courses_section_description',
        'forum_section_title', 'forum_section_description',
        'resources_section_title', 'resources_section_description',
        'tavi_test_section_title', 'tavi_test_section_description',
        'about_section_title', 'about_section_description',
        'about_welcome_title', 'about_subtitle',
        'about_features_title', 'about_features_subtitle',
        'features_title', 'features_subtitle',
        'about_gallery_title', 'about_gallery_subtitle',
        'services_title', 'services_subtitle'
    ],
    'gallery_item': ['caption', 'title', 'description']
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
    
    Args:
        content_type: Type of content ('course', 'resource', 'home_content', etc.)
        content_id: ID of the content item
        field_name: Name of the field being translated
        text: Text to translate
        source_language: Source language code (if None, auto-detects)
        session: SQLAlchemy session to use (if None, uses db.session)
    """
    if not text or not text.strip():
        return
    
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
    
    for target_lang in target_langs:
        if target_lang == source_language:
            continue
            
        try:
            # Check if content contains HTML (both actual tags and entities)
            is_html = bool(re.search(r'<[^>]+>|&lt;|&gt;|&amp;', text))
            
            if is_html:
                # Use HTML-aware translation
                translated = translation_service.translate_html(text, target_lang, source_language)
                print(f"   Translated HTML content for {content_type}:{content_id}.{field_name} -> {target_lang}")
            else:
                # Use regular text translation
                translated = translation_service.get_translation(text, target_lang, source_language)
            
            if not translated:
                print(f"Warning: Translation failed for {content_type}:{content_id}.{field_name} -> {target_lang}")
                continue
            
            # Check if translation already exists
            existing = session.query(ContentTranslation).filter_by(
                content_type=content_type,
                content_id=content_id,
                field_name=field_name,
                target_language=target_lang
            ).first()
            
            if existing:
                # Update existing translation
                existing.translated_text = translated
                existing.source_language = source_language
            else:
                # Create new translation
                new_translation = ContentTranslation(
                    content_type=content_type,
                    content_id=content_id,
                    field_name=field_name,
                    source_language=source_language,
                    target_language=target_lang,
                    translated_text=translated
                )
                session.add(new_translation)
            
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
    
    # Translate dropdown menu items
    if course.dropdown_menu:
        translate_json_array('course', course.id, 'dropdown_menu', course.dropdown_menu, 'text', session=session)
    # Translate page features
    if course.page_features:
        translate_json_array('course', course.id, 'page_features', course.page_features, session=session)

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


def auto_translate_home_content(home_content, session=None):
    """Automatically translate all translatable fields of home content."""
    fields = TRANSLATABLE_FIELDS.get('home_content', [])
    
    for field in fields:
        text = getattr(home_content, field, None)
        if text:
            translate_content('home_content', home_content.id, field, text, session=session)
    
    # Translate JSON arrays
    if home_content.features:
        translate_json_array('home_content', home_content.id, 'features', home_content.features, session=session)
    
    if home_content.logged_out_features:
        translate_json_array('home_content', home_content.id, 'logged_out_features', home_content.logged_out_features, session=session)
    
    if home_content.about_features:
        translate_json_array('home_content', home_content.id, 'about_features', home_content.about_features, session=session)
    
    # Translate gallery images (captions)
    if home_content.gallery_images:
        translate_json_array('home_content', home_content.id, 'gallery_images', home_content.gallery_images, 'caption', session=session)
    
    if home_content.about_gallery_images:
        translate_json_array('home_content', home_content.id, 'about_gallery_images', home_content.about_gallery_images, 'caption', session=session)


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
    
    translated_array = []
    
    for index, item in enumerate(json_array):
        if not isinstance(item, dict):
            translated_array.append(item)
            continue
        
        translated_item = item.copy()
        
        # Translate title if present
        if 'title' in item:
            sub_field_name = f"{field_name}[{index}].title"
            translated_item['title'] = get_translated_content(
                content_type, content_id, sub_field_name, item['title'], target_language
            )
        
        # Translate description if present
        if 'description' in item:
            sub_field_name = f"{field_name}[{index}].description"
            translated_item['description'] = get_translated_content(
                content_type, content_id, sub_field_name, item['description'], target_language
            )
        
        # Translate caption if present (for gallery items)
        if 'caption' in item:
            sub_field_name = f"{field_name}[{index}].caption"
            translated_item['caption'] = get_translated_content(
                content_type, content_id, sub_field_name, item['caption'], target_language
            )
        
        # Translate text if present (for dropdown menus)
        if 'text' in item:
            sub_field_name = f"{field_name}[{index}].text"
            translated_item['text'] = get_translated_content(
                content_type, content_id, sub_field_name, item['text'], target_language
            )

        # Translate button_text if present (for features)
        if 'button_text' in item:
            sub_field_name = f"{field_name}[{index}].button_text"
            translated_item['button_text'] = get_translated_content(
                content_type, content_id, sub_field_name, item.get('button_text', ''), target_language
            )
        
        # Translate tags if present (for carousel items or other content)
        if 'tags' in item:
            if isinstance(item['tags'], list):
                # If tags is an array of strings, translate each tag
                sub_field_name = f"{field_name}[{index}].tags"
                translated_item['tags'] = get_translated_string_array(
                    content_type, content_id, sub_field_name, item['tags'], target_language
                )
            elif isinstance(item['tags'], str) and item['tags'].strip():
                # If tags is a string (comma or space separated), translate it as text
                sub_field_name = f"{field_name}[{index}].tags"
                translated_item['tags'] = get_translated_content(
                    content_type, content_id, sub_field_name, item['tags'], target_language
                )
        
        translated_array.append(translated_item)
    
    return translated_array


def get_translated_string_array(content_type, content_id, field_name, string_array, target_language):
    """
    Get translated string array where each string is translated individually.
    
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
    
    translated_array = []
    
    for index, item in enumerate(string_array):
        if isinstance(item, str) and item.strip():
            sub_field_name = f"{field_name}[{index}]"
            translated_item = get_translated_content(
                content_type, content_id, sub_field_name, item, target_language
            )
            translated_array.append(translated_item)
        else:
            translated_array.append(item)
    
    return translated_array


def auto_translate_page_builder(course, session=None):
    """
    Automatically translate all translatable content from page builder blocks.
    
    This function extracts text fields from page builder blocks and translates them
    using the standard translation system.
    
    Args:
        course: Course object with page_builder_data
        session: SQLAlchemy session to use (if None, uses db.session)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not course or not course.page_builder_data:
        logger.warning(f"⚠️  No page_builder_data to translate for course {course.id if course else 'None'}")
        return
    
    if session is None:
        from yonca.models import db
        session = db.session
    
    page_builder_data = course.page_builder_data
    logger.warning(f"✓ PAGE BUILDER TRANSLATION: Starting for course {course.id}, blocks: {len(page_builder_data)}")
    
    for i, block in enumerate(page_builder_data):
        block_type = block.get('type', '')
        block_id = block.get('id', '')
        settings = block.get('settings', {})
        
        logger.warning(f"  Block {i}: type={block_type}, id={block_id}")
        
        try:
            if block_type == 'plain-text':
                # Translate plain text content
                if settings.get('text'):
                    field_name = f'page_builder[{block_id}].text'
                    text_content = settings['text'][:100] + '...' if len(settings['text']) > 100 else settings['text']
                    logger.warning(f"    → Translating plain-text: {text_content}")
                    translate_content('course', course.id, field_name, settings['text'], session=session)
            
            elif block_type == 'hero':
                # Translate hero title and subtitle
                if settings.get('title'):
                    field_name = f'page_builder[{block_id}].title'
                    logger.warning(f"    → Translating hero title: {settings['title']}")
                    translate_content('course', course.id, field_name, settings['title'], session=session)
                if settings.get('subtitle'):
                    field_name = f'page_builder[{block_id}].subtitle'
                    logger.warning(f"    → Translating hero subtitle: {settings['subtitle']}")
                    translate_content('course', course.id, field_name, settings['subtitle'], session=session)
            
            elif block_type == 'text-image':
                # Translate text + image content
                if settings.get('text'):
                    field_name = f'page_builder[{block_id}].text'
                    text_content = settings['text'][:100] + '...' if len(settings['text']) > 100 else settings['text']
                    logger.warning(f"    → Translating text-image: {text_content}")
                    translate_content('course', course.id, field_name, settings['text'], session=session)
            
            elif block_type == 'buttons':
                # Translate button texts
                buttons = settings.get('buttons', [])
                if buttons:
                    logger.warning(f"    → Translating {len(buttons)} button texts")
                    translate_json_array('course', course.id, f'page_builder[{block_id}].buttons', buttons, 'text', session=session)
            
            elif block_type == 'youtube':
                # YouTube blocks don't need translation (only have embed info)
                logger.warning(f"    ⊘ Skipping youtube block")
            
            elif block_type == 'carousel':
                # Translate carousel items (titles and descriptions)
                items = settings.get('items', [])
                if items:
                    logger.warning(f"    → Translating {len(items)} carousel items")
                    translate_json_array('course', course.id, f'page_builder[{block_id}].items', items, session=session)
        except Exception as e:
            logger.error(f"  ✗ ERROR translating block {i}: {str(e)}")
    
    # Make sure all translations are flushed to database
    try:
        session.flush()
        logger.warning(f"✓ PAGE BUILDER TRANSLATION: Flushed to DB for course {course.id}")
    except Exception as e:
        logger.error(f"✗ ERROR flushing page builder translations: {str(e)}")
    
    logger.warning(f"✓ PAGE BUILDER TRANSLATION: Complete for course {course.id}")


def get_translated_page_builder_data(course, target_language):
    """
    Get page builder data with translated content.
    
    Args:
        course: Course object with page_builder_data
        target_language: Target language code (can be string or Locale object)
    
    Returns:
        page_builder_data with translated content
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not course or not course.page_builder_data or not target_language:
        logger.warning(f"⚠️  No data to translate: course={course}, data={bool(course.page_builder_data if course else None)}, lang={target_language}")
        return course.page_builder_data or [] if course else []
    
    # Normalize language code
    lang_code = str(target_language)
    logger.warning(f"📖 RAW target_language: {repr(target_language)} (type: {type(target_language).__name__})")
    
    # Handle Locale objects: Locale('ru') -> 'ru', or 'ru_RU' -> 'ru'
    if hasattr(target_language, 'language'):
        # It's a Flask-Babel Locale object
        lang_code = target_language.language
        logger.warning(f"📖 Detected Locale object, language: {lang_code}")
    else:
        # It's a string, extract just the language part
        lang_code = lang_code.split('_')[0].lower()
        logger.warning(f"📖 Detected string, language: {lang_code}")
    
    if lang_code == 'en':
        logger.warning(f"📖 Language is English, returning original")
        return course.page_builder_data or []
    
    logger.warning(f"🔄 PAGE BUILDER RENDER: Getting translated data for course {course.id}, language: {lang_code}")
    
    import copy
    translated_data = copy.deepcopy(course.page_builder_data)
    blocks_with_translations = 0
    
    for block_idx, block in enumerate(translated_data):
        block_type = block.get('type', '')
        block_id = block.get('id', '')
        settings = block.get('settings', {})
        
        try:
            if block_type == 'plain-text':
                # Get translated text
                if settings.get('text'):
                    field_name = f'page_builder[{block_id}].text'
                    original_text = settings['text']
                    translated_text = get_translated_content('course', course.id, field_name, original_text, lang_code)
                    if translated_text != original_text:
                        logger.warning(f"  ✓ Found translation for plain-text block")
                        settings['text'] = translated_text
                        blocks_with_translations += 1
            
            elif block_type == 'hero':
                # Get translated title and subtitle
                if settings.get('title'):
                    field_name = f'page_builder[{block_id}].title'
                    original_title = settings['title']
                    translated_title = get_translated_content('course', course.id, field_name, original_title, lang_code)
                    if translated_title != original_title:
                        logger.warning(f"  ✓ Found translation for hero title")
                        settings['title'] = translated_title
                        blocks_with_translations += 1
                
                if settings.get('subtitle'):
                    field_name = f'page_builder[{block_id}].subtitle'
                    original_subtitle = settings['subtitle']
                    translated_subtitle = get_translated_content('course', course.id, field_name, original_subtitle, lang_code)
                    if translated_subtitle != original_subtitle:
                        logger.warning(f"  ✓ Found translation for hero subtitle")
                        settings['subtitle'] = translated_subtitle
            
            elif block_type == 'text-image':
                # Get translated text content
                if settings.get('text'):
                    field_name = f'page_builder[{block_id}].text'
                    original_text = settings['text']
                    translated_text = get_translated_content('course', course.id, field_name, original_text, lang_code)
                    if translated_text != original_text:
                        logger.warning(f"  ✓ Found translation for text-image block")
                        settings['text'] = translated_text
                        blocks_with_translations += 1
            
            elif block_type == 'buttons':
                # Get translated button texts
                buttons = settings.get('buttons', [])
                if buttons:
                    translated_buttons = get_translated_json_array('course', course.id, f'page_builder[{block_id}].buttons', buttons, lang_code)
                    settings['buttons'] = translated_buttons
            
            elif block_type == 'youtube':
                # YouTube blocks don't have translatable content
                pass
            
            elif block_type == 'carousel':
                # Get translated carousel items
                items = settings.get('items', [])
                if items:
                    logger.warning(f"    → Translating {len(items)} carousel items")
                    translated_items = get_translated_json_array('course', course.id, f'page_builder[{block_id}].items', items, lang_code)
                    settings['items'] = translated_items
                    blocks_with_translations += 1
        except Exception as e:
            logger.error(f"  ✗ ERROR processing block {block_idx}: {str(e)}")
    
    if blocks_with_translations == 0:
        logger.warning(f"⚠️  NO translations found! Check if language code '{lang_code}' is correct.")
    
    logger.warning(f"🔄 PAGE BUILDER RENDER: Complete ({blocks_with_translations} blocks translated)")
    return translated_data
