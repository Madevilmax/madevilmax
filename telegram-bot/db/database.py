import logging
import sqlite3
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent.parent / "tasks.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    logging.info("Initializing database at %s", DB_PATH)
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_groups (
                group_task_id INTEGER PRIMARY KEY,
                task_text TEXT NOT NULL,
                deadline TEXT NOT NULL,
                group_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_task_id INTEGER NOT NULL,
                assigned_to TEXT NOT NULL,
                assigned_by TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY (group_task_id) REFERENCES task_groups (group_task_id)
            )
            """
        )
        connection.commit()
        logging.info("Database initialized successfully")
    except Exception:
        if connection:
            connection.rollback()
        logging.exception("Failed to initialize database")
        raise
    finally:
        if connection:
            connection.close()
