# Deployment Checklist - Google File Picker Implementation

## Pre-Deployment Verification

### ✓ Code Changes
- [x] Updated `yonca/config.py` - Added GOOGLE_API_KEY config
- [x] Updated `yonca/google_drive_service.py` - Changed scope to drive.file
- [x] Updated `yonca/routes/auth.py` - Updated OAuth scope
- [x] Updated `yonca/routes/api.py` - Added new endpoints
- [x] Created `yonca/templates/components/google_file_picker.html` - File picker component
- [x] Created `yonca/templates/add_course_resource_example.html` - Example usage

### ✓ Syntax Verification
- [x] `yonca/google_drive_service.py` - No errors
- [x] `yonca/routes/auth.py` - No errors
- [x] `yonca/config.py` - No errors
- [x] `yonca/routes/api.py` - No errors

### ✓ Documentation
- [x] `docs/GOOGLE_FILE_PICKER.md` - Complete guide created
- [x] `IMPLEMENTATION_SUMMARY.md` - Summary created
- [x] `QUICKSTART.md` - Quick start guide created
- [x] `ENV_SETUP.md` - Environment setup guide created
- [x] `DEPLOYMENT_CHECKLIST.md` - This file

## Google Cloud Console Setup

### Required Configuration
- [ ] Google Cloud Project created
- [ ] Google Drive API enabled
- [ ] Google Picker API enabled
- [ ] API Key generated
- [ ] API Key restricted to:
  - [ ] Google Drive API
  - [ ] Google Picker API
- [ ] OAuth credentials verified (from client_secret_*.json)
- [ ] Redirect URIs configured:
  - [ ] http://127.0.0.1:5000/auth/google/link (dev)
  - [ ] https://yourdomain.com/auth/google/link (prod)

## Development Environment

### Local Setup
- [ ] .env file updated with `GOOGLE_API_KEY=your_key`
- [ ] Verified with: `python -c "from yonca import create_app; app = create_app(); print(app.config.get('GOOGLE_API_KEY'))"`
- [ ] Flask application starts without errors
- [ ] No import errors in Python files

### Local Testing
- [ ] File picker button appears on test page
- [ ] Clicking button opens Google Drive Picker
- [ ] Can select files from Google Drive
- [ ] Selected file information displays correctly
- [ ] Browser console has no JavaScript errors
- [ ] API endpoint `/api/import-drive-file` responds correctly
- [ ] File import completes successfully
- [ ] Database stores file information correctly

## Production Environment

### Environment Variables
- [ ] `GOOGLE_API_KEY` set in hosting platform
- [ ] `GOOGLE_CLIENT_ID` set in hosting platform
- [ ] `GOOGLE_CLIENT_SECRET` set in hosting platform
- [ ] `DATABASE_URL` correctly configured
- [ ] `SECRET_KEY` set to strong random value
- [ ] `FLASK_ENV=production` set

### Application Configuration
- [ ] `config.py` uses production settings
- [ ] Database migrations applied (if any)
- [ ] Static files collected/compiled
- [ ] Logging configured for production
- [ ] Error tracking enabled (Sentry, etc.)

### Google OAuth Setup
- [ ] Redirect URIs updated for production domain
- [ ] OAuth credentials are for production domain
- [ ] API Key restrictions match production domain
- [ ] HTTPS enabled for all external URLs

### Security
- [ ] No hardcoded credentials in code
- [ ] No API keys in git repository
- [ ] Environment variables secured
- [ ] HTTPS enabled (enforce redirects)
- [ ] CORS headers properly configured
- [ ] Rate limiting configured if needed
- [ ] Input validation on API endpoints

## Deployment Steps

### 1. Pre-Deployment Verification
```bash
# Clone latest code
git pull origin main

# Check for syntax errors
python -m py_compile yonca/config.py
python -m py_compile yonca/google_drive_service.py
python -m py_compile yonca/routes/auth.py
python -m py_compile yonca/routes/api.py

# Verify imports
python -c "from yonca.google_drive_service import import_drive_file, import_drive_folder"
python -c "from yonca.routes import api"
```

### 2. Environment Setup
```bash
# Set environment variables on production server
export GOOGLE_API_KEY="your_api_key_here"
export GOOGLE_CLIENT_ID="your_client_id_here"
export GOOGLE_CLIENT_SECRET="your_client_secret_here"

# Verify
echo "API Key: $GOOGLE_API_KEY"
```

### 3. Restart Application
```bash
# For systemd
sudo systemctl restart yonca
sudo systemctl status yonca

# For Docker
docker-compose restart web
docker-compose logs
```

### 4. Post-Deployment Verification
```bash
# Test configuration
curl -X GET https://yourdomain.com/

# Test file picker page loads
curl -X GET https://yourdomain.com/admin/resources

# Check application logs
tail -f /var/log/yonca.log

# Monitor for errors
# Watch for "Google API Key" or authentication errors
```

## Testing Checklist (Post-Deployment)

### User-Facing Features
- [ ] File picker button visible on appropriate pages
- [ ] Clicking button opens Google Drive Picker
- [ ] Can select files from Google Drive
- [ ] Selected files display correct information
- [ ] API endpoint accepts file selection
- [ ] Files are imported to database correctly

### API Endpoints
- [ ] `POST /api/import-drive-file` returns 200
- [ ] `POST /api/import-drive-file-to-resource` returns 201
- [ ] Invalid requests return 400
- [ ] Unauthenticated requests return 401
- [ ] Error handling returns proper messages

### Browser Compatibility
- [ ] Chrome/Chromium ✓
- [ ] Firefox ✓
- [ ] Safari ✓
- [ ] Edge ✓
- [ ] Mobile browsers (iOS Safari, Chrome Android) ✓

### Error Scenarios
- [ ] Missing API Key → proper error message
- [ ] Invalid API Key → proper error message
- [ ] User not authenticated → 401 response
- [ ] User not linked to Google → proper error message
- [ ] Network error during import → graceful handling
- [ ] File not found → proper error message
- [ ] Access denied → proper error message

## Rollback Plan

If issues occur post-deployment:

### Quick Rollback
```bash
# Revert code changes
git revert HEAD
git push origin main

# Or checkout previous version
git checkout main~1
git push origin main --force

# Restart application
sudo systemctl restart yonca
```

### Partial Rollback (Keep new code, revert scope)
```bash
# Edit yonca/google_drive_service.py
# Change: SCOPES = ['https://www.googleapis.com/auth/drive.file']
# To:     SCOPES = ['https://www.googleapis.com/auth/drive']

# Edit yonca/routes/auth.py
# Change scope from drive.file to drive

# Restart
sudo systemctl restart yonca
```

### Disable Feature Only
If file picker causes issues but rest of app works:
1. Remove `google_file_picker.html` from templates
2. Comment out API endpoints in `api.py`
3. Restart application
4. Existing functionality continues working

## Monitoring & Maintenance

### Daily Monitoring
- [ ] Check application logs for errors
- [ ] Monitor Google Drive API quota usage
- [ ] Check for failed authentication attempts
- [ ] Monitor API endpoint response times

### Weekly Tasks
- [ ] Review error logs for patterns
- [ ] Check Google Cloud Console for API alerts
- [ ] Verify API Key rotation schedule (quarterly)
- [ ] Test file picker functionality

### Monthly Tasks
- [ ] Review file import statistics
- [ ] Check disk space usage
- [ ] Review security audit logs
- [ ] Update documentation if needed

## Monitoring Commands

```bash
# Check application logs
tail -f /var/log/yonca.log | grep -i "google\|picker\|error"

# Monitor API usage
curl -X GET https://yourdomain.com/admin/api-stats

# Check Google Cloud quota
# Visit: https://console.cloud.google.com/iam-admin/quotas

# Test API endpoints
curl -X POST https://yourdomain.com/api/import-drive-file \
  -H "Content-Type: application/json" \
  -d '{"file_id":"test","file_name":"test.txt"}'
```

## Success Criteria

✓ Deployment is complete when:
1. All code changes applied without errors
2. Environment variables set and verified
3. Application starts and serves pages
4. File picker button visible on pages
5. File picker opens Google Drive dialog
6. Can select and import files from Google Drive
7. API endpoints respond correctly
8. Database stores imported file data
9. Browser console has no JavaScript errors
10. Logs show no critical errors
11. All stakeholders can access the feature
12. Documentation is accessible

## Sign-Off

- [ ] Code Review Completed
- [ ] Tests Passed
- [ ] Documentation Verified
- [ ] Google Cloud Setup Confirmed
- [ ] Deployment Executed Successfully
- [ ] Post-Deployment Tests Passed
- [ ] Stakeholders Notified
- [ ] Feature Ready for Use

## Support Contacts

- Deployment Issue: [DevOps Team]
- Google Cloud Issue: [Cloud Admin]
- Application Support: [Development Team]
- User Support: [Support Team]

## Next Steps After Deployment

1. **User Communication**
   - Announce feature availability
   - Share Quick Start guide (QUICKSTART.md)
   - Provide support contact information

2. **Training** (Optional)
   - Create video tutorial if needed
   - Provide example workflows
   - Document common use cases

3. **Feature Enhancement**
   - Collect user feedback
   - Monitor usage patterns
   - Plan improvements based on feedback

4. **Integration**
   - Add file picker to more pages
   - Create bulk import features
   - Integrate with admin dashboard

---

**Deployment Date**: _______________
**Deployed By**: _______________
**Verified By**: _______________
**Notes**: _______________

---

**Version**: 1.0
**Last Updated**: February 2026
**Status**: Ready for Deployment
