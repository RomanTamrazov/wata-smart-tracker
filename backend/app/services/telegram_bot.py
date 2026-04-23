from __future__ import annotations

import os
import re
import time
from datetime import datetime
from dataclasses import dataclass

import httpx

from app.config import settings
from app.utils import moscow_tz


@dataclass(slots=True)
class BotConfig:
    token: str
    api_base: str
    backend_base: str
    poll_interval: int


@dataclass(slots=True)
class ChatState:
    pending_action: str | None = None
    login_email: str | None = None


class TelegramBotRunner:
    def __init__(self, config: BotConfig) -> None:
        self._cfg = config
        self._offset = 0
        self._states: dict[str, ChatState] = {}

    def run_forever(self) -> None:
        print("[telegram-bot] started")
        while True:
            try:
                updates = self._get_updates()
                for item in updates:
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
                    self._handle_update(item)
            except KeyboardInterrupt:
                print("[telegram-bot] stopped")
                break
            except Exception as exc:
                print(f"[telegram-bot] loop error: {exc}")
                time.sleep(max(1, self._cfg.poll_interval))

    def _get_updates(self) -> list[dict]:
        response = httpx.get(
            f"{self._cfg.api_base}/bot{self._cfg.token}/getUpdates",
            params={"offset": self._offset, "timeout": 25},
            timeout=35.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")
        return list(data.get("result") or [])

    def _send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        try:
            payload: dict[str, object] = {"chat_id": chat_id, "text": text[:3900]}
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            httpx.post(
                f"{self._cfg.api_base}/bot{self._cfg.token}/sendMessage",
                json=payload,
                timeout=10.0,
            )
        except Exception as exc:
            print(f"[telegram-bot] sendMessage error: {exc}")

    def _delete_message(self, chat_id: str, message_id: int | None) -> None:
        if not message_id:
            return
        try:
            httpx.post(
                f"{self._cfg.api_base}/bot{self._cfg.token}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=10.0,
            )
        except Exception as exc:
            print(f"[telegram-bot] deleteMessage error: {exc}")

    @staticmethod
    def _status_label(value: str) -> str:
        mapping = {
            "todo": "К выполнению",
            "in_progress": "В работе",
            "done": "Готово",
        }
        return mapping.get(value, value)

    @staticmethod
    def _urgency_label(value: str) -> str:
        mapping = {
            "blue": "срок > 3 дней",
            "orange": "срок 1-3 дня",
            "red": "срок < 1 дня",
        }
        return mapping.get(value, value)

    @staticmethod
    def _status_emoji(value: str) -> str:
        mapping = {
            "todo": "📝",
            "in_progress": "⚙️",
            "done": "✅",
        }
        return mapping.get(value, "•")

    @staticmethod
    def _urgency_emoji(value: str) -> str:
        mapping = {
            "blue": "🔵",
            "orange": "🟠",
            "red": "🔴",
        }
        return mapping.get(value, "•")

    @staticmethod
    def _origin_emoji(value: str) -> str:
        mapping = {
            "teacher": "👩‍🏫",
            "parent": "👨‍👩‍👧",
            "student": "🧑‍🎓",
        }
        return mapping.get(value, "•")

    @staticmethod
    def _origin_label(value: str) -> str:
        mapping = {
            "teacher": "от учителя",
            "parent": "от родителя",
            "student": "личная",
        }
        return mapping.get(value, value)

    @staticmethod
    def _format_due(raw: str) -> str:
        text = raw.strip()
        if not text:
            return "без дедлайна"
        normalized = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=moscow_tz())
            dt_msk = dt.astimezone(moscow_tz())
            return f"{dt_msk.strftime('%d.%m.%Y %H:%M')} (МСК)"
        except Exception:
            return text

    def _study_coach_tip(self, prompt: str) -> str:
        lowered = prompt.lower()
        tired = any(word in lowered for word in ("устал", "нет сил", "не могу", "выгорел", "сложно", "тяжело"))
        if tired:
            return (
                "🧠 План на восстановление и фокус:\n"
                "1) Сделайте паузу 10-15 минут: вода, встать, пройтись.\n"
                "2) Вернитесь и решайте 25 минут без отвлечений.\n"
                "3) Если застряли — сформулируйте конкретный вопрос и отправьте учителю.\n\n"
                "Ты не обязан сделать всё идеально сразу. Двигайся маленькими шагами — это работает."
            )
        return (
            "🧠 Как подойти к задаче:\n"
            "1) Разберите условие: что дано и что нужно получить.\n"
            "2) Разбейте решение на 2-4 коротких шага.\n"
            "3) Решайте по таймеру 25/5 (25 минут работа, 5 минут пауза).\n"
            "4) Проверьте ответ и только потом отмечайте задачу выполненной.\n\n"
            "Если нужно, я подскажу тактику по конкретному предмету. Напишите: «Помоги с алгеброй/русским»."
        )

    @staticmethod
    def _main_keyboard() -> dict:
        return {
            "keyboard": [
                [{"text": "🔐 Войти"}, {"text": "📋 Мои задачи"}],
                [{"text": "➕ Добавить задачу"}, {"text": "🔥 Срочные"}],
                [{"text": "✅ Отметить выполненной"}, {"text": "🧠 Как решать?"}],
                [{"text": "❓ Помощь"}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        }

    @staticmethod
    def _cancel_keyboard() -> dict:
        return {
            "keyboard": [[{"text": "Отмена"}]],
            "resize_keyboard": True,
            "one_time_keyboard": False,
            "is_persistent": False,
        }

    def _state(self, chat_id: str) -> ChatState:
        return self._states.setdefault(chat_id, ChatState())

    @staticmethod
    def _extract_task_id(text: str) -> str:
        raw = text.strip()
        if re.fullmatch(r"[a-fA-F0-9]{32}", raw):
            return raw.lower()
        match = re.search(r"[a-fA-F0-9]{32}", raw)
        if match:
            return match.group(0).lower()
        return raw

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        message_id = message.get("message_id")
        if not chat_id:
            return

        text = str(message.get("text") or "").strip()
        if not text:
            return

        state = self._state(chat_id)

        if text.startswith("/start"):
            state.pending_action = None
            state.login_email = None
            self._send_message(
                chat_id,
                "Добро пожаловать в WATA Smart Tracker.\n\n"
                "Нажмите кнопку «🔐 Войти» и введите по шагам:\n"
                "1) почту\n"
                "2) пароль\n\n"
                "Можно и командой: /login <email> <password>\n"
                "Для безопасности сообщение с паролем в команде /login будет удалено автоматически.",
                reply_markup=self._main_keyboard(),
            )
            return

        if text == "Отмена":
            state.pending_action = None
            state.login_email = None
            self._send_message(
                chat_id,
                "Действие отменено.",
                reply_markup=self._main_keyboard(),
            )
            return

        if text.startswith("/login"):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                self._send_message(chat_id, "Формат: /login email пароль", reply_markup=self._main_keyboard())
                return
            self._cmd_login(
                chat_id=chat_id,
                username=message.get("from", {}).get("username"),
                email=parts[1],
                password=parts[2],
                source_message_id=message_id,
            )
            return

        if text in {"🔐 Войти", "Войти"}:
            state.pending_action = "login_email"
            state.login_email = None
            self._send_message(
                chat_id,
                "Введите email, который использовали при регистрации.",
                reply_markup=self._cancel_keyboard(),
            )
            return

        if text in {"❓ Помощь", "Помощь"}:
            self._send_message(
                chat_id,
                "Что можно сделать:\n"
                "1) Нажмите «🔐 Войти» для входа по почте и паролю.\n"
                "2) Нажмите «➕ Добавить задачу» и отправьте текст.\n"
                "3) Нажмите «📋 Мои задачи» для полного списка.\n"
                "4) Нажмите «🔥 Срочные» для ближайших дедлайнов.\n"
                "5) Нажмите «✅ Отметить выполненной», затем отправьте ID задачи.\n\n"
                "Для тактики решения нажмите «🧠 Как решать?».\n"
                "В любой момент нажмите «Отмена».",
                reply_markup=self._main_keyboard(),
            )
            return

        if text in {"🧠 Как решать?", "Как решать", "Помоги решить", "Как решить"}:
            self._send_message(
                chat_id,
                self._study_coach_tip(text),
                reply_markup=self._main_keyboard(),
            )
            return

        if text in {"➕ Добавить задачу", "Добавить задачу"}:
            state.pending_action = "add"
            state.login_email = None
            self._send_message(
                chat_id,
                "Отправьте текст учебной задачи одним сообщением.\n"
                "Пример: «Подготовить пересказ по литературе до пятницы».",
                reply_markup=self._cancel_keyboard(),
            )
            return

        if text in {"✅ Отметить выполненной", "Отметить выполненной"}:
            state.pending_action = "done"
            state.login_email = None
            self._send_message(
                chat_id,
                "Отправьте ID задачи, которую нужно отметить выполненной.\n"
                "ID можно скопировать из списка «📋 Мои задачи».",
                reply_markup=self._cancel_keyboard(),
            )
            return

        if text in {"📋 Мои задачи", "Мои задачи"}:
            self._cmd_list(chat_id, urgent_only=False)
            return

        if text in {"🔥 Срочные", "Срочные"}:
            self._cmd_list(chat_id, urgent_only=True)
            return

        if text.startswith("/add"):
            payload = text.replace("/add", "", 1).strip()
            if not payload:
                self._send_message(chat_id, "Формат: /add текст учебной задачи", reply_markup=self._main_keyboard())
                return
            self._cmd_add(chat_id, payload)
            return

        if text.startswith("/list"):
            self._cmd_list(chat_id, urgent_only=False)
            return

        if text.startswith("/urgent"):
            self._cmd_list(chat_id, urgent_only=True)
            return

        if text.startswith("/done"):
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                self._send_message(chat_id, "Формат: /done <task_id>", reply_markup=self._main_keyboard())
                return
            self._cmd_done(chat_id, self._extract_task_id(parts[1]))
            return

        if state.pending_action == "login_email":
            email = text.strip().lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                self._send_message(
                    chat_id,
                    "Похоже, это не email. Введите почту в формате name@example.com или нажмите «Отмена».",
                    reply_markup=self._cancel_keyboard(),
                )
                return
            state.login_email = email
            state.pending_action = "login_password"
            self._send_message(
                chat_id,
                "Теперь введите пароль от аккаунта.",
                reply_markup=self._cancel_keyboard(),
            )
            return

        if state.pending_action == "login_password":
            if not state.login_email:
                state.pending_action = "login_email"
                self._send_message(
                    chat_id,
                    "Сначала введите email.",
                    reply_markup=self._cancel_keyboard(),
                )
                return
            success = self._cmd_login(
                chat_id=chat_id,
                username=message.get("from", {}).get("username"),
                email=state.login_email,
                password=text,
                source_message_id=message_id,
                retry_with_cancel=True,
            )
            if success:
                state.pending_action = None
                state.login_email = None
            return

        if state.pending_action == "add":
            success = self._cmd_add(chat_id, text)
            if success:
                state.pending_action = None
            return

        if state.pending_action == "done":
            success = self._cmd_done(chat_id, self._extract_task_id(text))
            if success:
                state.pending_action = None
            return

        if any(marker in text.lower() for marker in ("как решить", "помоги решить", "не понимаю", "устал", "нет сил")):
            self._send_message(
                chat_id,
                self._study_coach_tip(text),
                reply_markup=self._main_keyboard(),
            )
            return

        self._send_message(
            chat_id,
            "Не понял сообщение. Используйте кнопки внизу или /start.",
            reply_markup=self._main_keyboard(),
        )

    def _cmd_login(
        self,
        chat_id: str,
        username: str | None,
        email: str,
        password: str,
        source_message_id: int | None = None,
        retry_with_cancel: bool = False,
    ) -> bool:
        try:
            response = httpx.post(
                f"{self._cfg.backend_base}/telegram/login",
                json={"chat_id": chat_id, "username": username, "email": email, "password": password},
                timeout=15.0,
            )
            if response.status_code >= 400:
                self._send_message(
                    chat_id,
                    f"Ошибка входа: {self._extract_error(response)}",
                    reply_markup=self._cancel_keyboard() if retry_with_cancel else self._main_keyboard(),
                )
                return False
            user = response.json().get("user") or {}
            self._send_message(
                chat_id,
                f"Вход выполнен: {user.get('full_name', 'пользователь')}",
                reply_markup=self._main_keyboard(),
            )
            return True
        finally:
            self._delete_message(chat_id, source_message_id)

    def _cmd_add(self, chat_id: str, text: str) -> bool:
        response = httpx.post(
            f"{self._cfg.backend_base}/telegram/notes",
            json={"chat_id": chat_id, "text": text},
            timeout=20.0,
        )
        if response.status_code >= 400:
            self._send_message(
                chat_id,
                f"Не удалось добавить задачу: {self._extract_error(response)}\nНажмите «Отмена» или отправьте другой текст.",
                reply_markup=self._cancel_keyboard(),
            )
            return False
        task = response.json().get("task") or {}
        due_line = self._format_due(str(task.get("due_at") or ""))
        self._send_message(
            chat_id,
            "✅ Задача добавлена\n"
            f"Название: {task.get('title', '')}\n"
            f"Дедлайн: {due_line}\n"
            f"ID: {task.get('id', '')}",
            reply_markup=self._main_keyboard(),
        )
        return True

    def _cmd_list(self, chat_id: str, urgent_only: bool) -> None:
        response = httpx.get(
            f"{self._cfg.backend_base}/telegram/tasks",
            params={"chat_id": chat_id, "urgent_only": urgent_only},
            timeout=15.0,
        )
        if response.status_code >= 400:
            self._send_message(
                chat_id,
                f"Не удалось получить список задач: {self._extract_error(response)}",
                reply_markup=self._main_keyboard(),
            )
            return
        tasks = list(response.json().get("tasks") or [])
        if not tasks:
            self._send_message(chat_id, "Список задач пока пуст.", reply_markup=self._main_keyboard())
            return

        done_count = sum(1 for item in tasks if str(item.get("status", "")) == "done")
        in_progress_count = sum(1 for item in tasks if str(item.get("status", "")) == "in_progress")
        todo_count = sum(1 for item in tasks if str(item.get("status", "")) == "todo")

        title = "🔥 Срочные задачи" if urgent_only else "📋 Мои задачи"
        lines = [
            f"{title} · {len(tasks)}",
            f"📝 К выполнению: {todo_count} | ⚙️ В работе: {in_progress_count} | ✅ Готово: {done_count}",
            "",
        ]
        for index, task in enumerate(tasks[:12], start=1):
            status_key = str(task.get("status", ""))
            urgency_key = str(task.get("urgency_color", ""))
            origin_key = str(task.get("origin", ""))
            status = self._status_label(str(task.get("status", "")))
            urgency = self._urgency_label(urgency_key)
            origin = self._origin_label(origin_key)
            due_text = self._format_due(str(task.get("due_at") or ""))
            lines.append(
                f"{index}) {task.get('title', '')}\n"
                f"   Статус: {self._status_emoji(status_key)} {status}\n"
                f"   Срочность: {self._urgency_emoji(urgency_key)} {urgency}\n"
                f"   Источник: {self._origin_emoji(origin_key)} {origin}\n"
                f"   Дедлайн: {due_text}\n"
                f"   ID: {task.get('id', '')}"
            )
            lines.append("")

        if todo_count > 0:
            lines.append("Совет: начните с первой срочной задачи и двигайтесь по одной карточке за раз.")
        else:
            lines.append("Отличная работа! Активных задач нет — можно немного отдохнуть.")

        self._send_message(chat_id, "\n".join(lines).strip(), reply_markup=self._main_keyboard())

    def _cmd_done(self, chat_id: str, task_id: str) -> bool:
        response = httpx.post(
            f"{self._cfg.backend_base}/telegram/tasks/done",
            json={"chat_id": chat_id, "task_id": task_id},
            timeout=15.0,
        )
        if response.status_code >= 400:
            self._send_message(
                chat_id,
                f"Не удалось отметить задачу: {self._extract_error(response)}\nПроверьте ID или нажмите «Отмена».",
                reply_markup=self._cancel_keyboard(),
            )
            return False
        task = response.json().get("task") or {}
        self._send_message(
            chat_id,
            f"✅ Отмечено как выполнено: {task.get('title', '')}\n"
            "Отличный прогресс. Так держать!",
            reply_markup=self._main_keyboard(),
        )
        return True

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            detail = body.get("detail")
            if isinstance(detail, str):
                return detail
        except Exception:
            pass
        return f"HTTP {response.status_code}"


def build_config() -> BotConfig:
    token = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Укажите TELEGRAM_BOT_TOKEN")
    backend_base = os.getenv("TELEGRAM_BACKEND_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
    return BotConfig(
        token=token,
        api_base=settings.telegram_api_base.rstrip("/"),
        backend_base=backend_base,
        poll_interval=max(1, settings.telegram_poll_interval_seconds),
    )


def main() -> None:
    runner = TelegramBotRunner(build_config())
    runner.run_forever()


if __name__ == "__main__":
    main()
