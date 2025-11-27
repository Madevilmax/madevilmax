from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


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


class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    groups: List[str] = Field(default_factory=list)


class Group(BaseModel):
    id: str
    name: str


class Config(BaseModel):
    task_created: bool = True
    task_completed: bool = True
    task_deleted: bool = True
    overdue_reminder: bool = True


class Stats(BaseModel):
    total_tasks: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    overdue_tasks: int = 0
    users_count: int = 0
    groups_count: int = 0


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
