"""
core/storage/log_store.py

CORRECTED. My first pass reconstructed a schema I couldn't verify
(the file was truncated when I first read it) and got it wrong --
invented columns like tts_provider_used, publish_dry_run, hashtags,
etc. The real schema is much simpler:

    id, timestamp, title, video_id, status, error

One deliberate, additive difference from the real file, not a silent
one: added a `brand_id` column. This is required for a shared log
store to be usable across brands at all -- every other column matches
exactly. If you'd rather keep fully separate DB files per brand
(matching the real file's single-brand "horror_log.db" naming) instead
of one shared file with a brand_id column, that's a one-line change
here plus a config value -- flag if you want that instead.
"""
import sqlite3
from datetime import datetime


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id TEXT NOT NULL,
            timestamp TEXT,
            title TEXT,
            video_id TEXT,
            status TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_result(db_path: str, brand_id: str, title: str, video_id: str,
               status: str, error: str = None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO posts (brand_id, timestamp, title, video_id, status, error) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (brand_id, datetime.now().isoformat(), title, video_id or "", status, error or ""),
    )
    conn.commit()
    conn.close()
