import logging
import logging
from datetime import datetime

from db.database import get_connection
from models import Stats


DATE_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y")


class StatsRepository:
    def get_stats(self) -> Stats:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM tasks")
            total_tasks = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")
            active_tasks = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
            completed_tasks = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT tg.deadline
                FROM tasks t
                JOIN task_groups tg ON t.group_task_id = tg.group_task_id
                WHERE t.status = 'active'
                """
            )
            deadlines = [row[0] for row in cursor.fetchall()]
            overdue_tasks = self._count_overdue(deadlines)

            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM groups")
            total_groups = cursor.fetchone()[0]

            return Stats(
                total_tasks=total_tasks,
                active_tasks=active_tasks,
                completed_tasks=completed_tasks,
                overdue_tasks=overdue_tasks,
                users_count=total_users,
                groups_count=total_groups,
            )
        except Exception:
            logging.exception("Failed to collect stats")
            raise
        finally:
            conn.close()

    @staticmethod
    def _parse_date(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            for fmt in DATE_FORMATS:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return None

    @classmethod
    def _count_overdue(cls, deadlines: list[str]) -> int:
        now = datetime.now()
        count = 0
        for dl in deadlines:
            parsed = cls._parse_date(dl)
            if parsed and parsed < now:
                count += 1
        return count
