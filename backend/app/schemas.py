from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    ClassApprovalMode,
    ClassJoinStatus,
    HelpRequestStatus,
    NotificationType,
    ParentGoalStatus,
    Role,
    TaskOrigin,
    TaskPriority,
    TaskSource,
    TaskStatus,
)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Role
    full_name: str
    email: EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    role: Role = Role.STUDENT
    class_request_ids: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginContext(BaseModel):
    student_ids: list[str] = Field(default_factory=list)
    teacher_ids: list[str] = Field(default_factory=list)
    parent_ids: list[str] = Field(default_factory=list)
    class_ids: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    user: UserView
    context: LoginContext


class ChatAssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    screen: str | None = None


class ChatAssistantResponse(BaseModel):
    reply: str
    suggested_actions: list[str] = Field(default_factory=list)
    provider: str


class LinkStudentTeacherRequest(BaseModel):
    student_email: EmailStr
    teacher_email: EmailStr


class LinkStudentParentRequest(BaseModel):
    student_email: EmailStr
    parent_email: EmailStr


class LinkedStudentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: EmailStr


class LinkedUserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: EmailStr


class StudentContactsResponse(BaseModel):
    student_id: str
    teachers: list[LinkedUserView] = Field(default_factory=list)
    parents: list[LinkedUserView] = Field(default_factory=list)


class TaskStepView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    title: str
    order_index: int
    is_done: bool


class CreateTaskRequest(BaseModel):
    student_id: str
    title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = None
    subject: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    source: TaskSource = TaskSource.MANUAL
    steps: list[str] = Field(default_factory=list)


class ExtractTaskRequest(BaseModel):
    student_id: str
    text: str = Field(min_length=1, max_length=4000)
    source: TaskSource = TaskSource.AI_EXTRACTED


class TaskPlanRequest(BaseModel):
    adaptive: bool = True


class UpdateTaskStatusRequest(BaseModel):
    status: TaskStatus


class TaskView(BaseModel):
    id: str
    student_id: str
    created_by_id: str
    title: str
    description: Optional[str]
    subject: Optional[str]
    priority: TaskPriority
    source: TaskSource
    status: TaskStatus
    due_at: Optional[datetime]
    planned_at: Optional[datetime]
    recommended_interval_hours: int
    missed_reminders: int
    assigned_by_role: Optional[Role] = None
    assigned_by_user_id: Optional[str] = None
    assignment_id: Optional[str] = None
    origin: TaskOrigin = TaskOrigin.STUDENT
    educational_validated: bool = True
    educational_reason: Optional[str] = None
    urgency_color: str = "blue"
    created_at: datetime
    completed_at: Optional[datetime]
    attachments: list["TaskAttachmentView"] = Field(default_factory=list)
    steps: list[TaskStepView] = Field(default_factory=list)


class PlanResponse(BaseModel):
    task_id: str
    planned_at: Optional[datetime]
    interval_hours: int
    steps: list[TaskStepView]
    provider: str


class ReminderRunRequest(BaseModel):
    student_id: Optional[str] = None


class ReminderRunResponse(BaseModel):
    processed_tasks: int
    reminders_sent: int
    escalations_sent: int


class ProgressResponse(BaseModel):
    student_id: str
    total_tasks: int
    completed_tasks: int
    overdue_tasks: int
    completion_rate: float
    points_total: int
    active_goal: Optional[str] = None
    goal_progress_rate: float = 0.0


class AnalyticsResponse(BaseModel):
    student_id: str
    hard_topics: list[str]
    recommendations: list[str]
    upcoming_high_priority: int


class TeacherReviewRequest(BaseModel):
    task_id: str
    score: int = Field(ge=1, le=5)
    comment: str = Field(min_length=2)


class TeacherReviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    teacher_id: str
    score: int
    comment: str
    created_at: datetime


class TeacherReviewDetailsView(BaseModel):
    id: str
    task_id: str
    teacher_id: str
    teacher_name: str
    teacher_email: EmailStr
    score: int
    comment: str
    created_at: datetime


class TeacherReviewSuggestRequest(BaseModel):
    task_id: str
    submission_id: Optional[str] = None


class TeacherReviewSuggestView(BaseModel):
    id: str
    task_id: str
    teacher_id: str
    submission_id: Optional[str] = None
    suggested_score: int
    summary: str
    issues: list[str] = Field(default_factory=list)
    recommendation: str
    provider: str
    created_at: datetime


class HelpRequestCreate(BaseModel):
    task_id: str
    question: str = Field(min_length=3)


class HelpRequestAnswer(BaseModel):
    help_request_id: str
    answer: str = Field(min_length=2)


class HelpRequestPayload(BaseModel):
    create: Optional[HelpRequestCreate] = None
    answer: Optional[HelpRequestAnswer] = None


class HelpRequestView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    student_id: str
    teacher_id: str
    question: str
    status: HelpRequestStatus
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]


class NotificationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    task_id: Optional[str]
    type: NotificationType
    message: str
    created_at: datetime
    is_read: bool


class ParentFeedResponse(BaseModel):
    parent_id: str
    student_summaries: list[ProgressResponse]
    notifications: list[NotificationView]


class SchoolClassCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    grade: Optional[str] = Field(default=None, max_length=16)
    approval_mode: ClassApprovalMode = ClassApprovalMode.AUTO


class SchoolClassView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    teacher_id: str
    title: str
    grade: Optional[str]
    approval_mode: ClassApprovalMode
    is_active: bool
    created_at: datetime
    member_count: int = 0
    pending_requests_count: int = 0


class PublicSchoolClassView(BaseModel):
    id: str
    title: str
    grade: Optional[str]
    approval_mode: ClassApprovalMode
    teacher_name: str
    is_invited: bool


class ClassInviteRequest(BaseModel):
    student_email: EmailStr


class ClassInviteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    class_id: str
    student_email: EmailStr
    created_at: datetime


ClassInviteStatus = Literal["invited", "pending", "approved", "member", "rejected"]
StudentInviteRequestStatus = Literal["none", "pending", "approved", "rejected"]


class ClassInviteStatusView(BaseModel):
    id: str
    class_id: str
    student_email: EmailStr
    student_id: Optional[str] = None
    student_full_name: Optional[str] = None
    status: ClassInviteStatus
    is_member: bool
    invite_created_at: datetime
    request_id: Optional[str] = None
    request_created_at: Optional[datetime] = None
    request_decided_at: Optional[datetime] = None


class StudentClassInviteView(BaseModel):
    id: str
    class_id: str
    class_title: str
    grade: Optional[str]
    teacher_name: str
    approval_mode: ClassApprovalMode
    invited_at: datetime
    request_status: StudentInviteRequestStatus
    is_member: bool
    can_request: bool


class ClassJoinRequestCreate(BaseModel):
    message: Optional[str] = Field(default=None, max_length=500)


class ClassJoinRequestDecision(BaseModel):
    status: ClassJoinStatus


class ClassJoinRequestView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    class_id: str
    student_id: str
    student_email: EmailStr
    status: ClassJoinStatus
    message: Optional[str]
    decided_by_user_id: Optional[str]
    created_at: datetime
    decided_at: Optional[datetime]


class AssignmentCreateRequest(BaseModel):
    target_class_id: Optional[str] = None
    target_student_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = None
    subject: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM


class AssignmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    teacher_id: str
    class_id: Optional[str]
    target_student_id: Optional[str]
    title: str
    description: Optional[str]
    subject: Optional[str]
    due_at: Optional[datetime]
    priority: TaskPriority
    created_at: datetime
    created_tasks: int = 0


class SubmissionAttachmentView(BaseModel):
    id: str
    submission_id: str
    file_name: str
    file_path: str
    mime_type: Optional[str]
    size_bytes: int
    created_at: datetime


class TaskAttachmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    file_name: str
    file_path: str
    mime_type: Optional[str]
    size_bytes: int
    created_at: datetime


class AssignmentAttachmentsUploadResponse(BaseModel):
    status: str
    assignment_id: str
    attached_files: int


class TaskSubmissionView(BaseModel):
    id: str
    task_id: str
    student_id: str
    text_answer: Optional[str]
    voice_transcript: Optional[str]
    created_at: datetime
    attachments: list[SubmissionAttachmentView] = Field(default_factory=list)


class ParentGoalCreateRequest(BaseModel):
    student_email: EmailStr
    title: str = Field(min_length=2, max_length=180)
    reward: str = Field(min_length=2, max_length=200)


class ParentGoalEvidenceCreateRequest(BaseModel):
    task_submission_id: Optional[str] = None
    comment: Optional[str] = None


class ParentGoalStatusUpdateRequest(BaseModel):
    status: ParentGoalStatus


class ParentGoalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str
    student_id: str
    title: str
    reward: str
    status: ParentGoalStatus
    created_at: datetime
    completed_at: Optional[datetime]


class ParentGoalEvidenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_goal_id: str
    student_id: str
    task_submission_id: Optional[str]
    comment: Optional[str]
    attachment_path: Optional[str]
    created_at: datetime


class TelegramLoginRequest(BaseModel):
    chat_id: str
    username: Optional[str] = None
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TelegramLoginResponse(BaseModel):
    status: str
    user: UserView


class TelegramNoteRequest(BaseModel):
    chat_id: str
    text: str = Field(min_length=1, max_length=2000)
    due_at: Optional[datetime] = None


class TelegramNoteResponse(BaseModel):
    status: str
    task: TaskView


class TelegramTasksResponse(BaseModel):
    status: str
    tasks: list[TaskView] = Field(default_factory=list)


class TelegramDoneRequest(BaseModel):
    chat_id: str
    task_id: str


class TelegramDoneResponse(BaseModel):
    status: str
    task: TaskView
