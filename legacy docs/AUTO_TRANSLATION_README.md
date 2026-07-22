# Auto-Translation System

## Overview

Content translations are **NOT** automatically triggered when content is saved. After editing courses, resources, or home content in the admin dashboard, you need to manually run the translation script.

## How to Translate Content

After creating or editing content, run:

```bash
# Translate all content
python translate_all_content.py

# Or translate specific types
python translate_all_content.py courses
python translate_all_content.py resources
python translate_all_content.py home
```

## Why Manual Translation?

Automatic translation on save was removed due to database session conflicts. The manual approach:
- ✅ More reliable - no transaction conflicts
- ✅ Faster admin saves - no waiting for translations
- ✅ Batch efficiency - translate multiple edits at once
- ✅ Control - choose when to translate

## Recommended Workflow

1. Edit multiple courses/resources in admin
2. When finished with edits, run: `python translate_all_content.py`
3. Translations update in database
4. Users see translated content when they switch languages

## Future: Admin Button

Future enhancement: Add a "Translate All" button in admin interface that runs the script automatically.
