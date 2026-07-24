# Fix for Large File Upload Timeouts - Caddy Version

## Problem
Worker timeouts occur when uploading large files (audio, video, etc.) because:
- Default gunicorn timeout is 30 seconds
- Large files take longer to upload to Google Drive
- Default file size and timeout limits

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

### 3. Created Caddyfile Configuration (`deploy/Caddyfile`)
Features:
- `max_size 500MB` - Allow 500MB uploads
- `dial_timeout 10m` - 10 minute connection timeout
- `response_header_timeout 10m` - 10 minute response timeout
- Automatic HTTPS with Let's Encrypt
- Gzip compression
- Security headers

## Deployment Steps

On the production server, run these commands:

```bash
# 1. Copy new files to server
scp gunicorn_config.py magsud@your-server:/home/magsud/work/LMS/
scp deploy/lms.service magsud@your-server:/home/magsud/work/LMS/deploy/
scp deploy/Caddyfile magsud@your-server:/home/magsud/work/LMS/deploy/

# 2. SSH into server
ssh magsud@your-server

# 3. Create logs directory if it doesn't exist
mkdir -p /home/magsud/work/LMS/logs

# 4. Update systemd service
sudo cp /home/magsud/work/LMS/deploy/lms.service /etc/systemd/system/
sudo systemctl daemon-reload

# 5. Update Caddy configuration
sudo cp /home/magsud/work/LMS/deploy/Caddyfile /etc/caddy/Caddyfile

# 6. Test Caddy configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# 7. Restart services
sudo systemctl restart lms
sudo systemctl restart caddy

# 8. Check status
sudo systemctl status lms
sudo systemctl status caddy
```

## Verify Fix

1. Try uploading a large file (e.g., 50MB+ audio/video)
2. Monitor logs: `sudo journalctl -u lms -f`
3. Should see successful upload without timeout errors

## File Size Limits

Current limits:
- **Caddy**: 500MB max upload
- **Gunicorn**: 10 minute timeout
- **Google Drive**: No limit (API handles large files)

To increase further, modify:
- `max_size` in Caddyfile
- `timeout` in gunicorn_config.py

## Troubleshooting

### 502 Bad Gateway Error
If you get a 502 error:

```bash
# 1. Check if logs directory exists
mkdir -p /home/magsud/work/LMS/logs

# 2. Check gunicorn status and errors
sudo systemctl status lms
sudo journalctl -u lms -n 50 --no-pager

# 3. Check if socket file exists
ls -la /tmp/lms.sock

# 4. Restart services
sudo systemctl restart lms
sleep 2
sudo systemctl restart caddy

# 5. Verify socket was created
ls -la /tmp/lms.sock
```

### Upload Timeouts
If timeouts still occur:
1. Check Caddy error log: `sudo journalctl -u caddy -n 50`
2. Check gunicorn log: `tail -f /home/magsud/work/LMS/logs/gunicorn-error.log`
3. Increase timeout values if needed

### Caddy Not Starting
If Caddy fails to start:
```bash
sudo systemctl status caddy
sudo journalctl -u caddy -n 50
sudo caddy validate --config /etc/caddy/Caddyfile
```

### HTTPS Certificate Issues
Caddy automatically gets Let's Encrypt certificates. If there are issues:
```bash
# Check Caddy logs
sudo journalctl -u caddy -f

# Make sure ports 80 and 443 are open
sudo ufw allow 80
sudo ufw allow 443

# Verify domain DNS points to your server
dig magsud.yourdomain.example.com
```

## Advantages of Caddy

1. **Automatic HTTPS** - No need to manually configure SSL certificates
2. **Simpler configuration** - Easier to read and maintain
3. **Better defaults** - Secure by default
4. **Automatic renewal** - Let's Encrypt certificates renew automatically
5. **HTTP/2 and HTTP/3** support out of the box
