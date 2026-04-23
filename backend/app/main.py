from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import settings
from app.database import build_engine, init_db
from app.services.ai_hybrid import HybridAIService
from app.services.emailer import SmtpEmailService
from app.services.reminder_worker import reminder_loop
from app.services.tracker import TrackerService


def create_app(database_url: str | None = None, enable_worker: bool | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        enabled = settings.enable_reminder_worker if enable_worker is None else enable_worker
        if enabled:
            app.state.reminder_task = asyncio.create_task(reminder_loop(app))
        try:
            yield
        finally:
            task = getattr(app.state, "reminder_task", None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="WATA Smart Tracker API", version="2.0.0", lifespan=lifespan)

    engine = build_engine(database_url=database_url)
    init_db(engine)

    app.state.engine = engine
    app.state.tracker = TrackerService(
        ai_service=HybridAIService(base_url=settings.ollama_base_url, model=settings.ollama_model),
        email_sender=SmtpEmailService(),
    )

    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    extra_origins = [item.strip() for item in settings.cors_origins_raw.split(",") if item.strip()]
    cors_origins.extend(extra_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    dist_dir = Path(settings.frontend_dist_dir).expanduser() if settings.frontend_dist_dir else None
    if dist_dir and (dist_dir / "index.html").exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def serve_index() -> FileResponse:
            return FileResponse(dist_dir / "index.html")

        @app.get("/{path_name:path}", include_in_schema=False)
        def serve_spa(path_name: str) -> FileResponse:
            if path_name.startswith("api/") or path_name in {"api", "health"}:
                raise HTTPException(status_code=404, detail="Not Found")
            file_path = dist_dir / path_name
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()
