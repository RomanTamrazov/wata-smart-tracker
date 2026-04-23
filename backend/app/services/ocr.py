from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import settings


@dataclass(slots=True)
class OCRResult:
    text: str
    provider: str


class OCRExtractionError(RuntimeError):
    pass


def extract_text_from_image(path: str | Path) -> OCRResult:
    if not settings.ocr_enabled:
        raise OCRExtractionError("OCR выключен в настройках")

    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        raise OCRExtractionError("Файл изображения не найден")

    try:
        from PIL import Image
        import pytesseract

        text = pytesseract.image_to_string(Image.open(image_path), lang=settings.ocr_lang)
        cleaned = " ".join((text or "").split())
        if cleaned:
            return OCRResult(text=cleaned, provider="pytesseract")
    except Exception:
        pass

    raise OCRExtractionError(
        "Не удалось распознать текст с изображения. Проверьте качество фото или установите OCR-зависимости."
    )
