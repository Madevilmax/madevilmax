import logging
import sqlite3
from typing import List

from db.database import get_connection
from models import User


class UsersRepository:
    def get_all_users(self) -> List[User]:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT u.username, u.full_name, ug.group_id
                FROM users u
                LEFT JOIN user_groups ug ON u.username = ug.username
                ORDER BY u.username
                """
            )
            users_map: dict[str, User] = {}
            for username, full_name, group_id in cursor.fetchall():
                if username not in users_map:
                    users_map[username] = User(username=username, full_name=full_name, groups=[])
                if group_id:
                    users_map[username].groups.append(group_id)
            return list(users_map.values())
        except Exception:
            logging.exception("Failed to fetch users")
            raise
        finally:
            conn.close()

    def upsert_user(self, username: str, full_name: str | None, groups: List[str]) -> User:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO users (username, full_name) VALUES (?, ?)",
                (username, full_name),
            )
            cursor.execute("DELETE FROM user_groups WHERE username = ?", (username,))
            for group_id in groups:
                cursor.execute(
                    "INSERT INTO user_groups (username, group_id) VALUES (?, ?)",
                    (username, group_id),
                )
            conn.commit()
            return User(username=username, full_name=full_name, groups=groups)
        except Exception:
            conn.rollback()
            logging.exception("Failed to upsert user %s", username)
            raise
        finally:
            conn.close()

    def update_user(self, username: str, full_name: str | None, groups: List[str]) -> User:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if cursor.fetchone() is None:
                raise ValueError(f"User {username} does not exist")
            cursor.execute(
                "UPDATE users SET full_name = ? WHERE username = ?",
                (full_name, username),
            )
            cursor.execute("DELETE FROM user_groups WHERE username = ?", (username,))
            for group_id in groups:
                cursor.execute(
                    "INSERT INTO user_groups (username, group_id) VALUES (?, ?)",
                    (username, group_id),
                )
            conn.commit()
            return User(username=username, full_name=full_name, groups=groups)
        except Exception:
            conn.rollback()
            logging.exception("Failed to update user %s", username)
            raise
        finally:
            conn.close()
