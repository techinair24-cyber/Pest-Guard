import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.getenv('DATABASE_PATH', str(BASE_DIR / 'pest_guard.db')))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BASE_DIR / DATABASE_PATH


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def init_db():
    with get_connection() as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                last_seen TEXT,
                microphone_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                vibration_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                ai_status TEXT NOT NULL DEFAULT 'UNKNOWN'
            );
            CREATE TABLE IF NOT EXISTS pests (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scientific_name TEXT,
                affected_crop TEXT NOT NULL,
                description TEXT NOT NULL,
                symptoms TEXT NOT NULL,
                risk TEXT NOT NULL,
                image TEXT
            );
            CREATE TABLE IF NOT EXISTS solutions (
                pest_id TEXT PRIMARY KEY,
                pest_name TEXT NOT NULL,
                risk TEXT NOT NULL,
                affected_crop TEXT NOT NULL,
                symptoms TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                prevention TEXT NOT NULL,
                FOREIGN KEY (pest_id) REFERENCES pests(id)
            );
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                pest TEXT,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                risk TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        ''')
        connection.commit()
