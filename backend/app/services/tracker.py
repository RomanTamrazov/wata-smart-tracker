from __future__ import annotations

from collections import defaultdict
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from email_validator import EmailNotValidError, validate_email
from sqlmodel import Session, func, select

from app.config import settings
from app.models import (
    AiReviewSuggestion,
    Assignment,
    AuthToken,
    ClassApprovalMode,
    ClassJoinRequest,
    ClassJoinStatus,
    ClassMembership,
    ClassStudentInvite,
    Goal,
    HelpRequest,
    HelpRequestStatus,
    Notification,
    NotificationType,
    ParentGoal,
    ParentGoalEvidence,
    ParentGoalStatus,
    PointEvent,
    ReminderEvent,
    ReminderRule,
    Role,
    SchoolClass,
    SubmissionAttachment,
    StudentParentLink,
    StudentTeacherLink,
    Task,
    TaskAttachment,
    TaskOrigin,
    TaskPriority,
    TaskSource,
    TaskSubmission,
    TaskStatus,
    TaskStep,
    TelegramLink,
    TeacherReview,
    User,
)
from app.schemas import (
    AnalyticsResponse,
    AssignmentCreateRequest,
    AssignmentView,
    AssignmentAttachmentsUploadResponse,
    ClassInviteStatusView,
    ClassInviteRequest,
    ClassInviteView,
    ClassJoinRequestCreate,
    ClassJoinRequestDecision,
    ClassJoinRequestView,
    ChatAssistantRequest,
    ChatAssistantResponse,
    CreateTaskRequest,
    ExtractTaskRequest,
    HelpRequestPayload,
    HelpRequestView,
    LinkedStudentView,
    LinkedUserView,
    LinkStudentParentRequest,
    LinkStudentTeacherRequest,
    LoginContext,
    LoginRequest,
    LoginResponse,
    NotificationView,
    ParentGoalCreateRequest,
    ParentGoalEvidenceView,
    ParentGoalStatusUpdateRequest,
    ParentGoalView,
    ParentFeedResponse,
    PlanResponse,
    PublicSchoolClassView,
    ProgressResponse,
    RegisterRequest,
    ReminderRunResponse,
    SchoolClassCreateRequest,
    SchoolClassView,
    StudentClassInviteView,
    StudentContactsResponse,
    TaskSubmissionView,
    TaskAttachmentView,
    TaskStepView,
    TaskView,
    TeacherReviewSuggestView,
    TeacherReviewDetailsView,
    TeacherReviewRequest,
    TeacherReviewView,
    TelegramLoginRequest,
    TelegramLoginResponse,
    TelegramNoteRequest,
    TelegramNoteResponse,
    UserView,
)
from app.security import generate_salt, hash_password, issue_token, verify_password
from app.services.ai_hybrid import HybridAIService
from app.services.education_filter import validate_educational_task_text
from app.services.emailer import EmailSender
from app.services.ocr import OCRExtractionError, extract_text_from_image
from app.services.uploads import save_upload
from app.utils import moscow_now, normalize_to_tz, task_urgency_color


class TrackerService:
    def __init__(
        self,
        ai_service: HybridAIService,
        email_sender: EmailSender,
        token_ttl_hours: int = settings.token_ttl_hours,
    ) -> None:
        self._ai = ai_service
        self._email = email_sender
        self._token_ttl_hours = token_ttl_hours

    def register(self, session: Session, payload: RegisterRequest) -> LoginResponse:
        email = self._normalize_registration_email(payload.email)
        normalized_full_name = self._normalize_and_validate_full_name(payload.full_name)
        existing = session.exec(select(User).where(User.email == email)).first()
        if existing:
            raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже зарегистрирован")

        salt = generate_salt()
        password_hash = hash_password(payload.password, salt)

        user = User(
            role=payload.role,
            full_name=normalized_full_name,
            email=email,
            password_hash=password_hash,
            password_salt=salt,
            is_active=True,
        )
        session.add(user)
        session.flush()

        if user.role == Role.STUDENT:
            session.add(
                Goal(
                    student_id=user.id,
                    title="Набрать первые 100 баллов",
                    target_points=100,
                    due_at=moscow_now() + timedelta(days=14),
                    is_active=True,
                )
            )
            if payload.class_request_ids:
                for class_id in {item.strip() for item in payload.class_request_ids if item.strip()}:
                    school_class = session.get(SchoolClass, class_id)
                    if not school_class or not school_class.is_active:
                        continue
                    invite = session.exec(
                        select(ClassStudentInvite).where(
                            ClassStudentInvite.class_id == class_id,
                            ClassStudentInvite.student_email == email,
                        )
                    ).first()
                    if not invite:
                        continue
                    existing_membership = session.exec(
                        select(ClassMembership).where(
                            ClassMembership.class_id == class_id,
                            ClassMembership.student_id == user.id,
                            ClassMembership.is_active == True,
                        )
                    ).first()
                    if existing_membership:
                        continue
                    existing_request = session.exec(
                        select(ClassJoinRequest).where(
                            ClassJoinRequest.class_id == class_id,
                            ClassJoinRequest.student_id == user.id,
                            ClassJoinRequest.status == ClassJoinStatus.PENDING,
                        )
                    ).first()
                    if existing_request:
                        continue
                    request = ClassJoinRequest(
                        class_id=class_id,
                        student_id=user.id,
                        student_email=email,
                        status=ClassJoinStatus.PENDING,
                        message="Заявка создана при регистрации",
                    )
                    session.add(request)
                    session.flush()
                    if school_class.approval_mode == ClassApprovalMode.AUTO:
                        self._approve_class_join_request(
                            session=session,
                            school_class=school_class,
                            request=request,
                            decided_by_user_id=school_class.teacher_id,
                        )

        token = self._issue_token(session, user.id)
        session.commit()
        session.refresh(user)

        self._email.send(
            to_email=user.email,
            subject="Добро пожаловать в WATA Smart Tracker",
            body=(
                f"Здравствуйте, {user.full_name}!\n\n"
                "Аккаунт успешно создан. Теперь вы можете управлять задачами,"
                " получать AI-подсказки и email-напоминания по дедлайнам."
            ),
        )

        return self._login_response(session, user, token)

    def _normalize_registration_email(self, email: str) -> str:
        blocked_domains = {
            item.strip().lower()
            for item in settings.blocked_email_domains_raw.split(",")
            if item.strip()
        }

        dns_resolver: Any = None
        if settings.email_check_deliverability:
            try:
                import dns.resolver

                dns_resolver = dns.resolver.Resolver()
                if not dns_resolver.nameservers:
                    raise RuntimeError("empty_nameservers")
            except Exception:
                try:
                    import dns.resolver

                    dns_resolver = dns.resolver.Resolver(configure=False)
                    dns_resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
                    dns_resolver.timeout = 2.0
                    dns_resolver.lifetime = 4.0
                except Exception:
                    dns_resolver = None

        try:
            validated = validate_email(
                email.strip(),
                check_deliverability=settings.email_check_deliverability,
                dns_resolver=dns_resolver,
            )
        except EmailNotValidError as exc:
            raise HTTPException(status_code=400, detail=f"Укажите реальную почту: {exc}") from exc
        except Exception:
            try:
                validated = validate_email(
                    email.strip(),
                    check_deliverability=False,
                )
            except EmailNotValidError as exc:
                raise HTTPException(status_code=400, detail=f"Укажите реальную почту: {exc}") from exc

        normalized = validated.normalized.lower()
        domain = normalized.split("@", 1)[1]
        if domain in blocked_domains:
            raise HTTPException(
                status_code=400,
                detail="Используйте личную почту. Временные/тестовые домены не поддерживаются.",
            )
        return normalized

    def _normalize_and_validate_full_name(self, full_name: str) -> str:
        normalized = re.sub(r"\s+", " ", (full_name or "").strip())
        if len(normalized) < 5:
            raise HTTPException(
                status_code=400,
                detail="Укажите имя и фамилию полностью.",
            )

        parts = normalized.split(" ")
        if len(parts) < 2:
            raise HTTPException(
                status_code=400,
                detail="Введите и имя, и фамилию.",
            )
        if len(parts) > 4:
            raise HTTPException(
                status_code=400,
                detail="Слишком длинное ФИО. Используйте формат: Имя Фамилия.",
            )

        valid_part = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,39}$")
        for part in parts:
            if not valid_part.fullmatch(part):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Имя и фамилия должны содержать только буквы и дефис "
                        "(например, Анна Петрова или Иван-Сергей Смирнов)."
                    ),
                )

        normalized_parts: list[str] = []
        for part in parts:
            normalized_parts.append("-".join(chunk.capitalize() for chunk in part.split("-")))
        return " ".join(normalized_parts)

    def login(self, session: Session, payload: LoginRequest) -> LoginResponse:
        email = payload.email.strip().lower()
        user = session.exec(select(User).where(User.email == email)).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Неверная почта или пароль")

        if not verify_password(payload.password, user.password_salt, user.password_hash):
            raise HTTPException(status_code=401, detail="Неверная почта или пароль")

        token = self._issue_token(session, user.id)
        session.commit()
        return self._login_response(session, user, token)

    def link_student_teacher(
        self,
        session: Session,
        payload: LinkStudentTeacherRequest,
        actor: User,
    ) -> None:
        if actor.role not in {Role.STUDENT, Role.TEACHER}:
            raise HTTPException(status_code=403, detail="Связь ученик-учитель может создавать только ученик или учитель")
        if actor.role == Role.TEACHER and actor.email != payload.teacher_email.lower():
            raise HTTPException(status_code=403, detail="Учитель может привязывать только себя")
        if actor.role == Role.STUDENT and actor.email != payload.student_email.lower():
            raise HTTPException(status_code=403, detail="Ученик может привязывать только себя")

        student = session.exec(
            select(User).where(User.email == payload.student_email.lower(), User.role == Role.STUDENT)
        ).first()
        teacher = session.exec(
            select(User).where(User.email == payload.teacher_email.lower(), User.role == Role.TEACHER)
        ).first()
        if not student or not teacher:
            raise HTTPException(status_code=404, detail="Ученик или учитель не найден")

        existing = session.exec(
            select(StudentTeacherLink).where(
                StudentTeacherLink.student_id == student.id,
                StudentTeacherLink.teacher_id == teacher.id,
            )
        ).first()
        if existing:
            return

        session.add(StudentTeacherLink(student_id=student.id, teacher_id=teacher.id))
        session.commit()

    def unlink_student_teacher(
        self,
        session: Session,
        payload: LinkStudentTeacherRequest,
        actor: User,
    ) -> None:
        if actor.role not in {Role.STUDENT, Role.TEACHER}:
            raise HTTPException(status_code=403, detail="Удалять связь ученик-учитель может только ученик или учитель")
        if actor.role == Role.TEACHER and actor.email != payload.teacher_email.lower():
            raise HTTPException(status_code=403, detail="Учитель может удалять только свои связи")
        if actor.role == Role.STUDENT and actor.email != payload.student_email.lower():
            raise HTTPException(status_code=403, detail="Ученик может удалять только свои связи")

        student = session.exec(
            select(User).where(User.email == payload.student_email.lower(), User.role == Role.STUDENT)
        ).first()
        teacher = session.exec(
            select(User).where(User.email == payload.teacher_email.lower(), User.role == Role.TEACHER)
        ).first()
        if not student or not teacher:
            raise HTTPException(status_code=404, detail="Ученик или учитель не найден")

        link = session.exec(
            select(StudentTeacherLink).where(
                StudentTeacherLink.student_id == student.id,
                StudentTeacherLink.teacher_id == teacher.id,
            )
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="Связь ученик-учитель не найдена")

        session.delete(link)
        session.commit()

    def link_student_parent(
        self,
        session: Session,
        payload: LinkStudentParentRequest,
        actor: User,
    ) -> None:
        if actor.role not in {Role.STUDENT, Role.PARENT}:
            raise HTTPException(status_code=403, detail="Связь ученик-родитель может создавать только ученик или родитель")
        if actor.role == Role.PARENT and actor.email != payload.parent_email.lower():
            raise HTTPException(status_code=403, detail="Родитель может привязывать только себя")
        if actor.role == Role.STUDENT and actor.email != payload.student_email.lower():
            raise HTTPException(status_code=403, detail="Ученик может привязывать только себя")

        student = session.exec(
            select(User).where(User.email == payload.student_email.lower(), User.role == Role.STUDENT)
        ).first()
        parent = session.exec(
            select(User).where(User.email == payload.parent_email.lower(), User.role == Role.PARENT)
        ).first()
        if not student or not parent:
            raise HTTPException(status_code=404, detail="Ученик или родитель не найден")

        existing = session.exec(
            select(StudentParentLink).where(
                StudentParentLink.student_id == student.id,
                StudentParentLink.parent_id == parent.id,
            )
        ).first()
        if existing:
            return

        parent_count = session.exec(
            select(func.count())
            .select_from(StudentParentLink)
            .where(StudentParentLink.student_id == student.id)
        ).one()
        if int(parent_count or 0) >= 2:
            raise HTTPException(status_code=400, detail="Можно привязать не больше двух родителей")

        session.add(StudentParentLink(student_id=student.id, parent_id=parent.id))
        session.commit()

    def unlink_student_parent(
        self,
        session: Session,
        payload: LinkStudentParentRequest,
        actor: User,
    ) -> None:
        if actor.role not in {Role.STUDENT, Role.PARENT}:
            raise HTTPException(status_code=403, detail="Удалять связь ученик-родитель может только ученик или родитель")
        if actor.role == Role.PARENT and actor.email != payload.parent_email.lower():
            raise HTTPException(status_code=403, detail="Родитель может удалять только свои связи")
        if actor.role == Role.STUDENT and actor.email != payload.student_email.lower():
            raise HTTPException(status_code=403, detail="Ученик может удалять только свои связи")

        student = session.exec(
            select(User).where(User.email == payload.student_email.lower(), User.role == Role.STUDENT)
        ).first()
        parent = session.exec(
            select(User).where(User.email == payload.parent_email.lower(), User.role == Role.PARENT)
        ).first()
        if not student or not parent:
            raise HTTPException(status_code=404, detail="Ученик или родитель не найден")

        link = session.exec(
            select(StudentParentLink).where(
                StudentParentLink.student_id == student.id,
                StudentParentLink.parent_id == parent.id,
            )
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="Связь ученик-родитель не найдена")

        session.delete(link)
        session.commit()

    def list_teacher_students(self, session: Session, teacher_id: str, actor: User) -> list[LinkedStudentView]:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Только учитель может смотреть список своих учеников")
        if actor.id != teacher_id:
            raise HTTPException(status_code=403, detail="Нельзя запрашивать список учеников другого учителя")

        linked_ids = set(
            session.exec(
                select(StudentTeacherLink.student_id).where(StudentTeacherLink.teacher_id == teacher_id)
            ).all()
        )
        class_ids = session.exec(
            select(SchoolClass.id).where(SchoolClass.teacher_id == teacher_id, SchoolClass.is_active == True)
        ).all()
        if class_ids:
            member_ids = session.exec(
                select(ClassMembership.student_id).where(
                    ClassMembership.class_id.in_(class_ids),
                    ClassMembership.is_active == True,
                )
            ).all()
            linked_ids.update(member_ids)

        if not linked_ids:
            return []

        rows = session.exec(
            select(User).where(User.id.in_(linked_ids), User.role == Role.STUDENT).order_by(User.full_name)
        ).all()
        return [LinkedStudentView(id=item.id, full_name=item.full_name, email=item.email) for item in rows]

    def student_contacts(self, session: Session, student_id: str, actor: User) -> StudentContactsResponse:
        self._ensure_student_access(session, actor, student_id)

        teacher_rows = session.exec(
            select(User)
            .join(StudentTeacherLink, StudentTeacherLink.teacher_id == User.id)
            .where(StudentTeacherLink.student_id == student_id, User.role == Role.TEACHER)
            .order_by(User.full_name)
        ).all()
        parent_rows = session.exec(
            select(User)
            .join(StudentParentLink, StudentParentLink.parent_id == User.id)
            .where(StudentParentLink.student_id == student_id, User.role == Role.PARENT)
            .order_by(User.full_name)
        ).all()

        return StudentContactsResponse(
            student_id=student_id,
            teachers=[LinkedUserView(id=item.id, full_name=item.full_name, email=item.email) for item in teacher_rows],
            parents=[LinkedUserView(id=item.id, full_name=item.full_name, email=item.email) for item in parent_rows],
        )

    def assistant_chat(
        self,
        actor: User,
        payload: ChatAssistantRequest,
    ) -> ChatAssistantResponse:
        reply = self._ai.assistant_reply(
            message=payload.message,
            role=actor.role.value,
            screen=payload.screen,
        )
        return ChatAssistantResponse(
            reply=reply.reply,
            suggested_actions=reply.suggested_actions,
            provider=reply.provider,
        )

    def create_task(self, session: Session, payload: CreateTaskRequest, actor: User) -> TaskView:
        if actor.role not in {Role.STUDENT, Role.TEACHER}:
            raise HTTPException(status_code=403, detail="Создавать задания могут только ученик или учитель")

        if actor.role == Role.STUDENT and actor.id != payload.student_id:
            raise HTTPException(status_code=403, detail="Ученик может создавать задачи только для себя")

        if actor.role == Role.STUDENT:
            self._validate_student_educational_text(
                " ".join([payload.title, payload.description or "", payload.subject or ""])
            )

        if actor.role == Role.TEACHER:
            self._ensure_student_access(session, actor, payload.student_id)

        task = Task(
            student_id=payload.student_id,
            created_by_id=actor.id,
            title=payload.title.strip(),
            description=(payload.description or "").strip() or None,
            subject=(payload.subject or "").strip() or None,
            due_at=normalize_to_tz(payload.due_at),
            priority=payload.priority,
            source=payload.source,
            assigned_by_role=actor.role,
            assigned_by_user_id=actor.id,
            origin=TaskOrigin.TEACHER if actor.role == Role.TEACHER else TaskOrigin.STUDENT,
            educational_validated=True,
            educational_reason=None,
        )
        session.add(task)
        session.flush()

        for idx, step in enumerate(payload.steps):
            text = step.strip()
            if text:
                session.add(TaskStep(task_id=task.id, title=text, order_index=idx))

        session.add(
            ReminderRule(
                task_id=task.id,
                interval_hours=3 if payload.priority == TaskPriority.HIGH else 6,
                escalate_after_misses=2,
                is_adaptive=False,
                active=True,
            )
        )

        self._notify(
            session,
            user_id=payload.student_id,
            task_id=task.id,
            type_=NotificationType.TASK_CREATED,
            message=f"Новое задание: {task.title}",
            email_subject="Новое задание в трекере",
        )

        session.commit()
        session.refresh(task)
        return self._task_view(session, task)

    def extract_task(self, session: Session, payload: ExtractTaskRequest, actor: User) -> TaskView:
        if actor.role == Role.STUDENT and actor.id != payload.student_id:
            raise HTTPException(status_code=403, detail="Ученик может добавлять AI-задачи только себе")
        if actor.role == Role.TEACHER:
            self._ensure_student_access(session, actor, payload.student_id)

        if actor.role == Role.STUDENT:
            self._validate_student_educational_text(payload.text)

        extracted = self._ai.extract_task(payload.text)
        task = Task(
            student_id=payload.student_id,
            created_by_id=actor.id,
            title=extracted.title,
            description=extracted.description,
            subject=extracted.subject,
            due_at=normalize_to_tz(extracted.due_at),
            priority=extracted.priority,
            source=TaskSource.AI_EXTRACTED,
            assigned_by_role=actor.role,
            assigned_by_user_id=actor.id,
            origin=TaskOrigin.TEACHER if actor.role == Role.TEACHER else TaskOrigin.STUDENT,
            educational_validated=True,
            educational_reason=None,
        )
        session.add(task)
        session.flush()

        session.add(
            ReminderRule(
                task_id=task.id,
                interval_hours=3 if extracted.priority == TaskPriority.HIGH else 6,
                escalate_after_misses=2,
                is_adaptive=True,
                active=True,
            )
        )

        self._notify(
            session,
            user_id=payload.student_id,
            task_id=task.id,
            type_=NotificationType.TASK_CREATED,
            message=f"Задание добавлено через AI ({extracted.provider}): {task.title}",
            email_subject="AI добавил новое задание",
        )

        session.commit()
        session.refresh(task)
        return self._task_view(session, task)

    def list_student_tasks(
        self,
        session: Session,
        student_id: str,
        actor: User,
        sort: str | None = None,
        include_source: bool = False,
    ) -> list[TaskView]:
        self._ensure_student_access(session, actor, student_id)
        tasks = session.exec(select(Task).where(Task.student_id == student_id)).all()
        if actor.role != Role.STUDENT:
            tasks = [task for task in tasks if not self._is_private_student_note(task)]
        if sort == "due_asc":
            far_future = moscow_now() + timedelta(days=3650)
            tasks = sorted(
                tasks,
                key=lambda task: (
                    normalize_to_tz(task.due_at) is None,
                    normalize_to_tz(task.due_at) or far_future,
                    task.created_at,
                ),
            )
        else:
            tasks = sorted(
                tasks,
                key=lambda task: (
                    task.status.value,
                    normalize_to_tz(task.due_at) or (moscow_now() + timedelta(days=3650)),
                    task.created_at,
                ),
            )
        return [self._task_view(session, task) for task in tasks]

    def list_task_reviews(self, session: Session, task_id: str, actor: User) -> list[TeacherReviewDetailsView]:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)

        reviews = session.exec(
            select(TeacherReview).where(TeacherReview.task_id == task_id).order_by(TeacherReview.created_at.desc())
        ).all()
        result: list[TeacherReviewDetailsView] = []
        for item in reviews:
            teacher = session.get(User, item.teacher_id)
            result.append(
                TeacherReviewDetailsView(
                    id=item.id,
                    task_id=item.task_id,
                    teacher_id=item.teacher_id,
                    teacher_name=teacher.full_name if teacher else "Учитель",
                    teacher_email=teacher.email if teacher else "unknown@example.com",
                    score=item.score,
                    comment=item.comment,
                    created_at=item.created_at,
                )
            )
        return result

    def update_task_status(self, session: Session, task_id: str, status: TaskStatus, actor: User) -> TaskView:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_student_access(session, actor, task.student_id)
        if actor.role != Role.STUDENT or actor.id != task.student_id:
            raise HTTPException(status_code=403, detail="Менять статус может только ученик-владелец задания")
        if status == TaskStatus.DONE and self._is_shared_homework(task):
            if not self._task_has_submission_evidence(session=session, task_id=task.id, student_id=actor.id):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Сначала сдайте решение по ДЗ: добавьте текст, голосовой текст или файл "
                        "через кнопку «Сдать решение»."
                    ),
                )

        first_completion = task.status != TaskStatus.DONE and status == TaskStatus.DONE

        task.status = status
        if status == TaskStatus.DONE:
            task.completed_at = moscow_now()
            task.missed_reminders = 0
        else:
            task.completed_at = None

        if first_completion:
            existing = session.exec(
                select(PointEvent).where(PointEvent.task_id == task.id, PointEvent.reason == "task_completed")
            ).first()
            if not existing:
                session.add(
                    PointEvent(
                        student_id=task.student_id,
                        task_id=task.id,
                        points=10,
                        reason="task_completed",
                    )
                )

            if self._is_shared_homework(task):
                teacher_ids, parent_ids = self._student_related_contacts(session, task.student_id)
                for user_id in teacher_ids + parent_ids:
                    self._notify(
                        session,
                        user_id=user_id,
                        task_id=task.id,
                        type_=NotificationType.TASK_COMPLETED,
                        message=f"Задание выполнено: {task.title}",
                        email_subject="Задание выполнено",
                    )

        session.add(task)
        session.commit()
        session.refresh(task)
        return self._task_view(session, task)

    def delete_completed_task(self, session: Session, task_id: str, actor: User) -> None:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        if actor.role != Role.STUDENT or actor.id != task.student_id:
            raise HTTPException(status_code=403, detail="Удалять выполненные задания может только ученик-владелец")
        if task.status != TaskStatus.DONE:
            raise HTTPException(status_code=400, detail="Удалять можно только выполненные задания")

        for step in session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all():
            session.delete(step)
        for rule in session.exec(select(ReminderRule).where(ReminderRule.task_id == task.id)).all():
            session.delete(rule)
        for event in session.exec(select(ReminderEvent).where(ReminderEvent.task_id == task.id)).all():
            session.delete(event)
        for notification in session.exec(select(Notification).where(Notification.task_id == task.id)).all():
            session.delete(notification)
        for point_event in session.exec(select(PointEvent).where(PointEvent.task_id == task.id)).all():
            session.delete(point_event)
        for review in session.exec(select(TeacherReview).where(TeacherReview.task_id == task.id)).all():
            session.delete(review)
        for help_request in session.exec(select(HelpRequest).where(HelpRequest.task_id == task.id)).all():
            session.delete(help_request)
        for task_attachment in session.exec(select(TaskAttachment).where(TaskAttachment.task_id == task.id)).all():
            session.delete(task_attachment)
        submissions = session.exec(select(TaskSubmission).where(TaskSubmission.task_id == task.id)).all()
        for submission in submissions:
            for attachment in session.exec(
                select(SubmissionAttachment).where(SubmissionAttachment.submission_id == submission.id)
            ).all():
                session.delete(attachment)
            session.delete(submission)

        session.delete(task)
        session.commit()

    def plan_task(self, session: Session, task_id: str, adaptive: bool) -> PlanResponse:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        plan = self._ai.plan_task(
            title=task.title,
            description=task.description,
            priority=task.priority,
            due_at=task.due_at,
        )

        task.planned_at = normalize_to_tz(plan.planned_at)
        task.recommended_interval_hours = plan.interval_hours
        session.add(task)

        for old_step in session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all():
            session.delete(old_step)

        created_steps: list[TaskStep] = []
        for idx, step_text in enumerate(plan.steps):
            step = TaskStep(task_id=task.id, title=step_text, order_index=idx)
            session.add(step)
            created_steps.append(step)

        rule = session.exec(select(ReminderRule).where(ReminderRule.task_id == task.id)).first()
        if rule is None:
            rule = ReminderRule(task_id=task.id)
        rule.interval_hours = plan.interval_hours
        rule.is_adaptive = adaptive
        rule.active = True
        session.add(rule)

        session.commit()
        for step in created_steps:
            session.refresh(step)

        return PlanResponse(
            task_id=task.id,
            planned_at=task.planned_at,
            interval_hours=plan.interval_hours,
            steps=[self._step_view(step) for step in created_steps],
            provider=plan.provider,
        )

    def run_reminders(self, session: Session, student_id: str | None = None) -> ReminderRunResponse:
        query = select(ReminderRule, Task).join(Task, ReminderRule.task_id == Task.id).where(ReminderRule.active == True)
        if student_id:
            query = query.where(Task.student_id == student_id)

        rows = session.exec(query).all()
        reminders_sent = 0
        escalations_sent = 0
        processed = 0
        now = moscow_now()

        for rule, task in rows:
            if task.status == TaskStatus.DONE:
                continue

            last_event = session.exec(
                select(ReminderEvent)
                .where(ReminderEvent.task_id == task.id)
                .order_by(ReminderEvent.fired_at.desc())
            ).first()
            if last_event is not None:
                last_fired_at = normalize_to_tz(last_event.fired_at)
                if last_fired_at is None:
                    continue
                delta = now - last_fired_at
                if delta.total_seconds() < rule.interval_hours * 3600:
                    continue

            processed += 1
            task.missed_reminders += 1

            teacher_ids: list[str] = []
            parent_ids: list[str] = []
            if self._is_shared_homework(task):
                teacher_ids, parent_ids = self._student_related_contacts(session, task.student_id)
            if task.missed_reminders >= rule.escalate_after_misses:
                escalations_sent += 1
                message = (
                    f"Эскалация: по задаче '{task.title}' пропущено {task.missed_reminders} "
                    "напоминаний"
                )
                session.add(ReminderEvent(task_id=task.id, status="escalated", message=message))

                self._notify(
                    session,
                    user_id=task.student_id,
                    task_id=task.id,
                    type_=NotificationType.ESCALATION,
                    message=message,
                    email_subject="Эскалация по задаче",
                )
                for user_id in teacher_ids + parent_ids:
                    self._notify(
                        session,
                        user_id=user_id,
                        task_id=task.id,
                        type_=NotificationType.ESCALATION,
                        message=message,
                        email_subject="Эскалация по задаче ученика",
                    )
            else:
                reminders_sent += 1
                message = (
                    f"Напоминание: пора вернуться к задаче '{task.title}'. "
                    f"Следующее напоминание через {rule.interval_hours} ч."
                )
                session.add(ReminderEvent(task_id=task.id, status="reminder", message=message))
                self._notify(
                    session,
                    user_id=task.student_id,
                    task_id=task.id,
                    type_=NotificationType.REMINDER,
                    message=message,
                    email_subject="Напоминание по задаче",
                )

            session.add(task)

        session.commit()
        return ReminderRunResponse(
            processed_tasks=processed,
            reminders_sent=reminders_sent,
            escalations_sent=escalations_sent,
        )

    def progress(self, session: Session, student_id: str) -> ProgressResponse:
        tasks = session.exec(select(Task).where(Task.student_id == student_id)).all()
        total = len(tasks)
        completed = sum(1 for task in tasks if task.status == TaskStatus.DONE)
        now = moscow_now()
        overdue = sum(
            1
            for task in tasks
            if task.status != TaskStatus.DONE
            and normalize_to_tz(task.due_at) is not None
            and normalize_to_tz(task.due_at) < now
        )
        completion_rate = round((completed / total) * 100, 2) if total else 0.0

        points = session.exec(
            select(func.coalesce(func.sum(PointEvent.points), 0)).where(PointEvent.student_id == student_id)
        ).one()

        goal = session.exec(select(Goal).where(Goal.student_id == student_id, Goal.is_active == True)).first()
        goal_title = goal.title if goal else None
        goal_progress = 0.0
        if goal and goal.target_points > 0:
            goal_progress = round((points / goal.target_points) * 100, 2)

        return ProgressResponse(
            student_id=student_id,
            total_tasks=total,
            completed_tasks=completed,
            overdue_tasks=overdue,
            completion_rate=completion_rate,
            points_total=int(points or 0),
            active_goal=goal_title,
            goal_progress_rate=goal_progress,
        )

    def analytics(self, session: Session, student_id: str) -> AnalyticsResponse:
        tasks = session.exec(select(Task).where(Task.student_id == student_id)).all()
        if not tasks:
            return AnalyticsResponse(
                student_id=student_id,
                hard_topics=[],
                recommendations=["Добавьте задания, чтобы собрать аналитику."],
                upcoming_high_priority=0,
            )

        subject_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "done": 0, "overdue": 0})
        now = moscow_now()
        upcoming_high = 0

        for task in tasks:
            subject = task.subject or "Без предмета"
            subject_stats[subject]["total"] += 1
            if task.status == TaskStatus.DONE:
                subject_stats[subject]["done"] += 1
            task_due_at = normalize_to_tz(task.due_at)
            if task.status != TaskStatus.DONE and task_due_at and task_due_at < now:
                subject_stats[subject]["overdue"] += 1
            if task.status != TaskStatus.DONE and task.priority == TaskPriority.HIGH:
                upcoming_high += 1

        summary = [
            {
                "subject": subject,
                "total": values["total"],
                "done": values["done"],
                "overdue": values["overdue"],
            }
            for subject, values in subject_stats.items()
        ]

        summary.sort(key=lambda x: (x["overdue"], x["total"] - x["done"]), reverse=True)
        hard_topics = [item["subject"] for item in summary if item["overdue"] > 0][:3]
        if not hard_topics:
            hard_topics = [item["subject"] for item in summary[:2]]

        ai_recs = self._ai.analytics(summary)
        return AnalyticsResponse(
            student_id=student_id,
            hard_topics=hard_topics,
            recommendations=ai_recs.recommendations,
            upcoming_high_priority=upcoming_high,
        )

    def create_teacher_review(self, session: Session, actor: User, payload: TeacherReviewRequest) -> TeacherReviewView:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Только учитель может оставлять проверку")

        task = session.get(Task, payload.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)

        review = TeacherReview(task_id=payload.task_id, teacher_id=actor.id, score=payload.score, comment=payload.comment)
        session.add(review)

        self._notify(
            session,
            user_id=task.student_id,
            task_id=task.id,
            type_=NotificationType.TEACHER_REVIEW,
            message=f"Учитель оставил комментарий по задаче '{task.title}'",
            email_subject="Комментарий учителя",
        )

        _, parent_ids = self._student_related_contacts(session, task.student_id)
        for parent_id in parent_ids:
            self._notify(
                session,
                user_id=parent_id,
                task_id=task.id,
                type_=NotificationType.TEACHER_REVIEW,
                message=f"Появилась проверка учителя по задаче '{task.title}'",
                email_subject="Проверка учителя",
            )

        if payload.score >= 4:
            session.add(PointEvent(student_id=task.student_id, task_id=task.id, points=5, reason="teacher_review_bonus"))

        session.commit()
        session.refresh(review)
        return TeacherReviewView.model_validate(review)

    def help_request(self, session: Session, actor: User, payload: HelpRequestPayload) -> HelpRequestView:
        if payload.create and payload.answer:
            raise HTTPException(status_code=400, detail="Передайте только create или answer")

        if payload.create:
            if actor.role != Role.STUDENT:
                raise HTTPException(status_code=403, detail="Создавать запрос помощи может только ученик")

            task = session.get(Task, payload.create.task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Задание не найдено")
            if self._is_private_student_note(task):
                raise HTTPException(status_code=400, detail="Запрос помощи доступен только по выданному домашнему заданию")

            teacher_link = session.exec(
                select(StudentTeacherLink).where(StudentTeacherLink.student_id == actor.id)
            ).first()
            teacher_id = teacher_link.teacher_id if teacher_link else None
            if not teacher_id:
                teacher_id = session.exec(
                    select(SchoolClass.teacher_id)
                    .join(ClassMembership, ClassMembership.class_id == SchoolClass.id)
                    .where(
                        ClassMembership.student_id == actor.id,
                        ClassMembership.is_active == True,
                        SchoolClass.is_active == True,
                    )
                ).first()
            if not teacher_id:
                raise HTTPException(status_code=400, detail="Сначала привяжите учителя или вступите в класс")

            request = HelpRequest(
                task_id=payload.create.task_id,
                student_id=actor.id,
                teacher_id=teacher_id,
                question=payload.create.question,
            )
            session.add(request)
            self._notify(
                session,
                user_id=teacher_id,
                task_id=task.id,
                type_=NotificationType.HELP_REQUEST,
                message=f"Новый запрос помощи по задаче '{task.title}'",
                email_subject="Новый запрос помощи",
            )
            session.commit()
            session.refresh(request)
            return HelpRequestView.model_validate(request)

        if payload.answer:
            if actor.role != Role.TEACHER:
                raise HTTPException(status_code=403, detail="Отвечать на запрос может только учитель")

            request = session.get(HelpRequest, payload.answer.help_request_id)
            if not request:
                raise HTTPException(status_code=404, detail="Запрос помощи не найден")
            if request.teacher_id != actor.id:
                raise HTTPException(status_code=403, detail="Запрос назначен другому учителю")

            request.answer = payload.answer.answer
            request.status = HelpRequestStatus.ANSWERED
            request.answered_at = moscow_now()
            session.add(request)

            task = session.get(Task, request.task_id)
            self._notify(
                session,
                user_id=request.student_id,
                task_id=request.task_id,
                type_=NotificationType.HELP_ANSWERED,
                message=f"Учитель ответил на запрос по задаче '{task.title if task else ''}'",
                email_subject="Ответ учителя по задаче",
            )
            _, parent_ids = self._student_related_contacts(session, request.student_id)
            for parent_id in parent_ids:
                self._notify(
                    session,
                    user_id=parent_id,
                    task_id=request.task_id,
                    type_=NotificationType.HELP_ANSWERED,
                    message="Учитель помог ученику по одной из задач",
                    email_subject="Учитель ответил по задаче",
                )

            session.commit()
            session.refresh(request)
            return HelpRequestView.model_validate(request)

        raise HTTPException(status_code=400, detail="Требуется поле create или answer")

    def list_help_requests(
        self,
        session: Session,
        actor: User,
        student_id: str | None,
        teacher_id: str | None,
        status: HelpRequestStatus | None,
    ) -> list[HelpRequestView]:
        if actor.role == Role.STUDENT:
            if student_id and student_id != actor.id:
                raise HTTPException(status_code=403, detail="Ученик может смотреть только свои запросы")
            student_id = actor.id
        elif actor.role == Role.TEACHER:
            if teacher_id and teacher_id != actor.id:
                raise HTTPException(status_code=403, detail="Учитель может смотреть только свои запросы")
            teacher_id = actor.id
        elif actor.role == Role.PARENT:
            linked_student_ids = list(
                session.exec(
                    select(StudentParentLink.student_id).where(StudentParentLink.parent_id == actor.id)
                ).all()
            )
            if not linked_student_ids:
                return []

        query = select(HelpRequest)
        if student_id:
            query = query.where(HelpRequest.student_id == student_id)
        if teacher_id:
            query = query.where(HelpRequest.teacher_id == teacher_id)
        if status:
            query = query.where(HelpRequest.status == status)
        if actor.role == Role.PARENT:
            query = query.where(HelpRequest.student_id.in_(linked_student_ids))

        rows = session.exec(query.order_by(HelpRequest.created_at.desc())).all()
        return [HelpRequestView.model_validate(item) for item in rows]

    def parent_feed(self, session: Session, parent_id: str) -> ParentFeedResponse:
        links = session.exec(select(StudentParentLink).where(StudentParentLink.parent_id == parent_id)).all()
        student_ids = [link.student_id for link in links]

        summaries = [self.progress(session, sid) for sid in student_ids]
        notifications = session.exec(
            select(Notification).where(Notification.user_id == parent_id).order_by(Notification.created_at.desc()).limit(50)
        ).all()

        return ParentFeedResponse(
            parent_id=parent_id,
            student_summaries=summaries,
            notifications=[NotificationView.model_validate(item) for item in notifications],
        )

    def create_class(self, session: Session, actor: User, payload: SchoolClassCreateRequest) -> SchoolClassView:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Класс может создавать только учитель")

        normalized_title = "".join(payload.title.strip().split())
        title_match = re.match(r"^(?P<grade>[1-9]|1[0-1])(?P<parallel>[A-Za-zА-Яа-яЁё])$", normalized_title)
        if not title_match:
            raise HTTPException(
                status_code=400,
                detail="Название класса должно быть в формате 1-11 + буква параллели, например 7А",
            )

        grade_from_title = int(title_match.group("grade"))
        normalized_parallel = title_match.group("parallel").upper()

        if payload.grade is not None:
            normalized_grade = payload.grade.strip()
            if not normalized_grade.isdigit():
                raise HTTPException(status_code=400, detail="Поле grade должно быть числом от 1 до 11")
            grade_value = int(normalized_grade)
            if grade_value < 1 or grade_value > 11:
                raise HTTPException(status_code=400, detail="Поле grade должно быть числом от 1 до 11")
            if grade_value != grade_from_title:
                raise HTTPException(
                    status_code=400,
                    detail="Номер класса в названии и в поле grade должен совпадать",
                )
        else:
            grade_value = grade_from_title

        school_class = SchoolClass(
            teacher_id=actor.id,
            title=f"{grade_value}{normalized_parallel}",
            grade=str(grade_value),
            approval_mode=payload.approval_mode,
            is_active=True,
        )
        session.add(school_class)
        session.commit()
        session.refresh(school_class)
        return SchoolClassView(
            id=school_class.id,
            teacher_id=school_class.teacher_id,
            title=school_class.title,
            grade=school_class.grade,
            approval_mode=school_class.approval_mode,
            is_active=school_class.is_active,
            created_at=school_class.created_at,
            member_count=0,
            pending_requests_count=0,
        )

    def list_teacher_classes(self, session: Session, actor: User) -> list[SchoolClassView]:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Только учитель может смотреть свои классы")
        rows = session.exec(
            select(SchoolClass)
            .where(SchoolClass.teacher_id == actor.id, SchoolClass.is_active == True)
            .order_by(SchoolClass.created_at.desc())
        ).all()
        if not rows:
            return []

        class_ids = [item.id for item in rows]

        member_counts: dict[str, int] = {
            class_id: int(count or 0)
            for class_id, count in session.exec(
                select(ClassMembership.class_id, func.count())
                .where(ClassMembership.class_id.in_(class_ids), ClassMembership.is_active == True)
                .group_by(ClassMembership.class_id)
            ).all()
        }
        pending_counts: dict[str, int] = {
            class_id: int(count or 0)
            for class_id, count in session.exec(
                select(ClassJoinRequest.class_id, func.count())
                .where(
                    ClassJoinRequest.class_id.in_(class_ids),
                    ClassJoinRequest.status == ClassJoinStatus.PENDING,
                )
                .group_by(ClassJoinRequest.class_id)
            ).all()
        }

        return [
            SchoolClassView(
                id=item.id,
                teacher_id=item.teacher_id,
                title=item.title,
                grade=item.grade,
                approval_mode=item.approval_mode,
                is_active=item.is_active,
                created_at=item.created_at,
                member_count=member_counts.get(item.id, 0),
                pending_requests_count=pending_counts.get(item.id, 0),
            )
            for item in rows
        ]

    def list_public_classes(self, session: Session, actor: User) -> list[PublicSchoolClassView]:
        classes = session.exec(
            select(SchoolClass).where(SchoolClass.is_active == True).order_by(SchoolClass.created_at.desc())
        ).all()
        invited_class_ids: set[str] = set()
        if actor.role == Role.STUDENT:
            invited_rows = session.exec(
                select(ClassStudentInvite.class_id).where(
                    ClassStudentInvite.student_email == actor.email.lower(),
                )
            ).all()
            invited_class_ids = set(invited_rows)

        teacher_map: dict[str, str] = {}
        for item in classes:
            if item.teacher_id not in teacher_map:
                teacher = session.get(User, item.teacher_id)
                teacher_map[item.teacher_id] = teacher.full_name if teacher else "Учитель"

        return [
            PublicSchoolClassView(
                id=item.id,
                title=item.title,
                grade=item.grade,
                approval_mode=item.approval_mode,
                teacher_name=teacher_map.get(item.teacher_id, "Учитель"),
                is_invited=item.id in invited_class_ids,
            )
            for item in classes
        ]

    def list_open_classes(self, session: Session) -> list[PublicSchoolClassView]:
        classes = session.exec(
            select(SchoolClass).where(SchoolClass.is_active == True).order_by(SchoolClass.created_at.desc())
        ).all()
        teacher_map: dict[str, str] = {}
        for item in classes:
            if item.teacher_id not in teacher_map:
                teacher = session.get(User, item.teacher_id)
                teacher_map[item.teacher_id] = teacher.full_name if teacher else "Учитель"
        return [
            PublicSchoolClassView(
                id=item.id,
                title=item.title,
                grade=item.grade,
                approval_mode=item.approval_mode,
                teacher_name=teacher_map.get(item.teacher_id, "Учитель"),
                is_invited=False,
            )
            for item in classes
        ]

    def add_class_invite(
        self,
        session: Session,
        actor: User,
        class_id: str,
        payload: ClassInviteRequest,
    ) -> ClassInviteView:
        school_class = self._ensure_teacher_class_access(session, actor, class_id)
        email = payload.student_email.strip().lower()
        existing = session.exec(
            select(ClassStudentInvite).where(
                ClassStudentInvite.class_id == class_id,
                ClassStudentInvite.student_email == email,
            )
        ).first()
        if existing:
            return ClassInviteView.model_validate(existing)

        invite = ClassStudentInvite(class_id=school_class.id, student_email=email)
        session.add(invite)

        student_user = session.exec(
            select(User).where(User.email == email, User.role == Role.STUDENT, User.is_active == True)
        ).first()
        if student_user:
            self._notify(
                session=session,
                user_id=student_user.id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message=f"Учитель добавил вас в список класса «{school_class.title}». Подайте заявку на вступление.",
                email_subject="Вас добавили в список класса",
            )

        session.commit()
        session.refresh(invite)
        return ClassInviteView.model_validate(invite)

    def add_class_member(
        self,
        session: Session,
        actor: User,
        class_id: str,
        payload: ClassInviteRequest,
    ) -> ClassInviteStatusView:
        school_class = self._ensure_teacher_class_access(session, actor, class_id)
        email = payload.student_email.strip().lower()

        invite = session.exec(
            select(ClassStudentInvite).where(
                ClassStudentInvite.class_id == class_id,
                ClassStudentInvite.student_email == email,
            )
        ).first()
        if not invite:
            invite = ClassStudentInvite(class_id=school_class.id, student_email=email)
            session.add(invite)
            session.flush()

        student_user = session.exec(
            select(User).where(User.email == email, User.role == Role.STUDENT, User.is_active == True)
        ).first()
        if student_user:
            membership = session.exec(
                select(ClassMembership).where(
                    ClassMembership.class_id == class_id,
                    ClassMembership.student_id == student_user.id,
                )
            ).first()
            if membership:
                if not membership.is_active:
                    membership.is_active = True
                    session.add(membership)
            else:
                session.add(ClassMembership(class_id=class_id, student_id=student_user.id, is_active=True))

            request = session.exec(
                select(ClassJoinRequest)
                .where(
                    ClassJoinRequest.class_id == class_id,
                    ClassJoinRequest.student_id == student_user.id,
                )
                .order_by(ClassJoinRequest.created_at.desc())
            ).first()
            now = moscow_now()
            if request:
                if request.status != ClassJoinStatus.APPROVED:
                    request.status = ClassJoinStatus.APPROVED
                    request.decided_by_user_id = actor.id
                    request.decided_at = now
                    session.add(request)
            else:
                session.add(
                    ClassJoinRequest(
                        class_id=class_id,
                        student_id=student_user.id,
                        student_email=email,
                        status=ClassJoinStatus.APPROVED,
                        message="Добавлен учителем",
                        decided_by_user_id=actor.id,
                        decided_at=now,
                    )
                )

            self._notify(
                session=session,
                user_id=student_user.id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message=f"Учитель добавил вас в класс «{school_class.title}».",
                email_subject="Вы добавлены в класс",
            )

        session.commit()
        return self._class_invite_status_row(session=session, class_id=class_id, invite=invite)

    def list_class_invites(
        self,
        session: Session,
        actor: User,
        class_id: str,
    ) -> list[ClassInviteStatusView]:
        self._ensure_teacher_class_access(session, actor, class_id)
        invites = session.exec(
            select(ClassStudentInvite)
            .where(ClassStudentInvite.class_id == class_id)
            .order_by(ClassStudentInvite.created_at.desc())
        ).all()
        if not invites:
            return []

        return [self._class_invite_status_row(session=session, class_id=class_id, invite=invite) for invite in invites]

    def list_my_class_invites(self, session: Session, actor: User) -> list[StudentClassInviteView]:
        if actor.role != Role.STUDENT:
            raise HTTPException(status_code=403, detail="Этот список доступен только ученику")

        invites = session.exec(
            select(ClassStudentInvite)
            .where(ClassStudentInvite.student_email == actor.email.lower())
            .order_by(ClassStudentInvite.created_at.desc())
        ).all()
        if not invites:
            return []

        results: list[StudentClassInviteView] = []
        for invite in invites:
            school_class = session.get(SchoolClass, invite.class_id)
            if not school_class or not school_class.is_active:
                continue

            teacher = session.get(User, school_class.teacher_id)
            membership = session.exec(
                select(ClassMembership).where(
                    ClassMembership.class_id == school_class.id,
                    ClassMembership.student_id == actor.id,
                    ClassMembership.is_active == True,
                )
            ).first()
            request = session.exec(
                select(ClassJoinRequest)
                .where(
                    ClassJoinRequest.class_id == school_class.id,
                    ClassJoinRequest.student_id == actor.id,
                )
                .order_by(ClassJoinRequest.created_at.desc())
            ).first()

            request_status = request.status.value if request else "none"
            is_member = membership is not None
            can_request = (not is_member) and request_status in {"none", "rejected"}

            results.append(
                StudentClassInviteView(
                    id=invite.id,
                    class_id=school_class.id,
                    class_title=school_class.title,
                    grade=school_class.grade,
                    teacher_name=teacher.full_name if teacher else "Учитель",
                    approval_mode=school_class.approval_mode,
                    invited_at=invite.created_at,
                    request_status=request_status,  # type: ignore[arg-type]
                    is_member=is_member,
                    can_request=can_request,
                )
            )

        return results

    def remove_class_invite(
        self,
        session: Session,
        actor: User,
        class_id: str,
        invite_id: str,
    ) -> None:
        self._ensure_teacher_class_access(session, actor, class_id)
        invite = session.get(ClassStudentInvite, invite_id)
        if not invite or invite.class_id != class_id:
            raise HTTPException(status_code=404, detail="Запись приглашения не найдена")

        student = session.exec(
            select(User).where(
                User.email == invite.student_email.lower(),
                User.role == Role.STUDENT,
                User.is_active == True,
            )
        ).first()

        if student:
            memberships = session.exec(
                select(ClassMembership).where(
                    ClassMembership.class_id == class_id,
                    ClassMembership.student_id == student.id,
                    ClassMembership.is_active == True,
                )
            ).all()
            for membership in memberships:
                membership.is_active = False
                session.add(membership)

            self._notify(
                session=session,
                user_id=student.id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message="Учитель удалил вас из списка класса.",
                email_subject="Изменение доступа к классу",
            )

        session.delete(invite)
        session.commit()

    def delete_class(self, session: Session, actor: User, class_id: str) -> None:
        school_class = self._ensure_teacher_class_access(session, actor, class_id)
        school_class.is_active = False
        session.add(school_class)

        memberships = session.exec(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.is_active == True,
            )
        ).all()
        member_ids: set[str] = set()
        for membership in memberships:
            membership.is_active = False
            session.add(membership)
            member_ids.add(membership.student_id)

        pending_requests = session.exec(
            select(ClassJoinRequest).where(
                ClassJoinRequest.class_id == class_id,
                ClassJoinRequest.status == ClassJoinStatus.PENDING,
            )
        ).all()
        for request in pending_requests:
            request.status = ClassJoinStatus.REJECTED
            request.decided_by_user_id = actor.id
            request.decided_at = moscow_now()
            session.add(request)

        for student_id in member_ids:
            self._notify(
                session=session,
                user_id=student_id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message=f"Класс «{school_class.title}» был закрыт учителем.",
                email_subject="Класс закрыт",
            )

        session.commit()

    def create_class_join_request(
        self,
        session: Session,
        actor: User,
        class_id: str,
        payload: ClassJoinRequestCreate,
    ) -> ClassJoinRequestView:
        if actor.role != Role.STUDENT:
            raise HTTPException(status_code=403, detail="Заявку в класс может отправить только ученик")
        school_class = session.get(SchoolClass, class_id)
        if not school_class or not school_class.is_active:
            raise HTTPException(status_code=404, detail="Класс не найден")

        invite = session.exec(
            select(ClassStudentInvite).where(
                ClassStudentInvite.class_id == class_id,
                ClassStudentInvite.student_email == actor.email.lower(),
            )
        ).first()
        if not invite:
            raise HTTPException(status_code=403, detail="Эта почта не добавлена в список класса")

        active_member = session.exec(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.student_id == actor.id,
                ClassMembership.is_active == True,
            )
        ).first()
        if active_member:
            raise HTTPException(status_code=409, detail="Вы уже состоите в этом классе")

        request = session.exec(
            select(ClassJoinRequest).where(
                ClassJoinRequest.class_id == class_id,
                ClassJoinRequest.student_id == actor.id,
                ClassJoinRequest.status == ClassJoinStatus.PENDING,
            )
        ).first()
        if request:
            return ClassJoinRequestView.model_validate(request)

        request = ClassJoinRequest(
            class_id=class_id,
            student_id=actor.id,
            student_email=actor.email.lower(),
            message=(payload.message or "").strip() or None,
            status=ClassJoinStatus.PENDING,
        )
        session.add(request)
        session.flush()

        if school_class.approval_mode == ClassApprovalMode.AUTO:
            self._approve_class_join_request(
                session=session,
                school_class=school_class,
                request=request,
                decided_by_user_id=school_class.teacher_id,
            )
        else:
            self._notify(
                session,
                user_id=school_class.teacher_id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message=f"Новая заявка в класс «{school_class.title}» от {actor.full_name}",
                email_subject="Новая заявка в класс",
            )

        session.commit()
        session.refresh(request)
        return ClassJoinRequestView.model_validate(request)

    def list_class_join_requests(
        self,
        session: Session,
        actor: User,
        class_id: str,
        status: ClassJoinStatus | None = None,
    ) -> list[ClassJoinRequestView]:
        self._ensure_teacher_class_access(session, actor, class_id)
        query = select(ClassJoinRequest).where(ClassJoinRequest.class_id == class_id)
        if status is not None:
            query = query.where(ClassJoinRequest.status == status)
        rows = session.exec(query.order_by(ClassJoinRequest.created_at.desc())).all()
        return [ClassJoinRequestView.model_validate(item) for item in rows]

    def decide_class_join_request(
        self,
        session: Session,
        actor: User,
        class_id: str,
        request_id: str,
        payload: ClassJoinRequestDecision,
    ) -> ClassJoinRequestView:
        school_class = self._ensure_teacher_class_access(session, actor, class_id)
        request = session.get(ClassJoinRequest, request_id)
        if not request or request.class_id != class_id:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if request.status != ClassJoinStatus.PENDING:
            raise HTTPException(status_code=400, detail="Эта заявка уже обработана")
        if payload.status == ClassJoinStatus.PENDING:
            raise HTTPException(status_code=400, detail="Нужно выбрать решение: approved или rejected")

        if payload.status == ClassJoinStatus.APPROVED:
            self._approve_class_join_request(
                session=session,
                school_class=school_class,
                request=request,
                decided_by_user_id=actor.id,
            )
        else:
            request.status = ClassJoinStatus.REJECTED
            request.decided_by_user_id = actor.id
            request.decided_at = moscow_now()
            session.add(request)
            self._notify(
                session,
                user_id=request.student_id,
                task_id=None,
                type_=NotificationType.CLASS_JOIN,
                message=f"Заявка в класс «{school_class.title}» отклонена учителем",
                email_subject="Решение по заявке в класс",
            )

        session.commit()
        session.refresh(request)
        return ClassJoinRequestView.model_validate(request)

    def create_assignment(
        self,
        session: Session,
        actor: User,
        payload: AssignmentCreateRequest,
    ) -> AssignmentView:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Выдавать задания может только учитель")
        if bool(payload.target_class_id) == bool(payload.target_student_id):
            raise HTTPException(
                status_code=400,
                detail="Укажите либо target_class_id, либо target_student_id",
            )

        school_class: SchoolClass | None = None
        student_ids: list[str] = []
        if payload.target_class_id:
            school_class = self._ensure_teacher_class_access(session, actor, payload.target_class_id)
            student_ids = list(
                session.exec(
                    select(ClassMembership.student_id).where(
                        ClassMembership.class_id == school_class.id,
                        ClassMembership.is_active == True,
                    )
                ).all()
            )
            if not student_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "В выбранном классе пока нет подтверждённых учеников. "
                        "Добавьте учеников по email и одобрите их заявки."
                    ),
                )
        else:
            if not payload.target_student_id:
                raise HTTPException(status_code=400, detail="Выберите ученика для точечной выдачи задания")
            target_student = session.get(User, payload.target_student_id or "")
            if not target_student or target_student.role != Role.STUDENT:
                raise HTTPException(status_code=404, detail="Ученик не найден")
            self._ensure_student_access(session, actor, target_student.id)
            student_ids = [target_student.id]

        assignment = Assignment(
            teacher_id=actor.id,
            class_id=school_class.id if school_class else None,
            target_student_id=payload.target_student_id,
            title=payload.title.strip(),
            description=(payload.description or "").strip() or None,
            subject=(payload.subject or "").strip() or None,
            priority=payload.priority,
            due_at=normalize_to_tz(payload.due_at),
        )
        session.add(assignment)
        session.flush()

        created_tasks = 0
        for student_id in student_ids:
            task = Task(
                student_id=student_id,
                created_by_id=actor.id,
                title=assignment.title,
                description=assignment.description,
                subject=assignment.subject,
                due_at=assignment.due_at,
                priority=assignment.priority,
                source=TaskSource.MANUAL,
                assigned_by_role=Role.TEACHER,
                assigned_by_user_id=actor.id,
                assignment_id=assignment.id,
                origin=TaskOrigin.TEACHER,
                educational_validated=True,
                educational_reason=None,
            )
            session.add(task)
            session.flush()
            session.add(
                ReminderRule(
                    task_id=task.id,
                    interval_hours=3 if assignment.priority == TaskPriority.HIGH else 6,
                    escalate_after_misses=2,
                    is_adaptive=True,
                    active=True,
                )
            )
            self._notify(
                session=session,
                user_id=student_id,
                task_id=task.id,
                type_=NotificationType.TASK_CREATED,
                message=f"Учитель выдал задание: {task.title}",
                email_subject="Новое домашнее задание",
            )
            created_tasks += 1

        session.commit()
        session.refresh(assignment)
        return AssignmentView(
            id=assignment.id,
            teacher_id=assignment.teacher_id,
            class_id=assignment.class_id,
            target_student_id=assignment.target_student_id,
            title=assignment.title,
            description=assignment.description,
            subject=assignment.subject,
            due_at=assignment.due_at,
            priority=assignment.priority,
            created_at=assignment.created_at,
            created_tasks=created_tasks,
        )

    def add_assignment_attachments(
        self,
        session: Session,
        actor: User,
        assignment_id: str,
        files: list[Any] | None,
    ) -> AssignmentAttachmentsUploadResponse:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Добавлять файлы к ДЗ может только учитель")
        assignment = session.get(Assignment, assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Выдача ДЗ не найдена")
        if assignment.teacher_id != actor.id:
            raise HTTPException(status_code=403, detail="Нет доступа к этой выдаче ДЗ")

        files = files or []
        uploads = [upload for upload in files if upload and getattr(upload, "filename", None)]
        if not uploads:
            raise HTTPException(status_code=400, detail="Добавьте хотя бы один файл")

        tasks = session.exec(select(Task).where(Task.assignment_id == assignment.id)).all()
        if not tasks:
            raise HTTPException(status_code=404, detail="Для этой выдачи пока нет созданных задач")

        attached_files = 0
        for upload in uploads:
            stored = save_upload(upload, subdir=f"assignments/{assignment.id}")
            for task in tasks:
                session.add(
                    TaskAttachment(
                        task_id=task.id,
                        file_name=stored.file_name,
                        file_path=stored.file_path,
                        mime_type=stored.mime_type,
                        size_bytes=stored.size_bytes,
                    )
                )
            attached_files += 1

        session.commit()
        return AssignmentAttachmentsUploadResponse(
            status="ok",
            assignment_id=assignment.id,
            attached_files=attached_files,
        )

    def list_task_attachments(self, session: Session, actor: User, task_id: str) -> list[TaskAttachmentView]:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)
        attachments = session.exec(
            select(TaskAttachment).where(TaskAttachment.task_id == task.id).order_by(TaskAttachment.created_at.desc())
        ).all()
        return [TaskAttachmentView.model_validate(item) for item in attachments]

    def resolve_task_attachment(
        self,
        session: Session,
        actor: User,
        attachment_id: str,
    ) -> tuple[str, str]:
        attachment = session.get(TaskAttachment, attachment_id)
        if not attachment:
            raise HTTPException(status_code=404, detail="Файл задания не найден")
        task = session.get(Task, attachment.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)
        file_path = Path(attachment.file_path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Файл задания отсутствует")
        return str(file_path), attachment.file_name

    def extract_task_from_photo(
        self,
        session: Session,
        actor: User,
        student_id: str,
        upload_file,
    ) -> TaskView:
        if actor.role == Role.STUDENT and actor.id != student_id:
            raise HTTPException(status_code=403, detail="Ученик может добавлять AI-задачи только себе")
        if actor.role == Role.TEACHER:
            self._ensure_student_access(session, actor, student_id)

        stored = save_upload(upload_file, subdir=f"ocr/{student_id}")
        try:
            ocr = extract_text_from_image(stored.file_path)
        except OCRExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = ExtractTaskRequest(student_id=student_id, text=ocr.text, source=TaskSource.AI_EXTRACTED)
        return self.extract_task(session, payload, actor)

    def create_task_submission(
        self,
        session: Session,
        actor: User,
        task_id: str,
        text_answer: str | None,
        voice_transcript: str | None,
        files: list[Any] | None,
    ) -> TaskSubmissionView:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        if actor.role != Role.STUDENT or actor.id != task.student_id:
            raise HTTPException(status_code=403, detail="Сдавать работу может только ученик-владелец задачи")

        text_answer = (text_answer or "").strip() or None
        voice_transcript = (voice_transcript or "").strip() or None
        files = files or []
        if not text_answer and not voice_transcript and not files:
            raise HTTPException(status_code=400, detail="Добавьте текст, голосовой текст или файл решения")

        submission = TaskSubmission(
            task_id=task.id,
            student_id=actor.id,
            text_answer=text_answer,
            voice_transcript=voice_transcript,
        )
        session.add(submission)
        session.flush()

        for upload in files:
            if not upload or not getattr(upload, "filename", None):
                continue
            stored = save_upload(upload, subdir=f"submissions/{task.id}")
            session.add(
                SubmissionAttachment(
                    submission_id=submission.id,
                    file_name=stored.file_name,
                    file_path=stored.file_path,
                    mime_type=stored.mime_type,
                    size_bytes=stored.size_bytes,
                )
            )

        if self._is_shared_homework(task):
            teacher_ids, parent_ids = self._student_related_contacts(session, task.student_id)
            for user_id in teacher_ids + parent_ids:
                self._notify(
                    session=session,
                    user_id=user_id,
                    task_id=task.id,
                    type_=NotificationType.TASK_COMPLETED,
                    message=f"Ученик отправил решение по задаче «{task.title}»",
                    email_subject="Поступило решение задачи",
                )

        session.commit()
        session.refresh(submission)
        return self._submission_view(session, submission)

    def list_task_submissions(self, session: Session, actor: User, task_id: str) -> list[TaskSubmissionView]:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)
        rows = session.exec(
            select(TaskSubmission).where(TaskSubmission.task_id == task_id).order_by(TaskSubmission.created_at.desc())
        ).all()
        return [self._submission_view(session, item) for item in rows]

    def resolve_submission_attachment(
        self,
        session: Session,
        actor: User,
        attachment_id: str,
    ) -> tuple[str, str]:
        attachment = session.get(SubmissionAttachment, attachment_id)
        if not attachment:
            raise HTTPException(status_code=404, detail="Файл не найден")
        submission = session.get(TaskSubmission, attachment.submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Сдача не найдена")
        task = session.get(Task, submission.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)
        file_path = Path(attachment.file_path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Файл вложения отсутствует")
        return str(file_path), attachment.file_name

    def suggest_teacher_review(
        self,
        session: Session,
        actor: User,
        task_id: str,
        submission_id: str | None,
    ) -> TeacherReviewSuggestView:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="ИИ-проверка доступна только учителю")
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        self._ensure_task_visibility(session, actor, task)

        submission: TaskSubmission | None = None
        if submission_id:
            submission = session.get(TaskSubmission, submission_id)
            if not submission or submission.task_id != task_id:
                raise HTTPException(status_code=404, detail="Сдача не найдена")
        else:
            submission = session.exec(
                select(TaskSubmission)
                .where(TaskSubmission.task_id == task_id)
                .order_by(TaskSubmission.created_at.desc())
            ).first()
        if not submission:
            raise HTTPException(status_code=404, detail="Для задачи пока нет сданного решения")

        raw_text_parts = [submission.text_answer or "", submission.voice_transcript or ""]
        attachments = session.exec(
            select(SubmissionAttachment).where(SubmissionAttachment.submission_id == submission.id)
        ).all()
        for attachment in attachments:
            mime = (attachment.mime_type or "").lower()
            if mime.startswith("image/"):
                try:
                    ocr_result = extract_text_from_image(attachment.file_path)
                    if ocr_result.text:
                        raw_text_parts.append(ocr_result.text)
                except Exception:
                    continue
        submission_text = "\\n".join([part.strip() for part in raw_text_parts if part.strip()])[:4000]

        ai_result = self._ai.suggest_review(
            task_title=task.title,
            task_description=task.description,
            submission_text=submission_text,
        )
        suggestion = AiReviewSuggestion(
            task_id=task.id,
            teacher_id=actor.id,
            submission_id=submission.id,
            suggested_score=ai_result.suggested_score,
            summary=ai_result.summary,
            issues=json.dumps(ai_result.issues, ensure_ascii=False),
            recommendation=ai_result.recommendation,
            provider=ai_result.provider,
        )
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
        return TeacherReviewSuggestView(
            id=suggestion.id,
            task_id=suggestion.task_id,
            teacher_id=suggestion.teacher_id,
            submission_id=suggestion.submission_id,
            suggested_score=suggestion.suggested_score,
            summary=suggestion.summary,
            issues=ai_result.issues,
            recommendation=suggestion.recommendation,
            provider=suggestion.provider,
            created_at=suggestion.created_at,
        )

    def create_parent_goal(self, session: Session, actor: User, payload: ParentGoalCreateRequest) -> ParentGoalView:
        if actor.role != Role.PARENT:
            raise HTTPException(status_code=403, detail="Создавать цели может только родитель")
        student = session.exec(
            select(User).where(User.email == payload.student_email.lower(), User.role == Role.STUDENT)
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail="Ученик с такой почтой не найден")

        link = session.exec(
            select(StudentParentLink).where(
                StudentParentLink.student_id == student.id,
                StudentParentLink.parent_id == actor.id,
            )
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Родитель не связан с этим учеником")

        goal = ParentGoal(
            parent_id=actor.id,
            student_id=student.id,
            title=payload.title.strip(),
            reward=payload.reward.strip(),
            status=ParentGoalStatus.ACTIVE,
        )
        session.add(goal)
        self._notify(
            session=session,
            user_id=student.id,
            task_id=None,
            type_=NotificationType.PARENT_GOAL,
            message=f"Родитель добавил цель: {goal.title}. Поощрение: {goal.reward}",
            email_subject="Новая цель от родителя",
        )
        session.commit()
        session.refresh(goal)
        return ParentGoalView.model_validate(goal)

    def list_parent_goals(
        self,
        session: Session,
        actor: User,
        parent_id: str | None = None,
        student_id: str | None = None,
    ) -> list[ParentGoalView]:
        if actor.role == Role.PARENT:
            query = select(ParentGoal).where(ParentGoal.parent_id == actor.id)
            if student_id:
                query = query.where(ParentGoal.student_id == student_id)
            rows = session.exec(query.order_by(ParentGoal.created_at.desc())).all()
            return [ParentGoalView.model_validate(item) for item in rows]
        if actor.role == Role.STUDENT:
            rows = session.exec(
                select(ParentGoal).where(ParentGoal.student_id == actor.id).order_by(ParentGoal.created_at.desc())
            ).all()
            return [ParentGoalView.model_validate(item) for item in rows]
        raise HTTPException(status_code=403, detail="Цели доступны ученику и родителю")

    def add_parent_goal_evidence(
        self,
        session: Session,
        actor: User,
        goal_id: str,
        task_submission_id: str | None,
        comment: str | None,
        files: list[Any] | None,
    ) -> ParentGoalEvidenceView:
        goal = session.get(ParentGoal, goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Цель не найдена")
        if actor.role != Role.STUDENT or actor.id != goal.student_id:
            raise HTTPException(status_code=403, detail="Добавлять доказательства по цели может только ученик")

        attachment_path: str | None = None
        for upload in files or []:
            if upload and getattr(upload, "filename", None):
                stored = save_upload(upload, subdir=f"parent_goals/{goal.id}")
                attachment_path = stored.file_path
                break

        evidence = ParentGoalEvidence(
            parent_goal_id=goal.id,
            student_id=actor.id,
            task_submission_id=task_submission_id,
            comment=(comment or "").strip() or None,
            attachment_path=attachment_path,
        )
        session.add(evidence)
        self._notify(
            session=session,
            user_id=goal.parent_id,
            task_id=None,
            type_=NotificationType.PARENT_GOAL,
            message=f"Ученик добавил подтверждение по цели «{goal.title}»",
            email_subject="Новое подтверждение по родительской цели",
        )
        session.commit()
        session.refresh(evidence)
        return ParentGoalEvidenceView.model_validate(evidence)

    def update_parent_goal_status(
        self,
        session: Session,
        actor: User,
        goal_id: str,
        payload: ParentGoalStatusUpdateRequest,
    ) -> ParentGoalView:
        goal = session.get(ParentGoal, goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Цель не найдена")
        if actor.role != Role.PARENT or actor.id != goal.parent_id:
            raise HTTPException(status_code=403, detail="Статус цели может менять только родитель-владелец")

        goal.status = payload.status
        goal.completed_at = moscow_now() if payload.status == ParentGoalStatus.COMPLETED else None
        session.add(goal)
        session.commit()
        session.refresh(goal)
        return ParentGoalView.model_validate(goal)

    def telegram_login(self, session: Session, payload: TelegramLoginRequest) -> TelegramLoginResponse:
        existing = session.exec(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == payload.chat_id)
        ).first()
        if existing and existing.failed_attempts >= settings.telegram_login_attempt_limit:
            raise HTTPException(status_code=429, detail="Слишком много неудачных попыток входа в Telegram")

        email = payload.email.strip().lower()
        user = session.exec(select(User).where(User.email == email, User.is_active == True)).first()
        if not user or not verify_password(payload.password, user.password_salt, user.password_hash):
            if existing:
                existing.failed_attempts += 1
                session.add(existing)
                session.commit()
            raise HTTPException(status_code=401, detail="Неверная почта или пароль")

        if not existing:
            existing = TelegramLink(
                user_id=user.id,
                telegram_chat_id=payload.chat_id,
                telegram_username=payload.username,
                failed_attempts=0,
                last_login_at=moscow_now(),
            )
        else:
            existing.user_id = user.id
            existing.telegram_username = payload.username
            existing.failed_attempts = 0
            existing.last_login_at = moscow_now()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return TelegramLoginResponse(status="ok", user=UserView.model_validate(user))

    def telegram_create_note(self, session: Session, payload: TelegramNoteRequest) -> TelegramNoteResponse:
        user = self._telegram_student_user(session, payload.chat_id)

        self._validate_student_educational_text(payload.text)

        title = payload.text.strip().split(".")[0][:140] or "Новая учебная заметка"
        task = self.create_task(
            session=session,
            payload=CreateTaskRequest(
                student_id=user.id,
                title=title,
                description=payload.text.strip(),
                due_at=payload.due_at,
                priority=TaskPriority.MEDIUM,
                source=TaskSource.TELEGRAM,
            ),
            actor=user,
        )
        return TelegramNoteResponse(status="ok", task=task)

    def telegram_list_tasks(self, session: Session, chat_id: str, urgent_only: bool = False) -> list[TaskView]:
        user = self._telegram_student_user(session, chat_id)
        tasks = self.list_student_tasks(
            session=session,
            student_id=user.id,
            actor=user,
            sort="due_asc",
            include_source=True,
        )
        if urgent_only:
            return [item for item in tasks if item.urgency_color in {"red", "orange"} and item.status != TaskStatus.DONE]
        return tasks

    def telegram_mark_done(self, session: Session, chat_id: str, task_id: str) -> TaskView:
        user = self._telegram_student_user(session, chat_id)
        task = session.get(Task, task_id)
        if not task or task.student_id != user.id:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        return self.update_task_status(session=session, task_id=task.id, status=TaskStatus.DONE, actor=user)

    def current_user(self, session: Session, token: str) -> User:
        auth = session.get(AuthToken, token)
        if not auth:
            raise HTTPException(status_code=401, detail="Недействительный токен")
        expires_at = normalize_to_tz(auth.expires_at)
        if expires_at is None or expires_at < moscow_now():
            session.delete(auth)
            session.commit()
            raise HTTPException(status_code=401, detail="Сессия истекла")

        user = session.get(User, auth.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Пользователь недоступен")
        return user

    def _issue_token(self, session: Session, user_id: str) -> str:
        token = issue_token()
        session.add(
            AuthToken(
                token=token,
                user_id=user_id,
                expires_at=moscow_now() + timedelta(hours=self._token_ttl_hours),
            )
        )
        return token

    def _login_response(self, session: Session, user: User, token: str) -> LoginResponse:
        context = self._build_context(session, user)
        return LoginResponse(
            access_token=token,
            user={"id": user.id, "role": user.role, "full_name": user.full_name, "email": user.email},
            context=context,
        )

    def _task_view(self, session: Session, task: Task) -> TaskView:
        steps = session.exec(select(TaskStep).where(TaskStep.task_id == task.id).order_by(TaskStep.order_index)).all()
        attachments = session.exec(
            select(TaskAttachment).where(TaskAttachment.task_id == task.id).order_by(TaskAttachment.created_at.desc())
        ).all()
        priority = task.priority or TaskPriority.MEDIUM
        source = task.source or TaskSource.MANUAL
        status = task.status or TaskStatus.TODO
        if task.origin:
            origin = task.origin
        elif task.assigned_by_role == Role.TEACHER:
            origin = TaskOrigin.TEACHER
        elif task.assigned_by_role == Role.PARENT:
            origin = TaskOrigin.PARENT
        else:
            origin = TaskOrigin.STUDENT
        return TaskView(
            id=task.id,
            student_id=task.student_id,
            created_by_id=task.created_by_id,
            title=task.title,
            description=task.description,
            subject=task.subject,
            priority=priority,
            source=source,
            status=status,
            due_at=task.due_at,
            planned_at=task.planned_at,
            recommended_interval_hours=int(task.recommended_interval_hours or 6),
            missed_reminders=int(task.missed_reminders or 0),
            assigned_by_role=task.assigned_by_role,
            assigned_by_user_id=task.assigned_by_user_id,
            assignment_id=task.assignment_id,
            origin=origin,
            educational_validated=bool(task.educational_validated if task.educational_validated is not None else True),
            educational_reason=task.educational_reason,
            urgency_color=task_urgency_color(task.due_at),
            created_at=task.created_at,
            completed_at=task.completed_at,
            attachments=[TaskAttachmentView.model_validate(item) for item in attachments],
            steps=[self._step_view(step) for step in steps],
        )

    @staticmethod
    def _step_view(step: TaskStep) -> TaskStepView:
        return TaskStepView.model_validate(step)

    def _submission_view(self, session: Session, submission: TaskSubmission) -> TaskSubmissionView:
        attachments = session.exec(
            select(SubmissionAttachment).where(SubmissionAttachment.submission_id == submission.id)
        ).all()
        return TaskSubmissionView(
            id=submission.id,
            task_id=submission.task_id,
            student_id=submission.student_id,
            text_answer=submission.text_answer,
            voice_transcript=submission.voice_transcript,
            created_at=submission.created_at,
            attachments=[
                {
                    "id": item.id,
                    "submission_id": item.submission_id,
                    "file_name": item.file_name,
                    "file_path": item.file_path,
                    "mime_type": item.mime_type,
                    "size_bytes": item.size_bytes,
                    "created_at": item.created_at,
                }
                for item in attachments
            ],
        )

    def _class_invite_status_row(
        self,
        session: Session,
        class_id: str,
        invite: ClassStudentInvite,
    ) -> ClassInviteStatusView:
        student = session.exec(
            select(User).where(
                User.email == invite.student_email.lower(),
                User.role == Role.STUDENT,
                User.is_active == True,
            )
        ).first()

        membership = None
        request = None
        status = "invited"
        is_member = False

        if student:
            membership = session.exec(
                select(ClassMembership).where(
                    ClassMembership.class_id == class_id,
                    ClassMembership.student_id == student.id,
                    ClassMembership.is_active == True,
                )
            ).first()
            if membership:
                status = "member"
                is_member = True
            else:
                request = session.exec(
                    select(ClassJoinRequest)
                    .where(
                        ClassJoinRequest.class_id == class_id,
                        ClassJoinRequest.student_id == student.id,
                    )
                    .order_by(ClassJoinRequest.created_at.desc())
                ).first()
                if request:
                    status = request.status.value

        return ClassInviteStatusView(
            id=invite.id,
            class_id=class_id,
            student_email=invite.student_email,
            student_id=student.id if student else None,
            student_full_name=student.full_name if student else None,
            status=status,  # type: ignore[arg-type]
            is_member=is_member,
            invite_created_at=invite.created_at,
            request_id=request.id if request else None,
            request_created_at=request.created_at if request else None,
            request_decided_at=request.decided_at if request else None,
        )

    def _ensure_teacher_class_access(self, session: Session, actor: User, class_id: str) -> SchoolClass:
        if actor.role != Role.TEACHER:
            raise HTTPException(status_code=403, detail="Только учитель имеет доступ к классам")
        school_class = session.get(SchoolClass, class_id)
        if not school_class or not school_class.is_active:
            raise HTTPException(status_code=404, detail="Класс не найден")
        if school_class.teacher_id != actor.id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому классу")
        return school_class

    def _approve_class_join_request(
        self,
        session: Session,
        school_class: SchoolClass,
        request: ClassJoinRequest,
        decided_by_user_id: str,
    ) -> None:
        request.status = ClassJoinStatus.APPROVED
        request.decided_by_user_id = decided_by_user_id
        request.decided_at = moscow_now()
        session.add(request)

        membership = session.exec(
            select(ClassMembership).where(
                ClassMembership.class_id == school_class.id,
                ClassMembership.student_id == request.student_id,
            )
        ).first()
        if membership:
            membership.is_active = True
            session.add(membership)
        else:
            session.add(ClassMembership(class_id=school_class.id, student_id=request.student_id, is_active=True))

        self._notify(
            session,
            user_id=request.student_id,
            task_id=None,
            type_=NotificationType.CLASS_JOIN,
            message=f"Вы вступили в класс «{school_class.title}»",
            email_subject="Заявка в класс одобрена",
        )

    def _telegram_student_user(self, session: Session, chat_id: str) -> User:
        link = session.exec(select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)).first()
        if not link:
            raise HTTPException(status_code=401, detail="Сначала выполните вход в Telegram-боте")
        user = session.get(User, link.user_id)
        if not user or user.role != Role.STUDENT:
            raise HTTPException(status_code=403, detail="Telegram-режим заметок доступен только ученику")
        return user

    def _validate_student_educational_text(self, text: str) -> None:
        rules = validate_educational_task_text(text)
        if not rules.is_valid:
            detail = rules.reason or "Можно добавлять только образовательные задания"
            if rules.suggestion:
                detail = f"{detail}. {rules.suggestion}"
            raise HTTPException(status_code=400, detail=detail)

        ai_check = self._ai.validate_educational_task_text(text)
        if not ai_check.is_educational:
            detail = ai_check.reason or "Текст не относится к учебному процессу"
            suggestion = ai_check.suggestion or "Опишите задание по предмету, что нужно сделать и дедлайн."
            raise HTTPException(status_code=400, detail=f"{detail}. {suggestion}")

    @staticmethod
    def _is_private_student_note(task: Task) -> bool:
        origin = task.origin or TaskOrigin.STUDENT
        if origin != TaskOrigin.STUDENT:
            return False
        if task.assignment_id:
            return False
        if task.assigned_by_role in {Role.TEACHER, Role.PARENT}:
            return False
        return task.created_by_id == task.student_id

    def _is_shared_homework(self, task: Task) -> bool:
        return not self._is_private_student_note(task)

    def _ensure_task_visibility(self, session: Session, actor: User, task: Task) -> None:
        self._ensure_student_access(session, actor, task.student_id)
        if self._is_private_student_note(task):
            if actor.role != Role.STUDENT or actor.id != task.student_id:
                raise HTTPException(status_code=403, detail="Личная заметка ученика недоступна для этой роли")

    @staticmethod
    def _task_has_submission_evidence(session: Session, task_id: str, student_id: str) -> bool:
        text_submission = session.exec(
            select(TaskSubmission.id).where(
                TaskSubmission.task_id == task_id,
                TaskSubmission.student_id == student_id,
                (
                    (TaskSubmission.text_answer != None)  # noqa: E711
                    | (TaskSubmission.voice_transcript != None)  # noqa: E711
                ),
            )
        ).first()
        if text_submission:
            return True

        attachment_submission = session.exec(
            select(SubmissionAttachment.id)
            .join(TaskSubmission, TaskSubmission.id == SubmissionAttachment.submission_id)
            .where(
                TaskSubmission.task_id == task_id,
                TaskSubmission.student_id == student_id,
            )
        ).first()
        return attachment_submission is not None

    def _student_related_contacts(self, session: Session, student_id: str) -> tuple[list[str], list[str]]:
        teachers = set(
            session.exec(
            select(StudentTeacherLink.teacher_id).where(StudentTeacherLink.student_id == student_id)
            ).all()
        )
        class_teacher_ids = session.exec(
            select(SchoolClass.teacher_id)
            .join(ClassMembership, ClassMembership.class_id == SchoolClass.id)
            .where(
                ClassMembership.student_id == student_id,
                ClassMembership.is_active == True,
                SchoolClass.is_active == True,
            )
        ).all()
        teachers.update(class_teacher_ids)

        parents = session.exec(
            select(StudentParentLink.parent_id).where(StudentParentLink.student_id == student_id)
        ).all()
        return list(teachers), list(parents)

    def _ensure_student_access(self, session: Session, actor: User, student_id: str) -> None:
        if actor.role == Role.STUDENT:
            if actor.id != student_id:
                raise HTTPException(status_code=403, detail="Ученик может смотреть только свои данные")
            return
        if actor.role == Role.TEACHER:
            linked = session.exec(
                select(StudentTeacherLink).where(
                    StudentTeacherLink.student_id == student_id,
                    StudentTeacherLink.teacher_id == actor.id,
                )
            ).first()
            if not linked:
                class_link = session.exec(
                    select(ClassMembership)
                    .join(SchoolClass, SchoolClass.id == ClassMembership.class_id)
                    .where(
                        ClassMembership.student_id == student_id,
                        ClassMembership.is_active == True,
                        SchoolClass.teacher_id == actor.id,
                        SchoolClass.is_active == True,
                    )
                ).first()
                if not class_link:
                    raise HTTPException(status_code=403, detail="Учитель не связан с этим учеником")
            return
        if actor.role == Role.PARENT:
            linked = session.exec(
                select(StudentParentLink).where(
                    StudentParentLink.student_id == student_id,
                    StudentParentLink.parent_id == actor.id,
                )
            ).first()
            if not linked:
                raise HTTPException(status_code=403, detail="Родитель не связан с этим учеником")
            return

    def _build_context(self, session: Session, user: User) -> LoginContext:
        if user.role == Role.STUDENT:
            teacher_ids, parent_ids = self._student_related_contacts(session, user.id)
            class_ids = session.exec(
                select(ClassMembership.class_id).where(
                    ClassMembership.student_id == user.id,
                    ClassMembership.is_active == True,
                )
            ).all()
            return LoginContext(
                student_ids=[user.id],
                teacher_ids=teacher_ids,
                parent_ids=parent_ids,
                class_ids=list(class_ids),
            )

        if user.role == Role.TEACHER:
            direct_student_ids = set(
                session.exec(select(StudentTeacherLink.student_id).where(StudentTeacherLink.teacher_id == user.id)).all()
            )
            teacher_class_ids = session.exec(
                select(SchoolClass.id).where(SchoolClass.teacher_id == user.id, SchoolClass.is_active == True)
            ).all()
            if teacher_class_ids:
                class_student_ids = session.exec(
                    select(ClassMembership.student_id).where(
                        ClassMembership.class_id.in_(teacher_class_ids),
                        ClassMembership.is_active == True,
                    )
                ).all()
                direct_student_ids.update(class_student_ids)
            return LoginContext(
                student_ids=list(direct_student_ids),
                teacher_ids=[user.id],
                parent_ids=[],
                class_ids=list(teacher_class_ids),
            )

        student_ids = session.exec(select(StudentParentLink.student_id).where(StudentParentLink.parent_id == user.id)).all()
        return LoginContext(student_ids=list(student_ids), teacher_ids=[], parent_ids=[user.id], class_ids=[])

    def _notify(
        self,
        session: Session,
        user_id: str,
        task_id: str | None,
        type_: NotificationType,
        message: str,
        email_subject: str | None = None,
    ) -> None:
        session.add(Notification(user_id=user_id, task_id=task_id, type=type_, message=message))

        user = session.get(User, user_id)
        if not user or not user.email:
            return

        subject = email_subject or "Уведомление WATA Smart Tracker"
        self._email.send(
            to_email=user.email,
            subject=subject,
            body=f"{message}\n\nВремя: {moscow_now().isoformat()}",
        )
        self._notify_telegram(session=session, user_id=user_id, message=message)

    def _notify_telegram(self, session: Session, user_id: str, message: str) -> None:
        token = settings.telegram_bot_token
        if not token:
            return
        links = session.exec(select(TelegramLink).where(TelegramLink.user_id == user_id)).all()
        if not links:
            return
        for link in links:
            try:
                import httpx

                httpx.post(
                    f"{settings.telegram_api_base.rstrip('/')}/bot{token}/sendMessage",
                    json={"chat_id": link.telegram_chat_id, "text": message[:3800]},
                    timeout=8.0,
                )
            except Exception:
                continue
