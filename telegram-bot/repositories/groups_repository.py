import logging
from typing import List

from db.database import get_connection
from models import Group


class GroupsRepository:
    def get_all_groups(self) -> List[Group]:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, name FROM groups ORDER BY name")
            rows = cursor.fetchall()
            return [Group(id=row[0], name=row[1]) for row in rows]
        except Exception:
            logging.exception("Failed to fetch groups")
            raise
        finally:
            conn.close()

    def create_or_update_group(self, group_id: str, name: str) -> Group:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO groups (id, name) VALUES (?, ?)",
                (group_id, name),
            )
            conn.commit()
            return Group(id=group_id, name=name)
        except Exception:
            conn.rollback()
            logging.exception("Failed to create or update group %s", group_id)
            raise
        finally:
            conn.close()
