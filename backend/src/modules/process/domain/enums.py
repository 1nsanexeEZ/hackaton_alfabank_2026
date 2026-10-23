"""Enumerations of the process engine."""

from enum import StrEnum


class NodeType(StrEnum):
    START = "start"
    END = "end"
    TASK = "task"  # service task: immediate or async step
    USER_TASK = "user_task"  # stoppable step: waits for a person
    GATEWAY = "gateway"


class OnFailure(StrEnum):
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


class StepKind(StrEnum):
    IMMEDIATE = "immediate"
    ASYNC = "async"
    STOPPABLE = "stoppable"


class ProcessStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WaitKind(StrEnum):
    COMMAND_REPLY = "command_reply"
    CLIENT_EVENT = "client_event"
    USER_TASK = "user_task"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


# A task someone still has to close: the underwriter queue and a cancelled process.
ACTIVE_TASK_STATUSES = [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]
