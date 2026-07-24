"""
Structured application logging — JSON-formatted rotating file handler plus a
human-readable console handler. No Flask/DB dependency beyond stdlib logging.
"""
import json
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(app=None):
    """Attach a rotating JSON file handler and a console handler to the root logger."""
    level_name = os.environ.get('LOG_LEVEL', 'DEBUG' if (app and app.debug) else 'INFO')
    level = getattr(logging, level_name.upper(), logging.INFO)

    os.makedirs(LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    file_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root_logger.addHandler(console_handler)
