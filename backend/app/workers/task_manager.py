"""
AutoJob AI — Background Task Manager
In-memory state store for tracking automation pipeline progress.

Each task has an ID, status, progress stages, and results.
SSE clients subscribe to real-time updates via asyncio Events.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("autojob.workers.task_manager")

# Max simultaneous browser automations (each uses 300-500 MB RAM)
MAX_CONCURRENT_AUTOMATIONS = 3


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(str, Enum):
    LOGIN = "login"
    SCRAPING = "scraping"
    AI_MATCHING = "ai_matching"
    APPLYING = "applying"
    SAVING = "saving"
    DONE = "done"


@dataclass
class TaskProgress:
    """Tracks progress within the current stage."""
    stage: PipelineStage = PipelineStage.LOGIN
    stage_message: str = "Initializing..."
    current_job_index: int = 0
    total_jobs: int = 0
    # Per-stage details
    jobs_scraped: int = 0
    jobs_matched: int = 0
    jobs_qualified: int = 0
    jobs_applied: int = 0
    jobs_failed: int = 0
    jobs_skipped: int = 0


@dataclass
class TaskState:
    """Complete state of a background task."""
    task_id: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: TaskProgress = field(default_factory=TaskProgress)
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # SSE notification mechanism
    _update_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    # History of progress messages for SSE clients that connect late
    _message_log: list[dict] = field(default_factory=list, repr=False)


class TaskManager:
    """
    Singleton in-memory task manager.
    Stores task states and provides SSE-compatible update mechanism.

    Usage:
        task_id = manager.create_task(user_id)
        manager.update_progress(task_id, stage="scraping", message="Found 5 jobs")
        manager.complete_task(task_id, result={...})
    """

    def __init__(self):
        self._tasks: dict[str, TaskState] = {}

    def create_task(self, user_id: str) -> str | None:
        """Create a new task and return its ID. Returns None if concurrency limit reached."""
        # Check concurrency limit
        active_count = sum(
            1 for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        )
        if active_count >= MAX_CONCURRENT_AUTOMATIONS:
            logger.warning(
                f"Concurrency limit reached ({active_count}/{MAX_CONCURRENT_AUTOMATIONS}). "
                f"Rejecting new task for user {user_id[:8]}"
            )
            return None

        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskState(task_id=task_id, user_id=user_id)
        logger.info(f"Task {task_id[:8]} created for user {user_id[:8]}")
        return task_id

    def get_task(self, task_id: str) -> TaskState | None:
        """Get task state by ID."""
        return self._tasks.get(task_id)

    def get_user_active_task(self, user_id: str) -> TaskState | None:
        """Get the currently running task for a user (if any)."""
        for task in self._tasks.values():
            if task.user_id == user_id and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return task
        return None

    def update_progress(
        self,
        task_id: str,
        stage: PipelineStage | None = None,
        message: str | None = None,
        **kwargs,
    ) -> None:
        """Update task progress and notify SSE subscribers."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.RUNNING
        task.updated_at = datetime.now(timezone.utc)

        if stage:
            task.progress.stage = stage
        if message:
            task.progress.stage_message = message

        # Update any extra progress fields
        for key, value in kwargs.items():
            if hasattr(task.progress, key):
                setattr(task.progress, key, value)

        # Log the message for late-joining SSE clients
        log_entry = {
            "stage": task.progress.stage.value,
            "message": task.progress.stage_message,
            "timestamp": task.updated_at.isoformat(),
            **{k: v for k, v in kwargs.items() if hasattr(task.progress, k)},
        }
        task._message_log.append(log_entry)

        # Wake up SSE subscribers
        task._update_event.set()
        task._update_event.clear()

        logger.debug(f"Task {task_id[:8]}: [{task.progress.stage.value}] {message}")

    def complete_task(self, task_id: str, result: dict) -> None:
        """Mark task as completed with final results."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.COMPLETED
        task.result = result
        task.progress.stage = PipelineStage.DONE
        task.progress.stage_message = "Pipeline complete"
        task.updated_at = datetime.now(timezone.utc)

        task._message_log.append({
            "stage": "done",
            "message": "Pipeline complete",
            "timestamp": task.updated_at.isoformat(),
            "result": result,
        })

        task._update_event.set()
        logger.info(f"Task {task_id[:8]}: COMPLETED")

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed with error message."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.FAILED
        task.error = error
        task.progress.stage_message = f"Failed: {error}"
        task.updated_at = datetime.now(timezone.utc)

        task._message_log.append({
            "stage": "error",
            "message": error,
            "timestamp": task.updated_at.isoformat(),
        })

        task._update_event.set()
        logger.error(f"Task {task_id[:8]}: FAILED — {error}")

    async def wait_for_update(self, task_id: str, timeout: float = 30.0) -> bool:
        """Wait for the next update on a task. Returns False on timeout."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        try:
            await asyncio.wait_for(task._update_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def get_message_log(self, task_id: str) -> list[dict]:
        """Get the full message log for a task (for late-joining SSE clients)."""
        task = self._tasks.get(task_id)
        if not task:
            return []
        return list(task._message_log)

    def cleanup_old_tasks(self, max_age_hours: int = 2) -> int:
        """Remove completed/failed tasks older than max_age_hours."""
        now = datetime.now(timezone.utc)
        to_remove = []
        for tid, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                age = (now - task.created_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(tid)

        for tid in to_remove:
            del self._tasks[tid]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old tasks")
        return len(to_remove)


# ── Singleton Instance ──────────────────────────────
task_manager = TaskManager()
