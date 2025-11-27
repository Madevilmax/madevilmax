import json
import logging

from db.database import get_connection
from models import Config


class ConfigRepository:
    def get_config(self) -> Config:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT key, value FROM config")
            rows = cursor.fetchall()
            defaults = Config().model_dump()
            for key, value in rows:
                if key in defaults:
                    if key in {"admins", "group_chat_ids"}:
                        try:
                            defaults[key] = json.loads(value)
                        except Exception:
                            defaults[key] = []
                    else:
                        defaults[key] = str(value).lower() in {"true", "1", "yes", "on"}
            return Config(**defaults)
        except Exception:
            logging.exception("Failed to fetch config")
            raise
        finally:
            conn.close()

    def set_config(self, cfg: Config) -> Config:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for key, val in cfg.model_dump().items():
                if key in {"admins", "group_chat_ids"}:
                    stored_val = json.dumps(val)
                else:
                    stored_val = "true" if val else "false"
                cursor.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    (key, stored_val),
                )
            conn.commit()
            return cfg
        except Exception:
            conn.rollback()
            logging.exception("Failed to save config")
            raise
        finally:
            conn.close()
