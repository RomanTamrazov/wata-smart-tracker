import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  addClassMember,
  answerHelpRequest,
  createAssignment,
  createSchoolClass,
  createTeacherReview,
  deleteSchoolClass,
  decideClassJoinRequest,
  listClassInvites,
  listClassJoinRequests,
  listHelpRequests,
  listTaskSubmissions,
  listTeacherClasses,
  listTeacherStudents,
  listStudentTasks,
  removeClassInvite,
  suggestTeacherReview,
  uploadAssignmentAttachments,
} from "../api";
import { formatDateTime } from "../date";
import { helpStatusLabel, taskStatusLabel } from "../labels";
import { ToastViewport } from "./ToastViewport";
import type {
  ClassInviteStatusRow,
  ClassJoinRequest,
  HelpRequest,
  LinkedStudent,
  SchoolClass,
  SessionData,
  Task,
  TaskSubmission,
  TeacherReviewSuggestion,
} from "../types";

interface TeacherDashboardProps {
  session: SessionData;
}

type TeacherViewMode = "classes" | "assignments" | "reviews";

function classInviteStatusLabel(status: ClassInviteStatusRow["status"]): string {
  if (status === "member") return "В классе";
  if (status === "pending") return "Заявка отправлена";
  if (status === "approved") return "Одобрено";
  if (status === "rejected") return "Отклонено";
  return "Добавлен в список";
}

export function TeacherDashboard({ session }: TeacherDashboardProps) {
  const token = session.access_token;
  const teacherId = session.user.id;

  const [students, setStudents] = useState<LinkedStudent[]>([]);
  const [classes, setClasses] = useState<SchoolClass[]>([]);
  const [tasksByStudent, setTasksByStudent] = useState<Record<string, Task[]>>({});
  const [classInvitesByClass, setClassInvitesByClass] = useState<Record<string, ClassInviteStatusRow[]>>({});
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [expandedClassId, setExpandedClassId] = useState<string | null>(null);
  const [expandedStudentByClass, setExpandedStudentByClass] = useState<Record<string, string | null>>({});
  const [helpRequests, setHelpRequests] = useState<HelpRequest[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string>("");
  const [classRequests, setClassRequests] = useState<ClassJoinRequest[]>([]);
  const [classInvites, setClassInvites] = useState<ClassInviteStatusRow[]>([]);
  const [submissionsByTask, setSubmissionsByTask] = useState<Record<string, TaskSubmission[]>>({});
  const [aiSuggestion, setAiSuggestion] = useState<TeacherReviewSuggestion | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [reviewTaskId, setReviewTaskId] = useState("");
  const [reviewScore, setReviewScore] = useState(5);
  const [reviewComment, setReviewComment] = useState("Отличная работа!");

  const [answerHelpId, setAnswerHelpId] = useState("");
  const [answerText, setAnswerText] = useState("");

  const [classNumber, setClassNumber] = useState<string>("");
  const [classParallel, setClassParallel] = useState("");
  const [classApproval, setClassApproval] = useState<"auto" | "manual">("auto");
  const [inviteEmail, setInviteEmail] = useState("");

  const [assignmentMode, setAssignmentMode] = useState<"class" | "student">("class");
  const [assignmentClassId, setAssignmentClassId] = useState("");
  const [assignmentStudentId, setAssignmentStudentId] = useState("");
  const [assignmentTitle, setAssignmentTitle] = useState("");
  const [assignmentSubject, setAssignmentSubject] = useState("");
  const [assignmentDescription, setAssignmentDescription] = useState("");
  const [assignmentDueAt, setAssignmentDueAt] = useState("");
  const [assignmentPriority, setAssignmentPriority] = useState<"low" | "medium" | "high">("medium");
  const [assignmentFiles, setAssignmentFiles] = useState<File[]>([]);
  const [viewMode, setViewMode] = useState<TeacherViewMode>("classes");

  const studentNameMap = useMemo(
    () => Object.fromEntries(students.map((student) => [student.id, student.full_name])),
    [students],
  );
  const selectedClass = useMemo(
    () => classes.find((item) => item.id === selectedClassId) ?? null,
    [classes, selectedClassId],
  );
  const assignmentClass = useMemo(
    () => classes.find((item) => item.id === assignmentClassId) ?? null,
    [classes, assignmentClassId],
  );
  const assignmentClassMemberCount = assignmentClass?.member_count ?? 0;
  const assignmentTargetsCount = assignmentMode === "class" ? assignmentClassMemberCount : assignmentStudentId ? 1 : 0;
  const canSubmitAssignment =
    assignmentTitle.trim().length > 0
    && (assignmentMode === "class"
      ? Boolean(assignmentClassId) && assignmentClassMemberCount > 0
      : Boolean(assignmentStudentId));

  const loadData = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const [linkedStudents, classRows, helps] = await Promise.all([
        listTeacherStudents(token, teacherId),
        listTeacherClasses(token),
        listHelpRequests(token, { teacher_id: teacherId }),
      ]);
      setStudents(linkedStudents);
      setClasses(classRows);
      setHelpRequests(helps);

      setSelectedClassId((prev) => {
        if (prev && classRows.some((item) => item.id === prev)) return prev;
        return classRows[0]?.id ?? "";
      });

      setExpandedClassId((prev) => {
        if (prev && classRows.some((item) => item.id === prev)) return prev;
        return classRows[0]?.id ?? null;
      });

      const taskLists = await Promise.all(
        linkedStudents.map((student) => listStudentTasks(student.id, token, { sort: "due_asc", include_source: true })),
      );
      const grouped = Object.fromEntries(linkedStudents.map((student, index) => [student.id, taskLists[index] ?? []]));
      setTasksByStudent(grouped);

      const merged = taskLists.flat();
      setAllTasks(merged);

      const classInviteEntries = await Promise.all(
        classRows.map(async (item) => {
          try {
            const rows = await listClassInvites(token, item.id);
            return [item.id, rows] as const;
          } catch {
            return [item.id, [] as ClassInviteStatusRow[]] as const;
          }
        }),
      );
      setClassInvitesByClass(Object.fromEntries(classInviteEntries));
      setReviewTaskId((prev) => {
        if (prev && merged.some((task) => task.id === prev)) return prev;
        return merged[0]?.id ?? "";
      });
      setAnswerHelpId((prev) => {
        if (prev && helps.some((item) => item.id === prev && item.status === "open")) return prev;
        return helps.find((item) => item.status === "open")?.id ?? "";
      });

      setAssignmentClassId((prev) => {
        if (prev && classRows.some((item) => item.id === prev)) return prev;
        return classRows[0]?.id ?? "";
      });
      setAssignmentStudentId((prev) => {
        if (prev && linkedStudents.some((item) => item.id === prev)) return prev;
        return linkedStudents[0]?.id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки данных учителя");
    } finally {
      setBusy(false);
    }
  }, [token, teacherId]);

  const loadClassRequests = useCallback(async (classId: string) => {
    if (!classId) {
      setClassRequests([]);
      setClassInvites([]);
      return;
    }
    try {
      const [rows, invitesRows] = await Promise.all([
        listClassJoinRequests(token, classId, "pending"),
        listClassInvites(token, classId),
      ]);
      setClassRequests(rows);
      setClassInvites(invitesRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить заявки класса");
    }
  }, [token]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (selectedClassId) {
      void loadClassRequests(selectedClassId);
    }
  }, [selectedClassId, loadClassRequests]);

  useEffect(() => {
    if (!info && !error) return;
    const timer = window.setTimeout(() => {
      setInfo(null);
      setError(null);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [info, error]);

  async function handleReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewTaskId) {
      setError("Выберите задачу для проверки и комментария.");
      return;
    }

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await createTeacherReview(token, {
        task_id: reviewTaskId,
        score: reviewScore,
        comment: reviewComment,
      });
      setInfo("Проверка и комментарий отправлены.");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить проверку");
    } finally {
      setBusy(false);
    }
  }

  async function handleAiSuggest() {
    if (!reviewTaskId) {
      setError("Сначала выберите задачу, чтобы получить ИИ-подсказку.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const suggestion = await suggestTeacherReview(token, { task_id: reviewTaskId });
      setAiSuggestion(suggestion);
      setReviewScore(suggestion.suggested_score);
      setReviewComment(suggestion.recommendation);
      setInfo("ИИ подготовил рекомендацию по оценке.");

      const taskSubmissions = await listTaskSubmissions(token, reviewTaskId);
      setSubmissionsByTask((prev) => ({ ...prev, [reviewTaskId]: taskSubmissions }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось получить ИИ-рекомендацию");
    } finally {
      setBusy(false);
    }
  }

  async function handleAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answerHelpId || !answerText.trim()) return;

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await answerHelpRequest(token, { help_request_id: answerHelpId, answer: answerText });
      setAnswerText("");
      setInfo("Ответ по запросу помощи отправлен.");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось ответить на запрос");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateClass(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedNumber = classNumber.trim();
    const normalizedParallel = classParallel.trim().toUpperCase();
    if (!normalizedNumber || !normalizedParallel) {
      setError("Выберите класс (1-11) и укажите букву параллели.");
      return;
    }
    if (!/^(?:[1-9]|1[0-1])$/.test(normalizedNumber)) {
      setError("Класс должен быть числом от 1 до 11.");
      return;
    }
    if (!/^[A-ZА-ЯЁ]$/u.test(normalizedParallel)) {
      setError("Параллель должна содержать одну букву.");
      return;
    }

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const classTitle = `${normalizedNumber}${normalizedParallel}`;
      const created = await createSchoolClass(token, {
        title: classTitle,
        grade: normalizedNumber,
        approval_mode: classApproval,
      });
      setClassNumber("");
      setClassParallel("");
      setSelectedClassId(created.id);
      setInfo("Класс создан.");
      await loadData();
      await loadClassRequests(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать класс");
    } finally {
      setBusy(false);
    }
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedClassId || !inviteEmail.trim()) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await addClassMember(token, selectedClassId, inviteEmail.trim().toLowerCase());
      setInviteEmail("");
      if (result.is_member) {
        setInfo("Ученик добавлен в класс.");
      } else {
        setInfo("Почта добавлена в список класса. После регистрации ученик появится в классе.");
      }
      await loadClassRequests(selectedClassId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить приглашение");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteClass() {
    if (!selectedClassId) return;
    const selected = classes.find((item) => item.id === selectedClassId);
    const className = selected?.title ?? "этот класс";
    const ok = window.confirm(`Удалить класс «${className}»?`);
    if (!ok) return;

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await deleteSchoolClass(token, selectedClassId);
      setInfo(`Класс «${className}» удалён.`);
      setSelectedClassId("");
      setClassRequests([]);
      setClassInvites([]);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить класс");
    } finally {
      setBusy(false);
    }
  }

  async function handleDecision(requestId: string, status: "approved" | "rejected") {
    if (!selectedClassId) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await decideClassJoinRequest(token, selectedClassId, requestId, status);
      setInfo(status === "approved" ? "Заявка одобрена." : "Заявка отклонена.");
      await loadClassRequests(selectedClassId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обработать заявку");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveInvite(inviteId: string, studentEmailValue: string) {
    if (!selectedClassId) return;
    const ok = window.confirm(`Удалить ${studentEmailValue} из списка класса?`);
    if (!ok) return;

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await removeClassInvite(token, selectedClassId, inviteId);
      setInfo("Ученик удалён из списка класса.");
      await loadClassRequests(selectedClassId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить ученика из класса");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assignmentTitle.trim()) {
      setError("Укажите тему задания.");
      return;
    }
    if (assignmentMode === "class" && !assignmentClassId) {
      setError("Выберите класс для массовой выдачи.");
      return;
    }
    if (assignmentMode === "class" && assignmentClassMemberCount === 0) {
      setError("В выбранном классе нет подтверждённых учеников.");
      return;
    }
    if (assignmentMode === "student" && !assignmentStudentId) {
      setError("Выберите ученика для точечной выдачи.");
      return;
    }

    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await createAssignment(token, {
        target_class_id: assignmentMode === "class" ? assignmentClassId || undefined : undefined,
        target_student_id: assignmentMode === "student" ? assignmentStudentId || undefined : undefined,
        title: assignmentTitle.trim(),
        subject: assignmentSubject.trim() || undefined,
        description: assignmentDescription.trim() || undefined,
        due_at: assignmentDueAt ? new Date(assignmentDueAt).toISOString() : null,
        priority: assignmentPriority,
      });
      let fileInfo = "";
      if (assignmentFiles.length) {
        const uploadResult = await uploadAssignmentAttachments(token, result.id, assignmentFiles);
        fileInfo = ` Файлов прикреплено: ${uploadResult.attached_files}.`;
      }
      setAssignmentTitle("");
      setAssignmentSubject("");
      setAssignmentDescription("");
      setAssignmentDueAt("");
      setAssignmentFiles([]);
      setInfo(`Задание выдано. Создано карточек: ${result.created_tasks}.${fileInfo}`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выдать задание");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ToastViewport
        items={[
          ...(error ? [{ id: "teacher-error", kind: "error" as const, text: error }] : []),
          ...(info ? [{ id: "teacher-info", kind: "success" as const, text: info }] : []),
        ]}
        onClose={(id) => {
          if (id === "teacher-error") setError(null);
          if (id === "teacher-info") setInfo(null);
        }}
      />

      <div className="dashboard-grid teacher-layout">
        <section className="panel guide-panel fade-up full-width">
          <h2>Маршрут учителя</h2>
        <ol className="guide-list">
          <li>Создайте класс и добавьте учеников по email.</li>
          <li>Обработайте заявки на вступление в класс.</li>
          <li>Выдавайте ДЗ всему классу или точечно ученику.</li>
          <li>Проверяйте решения: ИИ-подсказка + ваш финальный комментарий.</li>
        </ol>
          <div className="view-switch" style={{ marginTop: "0.7rem" }}>
            <button
              type="button"
              className={`button ${viewMode === "classes" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("classes")}
            >
              Классы
            </button>
            <button
              type="button"
              className={`button ${viewMode === "assignments" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("assignments")}
            >
              Выдача ДЗ
            </button>
            <button
              type="button"
              className={`button ${viewMode === "reviews" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("reviews")}
            >
              Проверка
            </button>
          </div>
        <div className="card-actions" style={{ marginTop: "0.7rem" }}>
          <button
            type="button"
            className="button ghost"
            onClick={() => {
              void loadData();
              if (selectedClassId) {
                void loadClassRequests(selectedClassId);
              }
            }}
            disabled={busy}
          >
            Обновить данные
          </button>
        </div>
        </section>

        {viewMode !== "reviews" && (
          <section className="panel tasks-panel fade-up">
        <h2>Классы и ученики</h2>
        <div className="student-folders">
          {classes.map((schoolClass) => {
            const isOpen = expandedClassId === schoolClass.id;
            const inviteRows = [...(classInvitesByClass[schoolClass.id] ?? [])].sort((a, b) => {
              const left = (a.student_full_name || a.student_email).toLowerCase();
              const right = (b.student_full_name || b.student_email).toLowerCase();
              return left.localeCompare(right, "ru");
            });
            const confirmedCount = inviteRows.filter((item) => item.is_member).length;
            const pendingCount = inviteRows.filter((item) => item.status === "pending").length;
            const openedStudentInviteId = expandedStudentByClass[schoolClass.id] ?? null;

            return (
              <article key={schoolClass.id} className={`student-folder ${isOpen ? "open" : ""}`}>
                <button
                  type="button"
                  className="folder-toggle"
                  onClick={() => setExpandedClassId((prev) => (prev === schoolClass.id ? null : schoolClass.id))}
                >
                  <span className="folder-arrow">{isOpen ? "▾" : "▸"}</span>
                  <span className="folder-title">{schoolClass.title}</span>
                  <span className="folder-email">
                    {schoolClass.grade ? `${schoolClass.grade} класс` : "Без указания параллели"} · В классе: {confirmedCount} ·
                    Ожидают: {pendingCount}
                  </span>
                  <span className="folder-count">{inviteRows.length} учеников</span>
                </button>

                {isOpen && (
                  <div className="folder-body">
                    <div className="student-folders">
                      {inviteRows.map((invite) => {
                        const studentTasks = invite.student_id ? tasksByStudent[invite.student_id] ?? [] : [];
                        const studentIsOpen = openedStudentInviteId === invite.id;
                        const studentLabel = invite.student_full_name || invite.student_email;
                        return (
                          <article key={invite.id} className={`student-folder ${studentIsOpen ? "open" : ""}`}>
                            <button
                              type="button"
                              className="folder-toggle"
                              onClick={() =>
                                setExpandedStudentByClass((prev) => ({
                                  ...prev,
                                  [schoolClass.id]: prev[schoolClass.id] === invite.id ? null : invite.id,
                                }))
                              }
                            >
                              <span className="folder-arrow">{studentIsOpen ? "▾" : "▸"}</span>
                              <span className="folder-title">{studentLabel}</span>
                              <span className="folder-email">
                                {invite.student_email} · {classInviteStatusLabel(invite.status)}
                              </span>
                              <span className="folder-count">
                                {invite.student_id ? `${studentTasks.length} задач` : "Нет аккаунта"}
                              </span>
                            </button>

                            {studentIsOpen && (
                              <div className="folder-body">
                                {invite.student_id ? (
                                  <div className="tasks-list compact folder-tasks">
                                    {studentTasks.map((task) => (
                                      <article key={task.id} className={`task-card compact urgency-${task.urgency_color}`}>
                                        <header>
                                          <h3>{task.title}</h3>
                                          <span className={`chip ${task.status}`}>{taskStatusLabel(task.status)}</span>
                                        </header>
                                        <p>
                                          <strong>Предмет:</strong> {task.subject || "Не указан"}
                                        </p>
                                        <p>
                                          <strong>Дедлайн:</strong> {formatDateTime(task.due_at)}
                                        </p>
                                      </article>
                                    ))}
                                    {!studentTasks.length && <p>У этого ученика пока нет задач.</p>}
                                  </div>
                                ) : (
                                  <p>Ученик ещё не зарегистрирован под этой почтой.</p>
                                )}
                              </div>
                            )}
                          </article>
                        );
                      })}
                      {!inviteRows.length && <p>В этом классе пока нет учеников.</p>}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
          {!classes.length && <p>Пока нет классов. Создайте первый класс справа.</p>}
        </div>
          </section>
        )}

        {viewMode !== "reviews" && (
          <section className="panel form-panel fade-up" style={{ animationDelay: "0.1s" }}>
            <h2>{viewMode === "classes" ? "Управление классами" : "Выдача домашнего задания"}</h2>

            {viewMode === "classes" && (
              <>
                <form onSubmit={handleCreateClass} className="stack-form">
          <label>
            Класс (1-11)
            <select value={classNumber} onChange={(event) => setClassNumber(event.target.value)}>
              <option value="">Выберите класс</option>
              {Array.from({ length: 11 }, (_, index) => {
                const value = String(index + 1);
                return (
                  <option key={value} value={value}>
                    {value}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            Параллель (буква)
            <input
              placeholder="Например, А"
              value={classParallel}
              maxLength={1}
              onChange={(event) => {
                const normalized = event.target.value.toUpperCase().replace(/[^A-ZА-ЯЁ]/gu, "");
                setClassParallel(normalized.slice(0, 1));
              }}
            />
          </label>
          <p className="hint-text">
            Итоговое название класса:{" "}
            <strong>{classNumber && classParallel ? `${classNumber}${classParallel.toUpperCase()}` : "укажите класс и параллель"}</strong>
          </p>
          <select value={classApproval} onChange={(event) => setClassApproval(event.target.value as "auto" | "manual")}>
            <option value="auto">Автоодобрение заявок</option>
            <option value="manual">Ручное одобрение заявок</option>
          </select>
                  <button className="button secondary" disabled={busy}>
                    Создать класс
                  </button>
                </form>

                <hr />

                <label>
          Активный класс
          <select value={selectedClassId} onChange={(event) => setSelectedClassId(event.target.value)}>
            <option value="">Выберите класс</option>
            {classes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {item.member_count} уч. · {item.pending_requests_count} заявок
              </option>
            ))}
          </select>
                </label>
                {selectedClass && (
          <>
            <p className="hint-text">
              Подтверждено учеников: {selectedClass.member_count}. Ожидают решения: {selectedClass.pending_requests_count}.
            </p>
            <div className="card-actions" style={{ marginTop: "0.45rem" }}>
              <button type="button" className="button danger" onClick={() => void handleDeleteClass()} disabled={busy}>
                Удалить класс
              </button>
            </div>
          </>
                )}

                <form onSubmit={handleInvite} className="stack-form" style={{ marginTop: "0.6rem" }}>
          <input
            type="email"
            placeholder="student@example.com"
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
          />
          <button className="button ghost" disabled={busy || !selectedClassId}>
            Добавить email в класс
          </button>
                </form>

                <div className="table-wrap" style={{ marginTop: "0.65rem" }}>
          <table className="class-table">
            <thead>
              <tr>
                <th>Email ученика</th>
                <th>Имя</th>
                <th>Статус</th>
                <th>Комментарий</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {classInvites.map((item) => {
                const pendingRequest = classRequests.find((request) => request.id === item.request_id);
                const requestId = item.request_id ?? "";
                return (
                  <tr key={item.id}>
                    <td>{item.student_email}</td>
                    <td>{item.student_full_name || "Ещё не зарегистрирован"}</td>
                    <td>{classInviteStatusLabel(item.status)}</td>
                    <td>{pendingRequest?.message || "-"}</td>
                    <td>
                      <div className="table-actions">
                        {item.status === "pending" && item.request_id && (
                          <>
                            <button
                              type="button"
                              className="button secondary"
                              onClick={() => void handleDecision(requestId, "approved")}
                              disabled={busy}
                            >
                              Одобрить
                            </button>
                            <button
                              type="button"
                              className="button ghost"
                              onClick={() => void handleDecision(requestId, "rejected")}
                              disabled={busy}
                            >
                              Отклонить
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          className="button ghost"
                          onClick={() => void handleRemoveInvite(item.id, item.student_email)}
                          disabled={busy}
                        >
                          Удалить из класса
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!classInvites.length && (
                <tr>
                  <td colSpan={5}>Пока никого не добавили в список класса.</td>
                </tr>
              )}
            </tbody>
          </table>
                </div>
              </>
            )}

            {viewMode === "assignments" && (
              <>
                <form onSubmit={handleCreateAssignment} className="stack-form">

                  <label>
                    Режим выдачи
                    <select value={assignmentMode} onChange={(event) => setAssignmentMode(event.target.value as "class" | "student")}>
                      <option value="class">Весь класс</option>
                      <option value="student">Отдельный ученик</option>
                    </select>
                  </label>

                  {assignmentMode === "class" ? (
                    <select value={assignmentClassId} onChange={(event) => setAssignmentClassId(event.target.value)}>
                      <option value="">Выберите класс</option>
                      {classes.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title} · {item.member_count} уч.
                        </option>
                      ))}
                    </select>
                  ) : (
                    <select value={assignmentStudentId} onChange={(event) => setAssignmentStudentId(event.target.value)}>
                      <option value="">Выберите ученика</option>
                      {students.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.full_name}
                        </option>
                      ))}
                    </select>
                  )}

                  <input
                    placeholder="Тема задания"
                    value={assignmentTitle}
                    onChange={(event) => setAssignmentTitle(event.target.value)}
                  />
                  <input
                    placeholder="Предмет"
                    value={assignmentSubject}
                    onChange={(event) => setAssignmentSubject(event.target.value)}
                  />
                  <textarea
                    placeholder="Описание задания"
                    value={assignmentDescription}
                    onChange={(event) => setAssignmentDescription(event.target.value)}
                  />
                  <div className="inline-grid">
                    <input
                      type="datetime-local"
                      value={assignmentDueAt}
                      onChange={(event) => setAssignmentDueAt(event.target.value)}
                    />
                    <select
                      value={assignmentPriority}
                      onChange={(event) => setAssignmentPriority(event.target.value as "low" | "medium" | "high")}
                    >
                      <option value="low">Низкий</option>
                      <option value="medium">Средний</option>
                      <option value="high">Высокий</option>
                    </select>
                  </div>
                  <label>
                    Файлы к заданию (можно несколько)
                    <input
                      type="file"
                      multiple
                      onChange={(event) => setAssignmentFiles(Array.from(event.target.files ?? []))}
                    />
                  </label>
                  <p className="hint-text">
                    {assignmentMode === "class"
                      ? assignmentClassMemberCount > 0
                        ? `Получат задание: ${assignmentClassMemberCount} ученик(а/ов).`
                        : "В выбранном классе пока нет подтверждённых учеников."
                      : assignmentStudentId
                        ? "Получит задание: 1 ученик."
                        : "Выберите ученика для точечной выдачи."}
                  </p>
                  {!!assignmentFiles.length && <p className="hint-text">Выбрано файлов: {assignmentFiles.length}</p>}
                  <button className="button secondary" disabled={busy || !canSubmitAssignment}>
                    Выдать домашнее задание ({assignmentTargetsCount})
                  </button>
                </form>
              </>
            )}
          </section>
        )}

        {viewMode === "reviews" && (
          <section className="panel help-panel fade-up" style={{ animationDelay: "0.15s" }}>
        <h2>Проверка и помощь</h2>

        <form onSubmit={handleReview} className="stack-form">
          <select value={reviewTaskId} onChange={(event) => setReviewTaskId(event.target.value)}>
            <option value="">Выберите задачу</option>
            {allTasks.map((task) => (
              <option key={task.id} value={task.id}>
                {(studentNameMap[task.student_id] ?? "Ученик")} - {task.title}
              </option>
            ))}
          </select>

          <div className="card-actions">
            <button type="button" className="button ghost" onClick={() => void handleAiSuggest()} disabled={busy || !reviewTaskId}>
              ИИ-подсказка оценки
            </button>
          </div>

          {!!aiSuggestion && (
            <article className="review-item">
              <p>
                <strong>ИИ предлагает:</strong> {aiSuggestion.suggested_score} / 5
              </p>
              <p>{aiSuggestion.summary}</p>
              <ul>
                {aiSuggestion.issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
              <p>{aiSuggestion.recommendation}</p>
              <p className="review-date">Источник: {aiSuggestion.provider}</p>
            </article>
          )}

          {!!submissionsByTask[reviewTaskId]?.length && (
            <article className="review-item">
              <p>
                <strong>Последние сдачи ученика:</strong>
              </p>
              {submissionsByTask[reviewTaskId].slice(0, 3).map((submission) => (
                <p key={submission.id}>
                  {formatDateTime(submission.created_at)} · {submission.text_answer || submission.voice_transcript || "Файловое вложение"}
                </p>
              ))}
            </article>
          )}

          <input
            type="number"
            min={1}
            max={5}
            value={reviewScore}
            onChange={(event) => setReviewScore(Number(event.target.value))}
          />

          <textarea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} />

          <button className="button secondary" disabled={busy}>
            Отправить комментарий
          </button>
        </form>

        <hr />

        <ul className="help-list">
          {helpRequests.map((item) => (
            <li key={item.id}>
              <strong>{helpStatusLabel(item.status)}</strong> · {studentNameMap[item.student_id] ?? "Ученик"}: {item.question}
            </li>
          ))}
        </ul>

        <form onSubmit={handleAnswer} className="stack-form">
          <select value={answerHelpId} onChange={(event) => setAnswerHelpId(event.target.value)}>
            <option value="">Выберите запрос</option>
            {helpRequests
              .filter((item) => item.status === "open")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.question.slice(0, 40)}
                </option>
              ))}
          </select>
          <textarea
            placeholder="Ответ ученику"
            value={answerText}
            onChange={(event) => setAnswerText(event.target.value)}
          />
          <button className="button ghost" disabled={busy}>
            Ответить
          </button>
        </form>
          </section>
        )}
      </div>
    </>
  );
}
