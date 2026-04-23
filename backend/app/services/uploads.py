from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.models import new_id


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(slots=True)
class StoredFile:
    file_name: str
    file_path: str
    mime_type: str | None
    size_bytes: int


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("._")
    return cleaned or f"file_{new_id()}.bin"


def save_upload(upload: UploadFile, subdir: str = "") -> StoredFile:
    root = Path(settings.upload_dir).expanduser().resolve()
    target_dir = (root / subdir).resolve()
    if root not in {target_dir, *target_dir.parents}:
        raise HTTPException(status_code=400, detail="Некорректный путь загрузки")

    target_dir.mkdir(parents=True, exist_ok=True)

    name = _safe_name(upload.filename or "upload.bin")
    target_path = target_dir / f"{new_id()}_{name}"

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    size = 0
    with target_path.open("wb") as fh:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                try:
                    target_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл слишком большой. Максимум {settings.max_upload_size_mb} МБ.",
                )
            fh.write(chunk)

    rel_path = str(target_path)
    return StoredFile(
        file_name=upload.filename or name,
        file_path=rel_path,
        mime_type=upload.content_type,
        size_bytes=size,
    )
