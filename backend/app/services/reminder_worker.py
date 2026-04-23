from __future__ import annotations

import asyncio

from sqlmodel import Session

from app.config import settings


async def reminder_loop(app) -> None:
    while True:
        try:
            with Session(app.state.engine) as session:
                app.state.tracker.run_reminders(session=session, student_id=None)
        except Exception as exc:  # pragma: no cover - safety for background loop
            print(f"[reminder-worker] error: {exc}")
        await asyncio.sleep(settings.reminder_worker_interval_seconds)
