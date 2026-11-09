"""SQLite schema and seed data for Read Flags.

Run directly (python app/database.py) to create database.db in the project root.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    job TEXT,
    bio TEXT,
    image_path TEXT DEFAULT '',
    is_blind_profile INTEGER DEFAULT 0,
    attachment_style TEXT,
    pace REAL,
    warmth REAL,
    volatility REAL,
    openness REAL,
    voice_anchors_json TEXT
);

CREATE TABLE IF NOT EXISTS relationship_state (
    character_id INTEGER PRIMARY KEY REFERENCES characters(id),
    trust REAL DEFAULT 3,
    interest REAL DEFAULT 4,
    comfort REAL DEFAULT 3,
    mood TEXT DEFAULT 'neutral',
    internal_conflict TEXT DEFAULT '',
    conflict_state TEXT DEFAULT 'none'
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    fact_text TEXT NOT NULL,
    turn_added INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    is_matched INTEGER DEFAULT 0,
    pending_reply TEXT,
    land_at REAL
);
"""

SEED_CHARACTERS = [
    {
        "id": 1,
        "name": "Nadia",
        "age": 29,
        "job": "ER nurse",
        "bio": "ER nurse. Night shifts, strong opinions about coffee. Don't open with hey.",
        "attachment_style": "anxious-avoidant",
        "pace": 0.3, "warmth": 0.6, "volatility": 0.4, "openness": 0.5,
        "voice": {
            "style": "Uses proper punctuation and capitalization. Dry, warm humor. Short answers when guarded.",
            "examples": [
                "Fine. But you owe me a coffee for that.",
                "I just got off a long shift. Ask me something better than how I am.",
                "That is either charming or a red flag. I haven't decided.",
            ],
            "fallback": "Sorry, I got paged. Say that again?",
        },
    },
    {
        "id": 2,
        "name": "Jules",
        "age": 26,
        "job": "bike mechanic",
        "bio": "bike mechanic. lowercase enthusiast. i will judge your playlist.",
        "attachment_style": "dismissive-avoidant",
        "pace": 0.6, "warmth": 0.4, "volatility": 0.5, "openness": 0.4,
        "voice": {
            "style": "all lowercase, short bursts of a few words, minimal punctuation, casual and a little guarded.",
            "examples": [
                "lol ok",
                "wait thats actually kinda cool",
                "idk man. maybe",
            ],
            "fallback": "lol sorry my phone glitched. what",
        },
    },
    {
        "id": 3,
        "name": "Elara",
        "age": 33,
        "job": "archivist",
        "bio": "Archivist. I prefer letters to texts, but I am adapting. Please use full sentences.",
        "attachment_style": "secure",
        "pace": 0.4, "warmth": 0.7, "volatility": 0.2, "openness": 0.6,
        "voice": {
            "style": "Formal, complete sentences. Courteous and precise vocabulary. No slang and no contractions.",
            "examples": [
                "I would be delighted to hear more about that.",
                "That is a curious answer. Please, continue.",
                "I confess I did not expect such honesty so early in our correspondence.",
            ],
            "fallback": "My apologies, I was distracted for a moment. Could you repeat that?",
        },
    },
]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables and seed the three starting characters if empty."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        if count == 0:
            for c in SEED_CHARACTERS:
                conn.execute(
                    "INSERT INTO characters (id, name, age, job, bio, image_path, is_blind_profile,"
                    " attachment_style, pace, warmth, volatility, openness, voice_anchors_json)"
                    " VALUES (?, ?, ?, ?, ?, '', 0, ?, ?, ?, ?, ?, ?)",
                    (c["id"], c["name"], c["age"], c["job"], c["bio"], c["attachment_style"],
                     c["pace"], c["warmth"], c["volatility"], c["openness"], json.dumps(c["voice"])),
                )
                conn.execute(
                    "INSERT INTO relationship_state (character_id) VALUES (?)", (c["id"],)
                )
        conn.commit()
    finally:
        conn.close()
    return DB_PATH


if __name__ == "__main__":
    path = init_db()
    print(f"Database ready: {path}")
