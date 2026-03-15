# Google File Picker Implementation Guide

## Overview
The application now supports Google Drive file/folder selection using the `drive.file` scope for least-privilege access. This scope ensures that:
- Users can only access files they explicitly select via the Picker dialog
- Files created by the application in Google Drive
- No access to private user files unless shared with the app

## Setup Requirements

### 1. Google Cloud Console Configuration
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable these APIs:
   - Google Drive API
   - Google Picker API

3. Create credentials:
   - OAuth 2.0 Client ID (already configured)
   - API Key (new - needed for Picker)

4. Set environment variable:
   ```bash
   GOOGLE_API_KEY=your_api_key_here
   ```

### 2. OAuth Scope Change
The OAuth scope has been updated to:
```
https://www.googleapis.com/auth/drive.file
```

## Using the File Picker

### Basic Integration
To add the file picker to any template:

```html
<!-- Include the file picker component -->
{% include 'components/google_file_picker.html' %}
```

Make sure to pass these variables to the template:
```python
return render_template('your_template.html', 
                      google_client_id=current_app.config.get('GOOGLE_CLIENT_ID'),
                      google_api_key=current_app.config.get('GOOGLE_API_KEY'))
```

### In a Form
```html
<form id="resourceForm">
    <div class="form-group">
        <label>Resource Name</label>
        <input type="text" id="resourceName" class="form-control" required>
    </div>
    
    <!-- File Picker -->
    {% include 'components/google_file_picker.html' %}
    
    <button type="submit" class="btn btn-primary">Create Resource</button>
</form>

<script>
// Listen for file selection
document.addEventListener('googleFileSelected', function(event) {
    const fileData = event.detail;
    console.log('Selected file:', fileData);
    // You can now use fileData.file_id in your submission
});

// Submit form with selected file
document.getElementById('resourceForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const fileId = document.getElementById('selectedFileId').value;
    if (!fileId) {
        alert('Please select a file first');
        return;
    }
    
    // Send to backend API
    fetch('/api/import-drive-file-to-resource', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            file_id: fileId,
            resource_name: document.getElementById('resourceName').value
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            alert('Resource created successfully!');
            // Refresh or redirect
        } else {
            alert('Error: ' + data.message);
        }
    });
});
</script>
```

## API Endpoints

### Import Google Drive File
**POST** `/api/import-drive-file`

Request body:
```json
{
    "file_id": "Google Drive file ID",
    "file_name": "Optional file name",
    "mime_type": "application/vnd.google-apps.folder or other mime type"
}
```

Response (success):
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

### Import to Resource
**POST** `/api/import-drive-file-to-resource`

Request body:
```json
{
    "file_id": "Google Drive file ID",
    "resource_id": "Optional: update existing resource"
}
```

Response (creates new resource):
```json
{
    "success": true,
    "message": "New resource created with Google Drive file",
    "resource_id": 123,
    "file_data": { ... }
}
```

## JavaScript API

### Getting the Selected File ID
```javascript
const fileId = document.getElementById('selectedFileId').value;
```

### Clearing Selection
```javascript
document.getElementById('pickerResult').style.display = 'none';
document.getElementById('selectedFileId').value = '';
```

### Listening for Selection Events
```javascript
document.addEventListener('googleFileSelected', function(event) {
    const {file_id, file_name, mime_type} = event.detail;
    // Handle selection
});
```

## Scope Differences

| Feature | `drive` | `drive.file` |
|---------|---------|------------|
| Access all files | ✅ | ❌ |
| Access app-created files | ✅ | ✅ |
| Access picker-selected files | ✅ | ✅ |
| Least privilege | ❌ | ✅ |
| Recommended for users | ❌ | ✅ |

## Important Notes

1. **User Confirmation**: Users must explicitly select files via the Picker - you cannot import arbitrary URLs
2. **Token Refresh**: The app handles automatic token refresh for expired credentials
3. **Error Handling**: Always check for 'error' field in API responses
4. **CORS**: Google Drive URLs are already configured with proper CORS headers
5. **Folder Support**: The Picker can select entire folders - the API recursively imports all files

## Troubleshooting

### "Google API Key is not configured"
- Set the `GOOGLE_API_KEY` environment variable
- Verify the API Key in Google Cloud Console

### "Failed to authenticate with Google"
- Ensure user has linked their Google account
- Check token expiration and refresh flow
- Verify OAuth credentials in `client_secret_*.json`

### Files not appearing in Picker
- Check that Google Drive API is enabled in Cloud Console
- Verify OAuth scope includes `drive.file`
- Ensure user has authenticated

## Migration Notes

If upgrading from `drive` scope:
- No changes needed for existing functionality
- `drive.file` is backward compatible for previously accessed files
- User may see permission re-consent dialog on first use
