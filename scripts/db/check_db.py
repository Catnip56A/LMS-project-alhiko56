import psycopg2
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")
parsed = urlparse(database_url)

# Construct connection to postgres database
postgres_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}/postgres"

try:
    conn = psycopg2.connect(postgres_url)
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datname = 'yonca_db'")
    result = cur.fetchone()
    print('yes' if result else 'no')
    conn.close()
except Exception as e:
    print('no')