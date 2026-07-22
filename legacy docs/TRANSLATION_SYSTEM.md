# Translation System Documentation

## Overview

The LMS platform uses a hybrid translation system that combines LibreTranslate (self-hosted, free) with Google Translator as a fallback, featuring automatic caching and protection for brand terms.

## Key Features

### 1. Protected Terms
- **Never Translated**: Brand name "LMS" and variants are preserved in all languages
- **Method**: Placeholder replacement before translation + HTML `translate="no"` attribute
- **Automatic**: No manual intervention needed

### 2. Translation Caching
- **Database Storage**: All translations stored in `translation` table
- **One-Time Translation**: Each unique text translated once, then served from cache
- **Performance**: Instant response for cached translations

### 3. Multi-Service Support
- **Primary**: LibreTranslate (self-hosted, free, supports Azerbaijani)
- **Fallback**: Google Translator via deep-translator library
- **Automatic Failover**: Switches to fallback if primary service fails

### 4. Supported Languages
- **English (en)**: Source language
- **Azerbaijani (az)**: LibreTranslate only (best quality)
- **Russian (ru)**: Both services supported

## Setup Instructions

### 1. Install LibreTranslate

#### Using Docker (Recommended)
```bash
docker run -d -p 5000:5000 libretranslate/libretranslate
```

#### Using Python
```bash
pip install libretranslate
libretranslate --host 0.0.0.0 --port 5000
```

### 2. Configure Environment

Add to your `.env` file:
```bash
# Translation Service
ENV=local  # or 'server' for production

# For local development, LibreTranslate runs on port 5000
# For server, it should run on port 5001 to avoid conflict with Flask
```

### 3. Install Dependencies

The required packages are already in `requirements.txt`:
```bash
pip install deep-translator requests
```

### 4. Generate Initial Translations

Run the translation generator to pre-cache common UI strings:
```bash
python generate_translations.py
```

This will:
- Translate all common UI strings to Azerbaijani and Russian
- Store them in the database for instant access
- Protect "LMS" brand name in all translations

## Usage

### In Python Code

```python
from lms.translation_service import translation_service

# Translate text
translated = translation_service.get_translation(
    text="Welcome to LMS!",
    target_language='az'  # or 'ru'
)
# Result: "LMS-ya xoş gəldiniz!" (LMS is preserved)
```

### In Templates

Use Flask-Babel's `_()` function with protected terms:
```html
<!-- Protected brand name -->
<h1><span translate="no">LMS</span> - {{ _('Learning Platform') }}</h1>

<!-- Or inline -->
<p>{{ _('Welcome to') }} <span translate="no">LMS</span>!</p>
```

### Protected Terms List

Edit `lms/core_translator.py` to add more protected terms:
```python
_PROTECTED_TERMS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r'LMS', re.IGNORECASE), '{LMS}', 'LMS'),
    (re.compile(r'Moxo', re.IGNORECASE), '{MOXO}', 'MOXO'),
]
```

## How It Works

### Translation Flow

1. **User Changes Language**: Clicks language toggle (English → Azeri → Russian)
2. **Session Storage**: Language preference saved in Flask session
3. **Content Request**: Page loads with selected language
4. **Cache Check**: System checks if translation exists in database
5. **Translation**:
   - If cached: Return from database (instant)
   - If not cached:
     a. Extract protected terms (e.g., "LMS")
     b. Replace with placeholders
     c. Send to LibreTranslate API
     d. Receive translation
     e. Restore protected terms
     f. Cache in database
     g. Return translated text
6. **Display**: Show translated content with protected terms intact

### Protected Terms Mechanism

```python
Original: "Welcome to LMS platform"
         ↓
Protected: "Welcome to __PROTECTED_0__ platform"
         ↓
Translated: "Xoş gəldiniz __PROTECTED_0__ platformasına"
         ↓
Restored: "Xoş gəldiniz LMS platformasına"
```

## Database Schema

### Translation Table

```sql
CREATE TABLE translation (
    id SERIAL PRIMARY KEY,
    source_text TEXT NOT NULL,
    source_language VARCHAR(10) DEFAULT 'auto',
    target_language VARCHAR(10) NOT NULL,
    translated_text TEXT NOT NULL,
    translation_service VARCHAR(50) DEFAULT 'libretranslate',
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_translation_lookup (source_text, target_language)
);
```

### Example Records

```
| source_text | target_language | translated_text | translation_service |
|-------------|-----------------|-----------------|---------------------|
| Welcome to LMS | az | LMS-ya xoş gəldiniz | libretranslate |
| Home | az | Ana səhifə | libretranslate |
| Courses | ru | Курсы | deep_translator |
```

## SEO Optimization

### Language-Specific URLs

Currently implemented:
- Session-based language switching
- Same URL for all languages

**Future Enhancement** (for better SEO):
```
/en/courses  → English
/az/courses  → Azerbaijani
/ru/courses  → Russian
```

### HTML Lang Attribute

Already implemented in templates:
```html
<html lang="{{ current_locale or 'en' }}">
```

### Hreflang Tags

**To Add** for SEO:
```html
<link rel="alternate" hreflang="en" href="https://lms.com/en/courses" />
<link rel="alternate" hreflang="az" href="https://lms.com/az/courses" />
<link rel="alternate" hreflang="ru" href="https://lms.com/ru/courses" />
```

## Performance

### Caching Benefits
- **First Request**: ~500ms (translation API call)
- **Cached Requests**: ~5ms (database lookup)
- **Reduction**: 99% faster for cached content

### Optimization Tips

1. **Pre-generate Common Strings**: Run `generate_translations.py` regularly
2. **Index Database**: Already indexed on `(source_text, target_language)`
3. **Batch Translations**: Translate multiple strings in one session

## Production Deployment

### Server Setup

1. **Run LibreTranslate on Different Port**:
```bash
# In systemd service or docker-compose
libretranslate --host 127.0.0.1 --port 5001
```

2. **Set Environment Variable**:
```bash
export ENV=server
```

3. **Nginx Configuration** (optional reverse proxy):
```nginx
location /translate {
    proxy_pass http://127.0.0.1:5001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Security

- LibreTranslate bound to localhost (not public)
- No API key required (self-hosted)
- Rate limiting handled by Flask

## Troubleshooting

### LibreTranslate Not Running

**Error**: `Connection refused to localhost:5000`

**Solution**:
```bash
# Check if LibreTranslate is running
curl http://localhost:5000/languages

# Start LibreTranslate
docker run -d -p 5000:5000 libretranslate/libretranslate
```

### Translations Not Caching

**Check**:
1. Database connection working?
2. `translation` table exists? Run `flask db upgrade`
3. Check Flask logs for errors

### Protected Terms Being Translated

**Fix**:
1. Verify term in `PROTECTED_TERMS` list
2. Check case sensitivity
3. Use `translate="no"` in HTML templates

## Maintenance

### Clear Translation Cache

```python
from lms import create_app
from lms.models import Translation, db

app = create_app()
with app.app_context():
    # Delete all translations for a specific language
    Translation.query.filter_by(target_language='az').delete()
    db.session.commit()
    
    # Or delete all translations
    Translation.query.delete()
    db.session.commit()
```

### Update Translations

1. Clear cache (if needed)
2. Run `python generate_translations.py`
3. Restart application

## Future Enhancements

1. **Admin UI**: Manage translations through web interface
2. **Export/Import**: Download translations as JSON/CSV
3. **Translation Memory**: Learn from manual corrections
4. **Language Detection**: Auto-detect user's preferred language
5. **URL-based Languages**: `/az/courses` instead of session
6. **More Languages**: Easy to add more target languages

## API Reference

### TranslationService Class

```python
class TranslationService:
    def get_translation(self, text, target_language, source_language=None)
        """Get cached or new translation"""
        
    def _protect_terms(self, text)
        """Replace protected terms with placeholders"""
        
    def _restore_terms(self, text, replacements)
        """Restore protected terms after translation"""
        
    def _translate_with_libretranslate(self, text, source_language, target_language)
        """Call LibreTranslate API"""
```

### Protected Terms

Current list:
- `LMS`
- `LMS`
- `lms`

Add more in `translation_service.py`:
```python
PROTECTED_TERMS = [
    'LMS',
    'LMS',
    'lms',
    'YourBrand',
    'ProductName',
    # etc.
]
```

## Support

For issues or questions:
1. Check LibreTranslate status: http://localhost:5000/languages
2. Review Flask application logs
3. Verify database has `translation` table
4. Check protected terms list in code

## License

This translation system uses:
- **LibreTranslate**: AGPLv3 (free, self-hosted)
- **deep-translator**: Apache 2.0
- **Flask-Babel**: BSD-3-Clause
