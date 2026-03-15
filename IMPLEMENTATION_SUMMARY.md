# Google Drive File Picker Implementation Summary

## Overview
The Yonca application has been updated to implement Google Drive file picker functionality using the `drive.file` OAuth scope. This provides users with a secure, least-privilege way to select and import files from Google Drive.

## Changes Made

### 1. Configuration Updates

#### `yonca/config.py`
- Added `GOOGLE_API_KEY` configuration parameter
- This is required for the Google Picker API to function
- Set via environment variable: `GOOGLE_API_KEY=your_key_here`

```python
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
```

### 2. Google Drive Service Updates

#### `yonca/google_drive_service.py`
- **Changed OAuth Scope**: Updated from `https://www.googleapis.com/auth/drive` to `https://www.googleapis.com/auth/drive.file`
- **Benefit**: Users can only access files they explicitly select via Picker or files created by the application
- **Least Privilege**: No access to private user files unless they're shared with the app

```python
SCOPES = ['https://www.googleapis.com/auth/drive.file']
```

### 3. Authentication Routes Updates

#### `yonca/routes/auth.py`
- Updated OAuth scope in `link_google_account()` function (line 154)
- Changed from: `'openid email profile https://www.googleapis.com/auth/drive'`
- Changed to: `'openid email profile https://www.googleapis.com/auth/drive.file'`
- Ensures consistency with Google Drive service configuration

### 4. New Frontend Component

#### `yonca/templates/components/google_file_picker.html` (NEW)
A reusable UI component that:
- Provides a "Choose from Google Drive" button
- Initializes Google Picker API
- Handles user authentication with Google
- Displays selected file information
- Emits custom `googleFileSelected` event for parent forms
- Shows file preview with ID and type

**Usage**: Simply include in any template:
```html
{% include 'components/google_file_picker.html' %}
```

### 5. API Endpoints

#### `yonca/routes/api.py`

**Added two new endpoints:**

##### POST `/api/import-drive-file`
Imports any Google Drive file or folder selected via the Picker.

Request:
```json
{
    "file_id": "Google Drive file ID",
    "file_name": "Optional filename",
    "mime_type": "application/vnd.google-apps.folder or other mime type"
}
```

Response:
```json
{
    "success": true,
    "message": "File successfully imported",
    "data": {
        "file_id": "...",
        "name": "filename",
        "mime_type": "...",
        "size": 12345,
        "view_link": "https://drive.google.com/...",
        "icon_link": "..."
    }
}
```

##### POST `/api/import-drive-file-to-resource`
Imports a Google Drive file to create or update a Resource (for course materials).

Request:
```json
{
    "file_id": "Google Drive file ID",
    "resource_id": "Optional: update existing resource"
}
```

Response:
```json
{
    "success": true,
    "message": "New resource created with Google Drive file",
    "resource_id": 123,
    "file_data": { ... }
}
```

### 6. Documentation

#### `docs/GOOGLE_FILE_PICKER.md` (NEW)
Comprehensive guide covering:
- Setup requirements
- Google Cloud Console configuration
- Usage examples
- API endpoint documentation
- JavaScript API reference
- Scope comparison table
- Troubleshooting guide

#### `yonca/templates/add_course_resource_example.html` (NEW)
Complete working example showing:
- How to integrate the file picker in a form
- File preview after selection
- Form submission with selected file
- Error handling and user feedback
- Styling and UX considerations

## Installation/Setup Steps

### 1. Environment Configuration
```bash
# Set the Google API Key (get from Google Cloud Console)
export GOOGLE_API_KEY=your_api_key_here
```

### 2. Google Cloud Console
1. Ensure these APIs are enabled:
   - Google Drive API
   - Google Picker API

2. Create credentials:
   - OAuth 2.0 Client ID (already configured)
   - API Key (new requirement for Picker)

3. Add redirect URIs if needed:
   - `http://127.0.0.1:5000/auth/google/link` (development)
   - `https://yourdomain.com/auth/google/link` (production)

### 3. No Database Migrations Required
- The implementation uses existing Resource model
- Uses existing Google authentication tokens
- No schema changes needed

## Security Considerations

### Least Privilege Access
- ✅ Only access selected files (via Picker)
- ✅ Access to app-created files in Drive
- ❌ NO access to arbitrary user files
- ❌ NO access to shared files unless selected by user

### Token Management
- Tokens are securely stored in user database
- Automatic refresh before expiration
- Invalid tokens are cleared immediately
- User must re-authenticate if tokens fail

### CORS Handling
- Google Drive URLs configured with CORS headers in `app.py`
- Allows media streaming from Google Drive
- Secure cross-origin requests

## Implementation Details

### JavaScript Event System
The file picker emits custom events that parent components can listen to:

```javascript
document.addEventListener('googleFileSelected', function(event) {
    const {file_id, file_name, mime_type} = event.detail;
    // Handle the selected file
});
```

### Folder Support
The implementation supports both:
- Individual files (PDF, images, documents, etc.)
- Entire folders (recursively imports all files)

Folder detection is automatic based on MIME type.

### Error Handling
All endpoints include:
- Authentication checks
- Proper HTTP status codes
- Descriptive error messages
- Stack trace logging for debugging

## Testing Recommendations

### Manual Testing
1. Link a Google account to a user
2. Access a page with the file picker
3. Click "Choose from Google Drive" button
4. Select a file from Google Drive
5. Verify file information is displayed
6. Submit form and verify import in database

### Edge Cases
- Test with large files
- Test with folder selection
- Test with permission-denied files
- Test with expired tokens
- Test without Google API Key configured

## Migration Path

### For Existing Users
- No action required
- Existing Google Drive integrations continue to work
- May see re-consent dialog on first use of new scope
- Backward compatible with previously accessed files

### For New Features
- Use `/api/import-drive-file` for standalone imports
- Use `/api/import-drive-file-to-resource` for course resources
- Include the file picker component in forms

## Future Enhancements

Potential improvements:
1. Add drag-and-drop support
2. Multiple file selection
3. Progress indicator for large imports
4. File filtering by type in Picker
5. Caching for frequently accessed files
6. Batch import from folder selections
7. Integration with admin dashboard
8. File management UI for uploaded resources

## Files Modified

1. `yonca/config.py` - Added GOOGLE_API_KEY config
2. `yonca/google_drive_service.py` - Changed scope to drive.file
3. `yonca/routes/auth.py` - Updated OAuth scope
4. `yonca/routes/api.py` - Added new endpoints and imports

## Files Created

1. `yonca/templates/components/google_file_picker.html` - Reusable file picker component
2. `yonca/templates/add_course_resource_example.html` - Example implementation
3. `docs/GOOGLE_FILE_PICKER.md` - Comprehensive documentation
4. `IMPLEMENTATION_SUMMARY.md` - This file

## Rollback Instructions

If needed to revert to previous `drive` scope:

1. In `yonca/google_drive_service.py` line 16:
   ```python
   SCOPES = ['https://www.googleapis.com/auth/drive']
   ```

2. In `yonca/routes/auth.py` line 154:
   ```python
   scope = 'openid email profile https://www.googleapis.com/auth/drive'
   ```

3. Remove the new endpoints from `yonca/routes/api.py`
4. Delete the file picker component and documentation

## Support & Troubleshooting

### Common Issues

**"Google API Key is not configured"**
- Set `GOOGLE_API_KEY` environment variable
- Verify API Key in Google Cloud Console

**"Picker API not loaded"**
- Check browser console for errors
- Verify Google APIs are enabled in Cloud Console
- Clear browser cache and reload

**"Failed to authenticate with Google"**
- Ensure user has linked Google account
- Check token expiration
- Verify OAuth credentials

**Files not appearing in Picker**
- Confirm Google Drive API is enabled
- Verify user has files in Google Drive
- Check browser permissions for Google Drive

## Questions?

Refer to:
1. `docs/GOOGLE_FILE_PICKER.md` - Comprehensive guide
2. `docs/FUNCTIONALITY.md` - Overall features
3. Code comments in `yonca/google_drive_service.py`
4. API endpoint docstrings in `yonca/routes/api.py`
