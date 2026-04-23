from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import TaskPriority
from app.utils import moscow_now, next_weekday, with_end_of_day


SUBJECTS = [
    "математика",
    "алгебра",
    "геометрия",
    "русский язык",
    "литература",
    "история",
    "обществознание",
    "физика",
    "химия",
    "биология",
    "английский",
    "информатика",
    "география",
]

WEEKDAYS = {
    "понедельника": 0,
    "вторника": 1,
    "среды": 2,
    "четверга": 3,
    "пятницы": 4,
    "субботы": 5,
    "воскресенья": 6,
}


@dataclass(slots=True)
class ExtractedTask:
    title: str
    description: str
    subject: str | None
    due_at: datetime | None
    priority: TaskPriority


@dataclass(slots=True)
class PlannedTask:
    planned_at: datetime | None
    interval_hours: int
    steps: list[str]


def parse_deadline(text: str, now: datetime | None = None) -> datetime | None:
    now = now or moscow_now()

    date_match = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?",
        text,
        flags=re.IGNORECASE,
    )
    if date_match:
        day, month, year, hour, minute = date_match.groups()
        h = int(hour) if hour is not None else 23
        m = int(minute) if minute is not None else 59
        return datetime(int(year), int(month), int(day), h, m, tzinfo=now.tzinfo)

    lowered = text.lower()
    if "завтра" in lowered:
        return with_end_of_day(now + timedelta(days=1))

    weekday_match = re.search(r"до\s+(понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья)", lowered)
    if weekday_match:
        target = WEEKDAYS[weekday_match.group(1)]
        return with_end_of_day(next_weekday(now, target))

    return None


def infer_subject(text: str) -> str | None:
    lowered = text.lower()
    for subject in SUBJECTS:
        if subject in lowered:
            return subject.title()
    return None


def infer_priority(text: str, due_at: datetime | None, now: datetime | None = None) -> TaskPriority:
    lowered = text.lower()
    if "срочно" in lowered or "важно" in lowered:
        return TaskPriority.HIGH

    now = now or moscow_now()
    if due_at is not None and (due_at - now).total_seconds() <= 48 * 3600:
        return TaskPriority.HIGH

    if "когда-нибудь" in lowered or "если успею" in lowered:
        return TaskPriority.LOW

    return TaskPriority.MEDIUM


def infer_title(text: str) -> str:
    sentence = re.split(r"[.!?\n]", text.strip(), maxsplit=1)[0].strip()
    if not sentence:
        return "Новое задание"
    return sentence[:140]


def extract_from_text(text: str, now: datetime | None = None) -> ExtractedTask:
    now = now or moscow_now()
    due_at = parse_deadline(text, now=now)
    subject = infer_subject(text)
    priority = infer_priority(text, due_at=due_at, now=now)

    return ExtractedTask(
        title=infer_title(text),
        description=text.strip(),
        subject=subject,
        due_at=due_at,
        priority=priority,
    )


def build_plan(title: str, description: str | None, priority: TaskPriority, due_at: datetime | None, now: datetime | None = None) -> PlannedTask:
    now = now or moscow_now()
    if due_at is None:
        planned_at = now + timedelta(hours=2)
    else:
        left = due_at - now
        if left.total_seconds() <= 12 * 3600:
            planned_at = now + timedelta(minutes=30)
        elif left.total_seconds() <= 36 * 3600:
            planned_at = now + timedelta(hours=1)
        else:
            planned_at = due_at - timedelta(hours=18)

    interval_hours = 3 if priority == TaskPriority.HIGH else 6

    base_steps = [
        "Изучить условие и критерии выполнения",
        "Подготовить материалы и источники",
        "Выполнить основную часть задания",
        "Проверить результат и отметить выполнение",
    ]

    if description and len(description) > 120:
        base_steps.insert(2, "Разбить работу на короткие подэтапы")

    return PlannedTask(
        planned_at=planned_at,
        interval_hours=interval_hours,
        steps=base_steps,
    )


def build_analytics(task_summaries: list[dict]) -> list[str]:
    if not task_summaries:
        return ["Добавьте первые задания, чтобы получить персональные рекомендации."]

    hard = [item["subject"] for item in task_summaries if item["overdue"] > 0]
    recommendations: list[str] = []

    if hard:
        recommendations.append(
            f"Сфокусируйтесь на темах: {', '.join(hard[:3])}. Запланируйте короткие сессии по 25 минут."
        )

    recommendations.append(
        "Ставьте время старта заранее и включайте адаптивные напоминания для задач с высоким приоритетом."
    )
    recommendations.append("После выполнения каждой задачи оставляйте заметку, что было сложным — это улучшит персональные советы.")
    return recommendations
