# Fix for Large File Upload Timeouts

## Problem
Worker timeouts occur when uploading large files (audio, video, etc.) because:
- Default gunicorn timeout is 30 seconds
- Large files take longer to upload to Google Drive
- Nginx has default file size and timeout limits

## Solution Applied

### 1. Created Gunicorn Configuration (`gunicorn_config.py`)
- **Timeout increased to 600 seconds (10 minutes)** for file uploads
- Workers: 3
- Max file size: 500MB
- Logging enabled

### 2. Updated Systemd Service (`deploy/lms.service`)
Changed from:
```bash
ExecStart=/home/magsud/work/LMS/venv/bin/gunicorn --workers 3 --bind unix:/tmp/lms.sock -m 007 wsgi:app
```

To:
```bash
ExecStart=/home/magsud/work/LMS/venv/bin/gunicorn --config gunicorn_config.py wsgi:app
```

### 3. Updated Nginx Configuration (`deploy/lms.nginx`)
Added:
- `client_max_body_size 500M` - Allow 500MB uploads
- `proxy_connect_timeout 600s` - 10 minute connection timeout
- `proxy_send_timeout 600s` - 10 minute send timeout
- `proxy_read_timeout 600s` - 10 minute read timeout
- `proxy_request_buffering off` - Stream uploads directly
- `proxy_buffering off` - Disable response buffering

## Deployment Steps

On the production server, run these commands:

```bash
# 1. Copy new files to server
scp gunicorn_config.py magsud@your-server:/home/magsud/work/LMS/
scp deploy/lms.service magsud@your-server:/home/magsud/work/LMS/deploy/
scp deploy/lms.nginx magsud@your-server:/home/magsud/work/LMS/deploy/

# 2. SSH into server
ssh magsud@your-server

# 3. Create logs directory if it doesn't exist
mkdir -p /home/magsud/work/LMS/logs

# 4. Update systemd service
sudo cp /home/magsud/work/LMS/deploy/lms.service /etc/systemd/system/
sudo systemctl daemon-reload

# 4. Update nginx configuration
sudo cp /home/magsud/work/LMS/deploy/lms.nginx /etc/nginx/sites-available/lms
sudo nginx -t  # Test configuration

# If nginx is not running, start it; otherwise reload it
sudo systemctl start nginx || sudo systemctl reload nginx

# 5. Restart gunicorn service
sudo systemctl restart lms

# 6. Check status
sudo systemctl status lms
sudo systemctl status nginx
sudo journalctl -u lms -f  # Monitor logs
```

## Verify Fix

1. Try uploading a large file (e.g., 50MB+ audio/video)
2. Monitor logs: `sudo journalctl -u lms -f`
3. Should see successful upload without timeout errors

## File Size Limits

Current limits:
- **Nginx**: 500MB max upload
- **Gunicorn**: 10 minute timeout
- **Google Drive**: No limit (API handles large files)

To increase further, modify:
- `client_max_body_size` in nginx config
- `timeout` in gunicorn_config.py

## Troubleshooting

### 502 Bad Gateway Error
If you get a 502 error after restarting:

```bash
# 1. Check if logs directory exists
mkdir -p /home/magsud/work/LMS/logs

# 2. Check gunicorn status and errors
sudo systemctl status lms
sudo journalctl -u lms -n 50 --no-pager

# 3. Check if socket file exists
ls -la /tmp/lms.sock

# 4. Check socket permissions
sudo chmod 666 /tmp/lms.sock  # Temporary fix

# 5. Restart services
sudo systemctl restart lms
sleep 2
sudo systemctl restart nginx

# 6. Verify socket was created
ls -la /tmp/lms.sock

# 7. Test the socket manually
curl --unix-socket /tmp/lms.sock http://localhost/
```

### Nginx Proxy Headers Warning
If you see: `could not build optimal proxy_headers_hash...`

Add these lines to `/etc/nginx/nginx.conf` in the `http` block:
```nginx
http {
    # ... existing config ...
    
    # Fix proxy headers hash warning
    proxy_headers_hash_max_size 1024;
    proxy_headers_hash_bucket_size 128;
    
    # ... rest of config ...
}
```
Then: `sudo systemctl restart nginx`

### Upload Timeouts
If timeouts still occur:
1. Check nginx error log: `sudo tail -f /var/log/nginx/error.log`
2. Check gunicorn log: `tail -f /home/magsud/work/LMS/logs/gunicorn-error.log`
3. Increase timeout values if needed
4. Consider implementing async background uploads for very large files

### Nginx Not Running
If nginx fails to start/reload:
```bash
sudo systemctl start nginx
sudo systemctl enable nginx  # Enable on boot
sudo systemctl status nginx
```
