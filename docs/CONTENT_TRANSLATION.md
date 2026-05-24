# Content Translation System

This document describes the automatic content translation system for dynamic content (courses, resources, gallery captions, home content).

## Overview

The system automatically translates dynamic content when it's created or updated, storing translations in the `content_translation` table. Forum translations are handled separately.

## Features

- **Automatic language detection**: Content language is automatically detected when created/updated
- **Multi-language translation**: Content is automatically translated to Azerbaijani (az) and Russian (ru)
- **Template helpers**: Use `translate_field()` and `translate_json()` to display translated content
- **Database caching**: Translations are stored in the database for fast retrieval
- **Protected terms**: "Yonca" brand name is never translated
- **Support for complex fields**: JSON arrays (features, gallery captions, dropdown menus) are fully supported

## Supported Content Types

### 1. Courses
**Translatable fields:**
- `title`
- `description`
- `page_welcome_title`
- `page_subtitle`
- `page_description`
- `dropdown_menu` (JSON array with `text` field)
- `page_features` (JSON array with `title` and `description` fields)

### 2. Course Content (Lessons/Materials)
**Translatable fields:**
- `title`
- `description`

### 3. Course Content Folders
**Translatable fields:**
- `title`
- `description`

### 4. Resources
**Translatable fields:**
- `title`
- `description`

### 5. Home Content
**Translatable fields:**
- `welcome_title`
- `subtitle`
- `get_started_text`
- `logged_out_welcome_title`
- `logged_out_subtitle`
- `logged_out_get_started_text`
- `courses_section_title`
- `courses_section_description`
- `forum_section_title`
- `forum_section_description`
- `resources_section_title`
- `resources_section_description`
- `moxo_test_section_title`
- `moxo_test_section_description`
- `contacts_section_title`
- `contacts_section_description`
- `about_section_title`
- `about_section_description`
- `about_welcome_title`
- `about_subtitle`
- `about_gallery_title`
- `about_gallery_subtitle`
- `features` (JSON array)
- `logged_out_features` (JSON array)
- `gallery_images` (JSON array with captions)
- `about_gallery_images` (JSON array with captions)

## Usage in Templates

### Simple Field Translation

```jinja2
{# Original field #}
<h1>{{ course.title }}</h1>

{# Translated field (automatically uses current language) #}
<h1>{{ translate_field('course', course.id, 'title', course.title) }}</h1>
```

### JSON Array Translation

```jinja2
{# Original JSON array #}
{% for feature in home_content.features %}
    <h3>{{ feature.title }}</h3>
    <p>{{ feature.description }}</p>
{% endfor %}

{# Translated JSON array #}
{% for feature in translate_json('home_content', home_content.id, 'features', home_content.features) %}
    <h3>{{ feature.title }}</h3>
    <p>{{ feature.description }}</p>
{% endfor %}
```

### Gallery Captions

```jinja2
{# Translated gallery with captions #}
{% for image in translate_json('home_content', home_content.id, 'gallery_images', home_content.gallery_images) %}
    <img src="{{ image.url }}" alt="{{ image.caption }}">
    <p>{{ image.caption }}</p>
{% endfor %}
```

### Course Dropdown Menu

```jinja2
{# Translated dropdown menu items #}
{% for item in translate_json('course', course.id, 'dropdown_menu', course.dropdown_menu) %}
    <a href="{{ item.url }}">{{ item.icon }} {{ item.text }}</a>
{% endfor %}
```

## Automatic Translation Triggers

Content is automatically translated when:

1. **Course created/updated**: All course fields are translated
2. **CourseContent created/updated**: Course content fields are translated
3. **CourseContentFolder created/updated**: Folder fields are translated
4. **Resource created/updated**: Resource fields are translated
5. **HomeContent created/updated**: All home content fields and JSON arrays are translated

## Example: Update Course and Auto-Translate

```python
from yonca.models import Course, db

# Create or update a course
course = Course.query.get(1)
course.title = "Introduction to Python Programming"
course.description = "Learn Python basics with hands-on exercises"
course.page_welcome_title = "Welcome to Python Course"

db.session.commit()  # Auto-translation happens automatically!

# Translations are now available in the database
# Templates will show translated versions based on current_locale
```

## How It Works

1. **Event Listeners**: SQLAlchemy event listeners are attached to `after_insert` and `after_update` events
2. **Translation Service**: The `TranslationService` uses GoogleTranslator to translate text
3. **Database Storage**: Translations are stored in `content_translation` table
4. **Template Helpers**: `translate_field()` and `translate_json()` fetch translations based on `current_locale`

## Database Schema

```sql
CREATE TABLE content_translation (
    id SERIAL PRIMARY KEY,
    content_type VARCHAR(50) NOT NULL,  -- 'course', 'resource', etc.
    content_id INTEGER NOT NULL,         -- ID of the content item
    field_name VARCHAR(100) NOT NULL,    -- 'title', 'description', etc.
    source_language VARCHAR(10) DEFAULT 'en',
    target_language VARCHAR(10) NOT NULL,  -- 'az' or 'ru'
    translated_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX idx_content_translation_lookup 
ON content_translation(content_type, content_id, field_name, target_language);
```

## Manual Translation

If you need to manually translate specific content:

```python
from yonca.content_translator import translate_content

# Translate a single field
translate_content(
    content_type='course',
    content_id=1,
    field_name='title',
    text='Introduction to Python',
    source_language='en'
)

# This creates translations to both 'az' and 'ru'
```

## Debugging

Check translation status in terminal:
```
✓ Auto-translated course: Introduction to Python Programming
✓ Auto-translated course content: Lesson 1 - Variables
✓ Auto-translated resource: Python Cheat Sheet
✓ Auto-translated home content
```

Query translations directly:
```python
from yonca.models import ContentTranslation

# Get all translations for a course
translations = ContentTranslation.query.filter_by(
    content_type='course',
    content_id=1
).all()

for t in translations:
    print(f"{t.field_name} ({t.target_language}): {t.translated_text}")
```

## Performance

- **Database caching**: Translations are cached in the database
- **Indexed lookups**: Fast retrieval using composite index
- **Lazy translation**: Only translates when content changes
- **Batch operations**: JSON arrays are translated in batch

## Limitations

- **Forum messages**: Forum has its own translation system (separate)
- **Real-time updates**: Translations happen on content save, not on-the-fly
- **Source language**: Currently assumes source is English ('en')

## Future Enhancements

- [ ] Support for more languages
- [ ] Admin UI to review/edit translations
- [ ] Translation quality review system
- [ ] Bulk re-translation command
- [ ] Translation fallback chain (az → en if translation missing)
