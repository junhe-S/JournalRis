"""Download record tracking via SQLite."""

import os
import sqlite3

DB_PATH = './data/record.db'


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            journal    TEXT NOT NULL,
            volume_num TEXT,
            volume     TEXT NOT NULL,
            file       TEXT NOT NULL,
            state      TEXT DEFAULT 'scanned',
            PRIMARY KEY (journal, volume)
        )
    ''')
    conn.commit()
    return conn


def is_downloaded(journal, volume):
    """Check if a volume has already been recorded."""
    conn = _connect()
    cur = conn.execute(
        'SELECT 1 FROM downloads WHERE journal = ? AND volume = ?',
        (journal, volume)
    )
    result = cur.fetchone() is not None
    conn.close()
    return result


def save(journal, volume, file, volume_num=None):
    """Record a finished download. volume_num is the volume number (e.g. '38' from '38-1')."""
    if volume_num is None:
        volume_num = volume.split('-')[0] if '-' in volume else None
    conn = _connect()
    conn.execute(
        'INSERT OR REPLACE INTO downloads (journal, volume_num, volume, file, state) VALUES (?, ?, ?, ?, ?)',
        (journal, volume_num, volume, file, 'scanned')
    )
    conn.commit()
    conn.close()
