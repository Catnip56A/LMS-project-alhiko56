# Gunicorn configuration file for Yonca
import os

# Server socket
bind = "0.0.0.0:8000"

# Worker processes — default: (2 × CPU) + 1, override via WEB_CONCURRENCY
workers = int(os.environ.get("WEB_CONCURRENCY", 3))
worker_class = "sync"

# Trust proxy headers from Caddy (needed for correct remote IP and HTTPS detection)
forwarded_allow_ips = "*"

# Timeout settings
# Increased timeout for large file uploads (10 minutes)
timeout = 600
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "/app/logs/gunicorn-access.log"
errorlog = "/app/logs/gunicorn-error.log"
loglevel = "info"

# Process naming
proc_name = "yonca"

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Application settings
# Allow large file uploads (500MB max)
max_requests = 1000
max_requests_jitter = 50
