from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from app.utils import moscow_now


def new_id() -> str:
    return str(uuid4())


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskSource(StrEnum):
    MANUAL = "manual"
    CLASS_CHAT = "class_chat"
    E_DIARY = "e_diary"
    VOICE = "voice"
    AI_EXTRACTED = "ai_extracted"
    TELEGRAM = "telegram"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskOrigin(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"


class NotificationType(StrEnum):
    TASK_CREATED = "task_created"
    REMINDER = "reminder"
    ESCALATION = "escalation"
    TASK_COMPLETED = "task_completed"
    TEACHER_REVIEW = "teacher_review"
    HELP_REQUEST = "help_request"
    HELP_ANSWERED = "help_answered"
    CLASS_JOIN = "class_join"
    PARENT_GOAL = "parent_goal"


class HelpRequestStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"


class ClassApprovalMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class ClassJoinStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ParentGoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class User(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    role: Role
    full_name: str = Field(index=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    password_salt: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=moscow_now)


class AuthToken(SQLModel, table=True):
    token: str = Field(primary_key=True, index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    expires_at: datetime = Field(index=True)


class StudentTeacherLink(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)


class StudentParentLink(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    parent_id: str = Field(foreign_key="user.id", index=True)


class SchoolClass(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)
    title: str = Field(index=True)
    grade: Optional[str] = Field(default=None, index=True)
    approval_mode: ClassApprovalMode = Field(default=ClassApprovalMode.AUTO, index=True)
    is_active: bool = True
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class ClassStudentInvite(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    class_id: str = Field(foreign_key="schoolclass.id", index=True)
    student_email: str = Field(index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class ClassJoinRequest(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    class_id: str = Field(foreign_key="schoolclass.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    student_email: str = Field(index=True)
    status: ClassJoinStatus = Field(default=ClassJoinStatus.PENDING, index=True)
    message: Optional[str] = None
    decided_by_user_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    decided_at: Optional[datetime] = Field(default=None, index=True)


class ClassMembership(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    class_id: str = Field(foreign_key="schoolclass.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=moscow_now, index=True)
    is_active: bool = True


class Assignment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)
    class_id: Optional[str] = Field(default=None, foreign_key="schoolclass.id", index=True)
    target_student_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    title: str
    description: Optional[str] = None
    subject: Optional[str] = Field(default=None, index=True)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, index=True)
    due_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class Task(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    created_by_id: str = Field(foreign_key="user.id", index=True)
    title: str
    description: Optional[str] = None
    subject: Optional[str] = Field(default=None, index=True)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, index=True)
    source: TaskSource = Field(default=TaskSource.MANUAL)
    status: TaskStatus = Field(default=TaskStatus.TODO, index=True)
    due_at: Optional[datetime] = Field(default=None, index=True)
    planned_at: Optional[datetime] = None
    recommended_interval_hours: int = 6
    missed_reminders: int = 0
    assigned_by_role: Optional[Role] = Field(default=None, index=True)
    assigned_by_user_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    assignment_id: Optional[str] = Field(default=None, foreign_key="assignment.id", index=True)
    origin: TaskOrigin = Field(default=TaskOrigin.STUDENT, index=True)
    educational_validated: bool = True
    educational_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    completed_at: Optional[datetime] = None


class TaskStep(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    title: str
    order_index: int = 0
    is_done: bool = False


class TaskSubmission(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    text_answer: Optional[str] = None
    voice_transcript: Optional[str] = None
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class SubmissionAttachment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    submission_id: str = Field(foreign_key="tasksubmission.id", index=True)
    file_name: str
    file_path: str
    mime_type: Optional[str] = None
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class TaskAttachment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    file_name: str
    file_path: str
    mime_type: Optional[str] = None
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class ReminderRule(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    interval_hours: int = 6
    escalate_after_misses: int = 2
    is_adaptive: bool = False
    active: bool = True


class ReminderEvent(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    fired_at: datetime = Field(default_factory=moscow_now, index=True)
    status: str
    message: str


class Notification(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    task_id: Optional[str] = Field(default=None, foreign_key="task.id", index=True)
    type: NotificationType = Field(index=True)
    message: str
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    is_read: bool = False


class Goal(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    title: str
    target_points: int
    due_at: Optional[datetime] = None
    is_active: bool = True


class ParentGoal(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    parent_id: str = Field(foreign_key="user.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    title: str
    reward: str
    status: ParentGoalStatus = Field(default=ParentGoalStatus.ACTIVE, index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    completed_at: Optional[datetime] = Field(default=None, index=True)


class ParentGoalEvidence(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    parent_goal_id: str = Field(foreign_key="parentgoal.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    task_submission_id: Optional[str] = Field(default=None, foreign_key="tasksubmission.id", index=True)
    comment: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class PointEvent(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    task_id: Optional[str] = Field(default=None, foreign_key="task.id", index=True)
    points: int
    reason: str
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class TeacherReview(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)
    score: int = Field(ge=1, le=5)
    comment: str
    created_at: datetime = Field(default_factory=moscow_now)


class AiReviewSuggestion(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)
    submission_id: Optional[str] = Field(default=None, foreign_key="tasksubmission.id", index=True)
    suggested_score: int = Field(ge=1, le=5)
    summary: str
    issues: Optional[str] = None
    recommendation: str
    provider: str = "fallback"
    created_at: datetime = Field(default_factory=moscow_now, index=True)


class HelpRequest(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    student_id: str = Field(foreign_key="user.id", index=True)
    teacher_id: str = Field(foreign_key="user.id", index=True)
    question: str
    status: HelpRequestStatus = Field(default=HelpRequestStatus.OPEN, index=True)
    answer: Optional[str] = None
    created_at: datetime = Field(default_factory=moscow_now, index=True)
    answered_at: Optional[datetime] = None


class TelegramLink(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    telegram_chat_id: str = Field(index=True, unique=True)
    telegram_username: Optional[str] = None
    failed_attempts: int = 0
    last_login_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=moscow_now, index=True)
