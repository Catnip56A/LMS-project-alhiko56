import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")

conn = psycopg2.connect(database_url)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'home_content'")
result = cur.fetchone()
print('yes' if result else 'no')
conn.close()