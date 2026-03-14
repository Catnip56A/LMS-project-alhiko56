# Yonca Additional Scripts

This folder contains utility scripts for testing, debugging, and maintaining the Yonca learning platform.

## Translation Scripts

### `translate_all_content.py`
Bulk translation script for all content types.
```bash
python translate_all_content.py [courses|resources|home|course_content|folders]
```

### `test_translation_quality.py`
Tests GoogleTranslator quality for Azerbaijani and Russian translations.

### `check_az_translations.py`
Checks what Azerbaijani translations exist in the database and identifies issues.

### `check_course_translations.py`
Verifies course translations are working correctly.

### `check_about_company_translations.py`
Verifies about company section translations exist.

### `clear_all_az_cache.py`
Clears all Azerbaijani translation caches (both ContentTranslation and Translation tables).

### `delete_bad_az_translations.py`
Deletes Azerbaijani translations that are identical to English source (indicating failed translation).

## Database Scripts

### `add_schema.py`
Adds database schema changes.

### `check_db.py`
Database connection and structure verification.

### `check_table.py`
Checks specific table structures.

### `reset_db.py`
Resets the database (use with caution).

### `fix_missing_columns.py`
Adds missing database columns.

### `fix_drive_links.py`
Fixes Google Drive link issues.

### `fix_resource_permissions.py`
Fixes resource permission issues.

### `migrate_token.py`
Migrates authentication tokens.

## User Management Scripts

### `create_admin.py`
Creates admin user accounts.

### `query_users.py`
Queries and displays user information.

### `delete_duplicate_google_accounts.py`
Removes duplicate Google account entries.

## Translation Testing Scripts

### `test_language_detection.py`
Tests automatic language detection functionality.

### `test_api_response.py`
Tests API endpoints return translated content correctly.

### `test_content_translation.py`
Tests content translation functions.

### `test_translation_display.py`
Tests translation display in templates.

### `test_delete_translations.py`
Documents the delete translations functionality and usage.

### `test_session.py`
Tests session management for translations.

## Legacy/Archive Scripts

### `auto_translate_po.py`
Legacy PO file translation script.

### `check_translations.py`
Legacy translation checker.

### `clear_translation_cache.py`
Legacy cache clearing script.

### `fix_translations.py`
Legacy translation fixing script.

### `generate_translations.py`
Legacy translation generation script.

### `translate_azeri.py`
Legacy Azerbaijani translation script.

### `test_auto_translation.py`
Legacy auto-translation testing.

### `test_language.py`
Legacy language testing.

## Usage Notes

- Most scripts require the Flask app context to be available
- Run scripts from the project root directory: `python Additional_scripts/script_name.py`
- Some scripts may require database access and should be run with caution in production
- Translation scripts use the free GoogleTranslator service (no API key needed)

## Recent Additions (January 2026)

- Translation quality testing and debugging scripts
- About company translation verification
- Cache management utilities
- API response testing tools