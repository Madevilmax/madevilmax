import asyncio
import datetime
import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import httpx
from aiogram import Bot, Dispatcher, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BASE_API_URL = "http://localhost:8000"
TASKS_PER_PAGE = 5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

router = Router()
# Global dispatcher so helpers can access FSM without relying on deprecated
# Dispatcher.get_current().
dp = Dispatcher()
dp.include_router(router)


class MessageCallbackAdapter:
    def __init__(self, message: types.Message, data: str):
        self.message = message
        self.from_user = message.from_user
        self.data = data

    async def answer(self, text: str = "", show_alert: bool = False) -> None:  # noqa: ARG002
        if text:
            await self.message.answer(text)


class AdminCreateTask(StatesGroup):
    choosing_executors = State()
    task_text = State()
    group = State()
    deadline = State()
    custom_deadline = State()


class AddUserState(StatesGroup):
    username = State()
    full_name = State()
    groups = State()


class AddAdminState(StatesGroup):
    username = State()


class ManageTextState(StatesGroup):
    waiting_text = State()


class ManageDeadlineState(StatesGroup):
    waiting_deadline = State()


DEFAULT_CONFIG: Dict[str, object] = {
    "group_chat_ids": [],
    "admins": [],
    "task_created": True,
    "task_completed": True,
    "task_deleted": True,
    "overdue_reminder": True,
}


def parse_env_list(var_name: str) -> List[str]:
    raw = os.getenv(var_name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def with_defaults(data: Dict[str, object] | None) -> Dict[str, object]:
    merged = DEFAULT_CONFIG.copy()
    if data:
        merged.update(data)
    if not merged.get("admins"):
        merged["admins"] = parse_env_list("ADMIN_USERNAMES")
    return merged


config: Dict[str, object] = with_defaults(None)
users_cache: List[dict] = []
groups_cache: List[dict] = []


async def fetch_config_from_api() -> Dict[str, object]:
    global config
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.get("/api/config")
            response.raise_for_status()
            remote = response.json()
            config = with_defaults(remote)
    except Exception as exc:
        logger.error("Failed to fetch config from API: %s", exc)
        config = with_defaults(config)
    return config


async def save_config_to_api(cfg: Dict[str, object]) -> None:
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            await client.post("/api/config", json=cfg)
    except Exception as exc:
        logger.error("Failed to persist config to API: %s", exc)


async def fetch_users_from_api() -> List[dict]:
    global users_cache
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.get("/api/users")
            response.raise_for_status()
            data = response.json()
            users_cache = data.get("users", [])
    except Exception as exc:
        logger.error("Failed to fetch users from API: %s", exc)
        users_cache = []
    return users_cache


async def fetch_groups_from_api() -> List[dict]:
    global groups_cache
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.get("/api/groups")
            response.raise_for_status()
            data = response.json()
            groups_cache = data.get("groups", [])
    except Exception as exc:
        logger.error("Failed to fetch groups from API: %s", exc)
        groups_cache = []
    return groups_cache


async def sync_bot_state() -> None:
    await asyncio.gather(fetch_config_from_api(), fetch_users_from_api(), fetch_groups_from_api())


def is_private_chat(chat: types.Chat) -> bool:
    return chat.type == "private"


async def get_all_tasks() -> List[dict]:
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.get("/api/tasks")
            response.raise_for_status()
            data = response.json()
            return data.get("tasks", [])
    except Exception as exc:
        logger.error("Failed to fetch tasks: %s", exc)
        raise RuntimeError("Не удалось получить задачи") from exc


async def create_task_group_via_api(
    task_text: str,
    deadline: str,
    group_id: str,
    assigned_to: List[str],
    assigned_by: str,
) -> dict:
    payload = {
        "task_text": task_text,
        "deadline": deadline,
        "group_id": group_id,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
    }
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.post("/api/tasks", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to create task group: %s", exc)
        raise RuntimeError("Не удалось создать задачу") from exc


async def add_executors_via_api(
    group_task_id: int, assigned_to: List[str], assigned_by: str
) -> dict:
    payload = {
        "group_task_id": group_task_id,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
    }
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.post("/api/tasks", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to add executors: %s", exc)
        raise RuntimeError("Не удалось добавить исполнителей") from exc


async def upsert_user_via_api(username: str, full_name: str, groups: List[str]) -> dict:
    payload = {"username": username, "full_name": full_name, "groups": groups}
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.post("/api/users", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to upsert user %s: %s", username, exc)
        raise RuntimeError("Не удалось сохранить пользователя") from exc


async def delete_user_via_api(username: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.delete(f"/api/users/{username}")
            if response.status_code == 404:
                raise RuntimeError("Пользователь не найден")
            response.raise_for_status()
    except Exception as exc:
        logger.error("Failed to delete user %s: %s", username, exc)
        raise RuntimeError("Не удалось удалить пользователя") from exc


async def update_task_status_via_api(task_id: int, status: str) -> dict:
    payload = {"status": status}
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.put(f"/api/tasks/{task_id}", json=payload)
            if response.status_code == 404:
                raise RuntimeError("Задача не найдена")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to update status for task %s: %s", task_id, exc)
        raise RuntimeError("Не удалось обновить статус задачи") from exc


async def update_group_via_api(
    task_id: int, task_text: Optional[str] = None, deadline: Optional[str] = None, group_id: Optional[str] = None
) -> dict:
    payload: Dict[str, object] = {"group_operation": True}
    if task_text is not None:
        payload["task_text"] = task_text
    if deadline is not None:
        payload["deadline"] = deadline
    if group_id is not None:
        payload["group_id"] = group_id
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.put(f"/api/tasks/{task_id}", json=payload)
            if response.status_code == 404:
                raise RuntimeError("Группа задач не найдена")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to update group for task %s: %s", task_id, exc)
        raise RuntimeError("Не удалось обновить группу задачи") from exc


async def delete_task_via_api(task_id: int) -> dict:
    try:
        async with httpx.AsyncClient(base_url=BASE_API_URL, timeout=15.0) as client:
            response = await client.delete(f"/api/tasks/{task_id}")
            if response.status_code == 404:
                raise RuntimeError("Задача не найдена")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to delete task %s: %s", task_id, exc)
        raise RuntimeError("Не удалось удалить задачу") from exc


def normalize_handle(username: str) -> str:
    return username if username.startswith("@") else f"@{username}"


def parse_assignees(raw: str) -> List[str]:
    users = [user.strip() for user in raw.split(",") if user.strip()]
    return [normalize_handle(user) for user in users]


def deadline_to_date(deadline: str) -> Optional[datetime.date]:
    try:
        return datetime.datetime.strptime(deadline, "%d.%m.%Y").date()
    except Exception:
        return None


def is_overdue(task: dict) -> bool:
    if task.get("status") == "completed":
        return False
    date_val = deadline_to_date(task.get("deadline", ""))
    if not date_val:
        return False
    return date_val < datetime.date.today()


def format_task_card(task: dict, include_completed_at: bool = False) -> str:
    lines = [
        f"#{task.get('id')} — {task.get('task_text', '')}",
        f"Срок: {task.get('deadline', '')}",
        f"Назначил: {task.get('assigned_by', '')}",
        f"Статус: {task.get('status', '')}",
    ]
    if include_completed_at:
        lines.append(f"Выполнено: {task.get('completed_at', '')}")
    return "\n".join(lines)


def format_task_line(task: dict) -> str:
    status = task.get("status", "").lower()
    status_icon = "✅" if status == "completed" else "🟡"
    return (
        f"#{task.get('id')} {status_icon} {task.get('task_text', '')} "
        f"(до {task.get('deadline', '')}) [group {task.get('group_task_id')}]")


def user_is_admin(username: Optional[str]) -> bool:
    if not username:
        return False
    handle = normalize_handle(username)
    return handle in set(config.get("admins", []))


def main_menu_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="📋 Мои задачи")]]
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Админ панель")])
    buttons.append([KeyboardButton(text="ℹ️ Помощь")])
    return ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, input_field_placeholder="Выберите действие"
    )


def my_tasks_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟡 Текущие задачи")],
            [KeyboardButton(text="🟢 Выполненные задачи")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите список задач",
    )


def admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая задача"), KeyboardButton(text="📋 Все задачи")],
            [KeyboardButton(text="❌ Просроченные"), KeyboardButton(text="👥 Задачи по сотрудникам")],
            [KeyboardButton(text="🏘 Задачи по группам"), KeyboardButton(text="🛠 Управление задачами")],
            [KeyboardButton(text="⚙️ Настройки уведомлений"), KeyboardButton(text="👤 Управление пользователями")],
            [KeyboardButton(text="👑 Управление администраторами"), KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие администратора",
    )


def build_task_buttons(task: dict, for_completed: bool = False, for_user: bool = False) -> List[InlineKeyboardButton]:
    buttons: List[InlineKeyboardButton] = []
    if for_user:
        if for_completed:
            buttons.append(InlineKeyboardButton(text="🔄 Открыть заново", callback_data=f"task:reopen:{task['id']}"))
            buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:delete:{task['id']}"))
        else:
            buttons.append(InlineKeyboardButton(text="✅ Завершить", callback_data=f"task:complete:{task['id']}"))
        return buttons

    if task.get("status") == "completed":
        buttons.append(InlineKeyboardButton(text="🔄 Открыть заново", callback_data=f"admin_task:reopen:{task['id']}"))
        buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_task:delete:{task['id']}"))
    else:
        buttons.append(InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_task:complete:{task['id']}"))
        buttons.append(InlineKeyboardButton(text="⏰ Изменить срок", callback_data=f"admin_task:deadline:{task['id']}"))
        buttons.append(InlineKeyboardButton(text="👤 Переназначить", callback_data=f"admin_task:reassign:{task['id']}"))
        buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_task:delete:{task['id']}"))
    return buttons


def paginate_tasks(tasks: List[dict], page: int) -> Tuple[List[dict], bool, bool]:
    start = page * TASKS_PER_PAGE
    end = start + TASKS_PER_PAGE
    sliced = tasks[start:end]
    has_prev = page > 0
    has_next = end < len(tasks)
    return sliced, has_prev, has_next


def task_matches_filter(task: dict, filter_key: str) -> bool:
    today = datetime.date.today()
    deadline_date = deadline_to_date(task.get("deadline", ""))
    status = task.get("status")
    if filter_key == "all":
        return True
    if filter_key == "active":
        return status == "active"
    if filter_key == "completed":
        return status == "completed"
    if filter_key == "overdue":
        return is_overdue(task)
    if not deadline_date:
        return False
    if filter_key == "today":
        return deadline_date == today
    if filter_key == "tomorrow":
        return deadline_date == today + datetime.timedelta(days=1)
    if filter_key == "week":
        return today <= deadline_date <= today + datetime.timedelta(days=7)
    if filter_key == "month":
        return today <= deadline_date <= today + datetime.timedelta(days=30)
    return True


admin_views: Dict[int, Dict[str, object]] = defaultdict(lambda: {"filter": "all", "page": 0})
selected_task_for_text: Dict[int, int] = {}
selected_task_for_deadline: Dict[int, int] = {}


async def show_main_menu(message: types.Message) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Главное меню доступно только в личном чате.")
        return
    is_admin = user_is_admin(message.from_user.username)
    await message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard(is_admin))


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Используйте личный чат со мной, чтобы открыть меню.")
        return
    text = (
        "Привет! Я помогаю управлять групповыми задачами.\n"
        "Используйте меню ниже."
    )
    await message.answer(text, reply_markup=main_menu_keyboard(user_is_admin(message.from_user.username)))


@router.message(lambda m: m.text == "📋 Мои задачи")
async def menu_my_tasks(message: types.Message) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Меню доступно только в личном чате.")
        return
    await message.answer("📋 Мои задачи", reply_markup=my_tasks_keyboard())


@router.message(lambda m: m.text == "👑 Админ панель")
async def menu_admin_panel(message: types.Message) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Меню доступно только в личном чате.")
        return
    if not user_is_admin(message.from_user.username):
        await message.answer("Недостаточно прав")
        return
    await message.answer("👑 Админ панель", reply_markup=admin_panel_keyboard())


def make_callback_from_message(message: types.Message, data: str) -> MessageCallbackAdapter:
    return MessageCallbackAdapter(message, data)


async def handle_admin_entry(message: types.Message, data: str) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Доступно только в личном чате.")
        return
    if not user_is_admin(message.from_user.username):
        await message.answer("Недостаточно прав")
        return
    placeholder = await message.answer("Загружаю...")
    callback = make_callback_from_message(placeholder, data)
    state = await dp.fsm.get_context(
        bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id
    )

    handlers_map = {
        "admin:new": cb_admin_new,
        "admin:all": cb_admin_all,
        "admin:overdue": cb_overdue,
        "admin:by_user": cb_by_user,
        "admin:by_group": cb_by_group,
        "admin:manage": cb_manage,
        "admin:notify": cb_notify,
        "admin:users": cb_users,
        "admin:admins": cb_admins,
    }

    handler = handlers_map.get(data)
    if handler is None:
        await message.answer("Неизвестное действие")
        return

    if data == "admin:new":
        await handler(callback, state)
    else:
        await handler(callback)


@router.message(F.text == "➕ Новая задача")
async def msg_admin_new(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:new")


@router.message(F.text == "📋 Все задачи")
async def msg_admin_all(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:all")


@router.message(F.text == "❌ Просроченные")
async def msg_admin_overdue(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:overdue")


@router.message(F.text == "👥 Задачи по сотрудникам")
async def msg_admin_by_user(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:by_user")


@router.message(F.text == "🏘 Задачи по группам")
async def msg_admin_by_group(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:by_group")


@router.message(F.text == "🛠 Управление задачами")
async def msg_admin_manage(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:manage")


@router.message(F.text == "⚙️ Настройки уведомлений")
async def msg_admin_notify(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:notify")


@router.message(F.text == "👤 Управление пользователями")
async def msg_admin_users(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:users")


@router.message(F.text == "👑 Управление администраторами")
async def msg_admin_admins(message: types.Message) -> None:
    await handle_admin_entry(message, "admin:admins")


@router.message(lambda m: m.text == "ℹ️ Помощь")
async def menu_help(message: types.Message) -> None:
    if not is_private_chat(message.chat):
        await message.answer("Меню доступно только в личном чате.")
        return
    help_text = (
        "Нажимайте кнопки панели, чтобы открыть список задач или админ-панель.\n"
        "Для детальных действий используйте кнопки под сообщениями."
    )
    await message.answer(help_text, reply_markup=main_menu_keyboard(user_is_admin(message.from_user.username)))


@router.callback_query(lambda c: c.data == "menu:main")
async def cb_menu_main(callback: types.CallbackQuery) -> None:
    await callback.message.answer(
        "🏠 Главное меню", reply_markup=main_menu_keyboard(user_is_admin(callback.from_user.username))
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "menu:mytasks")
async def cb_menu_mytasks(callback: types.CallbackQuery) -> None:
    await callback.message.answer("📋 Мои задачи", reply_markup=my_tasks_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "menu:admin")
async def cb_menu_admin(callback: types.CallbackQuery) -> None:
    if not user_is_admin(callback.from_user.username):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await callback.message.edit_text("👑 Админ панель", reply_markup=admin_panel_keyboard())
    await callback.answer()


async def show_my_tasks_selection(message: types.Message, selection: str) -> None:
    username = message.from_user.username if message.from_user else None
    if not username:
        await message.answer("Username не найден", reply_markup=my_tasks_keyboard())
        return
    handle = normalize_handle(username)
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await message.answer(str(exc), reply_markup=my_tasks_keyboard())
        return

    if selection == "active":
        active_tasks = [t for t in tasks if t.get("assigned_to") == handle and t.get("status") == "active"]
        if not active_tasks:
            await message.answer("Нет активных задач", reply_markup=my_tasks_keyboard())
            return
        for task in active_tasks:
            buttons = InlineKeyboardMarkup(
                inline_keyboard=[[btn for btn in build_task_buttons(task, for_user=True)]]
            )
            await message.answer(format_task_card(task), reply_markup=buttons)
        return

    if selection == "completed":
        completed_tasks = [t for t in tasks if t.get("assigned_to") == handle and t.get("status") == "completed"]
        completed_tasks = sorted(completed_tasks, key=lambda t: t.get("completed_at", ""), reverse=True)[:5]
        if not completed_tasks:
            await message.answer("Нет выполненных задач", reply_markup=my_tasks_keyboard())
            return
        for task in completed_tasks:
            buttons = InlineKeyboardMarkup(
                inline_keyboard=[[btn for btn in build_task_buttons(task, for_completed=True, for_user=True)]]
            )
            await message.answer(format_task_card(task, include_completed_at=True), reply_markup=buttons)


@router.message(F.text == "🟡 Текущие задачи")
async def msg_my_active(message: types.Message) -> None:
    await show_my_tasks_selection(message, "active")


@router.message(F.text == "🟢 Выполненные задачи")
async def msg_my_completed(message: types.Message) -> None:
    await show_my_tasks_selection(message, "completed")


@router.callback_query(lambda c: c.data and c.data.startswith("my:"))
async def cb_my_tasks(callback: types.CallbackQuery) -> None:
    selection = callback.data.split(":")[1]
    await show_my_tasks_selection(callback.message, selection)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("task:"))
async def cb_task_actions(callback: types.CallbackQuery) -> None:
    _, action, task_id_str = callback.data.split(":", maxsplit=2)
    task_id = int(task_id_str)
    try:
        if action == "complete":
            await update_task_status_via_api(task_id, "completed")
            await callback.answer("Задача завершена")
        elif action == "reopen":
            await update_task_status_via_api(task_id, "active")
            await callback.answer("Задача открыта заново")
        elif action == "delete":
            await delete_task_via_api(task_id)
            await callback.answer("Задача удалена")
        else:
            await callback.answer("Неизвестное действие")
            return
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.message.edit_text("Обновлено")


async def send_task_cards(chat: types.Message, tasks: List[dict], show_buttons: bool = True) -> None:
    for task in tasks:
        buttons_block: List[List[InlineKeyboardButton]] = []
        if show_buttons:
            row = build_task_buttons(task, for_completed=task.get("status") == "completed")
            while row:
                buttons_block.append([row.pop(0)])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons_block) if buttons_block else None
        await chat.answer(format_task_line(task), reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "admin:new")
async def cb_admin_new(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not user_is_admin(callback.from_user.username):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminCreateTask.choosing_executors)
    keyboard_rows: List[List[InlineKeyboardButton]] = []
    for idx, user in enumerate(users_cache):
        if idx % 2 == 0:
            keyboard_rows.append([])
        keyboard_rows[-1].append(
            InlineKeyboardButton(text=user.get("username"), callback_data=f"exec:toggle:{user.get('username')}")
        )
    keyboard_rows.append([InlineKeyboardButton(text="✔️ Завершить выбор", callback_data="exec:done")])
    keyboard_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="exec:cancel")])
    await callback.message.edit_text("Выберите исполнителей", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exec:"))
async def cb_exec_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = callback.data.split(":")
    action = data[1]
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("Создание задачи отменено", reply_markup=admin_panel_keyboard())
        await callback.answer()
        return

    context = await state.get_data()
    selected: List[str] = context.get("assignees", [])

    if action == "toggle":
        user = normalize_handle(data[2])
        if user in selected:
            selected.remove(user)
        else:
            selected.append(user)
        await state.update_data(assignees=selected)
        await callback.answer(f"Выбрано: {', '.join(selected) if selected else 'никто'}")
        return

    if action == "done":
        if not selected:
            await callback.answer("Нужно выбрать хотя бы одного исполнителя", show_alert=True)
            return
        await state.update_data(assignees=selected)
        await state.set_state(AdminCreateTask.task_text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="exec:cancel")]])
        await callback.message.edit_text("Введите описание задачи сообщением", reply_markup=keyboard)
        await callback.answer()


@router.message(AdminCreateTask.task_text)
async def admin_task_text(message: types.Message, state: FSMContext) -> None:
    await state.update_data(task_text=message.text)
    await state.set_state(AdminCreateTask.group)
    rows: List[List[InlineKeyboardButton]] = []
    group_choices = config.get("group_chat_ids", [])
    for group in group_choices:
        rows.append([InlineKeyboardButton(text=str(group), callback_data=f"group:choose:{group}")])
    rows.append([InlineKeyboardButton(text="Без уведомлений", callback_data="group:none")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="exec:cancel")])
    await message.answer("Выберите группу/чат для уведомлений", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(lambda c: c.data and c.data.startswith("group:"))
async def cb_choose_group(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if parts[1] == "none":
        group_id = ""
    else:
        group_id = parts[2]
    await state.update_data(group_id=group_id)
    await state.set_state(AdminCreateTask.deadline)
    rows = [
        [InlineKeyboardButton(text="⏰ Сегодня", callback_data="deadline:today")],
        [InlineKeyboardButton(text="⏰ Завтра", callback_data="deadline:tomorrow")],
        [InlineKeyboardButton(text="⏰ Через 3 дня", callback_data="deadline:3days")],
        [InlineKeyboardButton(text="⏰ Через неделю", callback_data="deadline:week")],
        [InlineKeyboardButton(text="📅 Указать дату вручную", callback_data="deadline:custom")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="exec:cancel")],
    ]
    await callback.message.edit_text("Выберите срок", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


def deadline_from_choice(choice: str) -> str:
    today = datetime.date.today()
    if choice == "today":
        return today.strftime("%d.%m.%Y")
    if choice == "tomorrow":
        return (today + datetime.timedelta(days=1)).strftime("%d.%m.%Y")
    if choice == "3days":
        return (today + datetime.timedelta(days=3)).strftime("%d.%m.%Y")
    if choice == "week":
        return (today + datetime.timedelta(days=7)).strftime("%d.%m.%Y")
    return today.strftime("%d.%m.%Y")


@router.callback_query(lambda c: c.data and c.data.startswith("deadline:"))
async def cb_deadline_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    _, choice = callback.data.split(":")
    if choice == "custom":
        await state.set_state(AdminCreateTask.custom_deadline)
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.ГГГГ",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="exec:cancel")]]),
        )
        await callback.answer()
        return

    deadline_str = deadline_from_choice(choice)
    await state.update_data(deadline=deadline_str)
    await finalize_task_creation(callback.message, callback.from_user, state)
    await callback.answer()


@router.message(AdminCreateTask.custom_deadline)
async def admin_custom_deadline(message: types.Message, state: FSMContext) -> None:
    await state.update_data(deadline=message.text.strip())
    await finalize_task_creation(message, message.from_user, state)


async def finalize_task_creation(message: types.Message, user: types.User, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        result = await create_task_group_via_api(
            task_text=data.get("task_text", ""),
            deadline=data.get("deadline", ""),
            group_id=str(data.get("group_id", "")),
            assigned_to=data.get("assignees", []),
            assigned_by=normalize_handle(user.username or "@web_user"),
        )
    except RuntimeError as exc:
        await message.answer(str(exc))
        return

    tasks = result.get("tasks", [])
    executors = ", ".join([t.get("assigned_to", "") for t in tasks])
    await message.answer(
        "Задача создана!\n"
        f"group_task_id: {result.get('group_task_id')}\n"
        f"Исполнители: {executors}\n"
        f"Срок: {data.get('deadline')}",
        reply_markup=admin_panel_keyboard(),
    )


async def render_tasks_page(callback: types.CallbackQuery, tasks: List[dict]) -> None:
    view = admin_views[callback.from_user.id]
    filtered = [t for t in tasks if task_matches_filter(t, view.get("filter", "all"))]
    page = int(view.get("page", 0))
    page_tasks, has_prev, has_next = paginate_tasks(filtered, page)
    if not page_tasks:
        await callback.message.edit_text("Нет задач по выбранному фильтру", reply_markup=admin_panel_keyboard())
        await callback.answer()
        return
    text_lines = [f"Страница {page + 1}", f"Фильтр: {view.get('filter')}"]
    for idx, task in enumerate(page_tasks, start=1 + page * TASKS_PER_PAGE):
        text_lines.append(f"{idx}. {format_task_line(task)}")
    nav_buttons: List[List[InlineKeyboardButton]] = []
    if has_prev:
        nav_buttons.append([InlineKeyboardButton(text="◀️ Предыдущая", callback_data="admin_page:prev")])
    if has_next:
        nav_buttons.append([InlineKeyboardButton(text="Следующая ▶️", callback_data="admin_page:next")])
    nav_buttons.append([InlineKeyboardButton(text="🎛 Фильтры", callback_data="admin:filters")])
    for task in page_tasks:
        row_buttons = build_task_buttons(task, for_completed=task.get("status") == "completed")
        nav_buttons.append([InlineKeyboardButton(text=f"# {task['id']}", callback_data="noop")])
        nav_buttons.append([InlineKeyboardButton(text=btn.text, callback_data=btn.callback_data) for btn in row_buttons])
    nav_buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")])
    await callback.message.edit_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=nav_buttons))
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:all")
async def cb_admin_all(callback: types.CallbackQuery) -> None:
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    admin_views[callback.from_user.id] = {"filter": "all", "page": 0}
    await render_tasks_page(callback, tasks)


@router.callback_query(lambda c: c.data and c.data.startswith("admin_page:"))
async def cb_admin_page(callback: types.CallbackQuery) -> None:
    direction = callback.data.split(":")[1]
    view = admin_views[callback.from_user.id]
    page = int(view.get("page", 0))
    if direction == "next":
        page += 1
    elif direction == "prev" and page > 0:
        page -= 1
    view["page"] = page
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await render_tasks_page(callback, tasks)


@router.callback_query(lambda c: c.data == "admin:filters")
async def cb_admin_filters(callback: types.CallbackQuery) -> None:
    rows = [
        [InlineKeyboardButton(text="🎯 Все задачи", callback_data="filter:all")],
        [InlineKeyboardButton(text="🟡 Активные", callback_data="filter:active")],
        [InlineKeyboardButton(text="🟢 Выполненные", callback_data="filter:completed")],
        [InlineKeyboardButton(text="🔴 Просроченные", callback_data="filter:overdue")],
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="filter:today")],
        [InlineKeyboardButton(text="📅 Завтра", callback_data="filter:tomorrow")],
        [InlineKeyboardButton(text="📅 Эта неделя", callback_data="filter:week")],
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data="filter:month")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")],
    ]
    await callback.message.edit_text("Выберите фильтр", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("filter:"))
async def cb_filter(callback: types.CallbackQuery) -> None:
    filter_key = callback.data.split(":")[1]
    admin_views[callback.from_user.id]["filter"] = filter_key
    admin_views[callback.from_user.id]["page"] = 0
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await render_tasks_page(callback, tasks)


@router.callback_query(lambda c: c.data == "noop")
async def cb_noop(callback: types.CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:overdue")
async def cb_overdue(callback: types.CallbackQuery) -> None:
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    overdue_tasks = [t for t in tasks if is_overdue(t)]
    if not overdue_tasks:
        await callback.message.edit_text("Просроченных задач нет", reply_markup=admin_panel_keyboard())
        await callback.answer()
        return
    await send_task_cards(callback.message, overdue_tasks)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:by_user")
async def cb_by_user(callback: types.CallbackQuery) -> None:
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await fetch_users_from_api()
    users_cfg: List[dict] = users_cache
    lines: List[str] = []
    for user in users_cfg:
        handle = normalize_handle(user.get("username", ""))
        full_name = user.get("full_name", handle)
        user_tasks = [t for t in tasks if t.get("assigned_to") == handle]
        active_count = len([t for t in user_tasks if t.get("status") == "active"])
        completed_count = len([t for t in user_tasks if t.get("status") == "completed"])
        lines.append(f"{full_name} ({handle})")
        lines.append(f"Активных: {active_count}")
        lines.append(f"Выполнено: {completed_count}")
        lines.append("Активные задачи:")
        for task in user_tasks:
            if task.get("status") != "active":
                continue
            overdue_flag = " 🔴" if is_overdue(task) else ""
            lines.append(f"- {task.get('task_text')} ({task.get('deadline')}){overdue_flag}")
        lines.append("")
    await callback.message.edit_text("\n".join(lines) or "Пользователи не найдены", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:by_group")
async def cb_by_group(callback: types.CallbackQuery) -> None:
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    groups: Dict[str, List[dict]] = defaultdict(list)
    for task in tasks:
        groups[str(task.get("group_id", ""))].append(task)
    buttons: List[List[InlineKeyboardButton]] = []
    lines: List[str] = ["Сводка по группам"]
    for group_id, group_tasks in groups.items():
        active = len([t for t in group_tasks if t.get("status") == "active"])
        completed = len([t for t in group_tasks if t.get("status") == "completed"])
        overdue = len([t for t in group_tasks if is_overdue(t)])
        lines.append(f"Группа {group_id}: 🟡 {active} / 🟢 {completed} / 🔴 {overdue}")
        buttons.append([InlineKeyboardButton(text=f"Группа {group_id}", callback_data=f"group:view:{group_id}")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("group:view:"))
async def cb_view_group(callback: types.CallbackQuery) -> None:
    _, _, group_id_str = callback.data.split(":")
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    group_tasks = [t for t in tasks if str(t.get("group_id")) == group_id_str]
    if not group_tasks:
        await callback.answer("Задачи не найдены", show_alert=True)
        return
    await callback.message.edit_text(f"Задачи группы {group_id_str}")
    await send_task_cards(callback.message, group_tasks)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:manage")
async def cb_manage(callback: types.CallbackQuery) -> None:
    rows = [
        [InlineKeyboardButton(text="✏️ Изменить текст задачи", callback_data="manage:edit_text")],
        [InlineKeyboardButton(text="⏰ Изменить срок", callback_data="manage:deadline")],
        [InlineKeyboardButton(text="👤 Переназначить исполнителя", callback_data="manage:reassign")],
        [InlineKeyboardButton(text="🗑 Удалить задачу", callback_data="manage:delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admin")],
    ]
    await callback.message.edit_text("Управление задачами", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("manage:"))
async def cb_manage_actions(callback: types.CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    try:
        tasks = await get_all_tasks()
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    lines = [f"{idx+1}. #{t['id']} {t['task_text']}" for idx, t in enumerate(tasks)]
    buttons = [[InlineKeyboardButton(text=f"{idx+1}", callback_data=f"select:{action}:{t['id']}")] for idx, t in enumerate(tasks)]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")])
    await callback.message.edit_text(
        "Выберите задачу:\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("select:"))
async def cb_select_task(callback: types.CallbackQuery, state: FSMContext) -> None:
    _, action, task_id_str = callback.data.split(":")
    task_id = int(task_id_str)
    if action == "delete":
        try:
            await delete_task_via_api(task_id)
            await callback.message.edit_text("Задача удалена")
        except RuntimeError as exc:
            await callback.answer(str(exc), show_alert=True)
        return
    if action == "edit_text":
        selected_task_for_text[callback.from_user.id] = task_id
        await state.set_state(ManageTextState.waiting_text)
        await callback.message.edit_text("Введите новый текст задачи")
        await callback.answer()
        return
    if action == "deadline":
        selected_task_for_deadline[callback.from_user.id] = task_id
        rows = [
            [InlineKeyboardButton(text="⏰ Сегодня", callback_data=f"deadline_update:{task_id}:today")],
            [InlineKeyboardButton(text="⏰ Завтра", callback_data=f"deadline_update:{task_id}:tomorrow")],
            [InlineKeyboardButton(text="⏰ Через 3 дня", callback_data=f"deadline_update:{task_id}:3days")],
            [InlineKeyboardButton(text="⏰ Через неделю", callback_data=f"deadline_update:{task_id}:week")],
            [InlineKeyboardButton(text="📅 Указать дату", callback_data=f"deadline_update:{task_id}:custom")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")],
        ]
        await callback.message.edit_text("Выберите новый срок", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await callback.answer()
        return
    if action == "reassign":
        try:
            await callback.answer("Для переназначения добавьте новых исполнителей через API группы", show_alert=True)
        except RuntimeError:
            pass
        return


@router.callback_query(lambda c: c.data and c.data.startswith("admin_task:"))
async def cb_admin_task_actions(callback: types.CallbackQuery) -> None:
    _, action, task_id_str = callback.data.split(":")
    task_id = int(task_id_str)
    try:
        if action == "complete":
            await update_task_status_via_api(task_id, "completed")
        elif action == "reopen":
            await update_task_status_via_api(task_id, "active")
        elif action == "deadline":
            selected_task_for_deadline[callback.from_user.id] = task_id
            rows = [
                [InlineKeyboardButton(text="⏰ Сегодня", callback_data=f"deadline_update:{task_id}:today")],
                [InlineKeyboardButton(text="⏰ Завтра", callback_data=f"deadline_update:{task_id}:tomorrow")],
                [InlineKeyboardButton(text="⏰ Через 3 дня", callback_data=f"deadline_update:{task_id}:3days")],
                [InlineKeyboardButton(text="⏰ Через неделю", callback_data=f"deadline_update:{task_id}:week")],
                [InlineKeyboardButton(text="📅 Указать дату", callback_data=f"deadline_update:{task_id}:custom")],
            ]
            await callback.message.answer("Выберите новый срок", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            await callback.answer()
            return
        elif action == "reassign":
            await callback.answer("Для переназначения создайте копии задачи на новых исполнителей", show_alert=True)
            return
        elif action == "delete":
            await delete_task_via_api(task_id)
        else:
            await callback.answer("Неизвестное действие")
            return
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Готово")


@router.callback_query(lambda c: c.data and c.data.startswith("deadline_update:"))
async def cb_deadline_update(callback: types.CallbackQuery, state: FSMContext) -> None:
    _, task_id_str, choice = callback.data.split(":")
    task_id = int(task_id_str)
    if choice == "custom":
        selected_task_for_deadline[callback.from_user.id] = task_id
        await state.set_state(ManageDeadlineState.waiting_deadline)
        await callback.message.edit_text("Отправьте новую дату сообщением (ДД.ММ.ГГГГ)")
        await callback.answer()
        return
    deadline_str = deadline_from_choice(choice)
    try:
        await update_group_via_api(task_id, deadline=deadline_str)
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.message.edit_text("Срок обновлен")
    await callback.answer()


@router.message(ManageDeadlineState.waiting_deadline)
async def msg_deadline_text(message: types.Message, state: FSMContext) -> None:
    task_id = selected_task_for_deadline.pop(message.from_user.id, None)
    await state.clear()
    if not task_id:
        await message.answer("Задача не выбрана")
        return
    try:
        await update_group_via_api(task_id, deadline=message.text.strip())
        await message.answer("Срок обновлен")
    except RuntimeError as exc:
        await message.answer(str(exc))


@router.message(ManageTextState.waiting_text)
async def msg_new_task_text(message: types.Message, state: FSMContext) -> None:
    task_id = selected_task_for_text.pop(message.from_user.id, None)
    await state.clear()
    if not task_id:
        await message.answer("Задача не выбрана")
        return
    try:
        await update_group_via_api(task_id, task_text=message.text.strip())
        await message.answer("Текст задачи обновлен")
    except RuntimeError as exc:
        await message.answer(str(exc))


@router.callback_query(lambda c: c.data == "admin:notify")
async def cb_notify(callback: types.CallbackQuery) -> None:
    settings = {
        key: config.get(key, DEFAULT_CONFIG[key])
        for key in ("task_created", "task_completed", "task_deleted", "overdue_reminder")
    }
    rows = [
        [InlineKeyboardButton(text=f"{'🔔' if settings.get('task_created') else '🔕'} Создание задач", callback_data="notify:task_created")],
        [InlineKeyboardButton(text=f"{'✅' if settings.get('task_completed') else '❌'} Завершение задач", callback_data="notify:task_completed")],
        [InlineKeyboardButton(text=f"{'🗑' if settings.get('task_deleted') else '📥'} Удаление задач", callback_data="notify:task_deleted")],
        [InlineKeyboardButton(text=f"{'⏰' if settings.get('overdue_reminder') else '⏳'} Напоминания о просрочке", callback_data="notify:overdue_reminder")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admin")],
    ]
    await callback.message.edit_text("Настройки уведомлений", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("notify:"))
async def cb_notify_toggle(callback: types.CallbackQuery) -> None:
    _, key = callback.data.split(":")
    config[key] = not config.get(key, True)
    await save_config_to_api(config)
    await cb_notify(callback)


@router.callback_query(lambda c: c.data == "admin:users")
async def cb_users(callback: types.CallbackQuery) -> None:
    rows = [
        [InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="users:add")],
        [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="users:remove")],
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="users:list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admin")],
    ]
    await callback.message.edit_text("Управление пользователями", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("users:"))
async def cb_users_actions(callback: types.CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    await fetch_users_from_api()
    if action == "list":
        lines = [f"{u.get('full_name', '')} ({u.get('username')})" for u in users_cache]
        await callback.message.edit_text("\n".join(lines) or "Нет пользователей")
        await callback.answer()
        return
    if action == "add":
        await state.set_state(AddUserState.username)
        await callback.message.edit_text("Введите @username нового пользователя")
        await callback.answer()
        return
    if action == "remove":
        buttons = [[InlineKeyboardButton(text=u.get("username"), callback_data=f"users:remove:{u.get('username')}")] for u in users_cache]
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu:admin")])
        await callback.message.edit_text("Выберите пользователя для удаления", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
        return


@router.callback_query(lambda c: c.data and c.data.startswith("users:remove:"))
async def cb_remove_user(callback: types.CallbackQuery) -> None:
    username = callback.data.split(":")[2]
    try:
        await delete_user_via_api(username)
        await fetch_users_from_api()
        await callback.message.edit_text("Пользователь удален")
    except RuntimeError as exc:
        await callback.message.edit_text(str(exc))
    await callback.answer()


@router.message(AddUserState.username)
async def add_user_username(message: types.Message, state: FSMContext) -> None:
    await state.update_data(username=normalize_handle(message.text.strip()))
    await state.set_state(AddUserState.full_name)
    await message.answer("Введите полное имя пользователя")


@router.message(AddUserState.full_name)
async def add_user_fullname(message: types.Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text.strip())
    await state.set_state(AddUserState.groups)
    await message.answer("Введите группы (через запятую)")


@router.message(AddUserState.groups)
async def add_user_groups(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    groups = [g.strip() for g in message.text.split(",") if g.strip()]
    try:
        await upsert_user_via_api(data.get("username"), data.get("full_name"), groups)
        await fetch_users_from_api()
    except RuntimeError as exc:
        await message.answer(str(exc))
        await state.clear()
        return
    await state.clear()
    await message.answer("Пользователь добавлен", reply_markup=admin_panel_keyboard())


@router.callback_query(lambda c: c.data == "admin:admins")
async def cb_admins(callback: types.CallbackQuery) -> None:
    rows = [
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="admins:add")],
        [InlineKeyboardButton(text="🗑 Удалить администратора", callback_data="admins:remove")],
        [InlineKeyboardButton(text="📋 Список администраторов", callback_data="admins:list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admin")],
    ]
    await callback.message.edit_text("Управление администраторами", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admins:"))
async def cb_admins_actions(callback: types.CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    await fetch_config_from_api()
    if action == "list":
        lines = [admin for admin in config.get("admins", [])]
        await callback.message.edit_text("\n".join(lines) or "Нет администраторов")
        await callback.answer()
        return
    if action == "add":
        await state.set_state(AddAdminState.username)
        await callback.message.edit_text("Введите @username администратора")
        await callback.answer()
        return
    if action == "remove":
        buttons = [[InlineKeyboardButton(text=adm, callback_data=f"admins:remove:{adm}")] for adm in config.get("admins", [])]
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu:admin")])
        await callback.message.edit_text("Выберите администратора для удаления", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
        return


@router.callback_query(lambda c: c.data and c.data.startswith("admins:remove:"))
async def cb_remove_admin(callback: types.CallbackQuery) -> None:
    username = callback.data.split(":")[2]
    config["admins"] = [adm for adm in config.get("admins", []) if adm != username]
    await save_config_to_api(config)
    await callback.message.edit_text("Администратор удален")
    await callback.answer()


@router.message(AddAdminState.username)
async def add_admin_username(message: types.Message, state: FSMContext) -> None:
    username = normalize_handle(message.text.strip())
    admins = set(config.get("admins", []))
    admins.add(username)
    config["admins"] = list(admins)
    await save_config_to_api(config)
    await state.clear()
    await message.answer("Администратор добавлен", reply_markup=admin_panel_keyboard())


@router.callback_query(lambda c: c.data == "admin:cancel")
async def cb_cancel(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text("Действие отменено", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith("/done"))
async def cmd_done(message: types.Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите id задачи, например: /done 15")
        return
    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("Некорректный id задачи")
        return
    try:
        await update_task_status_via_api(task_id, "completed")
    except RuntimeError as exc:
        await message.answer(str(exc))
        return
    await message.answer(f"✅ Задача #{task_id} отмечена как выполненная")


@router.message(lambda m: m.text and m.text.startswith("/mytasks"))
async def cmd_mytasks_text(message: types.Message) -> None:
    await message.answer("📋 Мои задачи", reply_markup=my_tasks_keyboard())


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Environment variable TELEGRAM_BOT_TOKEN is not set")
        return

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    logger.info("Bot started")
    await sync_bot_state()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
