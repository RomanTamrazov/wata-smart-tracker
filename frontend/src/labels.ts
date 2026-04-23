import type { HelpRequest, Role, Task, TaskStatus } from "./types";

const ROLE_LABELS: Record<Role, string> = {
  student: "УЧЕНИК",
  teacher: "УЧИТЕЛЬ",
  parent: "РОДИТЕЛЬ",
};

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "К выполнению",
  in_progress: "В работе",
  done: "Готово",
};

const HELP_STATUS_LABELS: Record<HelpRequest["status"], string> = {
  open: "Ожидает ответа",
  answered: "Есть ответ",
};

const ORIGIN_LABELS: Record<Task["origin"], string> = {
  student: "Личная",
  teacher: "От учителя",
  parent: "От родителя",
};

const URGENCY_LABELS: Record<Task["urgency_color"], string> = {
  blue: "Срок > 3 дней",
  orange: "Срок 1-3 дня",
  red: "Срок < 1 дня",
};

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? "ПОЛЬЗОВАТЕЛЬ";
}

export function taskStatusLabel(status: TaskStatus): string {
  return TASK_STATUS_LABELS[status] ?? "Статус неизвестен";
}

export function helpStatusLabel(status: HelpRequest["status"]): string {
  return HELP_STATUS_LABELS[status] ?? "Статус неизвестен";
}

export function taskOriginLabel(origin: Task["origin"]): string {
  return ORIGIN_LABELS[origin] ?? "Неизвестно";
}

export function urgencyLabel(color: Task["urgency_color"]): string {
  return URGENCY_LABELS[color] ?? "Срок не задан";
}
