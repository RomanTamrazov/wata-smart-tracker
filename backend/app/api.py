from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.models import ClassJoinStatus, HelpRequestStatus, User
from app.schemas import (
    AnalyticsResponse,
    AssignmentAttachmentsUploadResponse,
    AssignmentCreateRequest,
    AssignmentView,
    ChatAssistantRequest,
    ChatAssistantResponse,
    ClassInviteStatusView,
    ClassInviteRequest,
    ClassInviteView,
    ClassJoinRequestCreate,
    ClassJoinRequestDecision,
    ClassJoinRequestView,
    CreateTaskRequest,
    ExtractTaskRequest,
    HelpRequestPayload,
    HelpRequestView,
    LinkedStudentView,
    LinkStudentParentRequest,
    LinkStudentTeacherRequest,
    LoginRequest,
    LoginResponse,
    ParentFeedResponse,
    ParentGoalCreateRequest,
    ParentGoalEvidenceView,
    ParentGoalStatusUpdateRequest,
    ParentGoalView,
    PlanResponse,
    ProgressResponse,
    PublicSchoolClassView,
    RegisterRequest,
    ReminderRunRequest,
    ReminderRunResponse,
    SchoolClassCreateRequest,
    SchoolClassView,
    StudentClassInviteView,
    StudentContactsResponse,
    TaskPlanRequest,
    TaskAttachmentView,
    TaskSubmissionView,
    TaskView,
    TeacherReviewDetailsView,
    TeacherReviewRequest,
    TeacherReviewSuggestRequest,
    TeacherReviewSuggestView,
    TeacherReviewView,
    TelegramDoneRequest,
    TelegramDoneResponse,
    TelegramLoginRequest,
    TelegramLoginResponse,
    TelegramNoteRequest,
    TelegramNoteResponse,
    TelegramTasksResponse,
    UpdateTaskStatusRequest,
    UserView,
)
from app.services.tracker import TrackerService

router = APIRouter(prefix="/api/v1")


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


def get_tracker(request: Request) -> TrackerService:
    return request.app.state.tracker


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Нужен Bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Пустой токен")
    return tracker.current_user(session, token)


@router.post("/auth/register", response_model=LoginResponse, tags=["auth"])
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return tracker.register(session, payload)


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return tracker.login(session, payload)


@router.get("/auth/me", response_model=UserView, tags=["auth"])
def me(user: User = Depends(get_current_user)):
    return UserView(id=user.id, role=user.role, full_name=user.full_name, email=user.email)


@router.post("/links/student-teacher", tags=["links"])
def link_student_teacher(
    payload: LinkStudentTeacherRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.link_student_teacher(session, payload, user)
    return {"status": "ok"}


@router.post("/links/student-parent", tags=["links"])
def link_student_parent(
    payload: LinkStudentParentRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.link_student_parent(session, payload, user)
    return {"status": "ok"}


@router.delete("/links/student-teacher", tags=["links"])
def unlink_student_teacher(
    payload: LinkStudentTeacherRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.unlink_student_teacher(session, payload, user)
    return {"status": "ok"}


@router.delete("/links/student-parent", tags=["links"])
def unlink_student_parent(
    payload: LinkStudentParentRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.unlink_student_parent(session, payload, user)
    return {"status": "ok"}


@router.post("/assistant/chat", response_model=ChatAssistantResponse, tags=["assistant", "ai"])
def assistant_chat(
    payload: ChatAssistantRequest,
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.assistant_chat(user, payload)


@router.post("/tasks", response_model=TaskView, tags=["tasks"])
def create_task(
    payload: CreateTaskRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_task(session, payload, user)


@router.post("/tasks/extract", response_model=TaskView, tags=["tasks", "ai"])
def extract_task(
    payload: ExtractTaskRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.extract_task(session, payload, user)


@router.post("/tasks/extract/photo", response_model=TaskView, tags=["tasks", "ai"])
def extract_task_photo(
    student_id: Annotated[str, Form(...)],
    photo: Annotated[UploadFile, File(...)],
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.extract_task_from_photo(session=session, actor=user, student_id=student_id, upload_file=photo)


@router.get("/students/{student_id}/tasks", response_model=list[TaskView], tags=["tasks"])
def list_tasks(
    student_id: str,
    sort: str | None = Query(default=None),
    include_source: bool = Query(default=True),
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_student_tasks(session, student_id, user, sort=sort, include_source=include_source)


@router.get("/students/{student_id}/contacts", response_model=StudentContactsResponse, tags=["links"])
def student_contacts(
    student_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.student_contacts(session, student_id, user)


@router.delete("/tasks/{task_id}", tags=["tasks"])
def delete_task(
    task_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.delete_completed_task(session, task_id, user)
    return {"status": "deleted"}


@router.patch("/tasks/{task_id}/status", response_model=TaskView, tags=["tasks"])
def update_status(
    task_id: str,
    payload: UpdateTaskStatusRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.update_task_status(session, task_id, payload.status, user)


@router.post("/tasks/{task_id}/plan", response_model=PlanResponse, tags=["tasks", "ai"])
def plan_task(
    task_id: str,
    payload: TaskPlanRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    _: User = Depends(get_current_user),
):
    return tracker.plan_task(session, task_id=task_id, adaptive=payload.adaptive)


@router.post("/tasks/{task_id}/submissions", response_model=TaskSubmissionView, tags=["tasks", "submissions"])
def create_submission(
    task_id: str,
    text_answer: Annotated[str | None, Form()] = None,
    voice_transcript: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_task_submission(
        session=session,
        actor=user,
        task_id=task_id,
        text_answer=text_answer,
        voice_transcript=voice_transcript,
        files=files or [],
    )


@router.get("/tasks/{task_id}/submissions", response_model=list[TaskSubmissionView], tags=["tasks", "submissions"])
def list_submissions(
    task_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_task_submissions(session=session, actor=user, task_id=task_id)


@router.get("/tasks/{task_id}/attachments", response_model=list[TaskAttachmentView], tags=["tasks", "attachments"])
def list_task_attachments(
    task_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_task_attachments(session=session, actor=user, task_id=task_id)


@router.get("/files/attachments/{attachment_id}", tags=["submissions"])
def download_attachment(
    attachment_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    path, filename = tracker.resolve_submission_attachment(session=session, actor=user, attachment_id=attachment_id)
    return FileResponse(path=path, filename=filename)


@router.get("/files/task-attachments/{attachment_id}", tags=["attachments"])
def download_task_attachment(
    attachment_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    path, filename = tracker.resolve_task_attachment(session=session, actor=user, attachment_id=attachment_id)
    return FileResponse(path=path, filename=filename)


@router.post("/reminders/run", response_model=ReminderRunResponse, tags=["reminders"])
def run_reminders(
    payload: ReminderRunRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    _: User = Depends(get_current_user),
):
    return tracker.run_reminders(session, student_id=payload.student_id)


@router.get("/students/{student_id}/progress", response_model=ProgressResponse, tags=["analytics"])
def student_progress(
    student_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    _: User = Depends(get_current_user),
):
    return tracker.progress(session, student_id)


@router.get("/students/{student_id}/analytics", response_model=AnalyticsResponse, tags=["analytics", "ai"])
def student_analytics(
    student_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    _: User = Depends(get_current_user),
):
    return tracker.analytics(session, student_id)


@router.post("/teacher/reviews", response_model=TeacherReviewView, tags=["teacher"])
def teacher_review(
    payload: TeacherReviewRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_teacher_review(session, user, payload)


@router.post("/teacher/reviews/suggest", response_model=TeacherReviewSuggestView, tags=["teacher", "ai"])
def teacher_review_suggest(
    payload: TeacherReviewSuggestRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.suggest_teacher_review(
        session=session,
        actor=user,
        task_id=payload.task_id,
        submission_id=payload.submission_id,
    )


@router.get("/tasks/{task_id}/reviews", response_model=list[TeacherReviewDetailsView], tags=["teacher", "tasks"])
def task_reviews(
    task_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_task_reviews(session, task_id, user)


@router.get("/teachers/{teacher_id}/students", response_model=list[LinkedStudentView], tags=["teacher"])
def teacher_students(
    teacher_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_teacher_students(session, teacher_id, user)


@router.post("/assignments", response_model=AssignmentView, tags=["teacher", "tasks"])
def create_assignment(
    payload: AssignmentCreateRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_assignment(session, user, payload)


@router.post(
    "/assignments/{assignment_id}/attachments",
    response_model=AssignmentAttachmentsUploadResponse,
    tags=["teacher", "tasks"],
)
def upload_assignment_attachments(
    assignment_id: str,
    files: Annotated[list[UploadFile] | None, File()] = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.add_assignment_attachments(session=session, actor=user, assignment_id=assignment_id, files=files or [])


@router.post("/classes", response_model=SchoolClassView, tags=["classes", "teacher"])
def create_class(
    payload: SchoolClassCreateRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_class(session, user, payload)


@router.get("/teacher/classes", response_model=list[SchoolClassView], tags=["classes", "teacher"])
def teacher_classes(
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_teacher_classes(session, user)


@router.get("/classes/public", response_model=list[PublicSchoolClassView], tags=["classes"])
def public_classes(
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_public_classes(session, user)


@router.get("/classes/open", response_model=list[PublicSchoolClassView], tags=["classes"])
def open_classes(
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return tracker.list_open_classes(session)


@router.post("/classes/{class_id}/invites", response_model=ClassInviteView, tags=["classes", "teacher"])
def class_invite(
    class_id: str,
    payload: ClassInviteRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.add_class_invite(session, user, class_id, payload)


@router.get("/classes/{class_id}/invites", response_model=list[ClassInviteStatusView], tags=["classes", "teacher"])
def class_invites_list(
    class_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_class_invites(session, user, class_id)


@router.post("/classes/{class_id}/members", response_model=ClassInviteStatusView, tags=["classes", "teacher"])
def class_member_add(
    class_id: str,
    payload: ClassInviteRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.add_class_member(session, user, class_id, payload)


@router.delete("/classes/{class_id}/invites/{invite_id}", tags=["classes", "teacher"])
def class_invite_remove(
    class_id: str,
    invite_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.remove_class_invite(session, user, class_id, invite_id)
    return {"status": "removed"}


@router.delete("/classes/{class_id}", tags=["classes", "teacher"])
def class_delete(
    class_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    tracker.delete_class(session, user, class_id)
    return {"status": "deleted"}


@router.get("/classes/my-invites", response_model=list[StudentClassInviteView], tags=["classes", "student"])
def my_class_invites(
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_my_class_invites(session, user)


@router.post("/classes/{class_id}/requests", response_model=ClassJoinRequestView, tags=["classes"])
def class_request(
    class_id: str,
    payload: ClassJoinRequestCreate,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_class_join_request(session, user, class_id, payload)


@router.get("/classes/{class_id}/requests", response_model=list[ClassJoinRequestView], tags=["classes", "teacher"])
def class_requests_list(
    class_id: str,
    status: ClassJoinStatus | None = Query(default=None),
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_class_join_requests(session, user, class_id, status=status)


@router.patch("/classes/{class_id}/requests/{request_id}", response_model=ClassJoinRequestView, tags=["classes", "teacher"])
def class_request_decision(
    class_id: str,
    request_id: str,
    payload: ClassJoinRequestDecision,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.decide_class_join_request(session, user, class_id, request_id, payload)


@router.post("/help-requests", response_model=HelpRequestView, tags=["help"])
def post_help_request(
    payload: HelpRequestPayload,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.help_request(session, user, payload)


@router.get("/help-requests", response_model=list[HelpRequestView], tags=["help"])
def get_help_requests(
    student_id: str | None = None,
    teacher_id: str | None = None,
    status: HelpRequestStatus | None = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_help_requests(
        session,
        actor=user,
        student_id=student_id,
        teacher_id=teacher_id,
        status=status,
    )


@router.get("/parents/{parent_id}/feed", response_model=ParentFeedResponse, tags=["parent"])
def parent_feed(
    parent_id: str,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    if user.role != "parent" or user.id != parent_id:
        raise HTTPException(status_code=403, detail="Доступ только к собственной ленте родителя")
    return tracker.parent_feed(session, parent_id)


@router.post("/parent/goals", response_model=ParentGoalView, tags=["parent"])
def create_parent_goal(
    payload: ParentGoalCreateRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.create_parent_goal(session, user, payload)


@router.get("/parent/goals", response_model=list[ParentGoalView], tags=["parent"])
def list_parent_goals(
    parent_id: str | None = None,
    student_id: str | None = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.list_parent_goals(session, user, parent_id=parent_id, student_id=student_id)


@router.post("/parent/goals/{goal_id}/evidence", response_model=ParentGoalEvidenceView, tags=["parent"])
def add_parent_goal_evidence(
    goal_id: str,
    task_submission_id: Annotated[str | None, Form()] = None,
    comment: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.add_parent_goal_evidence(
        session=session,
        actor=user,
        goal_id=goal_id,
        task_submission_id=task_submission_id,
        comment=comment,
        files=files or [],
    )


@router.patch("/parent/goals/{goal_id}/status", response_model=ParentGoalView, tags=["parent"])
def update_parent_goal_status(
    goal_id: str,
    payload: ParentGoalStatusUpdateRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
    user: User = Depends(get_current_user),
):
    return tracker.update_parent_goal_status(session, user, goal_id, payload)


@router.post("/telegram/login", response_model=TelegramLoginResponse, tags=["telegram"])
def telegram_login(
    payload: TelegramLoginRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return tracker.telegram_login(session, payload)


@router.post("/telegram/notes", response_model=TelegramNoteResponse, tags=["telegram"])
def telegram_note(
    payload: TelegramNoteRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return tracker.telegram_create_note(session, payload)


@router.get("/telegram/tasks", response_model=TelegramTasksResponse, tags=["telegram"])
def telegram_tasks(
    chat_id: str,
    urgent_only: bool = Query(default=False),
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    return TelegramTasksResponse(status="ok", tasks=tracker.telegram_list_tasks(session, chat_id, urgent_only))


@router.post("/telegram/tasks/done", response_model=TelegramDoneResponse, tags=["telegram"])
def telegram_done(
    payload: TelegramDoneRequest,
    session: Session = Depends(get_session),
    tracker: TrackerService = Depends(get_tracker),
):
    task = tracker.telegram_mark_done(session, payload.chat_id, payload.task_id)
    return TelegramDoneResponse(status="ok", task=task)
