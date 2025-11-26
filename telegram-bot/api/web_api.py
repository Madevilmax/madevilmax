import logging
from typing import Union

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from models import TaskAddExecutors, TaskCreate, TaskGroupUpdate, TaskStatusUpdate
from repositories.tasks_repository import TasksRepository


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

repository = TasksRepository()


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/api/tasks")
def get_tasks() -> dict:
    tasks = repository.get_all_tasks()
    return {"tasks": tasks}


@app.post("/api/tasks")
def create_or_add_tasks(
    payload: Union[TaskCreate, TaskAddExecutors] = Body(...),
) -> dict:
    try:
        if isinstance(payload, TaskCreate):
            tasks = repository.create_task_group(
                payload.task_text,
                payload.deadline,
                payload.group_id,
                payload.assigned_to,
                payload.assigned_by,
            )
            group_task_id = tasks[0].group_task_id if tasks else None
        else:
            tasks = repository.add_executors_to_group(
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
    task_id: int,
    payload: Union[TaskStatusUpdate, GroupOperationRequest] = Body(...),
) -> dict:
    try:
        if isinstance(payload, GroupOperationRequest) and payload.group_operation:
            task = repository.get_task_by_id(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} does not exist")
            repository.update_group(task.group_task_id, payload)
            return {"success": True, "group_task_id": task.group_task_id}
        updated_task = repository.update_task_status(task_id, payload.status)
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
        remaining = repository.delete_task(task_id)
        return {"success": True, "remaining_in_group": remaining}
    except ValueError as exc:
        logging.exception("Task not found for deletion")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to delete task")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.web_api:app", host="0.0.0.0", port=8000, reload=True)
