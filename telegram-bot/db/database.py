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
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                full_name TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_groups (
                username TEXT NOT NULL,
                group_id TEXT NOT NULL,
                PRIMARY KEY (username, group_id),
                FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_groups_username ON user_groups (username)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_groups_group_id ON user_groups (group_id)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_group_task_id ON tasks (group_task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks (assigned_to)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)"
        )
        cursor.executemany(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
            [
                ("task_created", "true"),
                ("task_completed", "true"),
                ("task_deleted", "true"),
                ("overdue_reminder", "true"),
                ("admins", "[]"),
                ("group_chat_ids", "[]"),
            ],
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
