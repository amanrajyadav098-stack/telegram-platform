import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(os.getenv("DATABASE_URL"))

conn.execute(
    """
    INSERT INTO videos
        (title, language, quality, file_size_bytes, duration_seconds)
    VALUES
        (%s, %s, %s, %s, %s)
    """,
    (
        "Test Movie",
        "Hindi",
        "1080p",
        500000000,
        7200,
    ),
)

conn.commit()
conn.close()

print("TEST VIDEO ADDED")