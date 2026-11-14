import sqlite3
from datetime import datetime

DB_PATH = "sitelog.db"


def get_conn() -> sqlite3.Connection:
    """Opens a SQLite connection with a 30s wait timeout so requests never collide."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Creates tables if they don't exist and seeds past history for GENERATOR-07."""
    conn = get_conn()
    cur = conn.cursor()

    # Enable WAL mode so reading and writing at the same time never locks the database
    cur.execute("PRAGMA journal_mode=WAL;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            note TEXT NOT NULL,
            logged_date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            handwritten_note TEXT NOT NULL,
            priority TEXT NOT NULL,
            sla_deadline TEXT NOT NULL,
            escalation_reason TEXT NOT NULL,
            confidence REAL NOT NULL,
            crop_url TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("SELECT COUNT(*) FROM inspection_history WHERE asset_id = 'GENERATOR-07'")
    if cur.fetchone()[0] == 0:
        seed_rows = [
            ("GENERATOR-07", "Oil Seal", "Minor oil misting near lower gasket", "2026-10-28"),
            ("GENERATOR-07", "Oil Seal", "Small oil drip spotted after 4hr run", "2026-11-05"),
        ]
        cur.executemany(
            "INSERT INTO inspection_history (asset_id, item_name, note, logged_date) VALUES (?, ?, ?, ?)",
            seed_rows,
        )

    conn.commit()
    conn.close()


def get_past_issue_count(asset_id: str) -> int:
    """Counts how many times this exact machine has had warnings in the past."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM inspection_history WHERE UPPER(asset_id) = UPPER(?)",
        (asset_id.strip(),),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def log_issue_to_history(
    asset_id: str,
    item_name: str,
    note: str,
    conn: sqlite3.Connection = None,
) -> None:
    """Reuses the open database connection (if provided) so SQLite doesn't lock itself."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()

    conn.execute(
        "INSERT INTO inspection_history (asset_id, item_name, note, logged_date) VALUES (?, ?, ?, ?)",
        (asset_id.upper().strip(), item_name, note, datetime.now().strftime("%Y-%m-%d")),
    )

    if owns_conn:
        conn.commit()
        conn.close()