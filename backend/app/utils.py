from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings


def moscow_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def moscow_now() -> datetime:
    return datetime.now(moscow_tz())


def with_end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=0, microsecond=0)


def normalize_to_tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=moscow_tz())
    return dt.astimezone(moscow_tz())


def next_weekday(base: datetime, weekday: int) -> datetime:
    days_ahead = (weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def task_urgency_color(due_at: datetime | None, now: datetime | None = None) -> str:
    if due_at is None:
        return "blue"

    current = now or moscow_now()
    normalized_due = normalize_to_tz(due_at)
    if normalized_due is None:
        return "blue"

    left_hours = (normalized_due - current).total_seconds() / 3600
    if left_hours > 72:
        return "blue"
    if left_hours >= 24:
        return "orange"
    return "red"
