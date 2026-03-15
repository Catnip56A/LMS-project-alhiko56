# Google File Picker - Quick Start Guide

## 5-Minute Setup

### Step 1: Get Your Google API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create one)
3. Enable these APIs:
   - Google Drive API
   - Google Picker API
4. Go to "Credentials" → "Create Credentials" → "API Key"
5. Copy your API Key

### Step 2: Add Environment Variable
```bash
# Add to your .env or environment
GOOGLE_API_KEY=your_api_key_from_step_1
```

### Step 3: Restart Your Application
```bash
# If using Flask dev server
flask run

# If using gunicorn
gunicorn -c gunicorn_config.py wsgi:app
```

## Using the File Picker

### In Any Template
```html
{% include 'components/google_file_picker.html' %}
```

### In a Form
```html
<form id="myForm">
    <!-- Your form fields -->
    
    <!-- Add file picker -->
    {% include 'components/google_file_picker.html' %}
    
    <button type="submit">Submit</button>
</form>

<script>
document.getElementById('myForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const fileId = document.getElementById('selectedFileId').value;
    const fileName = document.getElementById('selectedFileName').textContent;
    
    if (!fileId) {
        alert('Please select a file');
        return;
    }
    
    // Send to your API endpoint
    fetch('/api/import-drive-file', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            file_id: fileId,
            file_name: fileName
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            console.log('File imported:', data.data);
        } else {
            alert('Error: ' + data.message);
        }
    });
});
</script>
```

## API Endpoints

### Import File
```bash
curl -X POST http://localhost:5000/api/import-drive-file \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "YOUR_GOOGLE_DRIVE_FILE_ID",
    "file_name": "MyFile.pdf",
    "mime_type": "application/pdf"
  }'
```

### Create Resource from File
```bash
curl -X POST http://localhost:5000/api/import-drive-file-to-resource \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "YOUR_GOOGLE_DRIVE_FILE_ID"
  }'
```

## Testing

### Test Without Integration
```python
# In Python shell
from yonca.google_drive_service import authenticate, import_drive_file
from yonca.models import User

user = User.query.filter_by(username='testuser').first()
service = authenticate(user)

# Import a file
result = import_drive_file(service, 'YOUR_FILE_ID')
print(result)
```

### Check Configuration
```python
from flask import current_app

# Verify API Key is set
api_key = current_app.config.get('GOOGLE_API_KEY')
print(f"API Key configured: {'Yes' if api_key else 'No'}")

# Verify OAuth credentials
client_id = current_app.config.get('GOOGLE_CLIENT_ID')
print(f"OAuth configured: {'Yes' if client_id else 'No'}")
```

## Troubleshooting

### Issue: "Google API Key is not configured"
**Solution**: 
```bash
# Make sure GOOGLE_API_KEY is set
export GOOGLE_API_KEY=your_key
# Restart Flask
```

### Issue: File picker button appears but nothing happens
**Solution**:
1. Check browser console (F12 → Console tab)
2. Look for JavaScript errors
3. Verify API is enabled in Google Cloud Console
4. Clear browser cache

### Issue: "Access denied" error
**Solution**:
1. Ensure user has linked Google account
2. Check token expiration: `User.google_token_expiry`
3. Try unlinking and re-linking Google account

### Issue: No files appear in picker
**Solution**:
1. Verify user has files in Google Drive
2. Ensure Google Drive API is enabled
3. Check that client has Google Drive files

## What Scope Change Means

### Before (`drive` scope)
- Could access ALL files in user's Drive
- Higher security risk
- More permissions than needed

### After (`drive.file` scope)
- Only access selected files via Picker
- Only access app's created files
- No unauthorized access
- More secure (least privilege)

### For Users
- May see "Request new permissions" dialog first time
- Need to use Picker to select files (can't paste URLs)
- More control over what app can access

## Next Steps

1. **Add to Admin Dashboard**
   - Use file picker in resource management
   - Bulk import capabilities

2. **Add to Course Pages**
   - Let instructors easily add course materials
   - Import from Drive directly

3. **Add to User Profiles**
   - Let users import profile pictures
   - Store education documents

## File Structure
```
yonca/
├── config.py                                    (updated)
├── google_drive_service.py                      (updated)
├── routes/
│   ├── auth.py                                  (updated)
│   └── api.py                                   (updated)
└── templates/
    ├── components/
    │   └── google_file_picker.html             (NEW)
    └── add_course_resource_example.html        (NEW)

docs/
├── GOOGLE_FILE_PICKER.md                       (NEW)
└── ...

IMPLEMENTATION_SUMMARY.md                       (NEW)
QUICKSTART.md                                   (NEW)
```

## Support

For detailed documentation, see:
- [Google File Picker Documentation](docs/GOOGLE_FILE_PICKER.md)
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
- [Example Integration](yonca/templates/add_course_resource_example.html)

## Command Reference

```bash
# Set API Key in .env
echo "GOOGLE_API_KEY=your_key_here" >> .env

# Verify configuration
python -c "
from yonca import create_app
app = create_app()
with app.app_context():
    print('API Key:', bool(app.config.get('GOOGLE_API_KEY')))
    print('Client ID:', bool(app.config.get('GOOGLE_CLIENT_ID')))
"

# Test import function
python -c "
from yonca import create_app
from yonca.models import User
from yonca.google_drive_service import authenticate, import_drive_file

app = create_app()
with app.app_context():
    user = User.query.first()
    if user and user.google_access_token:
        service = authenticate(user)
        print('Google Drive authenticated:', bool(service))
"
```

---

**Last Updated**: February 2026
**Status**: Ready for Production
