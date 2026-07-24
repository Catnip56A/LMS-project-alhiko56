# Language-Specific Images

## Overview
The LMS platform now supports displaying different images based on the user's selected language. This feature automatically switches images when users change the website language between English (en), Azerbaijani (az), and Russian (ru).

## How It Works

### 1. Configuration
The system uses dictionaries in `config.py` to map languages to specific image paths:

```python
ABOUT_FEATURES_IMAGES = {
    'en': '/static/permanent/LMS_features_en.png',
    'az': '/static/permanent/LMS_features_az.png',
    'ru': '/static/permanent/LMS_features_ru.png',
}

ABOUT_HERO_BACKGROUND_IMAGES = {
    'en': '/static/permanent/Bg_aboutCompany_en.png',
    'az': '/static/permanent/Bg_aboutCompany_az.png',
    'ru': '/static/permanent/Bg_aboutCompany_ru.png',
}
```

### 2. Template Helper Function
A new `get_localized_image()` helper function is available in all templates:

```python
def get_localized_image(image_dict, fallback=''):
    """Get image URL based on current locale"""
    locale = str(get_locale()) if get_locale() else 'en'
    if isinstance(image_dict, dict):
        return image_dict.get(locale, image_dict.get('en', fallback))
    return fallback
```

### 3. Usage in Templates
In templates, use the helper function to automatically select the correct image:

```html
<!-- For feature images -->
<img src="{{ get_localized_image(config.ABOUT_FEATURES_IMAGES, config.ABOUT_FEATURES_IMAGE) }}" alt="Features">

<!-- For background images -->
<div style="background-image: url('{{ get_localized_image(config.ABOUT_HERO_BACKGROUND_IMAGES, config.ABOUT_HERO_BACKGROUND_IMAGE) }}');">
```

## Adding New Language-Specific Images

### Step 1: Create Language-Specific Image Files
Place your images in the `static/permanent/` directory with language suffixes:
- `image_name_en.png` (English)
- `image_name_az.png` (Azerbaijani)
- `image_name_ru.png` (Russian)

### Step 2: Update Configuration
Add the image configuration to `lms/config.py`:

```python
# In DevelopmentConfig, TestingConfig, and ProductionConfig
YOUR_IMAGE_NAME_IMAGES = {
    'en': '/static/permanent/image_name_en.png',
    'az': '/static/permanent/image_name_az.png',
    'ru': '/static/permanent/image_name_ru.png',
}
YOUR_IMAGE_NAME = '/static/permanent/image_name.png'  # fallback
```

### Step 3: Use in Template
In your template file:

```html
<img src="{{ get_localized_image(config.YOUR_IMAGE_NAME_IMAGES, config.YOUR_IMAGE_NAME) }}" alt="Description">
```

## Environment Variables (Production)
For production environments, you can override image paths using environment variables:

```bash
export ABOUT_FEATURES_IMAGE_EN="/path/to/features_en.png"
export ABOUT_FEATURES_IMAGE_AZ="/path/to/features_az.png"
export ABOUT_FEATURES_IMAGE_RU="/path/to/features_ru.png"
export ABOUT_HERO_BACKGROUND_IMAGE_EN="/path/to/bg_en.png"
export ABOUT_HERO_BACKGROUND_IMAGE_AZ="/path/to/bg_az.png"
export ABOUT_HERO_BACKGROUND_IMAGE_RU="/path/to/bg_ru.png"
```

## Currently Supported Images
- **Features Image**: Displays different feature diagrams per language
- **Hero Background**: Shows localized background images on the About page

## Fallback Behavior
If a language-specific image is not found:
1. Falls back to the English version
2. If English version doesn't exist, uses the general fallback image
3. This ensures the site always displays something, even if translations are incomplete

## Testing
To test language-specific images:
1. Navigate to the About page
2. Change the language using the language selector
3. Verify that the features image and background image change accordingly

## File Locations
- Configuration: `lms/config.py`
- Helper function: `lms/__init__.py` (in `inject_translation_helpers()`)
- Template usage: `lms/templates/index.html`
- Image files: `static/permanent/`
