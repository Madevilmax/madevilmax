import logging
import sqlite3
from datetime import datetime
from typing import List, Optional

from db.database import get_connection
from models import Task, TaskGroup, TaskGroupUpdate


class TasksRepository:
    def get_next_group_task_id(self, connection: Optional[sqlite3.Connection] = None) -> int:
        own_connection = connection is None
        conn = connection or get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(group_task_id) FROM task_groups")
            row = cursor.fetchone()
            max_id = row[0] if row and row[0] is not None else 0
            return max_id + 1
        finally:
            if own_connection:
                conn.close()

    def create_task_group(
        self,
        task_text: str,
        deadline: str,
        group_id: str,
        assigned_to: List[str],
        assigned_by: str,
    ) -> List[Task]:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        try:
            group_task_id = self.get_next_group_task_id(conn)
            cursor.execute(
                """
                INSERT INTO task_groups (group_task_id, task_text, deadline, group_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_task_id, task_text, deadline, group_id, now),
            )

            tasks: List[Task] = []
            for executor in assigned_to:
                cursor.execute(
                    """
                    INSERT INTO tasks (
                        group_task_id, assigned_to, assigned_by, status, created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (group_task_id, executor, assigned_by, "active", now, ""),
                )
                task_id = cursor.lastrowid
                tasks.append(
                    Task(
                        id=task_id,
                        group_task_id=group_task_id,
                        assigned_to=executor,
                        assigned_by=assigned_by,
                        status="active",
                        created_at=now,
                        completed_at="",
                    )
                )
            conn.commit()
            return tasks
        except Exception:
            conn.rollback()
            logging.exception("Failed to create task group")
            raise
        finally:
            conn.close()

    def add_executors_to_group(
        self, group_task_id: int, assigned_to: List[str], assigned_by: str
    ) -> List[Task]:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        try:
            cursor.execute("SELECT 1 FROM task_groups WHERE group_task_id = ?", (group_task_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Task group {group_task_id} does not exist")

            tasks: List[Task] = []
            for executor in assigned_to:
                cursor.execute(
                    """
                    INSERT INTO tasks (
                        group_task_id, assigned_to, assigned_by, status, created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (group_task_id, executor, assigned_by, "active", now, ""),
                )
                task_id = cursor.lastrowid
                tasks.append(
                    Task(
                        id=task_id,
                        group_task_id=group_task_id,
                        assigned_to=executor,
                        assigned_by=assigned_by,
                        status="active",
                        created_at=now,
                        completed_at="",
                    )
                )
            conn.commit()
            return tasks
        except Exception:
            conn.rollback()
            logging.exception("Failed to add executors to group %s", group_task_id)
            raise
        finally:
            conn.close()

    def get_all_tasks(self) -> List[Task]:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, group_task_id, assigned_to, assigned_by, status, created_at, completed_at
                FROM tasks
                """
            )
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]
        except Exception:
            logging.exception("Failed to fetch all tasks")
            raise
        finally:
            conn.close()

    def get_tasks_by_group(self, group_task_id: int) -> List[Task]:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, group_task_id, assigned_to, assigned_by, status, created_at, completed_at
                FROM tasks
                WHERE group_task_id = ?
                """,
                (group_task_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]
        except Exception:
            logging.exception("Failed to fetch tasks for group %s", group_task_id)
            raise
        finally:
            conn.close()

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, group_task_id, assigned_to, assigned_by, status, created_at, completed_at
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            return self._row_to_task(row) if row else None
        except Exception:
            logging.exception("Failed to fetch task with id %s", task_id)
            raise
        finally:
            conn.close()

    def update_group(self, group_task_id: int, task_group_update: TaskGroupUpdate) -> TaskGroup:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            fields = []
            values = []
            if task_group_update.task_text is not None:
                fields.append("task_text = ?")
                values.append(task_group_update.task_text)
            if task_group_update.deadline is not None:
                fields.append("deadline = ?")
                values.append(task_group_update.deadline)
            if task_group_update.group_id is not None:
                fields.append("group_id = ?")
                values.append(task_group_update.group_id)

            if fields:
                values.append(group_task_id)
                cursor.execute(
                    f"UPDATE task_groups SET {', '.join(fields)} WHERE group_task_id = ?",
                    tuple(values),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Task group {group_task_id} does not exist")
                conn.commit()

            cursor.execute(
                """
                SELECT group_task_id, task_text, deadline, group_id, created_at
                FROM task_groups
                WHERE group_task_id = ?
                """,
                (group_task_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Task group {group_task_id} does not exist")
            return TaskGroup(
                group_task_id=row[0],
                task_text=row[1],
                deadline=row[2],
                group_id=row[3],
                created_at=row[4],
            )
        except Exception:
            conn.rollback()
            logging.exception("Failed to update group %s", group_task_id)
            raise
        finally:
            conn.close()

    def update_task_status(self, task_id: int, new_status: str) -> Task:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        completed_at = now if new_status == "completed" else ""
        try:
            cursor.execute(
                """
                UPDATE tasks
                SET status = ?, completed_at = ?
                WHERE id = ?
                """,
                (new_status, completed_at, task_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} does not exist")
            conn.commit()
            updated_task = self.get_task_by_id(task_id)
            if updated_task is None:
                raise ValueError(f"Task {task_id} does not exist")
            return updated_task
        except Exception:
            conn.rollback()
            logging.exception("Failed to update status for task %s", task_id)
            raise
        finally:
            conn.close()

    def delete_task(self, task_id: int) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT group_task_id FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Task {task_id} does not exist")
            group_task_id = row[0]

            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

            cursor.execute(
                "SELECT COUNT(*) FROM tasks WHERE group_task_id = ?", (group_task_id,)
            )
            remaining = cursor.fetchone()[0]
            return remaining
        except Exception:
            conn.rollback()
            logging.exception("Failed to delete task %s", task_id)
            raise
        finally:
            conn.close()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row[0],
            group_task_id=row[1],
            assigned_to=row[2],
            assigned_by=row[3],
            status=row[4],
            created_at=row[5],
            completed_at=row[6],
        )
