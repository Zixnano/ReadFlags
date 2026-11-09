"""Conversation engine: fact extraction, prompt building, Ollama call, validation."""
import json
import logging
import os
import re
from contextlib import closing

import requests

import database

log = logging.getLogger("engine")

OLLAMA_URL = "http://localhost:11434"
MODEL = os.environ.get("READFLAGS_MODEL", "llama3.2:3b")

BANNED_PHRASES = [
    "as an ai", "language model", "i understand", "how can i help", "i'm here to help",
    "i am here to help", "feel free to", "is there anything else",
]
EMOJI_RE = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]")
VERBS = {"love": "loves", "like": "likes", "enjoy": "enjoys", "adore": "adores",
         "hate": "hates", "miss": "misses"}

_turns = {}


# ---------- characters ----------

def _row_to_char(row):
    c = dict(row)
    try:
        c["voice"] = json.loads(c.pop("voice_anchors_json") or "{}")
    except json.JSONDecodeError:
        c["voice"] = {}
    c["swiped"] = c.pop("thread_id") is not None
    c["matched"] = bool(c.pop("matched"))
    return c


def get_characters():
    """Return all character profiles with swipe/match status."""
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT c.*, t.is_matched AS matched, t.id AS thread_id FROM characters c "
            "LEFT JOIN chat_threads t ON t.character_id = c.id ORDER BY c.id"
        ).fetchall()
    return [_row_to_char(r) for r in rows]


def get_character(character_id):
    for c in get_characters():
        if c["id"] == character_id:
            return c
    raise KeyError(character_id)


def swipe(character_id, liked):
    with closing(database.connect()) as conn:
        row = conn.execute("SELECT id FROM chat_threads WHERE character_id = ?",
                           (character_id,)).fetchone()
        if row:
            conn.execute("UPDATE chat_threads SET is_matched = ? WHERE id = ?",
                         (1 if liked else 0, row["id"]))
        else:
            conn.execute("INSERT INTO chat_threads (character_id, is_matched) VALUES (?, ?)",
                         (character_id, 1 if liked else 0))
        conn.commit()


def reset_progress():
    """Forget swipes and remembered facts (for testing)."""
    with closing(database.connect()) as conn:
        conn.execute("DELETE FROM chat_threads")
        conn.execute("DELETE FROM facts")
        conn.commit()
    _turns.clear()


# ---------- facts ----------

def extract_fact(message):
    """Pull a simple fact about the player out of a message, or return None."""
    m = re.search(r"\bi\s+(?:really\s+|absolutely\s+)?(love|like|enjoy|adore|hate|miss)\s+"
                  r"(.+?)(?:[.!?,;]|\s+but\b|$)", message, re.I)
    if m:
        return f"Player {VERBS[m.group(1).lower()]} {m.group(2).strip()[:60]}"
    m = re.search(r"\bmy name is\s+([A-Za-z'\-]+)", message, re.I)
    if m:
        return f"Player's name is {m.group(1)}"
    m = re.search(r"\bi\s*(?:'m|am)\s+(?:a|an)\s+(.+?)(?:[.!?,;]|$)", message, re.I)
    if m:
        return f"Player is a {m.group(1).strip()[:60]}"
    m = re.search(r"\bi\s+work\s+(?:as|in|at)\s+(.+?)(?:[.!?,;]|$)", message, re.I)
    if m:
        return f"Player works {m.group(0).split(None, 2)[2].strip()[:60]}"
    m = re.search(r"\bi\s+live\s+in\s+(.+?)(?:[.!?,;]|$)", message, re.I)
    if m:
        return f"Player lives in {m.group(1).strip()[:60]}"
    m = re.search(r"\bi\s*(?:'m|am)\s+from\s+(.+?)(?:[.!?,;]|$)", message, re.I)
    if m:
        return f"Player is from {m.group(1).strip()[:60]}"
    return None


def _next_turn(conn, character_id):
    if character_id not in _turns:
        row = conn.execute("SELECT COALESCE(MAX(turn_added), 0) FROM facts WHERE character_id = ?",
                           (character_id,)).fetchone()
        _turns[character_id] = row[0]
    _turns[character_id] += 1
    return _turns[character_id]


def save_fact(character_id, fact_text):
    fact_text = fact_text.replace("\u2014", ", ").replace("\u2013", ", ")
    with closing(database.connect()) as conn:
        turn = _next_turn(conn, character_id)
        exists = conn.execute("SELECT 1 FROM facts WHERE character_id = ? AND fact_text = ?",
                              (character_id, fact_text)).fetchone()
        if not exists:
            conn.execute("INSERT INTO facts (character_id, fact_text, turn_added) VALUES (?, ?, ?)",
                         (character_id, fact_text, turn))
        conn.commit()


def get_facts(character_id, limit=12):
    with closing(database.connect()) as conn:
        rows = conn.execute("SELECT fact_text FROM facts WHERE character_id = ? "
                            "ORDER BY id DESC LIMIT ?", (character_id, limit)).fetchall()
    return [r["fact_text"] for r in reversed(rows)]


# ---------- generation ----------

def build_system_prompt(char, facts):
    voice = char["voice"]
    examples = " / ".join(f'"{e}"' for e in voice.get("examples", []))
    voice_text = f"{voice.get('style', '')} Examples: {examples}".strip()
    facts_text = "; ".join(facts) if facts else "none yet"
    return (f"You are {char['name']}, a {char['job']}. Attachment style: {char['attachment_style']}. "
            f"Max 3 sentences. No em dashes. Voice examples: {voice_text}. "
            f"Facts about player: {facts_text}. "
            f"Reply only with {char['name']}'s text message, no narration, no emojis.")


def validate_reply(text, name):
    """Clean model output: strip dashes, emojis, stock phrases; cap length."""
    text = (text or "").strip()
    text = re.split(r"\n\s*Player\s*:", text)[0]
    text = re.sub(rf"^{re.escape(name)}\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\*[^*]*\*", "", text)          # remove *actions*
    text = EMOJI_RE.sub("", text)
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")  # em and en dashes
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip().strip('"').strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not any(p in s.lower() for p in BANNED_PHRASES)]
    text = " ".join(kept[:3]).strip()
    if len(text) > 280:
        text = text[:280].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return text


def process_message(character_id, player_message, history=None):
    """Handle one player message and return the character's reply text.

    history: optional list of (sender, text) tuples, sender is "player" or "them".
    """
    char = get_character(character_id)
    fact = extract_fact(player_message)
    if fact:
        save_fact(character_id, fact)
        log.info("Saved fact: %s", fact)
    facts = get_facts(character_id)

    lines = []
    for sender, text in (history or [])[-8:]:
        lines.append(f"{'Player' if sender == 'player' else char['name']}: {text}")
    lines.append(f"Player: {player_message}")
    lines.append(f"{char['name']}:")

    payload = {
        "model": MODEL,
        "system": build_system_prompt(char, facts),
        "prompt": "\n".join(lines),
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.8, "num_predict": 90, "stop": ["\nPlayer:"]},
    }
    fallback = char["voice"].get("fallback", "Sorry, say that again?")
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        reply = validate_reply(r.json().get("response", ""), char["name"])
        return reply or fallback
    except Exception:
        log.exception("Ollama call failed")
        return fallback
