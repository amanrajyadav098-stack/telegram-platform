import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(os.getenv("DATABASE_URL"))

conn.execute(
    """
    UPDATE users
    SET access_expires_at = NOW() - INTERVAL '1 minute'
    WHERE telegram_id = %s
    """,
    (1506610221,),
)

conn.commit()
conn.close()

print("TEST EXPIRY SET")