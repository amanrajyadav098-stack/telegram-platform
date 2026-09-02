import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(os.getenv("DATABASE_URL"))

rows = conn.execute("""
    SELECT id, telegram_id, username, first_name, is_verified, access_expires_at
    FROM users
    ORDER BY id DESC
    LIMIT 10
""").fetchall()

print("USERS:")
for row in rows:
    print(row)

conn.close()