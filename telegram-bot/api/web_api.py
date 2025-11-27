import logging
from typing import Union

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from db.database import init_db
from models import (
    Config,
    Group,
    Stats,
    TaskAddExecutors,
    TaskCreate,
    TaskGroupUpdate,
    TaskStatusUpdate,
    User,
)
from repositories.config_repository import ConfigRepository
from repositories.groups_repository import GroupsRepository
from repositories.stats_repository import StatsRepository
from repositories.tasks_repository import TasksRepository
from repositories.users_repository import UsersRepository


class GroupOperationRequest(TaskGroupUpdate):
    group_operation: bool


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks_repo = TasksRepository()
users_repo = UsersRepository()
groups_repo = GroupsRepository()
config_repo = ConfigRepository()
stats_repo = StatsRepository()


@app.get("/")
def root() -> FileResponse:
    index_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Index not found")
    return FileResponse(index_path)


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/api/tasks")
def get_tasks() -> dict:
    tasks = tasks_repo.get_all_tasks()
    return {"tasks": tasks}


@app.post("/api/tasks")
def create_or_add_tasks(payload: Union[TaskCreate, TaskAddExecutors] = Body(...)) -> dict:
    try:
        if isinstance(payload, TaskCreate):
            tasks = tasks_repo.create_task_group(
                payload.task_text,
                payload.deadline,
                payload.group_id,
                payload.assigned_to,
                payload.assigned_by,
            )
            group_task_id = tasks[0].group_task_id if tasks else None
        else:
            tasks = tasks_repo.add_executors_to_group(
                payload.group_task_id,
                payload.assigned_to,
                payload.assigned_by,
            )
            group_task_id = payload.group_task_id
        return {"success": True, "group_task_id": group_task_id, "tasks": tasks}
    except ValueError as exc:
        logging.exception("Invalid request for creating or adding tasks")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to process task creation or executor addition")
        raise


@app.put("/api/tasks/{task_id}")
def update_task(
    task_id: int, payload: Union[TaskStatusUpdate, GroupOperationRequest] = Body(...)
) -> dict:
    try:
        if isinstance(payload, GroupOperationRequest) and payload.group_operation:
            task = tasks_repo.get_task_by_id(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} does not exist")
            tasks_repo.update_group(task.group_task_id, payload)
            return {"success": True, "group_task_id": task.group_task_id}
        updated_task = tasks_repo.update_task_status(task_id, payload.status)
        return {"success": True, "task": updated_task}
    except ValueError as exc:
        logging.exception("Task or group not found for update")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to update task or group")
        raise


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int) -> dict:
    try:
        remaining = tasks_repo.delete_task(task_id)
        return {"success": True, "remaining_in_group": remaining}
    except ValueError as exc:
        logging.exception("Task not found for deletion")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to delete task")
        raise


@app.get("/api/users")
def get_users() -> dict:
    return {"users": users_repo.get_all_users()}


@app.post("/api/users")
def upsert_user(user: User) -> dict:
    saved = users_repo.upsert_user(user.username, user.full_name, user.groups)
    return {"user": saved}


@app.delete("/api/users/{username}")
def delete_user(username: str) -> dict:
    try:
        users_repo.delete_user(username)
        return {"success": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/groups")
def get_groups() -> dict:
    return {"groups": groups_repo.get_all_groups()}


@app.post("/api/groups")
def upsert_group(group: Group) -> dict:
    saved = groups_repo.create_or_update_group(group.id, group.name)
    return {"group": saved}


@app.get("/api/config")
def get_config() -> dict:
    cfg: Config = config_repo.get_config()
    return cfg.model_dump()


@app.post("/api/config")
def update_config(cfg: Config) -> dict:
    saved = config_repo.set_config(cfg)
    return saved.model_dump()


@app.get("/api/stats")
def get_stats() -> dict:
    stats: Stats = stats_repo.get_stats()
    return stats.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.web_api:app", host="0.0.0.0", port=8000, reload=True)
