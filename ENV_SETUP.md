# Environment Setup Guide - Google File Picker

## Overview
This guide explains how to configure the Google File Picker feature in your Yonca application environment.

## Required Environment Variables

### GOOGLE_API_KEY (NEW - REQUIRED for File Picker)
The API Key is required for the Google Picker API to function.

**Get your API Key:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create a project
3. Enable these APIs under "APIs & Services → Enable APIs and Services":
   - Google Drive API
   - Google Picker API
4. Go to "Credentials" in the left sidebar
5. Click "Create Credentials" → "API Key"
6. Copy the generated key
7. (Optional) Restrict the key to just Google Drive API and your domain

**Add to environment:**

#### Development (.env file)
```bash
# In your .env file (at root of project)
GOOGLE_API_KEY=AIza_YourKeyHerexxxxxxxxxxxxxxxxxxxxx
```

#### Production (Environment Variables)
```bash
# Set in your hosting platform's environment variables
export GOOGLE_API_KEY="AIza_YourKeyHerexxxxxxxxxxxxxxxxxxxxx"

# Or in Docker:
ENV GOOGLE_API_KEY="AIza_YourKeyHerexxxxxxxxxxxxxxxxxxxxx"

# Or in systemd service file:
Environment="GOOGLE_API_KEY=AIza_YourKeyHerexxxxxxxxxxxxxxxxxxxxx"
```

### Existing Environment Variables (Already Configured)

These should already be set from your Google OAuth setup:

```bash
# Google OAuth credentials (from client_secret_*.json file)
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_secret_here

# Database URL
DATABASE_URL=sqlite:///yonca.db

# Secret key for Flask
SECRET_KEY=your_secret_key_here
```

## Verification Commands

### Check Configuration
```bash
# Verify all required Google settings are present
python -c "
from yonca import create_app
import os

app = create_app()
with app.app_context():
    print('=== Google Configuration ===')
    print(f'API Key: {\"✓\" if app.config.get(\"GOOGLE_API_KEY\") else \"✗\"}')
    print(f'Client ID: {\"✓\" if app.config.get(\"GOOGLE_CLIENT_ID\") else \"✗\"}')
    print(f'Client Secret: {\"✓\" if app.config.get(\"GOOGLE_CLIENT_SECRET\") else \"✗\"}')
    print()
    print('=== Scope Configuration ===')
    from yonca.google_drive_service import SCOPES
    print(f'Scope: {SCOPES[0]}')
    if 'drive.file' in SCOPES[0]:
        print('✓ Using least-privilege drive.file scope')
    else:
        print('✗ Not using drive.file scope!')
"
```

### Test Google Drive Access
```bash
python -c "
from yonca import create_app
from yonca.models import User

app = create_app()
with app.app_context():
    # Find a user with Google OAuth linked
    user = User.query.filter(User.google_access_token.isnot(None)).first()
    
    if not user:
        print('No user with linked Google account found')
        exit(1)
    
    from yonca.google_drive_service import authenticate
    service = authenticate(user)
    
    if service:
        print(f'✓ Successfully authenticated with Google Drive as {user.email}')
        print(f'✓ User: {user.username}')
        print(f'✓ Token expires: {user.google_token_expiry}')
    else:
        print('✗ Failed to authenticate with Google Drive')
"
```

## Deployment Checklists

### Pre-Deployment
- [ ] API Key created in Google Cloud Console
- [ ] Google Drive API enabled
- [ ] Google Picker API enabled
- [ ] API Key added to environment variables
- [ ] Environment variables verified with verification commands above
- [ ] All Python files syntax-checked
- [ ] Tested file picker in development environment

### Development Deployment
```bash
# 1. Update .env file
echo "GOOGLE_API_KEY=your_key_here" >> .env

# 2. Restart Flask
flask run

# 3. Test by visiting a page with the file picker
# 4. Verify in browser console (F12) there are no JavaScript errors
```

### Production Deployment (Linux/Systemd)
```bash
# 1. Add to systemd service file (/etc/systemd/system/yonca.service)
# Under [Service] section:
Environment="GOOGLE_API_KEY=your_key_here"

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Restart application
sudo systemctl restart yonca

# 4. Verify
sudo systemctl status yonca
sudo journalctl -u yonca -f
```

### Production Deployment (Docker)
```dockerfile
# In Dockerfile
ENV GOOGLE_API_KEY=${GOOGLE_API_KEY}

# Or in docker-compose.yml
services:
  web:
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
```

### Production Deployment (Hosting Platform)

#### Heroku
```bash
# Set environment variable
heroku config:set GOOGLE_API_KEY=your_key_here -a your-app-name

# Verify
heroku config:get GOOGLE_API_KEY -a your-app-name
```

#### AWS
In AWS Elastic Beanstalk or App Runner console:
- Navigate to "Environment Properties" or "Configuration"
- Add: `GOOGLE_API_KEY` = `your_key_here`
- Deploy

#### DigitalApp Cloud
In App Platform dashboard:
- Click your app
- Settings → Environment variables
- Add: key=`GOOGLE_API_KEY`, value=`your_key_here`
- Deploy

#### Google Cloud Run
```bash
gcloud run deploy yonca \
  --set-env-vars GOOGLE_API_KEY=your_key_here \
  --region us-central1
```

## Troubleshooting

### API Key Not Working
**Error**: "Google API Key is not configured"

**Solution**:
```bash
# 1. Verify key is set
echo $GOOGLE_API_KEY

# 2. Verify key is in config
python -c "from yonca import create_app; app = create_app(); print(app.config.get('GOOGLE_API_KEY'))"

# 3. Restart application after adding key
# 4. Clear browser cache
```

### "Invalid API Key"
**Error**: Google Picker API returns "Invalid API Key"

**Solutions**:
1. Verify API Key is correct (copy/paste carefully)
2. Verify APIs are enabled in Google Cloud Console:
   - Google Drive API ✓
   - Google Picker API ✓
3. Verify API Key is not restricted incorrectly
   - Should allow Google Picker API
   - Should restrict to your domain

### Picker Button Appears But Doesn't Work
**Error**: Click does nothing, browser console shows errors

**Solutions**:
1. Check browser console (F12 → Console tab)
2. Look for errors related to:
   - `gapi.picker` undefined
   - Cross-origin errors
   - Invalid API key
3. Clear browser cache
4. Try in incognito/private window

### File Picker Loads but No Files Show
**Error**: Picker opens but is empty

**Solutions**:
1. Verify user is signed into Google in browser
2. Ensure user has files in their Drive
3. Check browser console for errors
4. Try signing out and back into Google

## Google Cloud Console Setup Reference

### Complete Walkthrough

1. **Create Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Click project selector → New Project
   - Name: "Yonca Application"
   - Click Create

2. **Enable APIs**
   - Left sidebar → "APIs & Services" → "Enable APIs and Services"
   - Search for "Google Drive API" → Click → Enable
   - Search for "Google Picker API" → Click → Enable
   - (Optional) Enable "Google+ API" for user info

3. **Create API Key**
   - Left sidebar → "Credentials"
   - Click "Create Credentials" → "API Key"
   - Copy the key
   - (Optional) Click the key to restrict it:
     - API restrictions: "Google Drive API", "Google Picker API"
     - Key restrictions: "Websites" → Add your domain

4. **Create OAuth Credentials** (if needed)
   - Left sidebar → "Credentials"
   - Click "Create Credentials" → "OAuth Client ID"
   - Choose "Web Application"
   - Authorized redirect URIs:
     ```
     http://127.0.0.1:5000/auth/google/link
     http://localhost:5000/auth/google/link
     https://yourdomain.com/auth/google/link
     ```

5. **Download Credentials**
   - Click the newly created credential
   - Click "Download JSON"
   - Save as `client_secret_*.json` in project root

## Security Best Practices

### API Key Security
- ✓ Restrict to your domains
- ✓ Restrict to specific APIs (Drive, Picker only)
- ✓ Store in environment variables, NOT in code
- ✗ Do NOT commit `.env` file to Git
- ✗ Do NOT put API key in HTML/JavaScript directly
- ✗ Do NOT share API key in bug reports/forums

### Environment Variable Security
- Use `.env` file only in development
- Use secure environment variable management in production
- Rotate keys regularly (quarterly recommended)
- Monitor API usage for unusual activity
- Set up billing alerts in Google Cloud Console

### OAuth Security
- Token refresh handled automatically
- Invalid tokens cleared immediately
- User can unlink account anytime
- Tokens stored in database with appropriate encryption

## Configuration File Reference

### config.py
```python
# Google API Key for Picker API
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

# Google OAuth credentials (from JSON file or env vars)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
```

### .env (Development)
```
FLASK_ENV=development
DATABASE_URL=sqlite:///yonca.db
SECRET_KEY=dev-secret-key-change-in-production
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_secret_here
GOOGLE_API_KEY=AIza_YourKeyHerexxxxxxxxxxxxxxxxxxxxx
```

## Support Resources

- [Google Cloud Documentation](https://cloud.google.com/docs)
- [Google Drive API Reference](https://developers.google.com/drive/api/v3/reference)
- [Google Picker Documentation](https://developers.google.com/picker/docs)
- [File Picker Implementation Guide](docs/GOOGLE_FILE_PICKER.md)
- [Quick Start Guide](QUICKSTART.md)

## Questions?

1. Check the troubleshooting section above
2. Review [GOOGLE_FILE_PICKER.md](docs/GOOGLE_FILE_PICKER.md)
3. Check browser console for JavaScript errors
4. Verify all environment variables are set
5. Test with verification commands above

---

**Last Updated**: February 2026
**Required For**: Google File Picker Feature
**Difficulty**: Easy (5-10 minutes)
