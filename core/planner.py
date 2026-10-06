"""Task state for multi-step agent work.

The agent loop drives a Task through statuses while Gemini requests tools;
steps, results, retries and errors are tracked for observability and recovery.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskStep:
    index: int
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class Task:
    objective: str
    id: str = field(default_factory=lambda: "task_" + uuid.uuid4().hex[:8])
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    steps: list[TaskStep] = field(default_factory=list)
    completed_steps: int = 0
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def current_step(self) -> int:
        return len(self.steps)

    def add_step(self, tool: str, arguments: dict[str, Any], result: dict[str, Any] | None = None,
                 error: str | None = None) -> TaskStep:
        step = TaskStep(index=len(self.steps), tool=tool, arguments=arguments,
                        result=result, error=error)
        self.steps.append(step)
        if result is not None:
            self.tool_results.append(result)
            if result.get("success"):
                self.completed_steps += 1
        if error:
            self.errors.append(error)
        return step

    @property
    def is_terminal(self) -> bool:
        return self.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class Planner:
    """Creates task objects for user objectives."""

    def new_task(self, objective: str) -> Task:
        return Task(objective=objective, status=TaskStatus.RUNNING)
