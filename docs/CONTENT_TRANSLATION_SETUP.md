# Content Translation System - Setup Complete ✓

## Summary

A comprehensive automatic content translation system has been successfully created for the Yonca platform. The system automatically detects the language of dynamic content (courses, resources, gallery captions, home content) and translates it into Azerbaijani (az) and Russian (ru).

## What Was Implemented

### 1. Database Model
- **ContentTranslation** model created in `yonca/models/__init__.py`
- Stores translations with content_type, content_id, field_name, language
- Indexed for fast lookups

### 2. Translation Helper Module
- **yonca/content_translator.py** - Core translation logic
- Functions for each content type:
  - `auto_translate_course()`
  - `auto_translate_resource()`
  - `auto_translate_home_content()`
  - `auto_translate_course_content()`
  - `auto_translate_course_content_folder()`
- Handles JSON arrays (features, gallery captions, dropdown menus)
- Integrates with existing TranslationService (GoogleTranslator)

### 3. Template Helpers
- Added to `yonca/__init__.py` as context processors
- **translate_field()** - Translate simple text fields
- **translate_json()** - Translate JSON arrays
- Automatically uses current_locale from session

### 4. Translation Scripts
- **translate_all_content.py** - Bulk translate existing content
- **test_content_translation.py** - Test script with examples
- Can translate by type: `python translate_all_content.py courses`

### 5. Documentation
- **docs/CONTENT_TRANSLATION.md** - Comprehensive guide
- Examples for all content types
- Database schema documentation
- Debugging tips

## Translation Coverage

### Already Translated ✓
- **2 Courses** - All fields (title, description, features, dropdown menus)
- **1 Home Content** - All 30+ fields including JSON arrays
- Includes gallery captions, section titles, features lists

### Translatable Fields by Type

**Courses (Course model)**
- title, description
- page_welcome_title, page_subtitle, page_description
- dropdown_menu (JSON)
- page_features (JSON)

**Resources (Resource model)**
- title, description

**Home Content (HomeContent model)**
- 30+ text fields
- features, logged_out_features
- gallery_images, about_gallery_images (JSON with captions)

**Course Content & Folders**
- title, description

## Usage in Templates

### Simple Field
```jinja2
{# Before #}
<h1>{{ course.title }}</h1>

{# After - automatically translates based on current language #}
<h1>{{ translate_field('course', course.id, 'title', course.title) }}</h1>
```

### JSON Array
```jinja2
{# Before #}
{% for feature in home_content.features %}
    <h3>{{ feature.title }}</h3>
    <p>{{ feature.description }}</p>
{% endfor %}

{# After - automatically translates all fields #}
{% for feature in translate_json('home_content', home_content.id, 'features', home_content.features) %}
    <h3>{{ feature.title }}</h3>
    <p>{{ feature.description }}</p>
{% endfor %}
```

### Gallery Captions
```jinja2
{# Automatically translates captions #}
{% for image in translate_json('home_content', home_content.id, 'gallery_images', home_content.gallery_images) %}
    <img src="{{ image.url }}" alt="{{ image.caption }}">
    <p>{{ image.caption }}</p>
{% endfor %}
```

## How to Translate New Content

### Option 1: Manual Translation (Recommended)
When you create/edit content in admin dashboard, run:
```bash
python translate_all_content.py courses    # Translate courses
python translate_all_content.py resources  # Translate resources
python translate_all_content.py home       # Translate home content
python translate_all_content.py            # Translate everything
```

### Option 2: Programmatic
```python
from yonca.content_translator import auto_translate_course

# After creating/updating a course
course = Course(title="New Course", description="...")
db.session.add(course)
db.session.commit()

# Manually trigger translation
auto_translate_course(course)
db.session.commit()
```

## Next Steps to Enable in Production

### 1. Update Templates
Find and replace original fields with translation helpers:

**For courses:**
```jinja2
{{ course.title }} → {{ translate_field('course', course.id, 'title', course.title) }}
{{ course.description }} → {{ translate_field('course', course.id, 'description', course.description) }}
```

**For home content:**
```jinja2
{{ home_content.welcome_title }} → {{ translate_field('home_content', home_content.id, 'welcome_title', home_content.welcome_title) }}

{{ home_content.features }} → translate_json('home_content', home_content.id, 'features', home_content.features)
```

### 2. Translation Workflow
1. Admin edits content in English
2. Run translation script: `python translate_all_content.py`
3. Translations stored in database
4. Users see translated content based on language selection

### 3. Update Admin Dashboard (Optional)
Add a "Translate" button in admin interface that runs the translation script for specific content.

## Files Created/Modified

### New Files
- `yonca/content_translator.py` - Translation logic
- `translate_all_content.py` - Bulk translation utility
- `test_content_translation.py` - Test script
- `docs/CONTENT_TRANSLATION.md` - Documentation

### Modified Files
- `yonca/models/__init__.py` - Added ContentTranslation model
- `yonca/__init__.py` - Added template helpers (translate_field, translate_json)

## Performance

- **Database caching**: Translations cached in `content_translation` table
- **Indexed lookups**: Fast retrieval using composite index
- **Translation service**: Uses GoogleTranslator (deep-translator library)
- **Cache hits**: Terminal shows "Translation cache hit" for repeated text

## Example Output

```
✓ Translated course:2.title -> az
✓ Translated course:2.title -> ru
✓ Translated course:2.description -> az
✓ Translated course:2.description -> ru
✓ Translated course:2.dropdown_menu[0].text -> az
✓ Translated course:2.dropdown_menu[0].text -> ru
✓ Translated course: Web Development Fundamentals
```

## Limitations

- **Forum messages**: Have separate translation system (not affected)
- **Source language**: Currently assumes English ('en')
- **Manual trigger**: Need to run script after admin edits (no auto-trigger on save)

## Future Enhancements

- [ ] Auto-translate on admin save (add event listeners in admin interface)
- [ ] Admin UI to review/edit translations
- [ ] Support for more languages beyond az/ru
- [ ] Translation quality review system
- [ ] Bulk re-translation command for specific content

## Testing

Run test script to verify:
```bash
python test_content_translation.py
```

Check translations in database:
```python
from yonca.models import ContentTranslation
translations = ContentTranslation.query.filter_by(content_type='course', content_id=1).all()
for t in translations:
    print(f"{t.field_name} ({t.target_language}): {t.translated_text}")
```

## Support

See detailed documentation: `docs/CONTENT_TRANSLATION.md`

Questions? Check the translation service logs for debugging:
- LibreTranslate connection errors are normal (falls back to GoogleTranslator)
- Look for "Translation cache hit" for cached translations
- Check terminal for "✓ Translated" messages
