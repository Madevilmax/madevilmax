PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- Пользователи
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    username  TEXT PRIMARY KEY,
    full_name TEXT
);

------------------------------------------------------------
-- Группы / чаты для уведомлений
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS groups (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

------------------------------------------------------------
-- Связка пользователь ↔ группа
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_groups (
    username TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (username, group_id),
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_groups_username ON user_groups (username);
CREATE INDEX IF NOT EXISTS idx_user_groups_group_id ON user_groups (group_id);

------------------------------------------------------------
-- Настройки уведомлений
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO config (key, value) VALUES
    ('task_created', 'true'),
    ('task_completed', 'true'),
    ('task_deleted', 'true'),
    ('overdue_reminder', 'true');

------------------------------------------------------------
-- Группы задач
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_groups (
    group_task_id INTEGER PRIMARY KEY,
    task_text     TEXT NOT NULL,
    deadline      TEXT NOT NULL,      -- формат хранения: DD.MM.YYYY
    group_id      TEXT NOT NULL,
    created_at    TEXT NOT NULL       -- формат хранения: DD.MM.YYYY HH:MM:SS
);

------------------------------------------------------------
-- Индивидуальные задачи по исполнителям
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_task_id INTEGER NOT NULL,
    assigned_to   TEXT NOT NULL,
    assigned_by   TEXT NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    completed_at  TEXT NOT NULL,
    FOREIGN KEY (group_task_id) REFERENCES task_groups (group_task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_group_task_id ON tasks (group_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks (assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
