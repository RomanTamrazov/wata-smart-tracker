from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.models import TaskPriority
from app.services.ai_fallback import build_analytics, build_plan, extract_from_text
from app.utils import moscow_now


class ModelNotReadyError(RuntimeError):
    pass


@dataclass(slots=True)
class AIExtractionResult:
    title: str
    description: str
    subject: str | None
    due_at: datetime | None
    priority: TaskPriority
    provider: str


@dataclass(slots=True)
class AIPlanResult:
    planned_at: datetime | None
    interval_hours: int
    steps: list[str]
    provider: str


@dataclass(slots=True)
class AIAnalyticsResult:
    recommendations: list[str]
    provider: str


@dataclass(slots=True)
class AIEducationalCheckResult:
    is_educational: bool
    reason: str | None
    suggestion: str | None
    provider: str


@dataclass(slots=True)
class AssistantReplyResult:
    reply: str
    suggested_actions: list[str]
    provider: str


@dataclass(slots=True)
class ReviewSuggestionResult:
    suggested_score: int
    summary: str
    issues: list[str]
    recommendation: str
    provider: str


_OLLAMA_BASE_OPTIONS: dict[str, Any] = {
    "temperature": 0.1,
    "num_predict": 300,
    "num_ctx": 2048,
    "repeat_penalty": 1.1,
}

_OLLAMA_ASSISTANT_OPTIONS: dict[str, Any] = {
    "temperature": 0.1,
    "num_predict": 220,
    "num_ctx": 1536,
    "repeat_penalty": 1.1,
}

_OLLAMA_CLASSIFIER_OPTIONS: dict[str, Any] = {
    "temperature": 0.0,
    "num_predict": 120,
    "num_ctx": 1024,
}

_OLLAMA_KEEP_ALIVE = "30m"


class HybridAIService:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._request_timeout = max(10, int(settings.ollama_request_timeout_seconds))

    def extract_task(self, text: str) -> AIExtractionResult:
        fallback = extract_from_text(text)
        try:
            payload = self._ask_ollama(
                prompt=(
                    "Верни JSON: title, description, subject, due_at_iso8601_or_null, priority.\n"
                    "priority: low|medium|high.\n"
                    f"Текст: {text}"
                ),
                options=_OLLAMA_BASE_OPTIONS,
            )
            raw_due = payload.get("due_at_iso8601_or_null")
            due_at = datetime.fromisoformat(raw_due) if raw_due else fallback.due_at
            pr = str(payload.get("priority", fallback.priority.value)).lower()
            priority = TaskPriority(pr) if pr in {"low", "medium", "high"} else fallback.priority
            return AIExtractionResult(
                title=str(payload.get("title") or fallback.title)[:140],
                description=str(payload.get("description") or fallback.description),
                subject=(str(payload.get("subject")) if payload.get("subject") else fallback.subject),
                due_at=due_at,
                priority=priority,
                provider=f"ollama:{self._model}",
            )
        except ModelNotReadyError:
            return AIExtractionResult(
                title=fallback.title,
                description=fallback.description,
                subject=fallback.subject,
                due_at=fallback.due_at,
                priority=fallback.priority,
                provider="fallback:model_not_ready",
            )
        except Exception:
            return AIExtractionResult(
                title=fallback.title,
                description=fallback.description,
                subject=fallback.subject,
                due_at=fallback.due_at,
                priority=fallback.priority,
                provider="fallback",
            )

    def plan_task(
        self,
        title: str,
        description: str | None,
        priority: TaskPriority,
        due_at: datetime | None,
    ) -> AIPlanResult:
        fallback = build_plan(title=title, description=description, priority=priority, due_at=due_at)
        try:
            payload = self._ask_ollama(
                prompt=(
                    "Верни JSON: planned_at_iso8601_or_null, interval_hours, steps (массив строк).\n"
                    f"title={title}\ndescription={description}\n"
                    f"priority={priority.value}\ndue_at={due_at.isoformat() if due_at else None}"
                ),
                options=_OLLAMA_BASE_OPTIONS,
            )
            raw_planned = payload.get("planned_at_iso8601_or_null")
            planned_at = datetime.fromisoformat(raw_planned) if raw_planned else fallback.planned_at
            now = moscow_now()
            if planned_at is not None:
                if planned_at.tzinfo is None:
                    planned_at = planned_at.replace(tzinfo=now.tzinfo)
                if planned_at < now - timedelta(minutes=5):
                    planned_at = fallback.planned_at
            interval = int(payload.get("interval_hours") or fallback.interval_hours)
            steps = [str(item).strip() for item in payload.get("steps", []) if str(item).strip()]
            if not steps:
                steps = fallback.steps
            return AIPlanResult(
                planned_at=planned_at,
                interval_hours=max(1, min(interval, 24)),
                steps=steps[:8],
                provider=f"ollama:{self._model}",
            )
        except ModelNotReadyError:
            return AIPlanResult(
                planned_at=fallback.planned_at,
                interval_hours=fallback.interval_hours,
                steps=fallback.steps,
                provider="fallback:model_not_ready",
            )
        except Exception:
            return AIPlanResult(
                planned_at=fallback.planned_at,
                interval_hours=fallback.interval_hours,
                steps=fallback.steps,
                provider="fallback",
            )

    def analytics(self, task_summaries: list[dict[str, Any]]) -> AIAnalyticsResult:
        fallback_recs = build_analytics(task_summaries)
        try:
            payload = self._ask_ollama(
                prompt=(
                    "Верни JSON: recommendations (массив из 3 коротких советов).\n"
                    f"Данные: {json.dumps(task_summaries, ensure_ascii=False)}"
                ),
                options=_OLLAMA_BASE_OPTIONS,
            )
            recs = self._normalize_recommendations(payload.get("recommendations"), fallback_recs)
            return AIAnalyticsResult(recommendations=recs[:4], provider=f"ollama:{self._model}")
        except ModelNotReadyError:
            return AIAnalyticsResult(recommendations=fallback_recs, provider="fallback:model_not_ready")
        except Exception:
            return AIAnalyticsResult(recommendations=fallback_recs, provider="fallback")

    def validate_educational_task_text(self, text: str) -> AIEducationalCheckResult:
        stripped = (text or "").strip()
        if not stripped:
            return AIEducationalCheckResult(
                is_educational=False,
                reason="Пустой текст задачи",
                suggestion="Опишите конкретное школьное задание по предмету и дедлайн.",
                provider="fallback",
            )
        try:
            payload = self._ask_ollama(
                prompt=(
                    "Ты классификатор школьных задач.\n"
                    "Определи, относится ли текст к учебному процессу (уроки, домашнее задание, контрольная, проект).\n"
                    "Неучебные примеры: игры, дота, cs, прогулка, сериал, покупки, развлечения, бытовые дела.\n"
                    "Верни строго JSON:\n"
                    "{\"is_educational\":true|false,\"reason\":\"...\",\"suggested_rewrite\":\"...\"}\n"
                    "reason: коротко (до 160 символов), почему так.\n"
                    "suggested_rewrite: корректная учебная формулировка, если исходник неучебный.\n"
                    f"Текст: {stripped}"
                ),
                options=_OLLAMA_CLASSIFIER_OPTIONS,
                timeout_seconds=min(10.0, float(self._request_timeout)),
            )
            raw_educational = (
                payload.get("is_educational")
                if "is_educational" in payload
                else payload.get("isEducational", payload.get("educational", payload.get("label")))
            )
            is_educational = self._coerce_bool(raw_educational, default=True)
            reason = self._sanitize_sentence(str(payload.get("reason") or "")) or None
            suggestion = self._sanitize_sentence(str(payload.get("suggested_rewrite") or "")) or None
            return AIEducationalCheckResult(
                is_educational=is_educational,
                reason=reason,
                suggestion=suggestion,
                provider=f"ollama:{self._model}",
            )
        except ModelNotReadyError:
            return AIEducationalCheckResult(
                is_educational=True,
                reason=None,
                suggestion=None,
                provider="fallback:model_not_ready",
            )
        except Exception:
            return AIEducationalCheckResult(
                is_educational=True,
                reason=None,
                suggestion=None,
                provider="fallback",
            )

    def assistant_reply(
        self,
        message: str,
        role: str,
        screen: str | None = None,
    ) -> AssistantReplyResult:
        role_context = self._assistant_role_context(role=role)
        screen_name = screen or "не указан"
        screen_context = self._assistant_screen_context(screen_name)
        intent_focus = self._assistant_intent_focus(message=message, role=role)
        prompt = self._assistant_build_prompt(
            role=role,
            screen_name=screen_name,
            screen_context=screen_context,
            role_context=role_context,
            intent_focus=intent_focus,
            message=message,
        )
        started_at = time.monotonic()

        try:
            payload = self._ask_ollama(
                prompt=prompt,
                options=_OLLAMA_ASSISTANT_OPTIONS,
                timeout_seconds=15.0,
                allow_raw_text=True,
            )
            reply_text = self._assistant_polish_text(self._assistant_extract_reply(payload))
            actions = [self._assistant_polish_text(item) for item in self._assistant_extract_actions(payload)]
            actions = self._assistant_normalize_actions(actions)

            issues = self._assistant_quality_issues(
                reply_text=reply_text,
                actions=actions,
                message=message,
                role=role,
            )
            repair_attempt = 0

            while issues and repair_attempt < 2:
                elapsed = time.monotonic() - started_at
                remaining = max(3.0, 15.0 - elapsed)
                if remaining <= 1.5:
                    break

                repair_payload = self._ask_ollama(
                    prompt=self._assistant_build_repair_prompt(
                        role=role,
                        screen_name=screen_name,
                        screen_context=screen_context,
                        role_context=role_context,
                        intent_focus=intent_focus,
                        message=message,
                        bad_reply=reply_text,
                        bad_actions=actions,
                        issues=issues,
                    ),
                    options=_OLLAMA_ASSISTANT_OPTIONS,
                    timeout_seconds=remaining,
                    allow_raw_text=True,
                )

                candidate_reply = self._assistant_polish_text(self._assistant_extract_reply(repair_payload))
                candidate_actions = [
                    self._assistant_polish_text(item) for item in self._assistant_extract_actions(repair_payload)
                ]
                candidate_actions = self._assistant_normalize_actions(candidate_actions)

                if candidate_reply:
                    reply_text = candidate_reply
                if candidate_actions:
                    actions = candidate_actions

                issues = self._assistant_quality_issues(
                    reply_text=reply_text,
                    actions=actions,
                    message=message,
                    role=role,
                )
                repair_attempt += 1

            if not reply_text:
                reply_text = "Не удалось получить содержательный ответ от модели. Повторите запрос чуть конкретнее."

            if len(actions) < 3:
                elapsed = time.monotonic() - started_at
                remaining = max(2.0, 15.0 - elapsed)
                if remaining > 1.0:
                    generated_actions = self._assistant_generate_actions(
                        role=role,
                        screen_name=screen_name,
                        message=message,
                        reply_text=reply_text,
                        timeout_seconds=remaining,
                    )
                    if generated_actions:
                        actions = self._assistant_normalize_actions(actions + generated_actions)

            if len(reply_text) > 700:
                reply_text = reply_text[:700].rstrip() + "…"

            if len(actions) < 3:
                actions = self._assistant_normalize_actions(actions + self._assistant_default_actions(role, message))
            reply_text, actions = self._assistant_enforce_intent_output(
                reply_text=reply_text,
                actions=actions,
                role=role,
                message=message,
            )
            actions = actions[:3]

            return AssistantReplyResult(reply=reply_text, suggested_actions=actions, provider=f"ollama:{self._model}")

        except ModelNotReadyError as exc:
            return AssistantReplyResult(
                reply="Модель Ollama недоступна или ещё загружается.",
                suggested_actions=[
                    "Проверить запуск `ollama serve`",
                    f"Проверить наличие модели `{self._model}`",
                    "Повторить запрос через 10 секунд",
                ],
                provider=f"ollama:unavailable:{self._model}:{exc}",
            )
        except Exception as exc:
            return AssistantReplyResult(
                reply="Не удалось получить корректный ответ от Ollama. Проверьте сервер модели и повторите запрос.",
                suggested_actions=[
                    "Проверить `ollama serve`",
                    "Проверить `ollama list`",
                    "Повторить запрос",
                ],
                provider=f"ollama:error:{self._model}:{exc.__class__.__name__}",
            )

    @staticmethod
    def _assistant_role_context(role: str) -> str:
        if role == "teacher":
            return (
                "- Режим «Классы»: создание класса, выбор активного класса, добавление email ученика.\n"
                "- Режим «Выдача ДЗ»: выбор «Весь класс» или «Отдельный ученик», тема, предмет, описание, дедлайн, кнопка «Выдать домашнее задание».\n"
                "- Режим «Проверка»: выбор задачи, ИИ-подсказка оценки, поле комментария, кнопка «Отправить комментарий»."
            )
        if role == "student":
            return (
                "- Режим «Обзор»: карточки задач, кнопки «Построить план», «Отметить готовность», «Сдать решение».\n"
                "- Режим «Добавить задание»: ручное создание, ИИ-извлечение текста/фото.\n"
                "- Режим «Связи и классы»: запрос помощи, привязка родителя, заявки в классы."
            )
        return (
            "- Подключить ученика по email.\n"
            "- Создать цель и поощрение.\n"
            "- Отметить цель выполненной и просматривать ленту прогресса."
        )

    @staticmethod
    def _assistant_build_prompt(
        role: str,
        screen_name: str,
        screen_context: str,
        role_context: str,
        intent_focus: str,
        message: str,
    ) -> str:
        return (
            "Ты ИИ-навигатор платформы WATA Smart Tracker.\n"
            "Отвечай только на русском, без англицизмов и без общих отговорок.\n"
            "Задача: дать конкретный маршрут в интерфейсе для текущего вопроса.\n"
            "Верни строго JSON формата:\n"
            "{\"reply\":\"...\",\"suggested_actions\":[\"...\",\"...\",\"...\"]}\n"
            "Правила:\n"
            "1) reply: 1-2 коротких предложения, только по делу.\n"
            "2) suggested_actions: ровно 3 коротких шага, каждый начинается с глагола.\n"
            "3) Не выдумывай элементы интерфейса, используй только доступные режимы.\n"
            "4) Не пиши дисклеймеры вида «я не могу» или «обратитесь к специалисту».\n"
            "5) Не добавляй текст вне JSON.\n"
            f"Роль пользователя: {role}.\n"
            f"Текущий экран: {screen_name}.\n"
            f"Контекст экрана: {screen_context}\n"
            f"Доступные режимы и действия:\n{role_context}\n"
            f"Фокус запроса: {intent_focus}\n"
            f"Вопрос пользователя: {message}"
        )

    @staticmethod
    def _assistant_build_repair_prompt(
        role: str,
        screen_name: str,
        screen_context: str,
        role_context: str,
        intent_focus: str,
        message: str,
        bad_reply: str,
        bad_actions: list[str],
        issues: list[str],
    ) -> str:
        issue_line = "; ".join(issues[:6]) if issues else "ответ слишком общий"
        return (
            "Исправь некачественный ответ ассистента.\n"
            "Верни только JSON:\n"
            "{\"reply\":\"...\",\"suggested_actions\":[\"...\",\"...\",\"...\"]}\n"
            "Требования:\n"
            "- чистый русский язык;\n"
            "- конкретные шаги по интерфейсу;\n"
            "- без дисклеймеров и лишнего текста.\n"
            f"Роль: {role}. Экран: {screen_name}. Контекст экрана: {screen_context}\n"
            f"Доступные режимы:\n{role_context}\n"
            f"Фокус запроса: {intent_focus}\n"
            f"Вопрос: {message}\n"
            f"Проблемы черновика: {issue_line}\n"
            f"Черновой reply: {bad_reply}\n"
            f"Черновые шаги: {bad_actions}"
        )

    @staticmethod
    def _assistant_screen_context(screen_name: str) -> str:
        screen = (screen_name or "").lower().strip()
        if "teacher" in screen:
            return "Панель учителя: классы, выдача домашнего задания, проверка и комментарии."
        if "student" in screen:
            return "Панель ученика: список задач, AI-план, сдача решения, запрос помощи."
        if "parent" in screen:
            return "Панель родителя: цели с поощрениями, подтверждение выполнения, лента прогресса."
        return "Главная панель проекта с ролевыми разделами."

    @staticmethod
    def _assistant_intent_focus(message: str, role: str) -> str:
        text = (message or "").lower()
        if role == "teacher":
            if any(token in text for token in ("провер", "оцен", "коммент", "отзыв")):
                return (
                    "Проверка ДЗ: обязательно упомяни режим «Проверка», выбор задачи, "
                    "комментарий и отправку оценки."
                )
            if any(token in text for token in ("выдать", "дз", "домаш", "задани")):
                return (
                    "Выдача ДЗ: обязательно упомяни режим «Выдача ДЗ», выбор получателя "
                    "(класс или ученик), заполнение дедлайна и кнопку «Выдать домашнее задание»."
                )
            if any(token in text for token in ("класс", "ученик", "добав", "удал")):
                return "Управление классом и составом учеников."
        if role == "student":
            if any(token in text for token in ("план", "постро", "шаг")):
                return "Построить пошаговый план выполнения задачи."
            if any(token in text for token in ("сдать", "решени", "файл", "фото", "голос")):
                return "Сдать решение по задаче с материалами."
            if any(token in text for token in ("добав", "задач", "извлеч", "ocr")):
                return "Добавить учебную задачу вручную или через AI/OCR."
        if role == "parent":
            if any(token in text for token in ("цель", "поощр", "награда")):
                return "Создать цель с поощрением и подтвердить выполнение."
        return "Пошаговая навигация по текущему запросу пользователя."

    def _assistant_quality_issues(
        self,
        reply_text: str,
        actions: list[str],
        message: str,
        role: str,
    ) -> list[str]:
        issues: list[str] = []
        lowered_message = (message or "").lower()
        is_teacher_review_intent = role == "teacher" and any(
            token in lowered_message for token in ("провер", "оцен", "коммент")
        )
        is_teacher_assignment_intent = role == "teacher" and any(
            token in lowered_message for token in ("выдать", "дз", "домаш")
        ) and not is_teacher_review_intent
        lowered_reply = (reply_text or "").lower()

        if not reply_text.strip():
            issues.append("пустой ответ")
        if self._looks_garbled(reply_text):
            issues.append("поврежденный текст")
        if self._assistant_contains_refusal_or_disclaimer(lowered_reply):
            issues.append("дисклеймер вместо ответа")
        if len(actions) < 2:
            issues.append("мало шагов")
        if any(self._looks_garbled(item) for item in actions):
            issues.append("поврежденные шаги")
        if self._assistant_is_generic_reply(reply_text):
            issues.append("слишком общий ответ")
        if self._assistant_requires_route(message) and not self._assistant_has_ui_anchor(reply_text, actions):
            issues.append("нет маршрута по интерфейсу")
        if is_teacher_assignment_intent:
            merged = f"{reply_text} {' '.join(actions)}".lower()
            has_issue_flow = (
                "выдача дз" in merged
                or "режим «выдача дз»" in merged
                or "режим 'выдача дз'" in merged
                or "выдать домашнее задание" in merged
            )
            has_issue_action = any(
                token in " ".join(actions).lower()
                for token in ("выдать", "выдача", "домашнее задание")
            )
            if not has_issue_flow:
                issues.append("нет шага по выдаче дз")
            if not has_issue_action:
                issues.append("нет действия с выдачей дз")
        if is_teacher_review_intent:
            merged = f"{reply_text} {' '.join(actions)}".lower()
            if "провер" not in merged and "оцен" not in merged and "коммент" not in merged:
                issues.append("нет шага по проверке дз")
        return issues

    @staticmethod
    def _assistant_requires_route(message: str) -> bool:
        text = (message or "").lower()
        markers = ("как", "куда", "где", "что наж", "выдать", "добав", "созда", "провер", "отправ")
        return any(marker in text for marker in markers)

    @staticmethod
    def _assistant_has_ui_anchor(reply_text: str, actions: list[str]) -> bool:
        text = f"{reply_text} {' '.join(actions)}".lower()
        ui_markers = (
            "режим",
            "раздел",
            "вклад",
            "кноп",
            "карточ",
            "поле",
            "форма",
            "откры",
            "выбер",
            "наж",
            "перей",
        )
        return any(marker in text for marker in ui_markers)

    def _assistant_is_generic_reply(self, text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return True
        generic_markers = (
            "сформулируйте цель",
            "сделайте ближайший шаг",
            "проверьте результат",
            "могу помочь",
            "выполните шаги",
            "можно сделать следующие шаги",
        )
        if any(marker in lowered for marker in generic_markers):
            return True
        word_count = len(re.findall(r"\w+", lowered))
        return word_count < 6 and not self._assistant_has_ui_anchor(text, [])

    def _assistant_generate_actions(
        self,
        role: str,
        screen_name: str,
        message: str,
        reply_text: str,
        timeout_seconds: float,
    ) -> list[str]:
        try:
            payload = self._ask_ollama(
                prompt=(
                    "Сгенерируй только JSON: "
                    "{\"suggested_actions\":[\"...\",\"...\",\"...\"]}\n"
                    "Нужны ровно 3 коротких шага по интерфейсу, каждый начинается с глагола.\n"
                    f"Роль: {role}. Экран: {screen_name}.\n"
                    f"Вопрос: {message}\n"
                    f"Текущий ответ: {reply_text}"
                ),
                options=_OLLAMA_ASSISTANT_OPTIONS,
                timeout_seconds=max(2.0, timeout_seconds),
                allow_raw_text=True,
            )
            actions = [self._assistant_polish_text(item) for item in self._assistant_extract_actions(payload)]
            return self._assistant_normalize_actions(actions)
        except Exception:
            return []

    @staticmethod
    def _assistant_default_actions(role: str, message: str) -> list[str]:
        text = (message or "").lower()
        if role == "teacher" and ("провер" in text or "оцен" in text or "коммент" in text):
            return [
                "Открыть режим «Проверка»",
                "Выбрать задачу ученика",
                "Написать комментарий и отправить",
            ]
        if role == "teacher" and ("выдать" in text or "дз" in text or "домаш" in text):
            return [
                "Открыть режим «Выдача ДЗ»",
                "Выбрать класс или ученика",
                "Нажать «Выдать домашнее задание»",
            ]
        if role == "student":
            return [
                "Открыть раздел задач",
                "Выбрать нужную карточку",
                "Выполнить действие и проверить статус",
            ]
        return [
            "Открыть нужный раздел",
            "Выполнить действие",
            "Проверить результат",
        ]

    def _assistant_enforce_intent_output(
        self,
        reply_text: str,
        actions: list[str],
        role: str,
        message: str,
    ) -> tuple[str, list[str]]:
        text = (message or "").lower()
        is_teacher_review_intent = role == "teacher" and any(token in text for token in ("провер", "оцен", "коммент"))
        is_teacher_assignment_intent = role == "teacher" and any(
            token in text for token in ("выдать", "дз", "домаш")
        ) and not is_teacher_review_intent
        merged_actions = " ".join(actions).lower()
        reply_lower = (reply_text or "").lower()

        if is_teacher_review_intent:
            required_actions = [
                "Открыть режим «Проверка»",
                "Выбрать задачу ученика и посмотреть сдачу",
                "Отправить оценку и комментарий",
            ]
            if "провер" not in reply_lower and "оцен" not in reply_lower:
                base = reply_text.rstrip(". ").strip()
                if base:
                    reply_text = f"{base}. Откройте режим «Проверка», выберите задачу и отправьте оценку с комментарием."
                else:
                    reply_text = "Откройте режим «Проверка», выберите задачу и отправьте оценку с комментарием."
            if "провер" not in merged_actions and "оцен" not in merged_actions and "коммент" not in merged_actions:
                actions = required_actions

        if is_teacher_assignment_intent:
            required_actions = [
                "Открыть режим «Выдача ДЗ»",
                "Выбрать класс или ученика и заполнить поля",
                "Нажать «Выдать домашнее задание»",
            ]
            if "выдача дз" not in reply_lower and "выдать домашнее задание" not in reply_lower:
                base = reply_text.rstrip(". ").strip()
                if base:
                    reply_text = f"{base}. Откройте режим «Выдача ДЗ», заполните поля и нажмите «Выдать домашнее задание»."
                else:
                    reply_text = "Откройте режим «Выдача ДЗ», заполните поля и нажмите «Выдать домашнее задание»."
            if "выдать" not in merged_actions and "выдача" not in merged_actions:
                actions = required_actions

        actions = self._assistant_normalize_actions(actions)
        return reply_text, actions

    def _assistant_normalize_actions(self, raw_actions: Any) -> list[str]:
        normalized: list[str] = []
        if isinstance(raw_actions, list):
            items = raw_actions
        elif isinstance(raw_actions, str):
            parts = [part.strip() for part in re.split(r"[;\n]+", raw_actions) if part.strip()]
            items = parts
        else:
            items = []

        for item in items:
            source = item
            if isinstance(item, dict):
                source = (
                    item.get("action")
                    or item.get("step")
                    or item.get("title")
                    or item.get("name")
                    or item.get("text")
                    or ""
                )
            cleaned = self._sanitize_sentence(str(source))
            cleaned = re.sub(r"^[0-9]+[).:-]\s*", "", cleaned)
            if not cleaned or self._looks_garbled(cleaned):
                continue
            if cleaned and cleaned[0].islower():
                cleaned = cleaned[0].upper() + cleaned[1:]
            if len(cleaned.split()) < 2:
                continue
            normalized.append(cleaned)
        unique: list[str] = []
        for item in normalized:
            lowered = item.lower()
            if lowered in {x.lower() for x in unique}:
                continue
            unique.append(item)
        return unique[:3]

    def _assistant_extract_reply(self, payload: dict[str, Any]) -> str:
        for key in ("reply", "answer", "text", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                cleaned = self._sanitize_sentence(value)
                if cleaned.startswith("{") and cleaned.endswith("}"):
                    try:
                        nested = self._extract_json(cleaned)
                        nested_reply = self._assistant_extract_reply(nested)
                        if nested_reply:
                            return nested_reply
                        return ""
                    except Exception:
                        if "suggested" in cleaned.lower() or "action" in cleaned.lower():
                            return ""
                return cleaned
        return ""

    def _assistant_extract_actions(self, payload: dict[str, Any]) -> list[str]:
        for key in ("suggested_actions", "suggestedactions", "actions", "steps", "suggestedSteps"):
            if key in payload:
                actions = self._assistant_normalize_actions(payload.get(key))
                if actions:
                    return actions
        for key in ("reply", "answer", "text", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                raw = value.strip()
                if raw.startswith("{") and raw.endswith("}"):
                    try:
                        nested = self._extract_json(raw)
                    except Exception:
                        continue
                    nested_actions = self._assistant_extract_actions(nested)
                    if nested_actions:
                        return nested_actions
        return []

    @staticmethod
    def _assistant_polish_text(text: str) -> str:
        cleaned = (text or "").strip()
        replacements = {
            "following actions": "следующие действия",
            "nút": "кнопка",
            "nhập": "ввести",
            "plans": "план",
            "planом": "планом",
            "p lan": "план",
            "dash板": "панель",
            "homework": "домашнее задание",
            "foto": "фото",
            "под following": "по следующим",
            "textbooks": "учебники",
        }
        lowered = cleaned.lower()
        for bad, good in replacements.items():
            if bad in lowered:
                cleaned = re.sub(re.escape(bad), good, cleaned, flags=re.IGNORECASE)
                lowered = cleaned.lower()
        cleaned = re.sub(r"[\u200b-\u200d\ufeff]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = cleaned.strip(" \"'")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _assistant_contains_refusal_or_disclaimer(text: str) -> bool:
        refusal_markers = (
            "не могу",
            "не имею знаний",
            "не обладаю знаниями",
            "обратитесь к специалисту",
            "я всего лишь",
            "как искусственный интеллект",
            "не могу предоставить реальную тактику",
            "требует конкретных знаний",
        )
        return any(marker in text for marker in refusal_markers)

    def suggest_review(
        self,
        task_title: str,
        task_description: str | None,
        submission_text: str | None,
    ) -> ReviewSuggestionResult:
        base_text = " ".join(
            [
                (task_title or "").strip(),
                (task_description or "").strip(),
                (submission_text or "").strip(),
            ]
        ).strip()
        normalized = base_text.lower()

        fallback = ReviewSuggestionResult(
            suggested_score=4 if len(normalized) > 40 else 3,
            summary="Автоматическая проверка в fallback-режиме: оценка ориентировочная.",
            issues=(
                ["Ответ слишком короткий, стоит добавить пояснение решения."]
                if len((submission_text or "").strip()) < 20
                else ["Проверьте точность формулировок и соответствие условию задачи."]
            ),
            recommendation="Уточните ключевые шаги решения и проверьте терминологию.",
            provider="fallback",
        )

        try:
            payload = self._ask_ollama(
                prompt=(
                    "Проверь домашнюю работу. Верни JSON: "
                    "suggested_score (1-5), summary, issues (массив), recommendation.\n"
                    f"Задание: {task_title}\n"
                    f"Описание: {task_description or ''}\n"
                    f"Ответ ученика: {submission_text or ''}\n"
                ),
                options=_OLLAMA_BASE_OPTIONS,
            )
            score = int(payload.get("suggested_score") or fallback.suggested_score)
            if score < 1 or score > 5:
                score = fallback.suggested_score

            issues_raw = payload.get("issues")
            issues: list[str] = []
            if isinstance(issues_raw, list):
                issues = [self._sanitize_sentence(str(item)) for item in issues_raw if str(item).strip()]
            if not issues:
                issues = fallback.issues

            summary = self._sanitize_sentence(str(payload.get("summary") or fallback.summary))
            recommendation = self._sanitize_sentence(
                str(payload.get("recommendation") or fallback.recommendation)
            )
            if not summary:
                summary = fallback.summary
            if not recommendation:
                recommendation = fallback.recommendation

            return ReviewSuggestionResult(
                suggested_score=score,
                summary=summary,
                issues=issues[:5],
                recommendation=recommendation,
                provider=f"ollama:{self._model}",
            )
        except ModelNotReadyError:
            return ReviewSuggestionResult(
                suggested_score=fallback.suggested_score,
                summary=fallback.summary,
                issues=fallback.issues,
                recommendation=fallback.recommendation,
                provider="fallback:model_not_ready",
            )
        except Exception:
            return fallback

    def _ask_ollama(
        self,
        prompt: str,
        options: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        allow_raw_text: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "keep_alive": _OLLAMA_KEEP_ALIVE,
            "options": options or _OLLAMA_BASE_OPTIONS,
        }
        last_connect_error: Exception | None = None

        for base_url in self._candidate_ollama_urls():
            try:
                data = self._post_generate_with_compat(
                    base_url=base_url,
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
                error_text = str(data.get("error") or "").strip()
                if error_text:
                    if "not found" in error_text.lower():
                        raise ModelNotReadyError(error_text)
                    raise RuntimeError(error_text)
                text = str(data.get("response", "")).strip()
                try:
                    return self._extract_json(text)
                except Exception:
                    if allow_raw_text:
                        return {"reply": text, "suggested_actions": []}
                    raise
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_connect_error = exc
                continue

        if last_connect_error is not None:
            raise last_connect_error
        raise RuntimeError("Не удалось обратиться к Ollama")

    def _post_generate_with_compat(
        self,
        base_url: str,
        payload: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        timeout_value = timeout_seconds if timeout_seconds is not None else self._request_timeout
        response = httpx.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=timeout_value,
        )
        if response.status_code < 400:
            return response.json()

        if response.status_code != 400:
            response.raise_for_status()

        compat_payload = dict(payload)
        compat_payload.pop("keep_alive", None)
        options = compat_payload.get("options")
        if isinstance(options, dict):
            allowed = {"temperature", "num_predict", "num_ctx", "top_p", "top_k", "repeat_penalty"}
            compat_payload["options"] = {k: v for k, v in options.items() if k in allowed}
            if not compat_payload["options"]:
                compat_payload.pop("options", None)

        retry = httpx.post(
            f"{base_url}/api/generate",
            json=compat_payload,
            timeout=timeout_value,
        )
        if retry.status_code < 400:
            return retry.json()

        minimal_payload: dict[str, Any] = {
            "model": payload.get("model"),
            "prompt": payload.get("prompt"),
            "stream": False,
        }
        if payload.get("format") == "json":
            minimal_payload["format"] = "json"

        retry_min = httpx.post(
            f"{base_url}/api/generate",
            json=minimal_payload,
            timeout=timeout_value,
        )
        retry_min.raise_for_status()
        return retry_min.json()

    def _candidate_ollama_urls(self) -> list[str]:
        candidates = [self._base_url.rstrip("/")]

        if "host.docker.internal" in self._base_url:
            candidates.append(self._base_url.replace("host.docker.internal", "127.0.0.1").rstrip("/"))
            candidates.append(self._base_url.replace("host.docker.internal", "localhost").rstrip("/"))

        if "127.0.0.1" in self._base_url:
            candidates.append(self._base_url.replace("127.0.0.1", "host.docker.internal").rstrip("/"))
        if "localhost" in self._base_url:
            candidates.append(self._base_url.replace("localhost", "host.docker.internal").rstrip("/"))

        unique: list[str] = []
        for item in candidates:
            if item and item not in unique:
                unique.append(item)
        return unique

    def _normalize_recommendations(self, raw: Any, fallback_recs: list[str]) -> list[str]:
        if not isinstance(raw, list):
            return fallback_recs

        normalized: list[str] = []
        for item in raw:
            text = ""
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                subject = str(item.get("subject") or "").strip()
                if subject:
                    total = int(item.get("total") or 0)
                    done = int(item.get("done") or 0)
                    overdue = int(item.get("overdue") or 0)
                    text = f"По предмету «{subject}»: выполнено {done} из {total}, просрочек {overdue}."
            else:
                continue

            cleaned = self._sanitize_sentence(text)
            if not cleaned:
                continue
            if cleaned.startswith("{") and cleaned.endswith("}"):
                continue
            if self._looks_garbled(cleaned):
                continue
            normalized.append(cleaned)

        if not normalized:
            return fallback_recs
        return normalized

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "да", "educational", "учебное"}:
                return True
            if lowered in {"false", "0", "no", "нет", "non_educational", "неучебное"}:
                return False
        return default

    @staticmethod
    def _sanitize_sentence(text: str) -> str:
        cleaned = text.replace("\n", " ").replace("\t", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"[`*_#~^]", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _looks_garbled(text: str) -> bool:
        lowered = text.lower()
        if re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", lowered):
            return True
        if any(token in lowered for token in ("nút", "nhập", "p lan", "пlan")):
            return True

        latin_letters = len(re.findall(r"[A-Za-z]", text))
        cyrillic_letters = len(re.findall(r"[А-Яа-яЁё]", text))
        return latin_letters > 14 and latin_letters > cyrillic_letters

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            pass

        block_match = re.search(r"\{[\s\S]*\}", text)
        if not block_match:
            candidate = text.strip()
        else:
            candidate = block_match.group(0).strip()

        try:
            return json.loads(candidate)
        except Exception:
            pass

        try:
            parsed = ast.literal_eval(candidate)
        except Exception as exc:
            raise ValueError("No JSON block in LLM response") from exc
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not dict-like")
        return parsed
