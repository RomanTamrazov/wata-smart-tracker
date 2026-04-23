from __future__ import annotations

from dataclasses import dataclass


NON_EDUCATIONAL_MARKERS = (
    "дота",
    "dota",
    "кс",
    "counter strike",
    "cs2",
    "roblox",
    "майнкрафт",
    "minecraft",
    "brawl stars",
    "играть",
    "катка",
    "стрим",
    "тикток",
    "tiktok",
    "ютуб",
    "youtube",
    "сериал",
    "фильм",
    "гулять",
    "вечерин",
    "ресторан",
    "заказать еду",
    "погулять",
    "шопинг",
)

EDUCATIONAL_MARKERS = (
    "урок",
    "задани",
    "домаш",
    "дз",
    "контроль",
    "сочинен",
    "реферат",
    "предмет",
    "учител",
    "школ",
    "класс",
    "олимпиад",
    "алгебр",
    "геометр",
    "математ",
    "русск",
    "литератур",
    "физик",
    "хим",
    "биолог",
    "истори",
    "географ",
    "информат",
    "английск",
    "обществозн",
    "контурная карта",
    "упражнен",
)


@dataclass(slots=True)
class EducationalValidationResult:
    is_valid: bool
    reason: str | None = None
    suggestion: str | None = None


def validate_educational_task_text(text: str) -> EducationalValidationResult:
    lowered = (text or "").strip().lower()
    if not lowered:
        return EducationalValidationResult(is_valid=False, reason="Пустой текст задачи", suggestion="Опишите учебное задание")

    if any(marker in lowered for marker in NON_EDUCATIONAL_MARKERS):
        return EducationalValidationResult(
            is_valid=False,
            reason="Заметка похожа на неучебную активность",
            suggestion="Добавьте только учебную задачу: предмет, что сделать и дедлайн",
        )

    if any(marker in lowered for marker in EDUCATIONAL_MARKERS):
        return EducationalValidationResult(is_valid=True)

    action_markers = ("сделать", "решить", "подготовить", "написать", "выучить", "прочитать", "сдать", "повторить")
    deadline_markers = ("до ", "к ", "на завтра", "до завтра", "до пятницы", "дедлайн")

    has_action = any(token in lowered for token in action_markers)
    has_deadline = any(token in lowered for token in deadline_markers)
    has_subject_hint = any(
        token in lowered
        for token in (
            "алгебр",
            "геометр",
            "математ",
            "русск",
            "литератур",
            "физик",
            "хим",
            "биолог",
            "истори",
            "географ",
            "информат",
            "английск",
            "предмет",
            "урок",
        )
    )

    if has_action and (has_deadline or has_subject_hint):
        return EducationalValidationResult(is_valid=True)

    return EducationalValidationResult(
        is_valid=False,
        reason="Не удалось подтвердить, что это школьное задание",
        suggestion="Укажите предмет, формулировку задания и срок сдачи",
    )
