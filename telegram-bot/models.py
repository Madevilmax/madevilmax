from typing import List, Optional

from pydantic import BaseModel, field_validator


class TaskGroup(BaseModel):
    group_task_id: int
    task_text: str
    deadline: str
    group_id: str
    created_at: str


class Task(BaseModel):
    id: int
    group_task_id: int
    assigned_to: str
    assigned_by: str
    status: str
    created_at: str
    completed_at: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"active", "completed"}:
            raise ValueError("status must be 'active' or 'completed'")
        return value


class TaskCreate(BaseModel):
    task_text: str
    deadline: str
    group_id: str
    assigned_to: List[str]
    assigned_by: str


class TaskAddExecutors(BaseModel):
    group_task_id: int
    assigned_to: List[str]
    assigned_by: str


class TaskGroupUpdate(BaseModel):
    task_text: Optional[str] = None
    deadline: Optional[str] = None
    group_id: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str  # "active" or "completed"

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"active", "completed"}:
            raise ValueError("status must be 'active' or 'completed'")
        return value
