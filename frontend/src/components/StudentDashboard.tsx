import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  addParentGoalEvidence,
  createClassJoinRequest,
  createHelpRequest,
  createTask,
  createTaskSubmission,
  deleteTask,
  extractTask,
  extractTaskPhoto,
  getAttachmentUrl,
  getTaskAttachmentUrl,
  getAnalytics,
  getProgress,
  getStudentContacts,
  linkStudentParent,
  listMyClassInvites,
  listParentGoals,
  listPublicClasses,
  listStudentTasks,
  listTaskSubmissions,
  listTaskReviews,
  planTask,
  runReminders,
  unlinkStudentParent,
  updateTaskStatus,
} from "../api";
import { formatDateTime } from "../date";
import { taskOriginLabel, taskStatusLabel, urgencyLabel } from "../labels";
import { ToastViewport } from "./ToastViewport";
import type {
  Analytics,
  ParentGoal,
  Progress,
  PublicSchoolClass,
  SessionData,
  StudentClassInvite,
  StudentContacts,
  Task,
  TaskPriority,
  TeacherReviewDetails,
  TaskSubmission,
} from "../types";

type SpeechRecognitionCtor = new () => {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
  start: () => void;
};

function resolveSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

function normalizeAnalyticsTip(raw: string): string {
  const text = raw.trim();
  if (!text) return "";

  if (text.startsWith("{") && text.endsWith("}")) {
    const jsonLike = text.replaceAll("'", '"');
    try {
      const parsed = JSON.parse(jsonLike) as {
        subject?: string;
        total?: number;
        done?: number;
        overdue?: number;
      };
      if (parsed.subject) {
        return `По предмету «${parsed.subject}»: выполнено ${parsed.done ?? 0} из ${parsed.total ?? 0}, просрочек ${parsed.overdue ?? 0}.`;
      }
    } catch {
      return "";
    }
  }

  return text;
}

function classInviteStatusLabel(invite: StudentClassInvite): string {
  if (invite.is_member) return "В классе";
  if (invite.request_status === "pending") return "Заявка отправлена";
  if (invite.request_status === "approved") return "Одобрено учителем";
  if (invite.request_status === "rejected") return "Заявка отклонена";
  return "Добавлен учителем";
}

function mapPublicToInviteRow(item: PublicSchoolClass): StudentClassInvite {
  return {
    id: `public-${item.id}`,
    class_id: item.id,
    class_title: item.title,
    grade: item.grade,
    teacher_name: item.teacher_name,
    approval_mode: item.approval_mode,
    invited_at: new Date().toISOString(),
    request_status: "none",
    is_member: false,
    can_request: true,
  };
}

interface StudentDashboardProps {
  session: SessionData;
}

type StudentViewMode = "overview" | "create" | "connections";
type StudentTaskTypeFilter = "all" | "homework" | "personal";
type StudentDeadlineFilter = "all" | "expiring" | "not_expiring";

export function StudentDashboard({ session }: StudentDashboardProps) {
  const token = session.access_token;
  const studentId = useMemo(
    () => session.context.student_ids[0] ?? session.user.id,
    [session.context.student_ids, session.user.id],
  );

  const [tasks, setTasks] = useState<Task[]>([]);
  const [contacts, setContacts] = useState<StudentContacts | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [classInvites, setClassInvites] = useState<StudentClassInvite[]>([]);
  const [parentGoals, setParentGoals] = useState<ParentGoal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [reviewsTask, setReviewsTask] = useState<Task | null>(null);
  const [taskReviews, setTaskReviews] = useState<TeacherReviewDetails[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);

  const [manualTitle, setManualTitle] = useState("");
  const [manualSubject, setManualSubject] = useState("");
  const [manualDescription, setManualDescription] = useState("");
  const [manualDueAt, setManualDueAt] = useState("");
  const [manualPriority, setManualPriority] = useState<TaskPriority>("medium");

  const [extractText, setExtractText] = useState("");
  const [extractPhoto, setExtractPhoto] = useState<File | null>(null);
  const [voiceListening, setVoiceListening] = useState(false);

  const [helpTaskId, setHelpTaskId] = useState("");
  const [helpQuestion, setHelpQuestion] = useState("");
  const [parentEmail, setParentEmail] = useState("");

  const [classMessage, setClassMessage] = useState("");

  const [submissionTask, setSubmissionTask] = useState<Task | null>(null);
  const [submissionText, setSubmissionText] = useState("");
  const [submissionVoiceText, setSubmissionVoiceText] = useState("");
  const [submissionFiles, setSubmissionFiles] = useState<File[]>([]);
  const [submissionHistory, setSubmissionHistory] = useState<TaskSubmission[]>([]);
  const [submissionHistoryLoading, setSubmissionHistoryLoading] = useState(false);

  const [goalTargetId, setGoalTargetId] = useState<string>("");
  const [goalEvidenceComment, setGoalEvidenceComment] = useState("");
  const [goalEvidenceFile, setGoalEvidenceFile] = useState<File | null>(null);
  const [viewMode, setViewMode] = useState<StudentViewMode>("overview");
  const [taskTypeFilter, setTaskTypeFilter] = useState<StudentTaskTypeFilter>("all");
  const [deadlineFilter, setDeadlineFilter] = useState<StudentDeadlineFilter>("all");
  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const isPersonal = task.origin === "student";
      if (taskTypeFilter === "homework" && isPersonal) return false;
      if (taskTypeFilter === "personal" && !isPersonal) return false;

      if (deadlineFilter !== "all") {
        const isExpiring = task.urgency_color === "red";
        if (deadlineFilter === "expiring" && !isExpiring) return false;
        if (deadlineFilter === "not_expiring" && isExpiring) return false;
      }
      return true;
    });
  }, [tasks, taskTypeFilter, deadlineFilter]);
  const homeworkTasks = useMemo(() => filteredTasks.filter((task) => task.origin !== "student"), [filteredTasks]);
  const personalTasks = useMemo(() => filteredTasks.filter((task) => task.origin === "student"), [filteredTasks]);
  const nearestTasks = useMemo(
    () => homeworkTasks.filter((task) => task.status !== "done").slice(0, 3),
    [homeworkTasks],
  );

  const loadDashboard = useCallback(async () => {
    setError(null);
    try {
      const [tasksData, progressData, analyticsData, contactsData, publicClassesData, goalsData] = await Promise.all([
        listStudentTasks(studentId, token, { sort: "due_asc", include_source: true }),
        getProgress(token, studentId),
        getAnalytics(token, studentId),
        getStudentContacts(token, studentId),
        listPublicClasses(token),
        listParentGoals(token),
      ]);

      let classesData: StudentClassInvite[] = [];
      try {
        classesData = await listMyClassInvites(token);
      } catch {
        classesData = [];
      }

      const classRowsMap = new Map<string, StudentClassInvite>();
      for (const item of classesData) {
        classRowsMap.set(item.class_id, item);
      }
      for (const item of publicClassesData) {
        if (item.is_invited && !classRowsMap.has(item.id)) {
          classRowsMap.set(item.id, mapPublicToInviteRow(item));
        }
      }
      const mergedClassRows = Array.from(classRowsMap.values()).sort((a, b) => a.class_title.localeCompare(b.class_title, "ru"));
      setTasks(tasksData);
      setProgress(progressData);
      setAnalytics(analyticsData);
      setContacts(contactsData);
      setClassInvites(mergedClassRows);
      setParentGoals(goalsData);
      const helpTask = tasksData.find((item) => item.origin !== "student") ?? tasksData[0];
      setHelpTaskId((prev) => prev || helpTask?.id || "");
      setGoalTargetId((prev) => prev || goalsData[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить данные");
    }
  }, [studentId, token]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!info && !error) return;
    const timer = window.setTimeout(() => {
      setInfo(null);
      setError(null);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [info, error]);

  function setSuccess(message: string) {
    setError(null);
    setInfo(message);
  }

  async function handleDownloadFile(url: string, fileName: string) {
    setError(null);
    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
      setSuccess(`Файл «${fileName}» скачан.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось скачать файл");
    }
  }

  function startVoiceCapture(target: "extract" | "submission") {
    setError(null);
    setInfo(null);
    const Ctor = resolveSpeechRecognitionCtor();
    if (!Ctor) {
      setError("Голосовой ввод не поддерживается в этом браузере.");
      return;
    }

    const recognition = new Ctor();
    recognition.lang = "ru-RU";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: Event) => {
      const speechEvent = event as Event & {
        results?: ArrayLike<ArrayLike<{ transcript?: string }>>;
      };
      const transcript = speechEvent.results?.[0]?.[0]?.transcript?.trim() ?? "";
      if (!transcript) {
        setInfo("Речь не распознана, попробуйте ещё раз.");
        return;
      }
      if (target === "extract") {
        setExtractText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        setSuccess("Текст с голоса добавлен в поле ИИ-извлечения.");
      } else {
        setSubmissionVoiceText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        setSuccess("Голосовой текст добавлен в блок сдачи решения.");
      }
    };

    recognition.onerror = () => {
      setError("Не удалось распознать голос. Проверьте доступ к микрофону.");
    };

    recognition.onend = () => {
      setVoiceListening(false);
    };

    setVoiceListening(true);
    recognition.start();
  }

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manualTitle.trim()) return;

    setBusyTaskId("create");
    setError(null);
    setInfo(null);
    try {
      await createTask(token, {
        student_id: studentId,
        title: manualTitle,
        subject: manualSubject,
        description: manualDescription,
        due_at: manualDueAt ? new Date(manualDueAt).toISOString() : null,
        priority: manualPriority,
      });

      setManualTitle("");
      setManualSubject("");
      setManualDescription("");
      setManualDueAt("");
      setManualPriority("medium");
      setSuccess("Задача добавлена.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка при создании задачи");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleExtractTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!extractText.trim()) return;

    setBusyTaskId("extract");
    setError(null);
    setInfo(null);
    try {
      await extractTask(token, studentId, extractText);
      setExtractText("");
      setSuccess("ИИ-извлечение завершено, задача добавлена в список.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка ИИ-извлечения");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleExtractPhoto(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!extractPhoto) {
      setError("Выберите фото задания для OCR.");
      return;
    }
    setBusyTaskId("extract-photo");
    setError(null);
    setInfo(null);
    try {
      await extractTaskPhoto(token, studentId, extractPhoto);
      setExtractPhoto(null);
      setSuccess("Фото обработано: текст извлечён, задача создана.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось извлечь задачу с фото");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handlePlan(taskId: string) {
    setBusyTaskId(taskId);
    setError(null);
    setInfo(null);
    try {
      const plan = await planTask(token, taskId, true);
      setTasks((prev) =>
        prev.map((task) =>
          task.id === taskId
            ? {
                ...task,
                planned_at: plan.planned_at ?? task.planned_at,
                recommended_interval_hours: plan.interval_hours,
                steps: plan.steps,
              }
            : task,
        ),
      );
      setSuccess(`План построен: ${plan.steps.length} шаг(а/ов).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось построить план");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleComplete(taskId: string) {
    setBusyTaskId(taskId);
    setError(null);
    setInfo(null);
    try {
      await updateTaskStatus(token, taskId, "done");
      setSuccess("Задание отмечено как выполненное.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить статус");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleDeleteDoneTask() {
    if (!deleteTarget) return;
    const actionId = `delete-${deleteTarget.id}`;

    setBusyTaskId(actionId);
    setError(null);
    setInfo(null);
    try {
      await deleteTask(token, deleteTarget.id);
      setDeleteTarget(null);
      setSuccess("Выполненное задание удалено.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить задание");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleRunReminders() {
    setBusyTaskId("reminders");
    setError(null);
    setInfo(null);
    try {
      await runReminders(token, studentId);
      setSuccess("Цикл напоминаний запущен.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка запуска напоминаний");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleHelp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!helpTaskId || !helpQuestion.trim()) return;

    setBusyTaskId("help");
    setError(null);
    setInfo(null);
    try {
      await createHelpRequest(token, { task_id: helpTaskId, question: helpQuestion });
      setHelpQuestion("");
      setSuccess("Запрос помощи отправлен учителю.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить запрос помощи");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleLinkParent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!parentEmail.trim()) return;
    setBusyTaskId("link-parent");
    setError(null);
    setInfo(null);
    try {
      await linkStudentParent(token, {
        student_email: session.user.email,
        parent_email: parentEmail.trim().toLowerCase(),
      });
      setParentEmail("");
      setSuccess("Родитель успешно привязан.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось привязать родителя");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleJoinClass(classId: string) {
    setBusyTaskId(`class-${classId}`);
    setError(null);
    setInfo(null);
    try {
      await createClassJoinRequest(token, classId, classMessage || undefined);
      setSuccess("Заявка в класс отправлена.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить заявку в класс");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function loadSubmissionHistory(taskId: string) {
    setSubmissionHistoryLoading(true);
    try {
      const items = await listTaskSubmissions(token, taskId);
      setSubmissionHistory(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить приложенные решения");
    } finally {
      setSubmissionHistoryLoading(false);
    }
  }

  async function handleOpenSubmission(task: Task) {
    setSubmissionTask(task);
    setSubmissionHistory([]);
    setSubmissionText("");
    setSubmissionVoiceText("");
    setSubmissionFiles([]);
    await loadSubmissionHistory(task.id);
  }

  async function handleSubmitSolution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!submissionTask) return;
    setBusyTaskId(`submit-${submissionTask.id}`);
    setError(null);
    setInfo(null);
    try {
      await createTaskSubmission(token, submissionTask.id, {
        text_answer: submissionText,
        voice_transcript: submissionVoiceText,
        files: submissionFiles,
      });
      setSubmissionText("");
      setSubmissionVoiceText("");
      setSubmissionFiles([]);
      setSuccess("Решение отправлено учителю.");
      await loadSubmissionHistory(submissionTask.id);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить решение");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleAddGoalEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goalTargetId) {
      setError("Выберите цель от родителя.");
      return;
    }
    setBusyTaskId(`goal-${goalTargetId}`);
    setError(null);
    setInfo(null);
    try {
      await addParentGoalEvidence(token, goalTargetId, {
        comment: goalEvidenceComment,
        files: goalEvidenceFile ? [goalEvidenceFile] : [],
      });
      setGoalEvidenceComment("");
      setGoalEvidenceFile(null);
      setSuccess("Подтверждение по цели отправлено родителю.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить подтверждение по цели");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleUnlinkParent(parentEmailValue: string) {
    setBusyTaskId(`unlink-parent-${parentEmailValue}`);
    setError(null);
    setInfo(null);
    try {
      await unlinkStudentParent(token, {
        student_email: session.user.email,
        parent_email: parentEmailValue.toLowerCase(),
      });
      setSuccess("Родитель отвязан.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отвязать родителя");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleOpenReviews(task: Task) {
    setReviewsTask(task);
    setTaskReviews([]);
    setReviewsLoading(true);
    setError(null);
    try {
      const items = await listTaskReviews(token, task.id);
      setTaskReviews(items);
      if (!items.length) {
        setSuccess("По этой задаче пока нет комментариев учителя.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить комментарии учителя");
    } finally {
      setReviewsLoading(false);
    }
  }

  return (
    <>
      <ToastViewport
        items={[
          ...(error ? [{ id: "student-error", kind: "error" as const, text: error }] : []),
          ...(info ? [{ id: "student-info", kind: "success" as const, text: info }] : []),
        ]}
        onClose={(id) => {
          if (id === "student-error") setError(null);
          if (id === "student-info") setInfo(null);
        }}
      />

      <div className="dashboard-grid">
        <section className="panel guide-panel fade-up full-width">
          <h2>Что делать сейчас</h2>
          {nearestTasks.length ? (
            <ul className="guide-list">
              {nearestTasks.map((task) => (
                <li key={task.id}>
                  <strong>{task.title}</strong> — {formatDateTime(task.due_at)} ({urgencyLabel(task.urgency_color)})
                </li>
              ))}
            </ul>
          ) : (
            <p>Активных задач нет. Добавьте новую задачу вручную, голосом или через фото OCR.</p>
          )}

          <div className="view-switch" style={{ marginTop: "0.7rem" }}>
            <button
              type="button"
              className={`button ${viewMode === "overview" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("overview")}
            >
              Обзор
            </button>
            <button
              type="button"
              className={`button ${viewMode === "create" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("create")}
            >
              Добавить задание
            </button>
            <button
              type="button"
              className={`button ${viewMode === "connections" ? "primary" : "ghost"}`}
              onClick={() => setViewMode("connections")}
            >
              Связи и классы
            </button>
          </div>
        </section>

        {viewMode === "create" && (
          <>
            <section className="panel form-panel fade-up">
              <h2>Ручное создание задания</h2>
              <form onSubmit={handleCreateTask} className="stack-form">
                <input
                  placeholder="Название задания"
                  value={manualTitle}
                  onChange={(event) => setManualTitle(event.target.value)}
                />
                <input
                  placeholder="Предмет"
                  value={manualSubject}
                  onChange={(event) => setManualSubject(event.target.value)}
                />
                <textarea
                  placeholder="Описание"
                  value={manualDescription}
                  onChange={(event) => setManualDescription(event.target.value)}
                />

                <div className="inline-grid">
                  <input
                    type="datetime-local"
                    value={manualDueAt}
                    onChange={(event) => setManualDueAt(event.target.value)}
                  />
                  <select value={manualPriority} onChange={(event) => setManualPriority(event.target.value as TaskPriority)}>
                    <option value="low">Низкий</option>
                    <option value="medium">Средний</option>
                    <option value="high">Высокий</option>
                  </select>
                </div>

                <button className="button primary" disabled={busyTaskId === "create"}>
                  {busyTaskId === "create" ? "Создаём..." : "Добавить задачу"}
                </button>
              </form>
            </section>

            <section className="panel form-panel fade-up" style={{ animationDelay: "0.1s" }}>
              <h2>ИИ-извлечение задания</h2>
              <form onSubmit={handleExtractTask} className="stack-form">
                <textarea
                  placeholder="Вставьте текст/голос-текст задания"
                  value={extractText}
                  onChange={(event) => setExtractText(event.target.value)}
                />
                <div className="inline-actions">
                  <button
                    type="button"
                    className="button ghost"
                    onClick={() => startVoiceCapture("extract")}
                    disabled={voiceListening}
                  >
                    {voiceListening ? "Слушаю..." : "Озвучить текст"}
                  </button>
                </div>
                <button className="button secondary" disabled={busyTaskId === "extract"}>
                  {busyTaskId === "extract" ? "Анализируем..." : "Извлечь задание"}
                </button>
              </form>

              <form onSubmit={handleExtractPhoto} className="stack-form" style={{ marginTop: "0.65rem" }}>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(event) => setExtractPhoto(event.target.files?.[0] ?? null)}
                />
                <button className="button ghost" disabled={busyTaskId === "extract-photo"}>
                  {busyTaskId === "extract-photo" ? "Распознаём фото..." : "Извлечь из фото (OCR)"}
                </button>
              </form>

              <button
                className="button ghost"
                onClick={() => void handleRunReminders()}
                disabled={busyTaskId === "reminders"}
                style={{ marginTop: "0.65rem" }}
              >
                {busyTaskId === "reminders" ? "Запускаем цикл..." : "Запустить цикл напоминаний"}
              </button>
            </section>
          </>
        )}

        {viewMode === "overview" && (
          <>
            <section className="panel metrics-panel fade-up" style={{ animationDelay: "0.15s" }}>
              <h2>Прогресс</h2>
              <div className="metrics-grid">
                <div>
                  <span>Выполнено</span>
                  <strong>{progress?.completed_tasks ?? 0}</strong>
                </div>
                <div>
                  <span>Всего задач</span>
                  <strong>{progress?.total_tasks ?? 0}</strong>
                </div>
                <div>
                  <span>Баллы</span>
                  <strong>{progress?.points_total ?? 0}</strong>
                </div>
                <div>
                  <span>Просрочки</span>
                  <strong>{progress?.overdue_tasks ?? 0}</strong>
                </div>
              </div>

              <div className="progress-bar">
                <div style={{ width: `${Math.min(progress?.completion_rate ?? 0, 100)}%` }} />
              </div>
              <p>Процент выполнения: {progress?.completion_rate ?? 0}%</p>
              <p>
                Цель: <strong>{progress?.active_goal ?? "Не задана"}</strong>
              </p>
            </section>

            <section className="panel tasks-panel fade-up" style={{ animationDelay: "0.2s" }}>
              <h2>Задачи</h2>
              <div className="card-actions" style={{ marginBottom: "0.55rem" }}>
                <button type="button" className="button ghost" onClick={() => void loadDashboard()} disabled={Boolean(busyTaskId)}>
                  Обновить список задач
                </button>
                <select value={taskTypeFilter} onChange={(event) => setTaskTypeFilter(event.target.value as StudentTaskTypeFilter)}>
                  <option value="all">Все задачи</option>
                  <option value="homework">Только ДЗ</option>
                  <option value="personal">Только личные заметки</option>
                </select>
                <select value={deadlineFilter} onChange={(event) => setDeadlineFilter(event.target.value as StudentDeadlineFilter)}>
                  <option value="all">Любой дедлайн</option>
                  <option value="expiring">Истекает (≤ 24ч)</option>
                  <option value="not_expiring">Неистекающее (&gt; 24ч)</option>
                </select>
              </div>
              <h3>Выданное домашнее задание</h3>
              <div className="tasks-list">
                {homeworkTasks.map((task) => (
                  <article key={task.id} className={`task-card urgency-${task.urgency_color}`}>
                    <header>
                      <h3>{task.title}</h3>
                      <span className={`chip ${task.status}`}>{taskStatusLabel(task.status)}</span>
                    </header>
                    <p>{task.description || "Без описания"}</p>
                    <p>
                      <strong>Источник:</strong> {taskOriginLabel(task.origin)}
                    </p>
                    <p>
                      <strong>Срочность:</strong> {urgencyLabel(task.urgency_color)}
                    </p>
                    <p>
                      <strong>Предмет:</strong> {task.subject || "Не указан"}
                    </p>
                    <p>
                      <strong>Дедлайн:</strong> {formatDateTime(task.due_at)}
                    </p>
                    <p>
                      <strong>План старта:</strong> {formatDateTime(task.planned_at)}
                    </p>
                    {!!task.attachments.length && (
                      <div className="summary-list">
                        {task.attachments.map((attachment) => (
                          <button
                            key={attachment.id}
                            type="button"
                            className="button ghost"
                            onClick={() => void handleDownloadFile(getTaskAttachmentUrl(attachment.id), attachment.file_name)}
                          >
                            Скачать файл задания: {attachment.file_name}
                          </button>
                        ))}
                      </div>
                    )}
                    {!!task.steps.length && (
                      <ul>
                        {task.steps.map((step) => (
                          <li key={step.id}>{step.title}</li>
                        ))}
                      </ul>
                    )}
                    <div className="card-actions">
                      <button className="button secondary" onClick={() => void handlePlan(task.id)} disabled={busyTaskId === task.id}>
                        Построить план
                      </button>
                      <button
                        className="button primary"
                        onClick={() => void handleComplete(task.id)}
                        disabled={task.status === "done" || busyTaskId === task.id}
                      >
                        Отметить готовность
                      </button>
                      <button
                        type="button"
                        className="button ghost"
                        onClick={() => void handleOpenSubmission(task)}
                        disabled={busyTaskId === task.id}
                      >
                        Сдать решение
                      </button>
                      <button
                        type="button"
                        className="button ghost"
                        onClick={() => void handleOpenReviews(task)}
                        disabled={busyTaskId === task.id}
                      >
                        Комментарий учителя
                      </button>
                      {task.status === "done" && (
                        <button
                          type="button"
                          className="trash-button"
                          title="Удалить выполненное задание"
                          onClick={() => setDeleteTarget(task)}
                        >
                          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M9 3h6l1 2h4v2h-2v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7H4V5h4l1-2Zm-1 4v13h8V7H8Zm2 2h2v9h-2V9Zm4 0h2v9h-2V9Z" />
                          </svg>
                          Удалить
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {!homeworkTasks.length && <p>По текущим фильтрам выданных ДЗ нет.</p>}
              </div>

              <h3 style={{ marginTop: "0.8rem" }}>Личные заметки (видны только вам)</h3>
              <div className="tasks-list">
                {personalTasks.map((task) => (
                  <article key={task.id} className={`task-card urgency-${task.urgency_color}`}>
                    <header>
                      <h3>{task.title}</h3>
                      <span className={`chip ${task.status}`}>{taskStatusLabel(task.status)}</span>
                    </header>
                    <p>{task.description || "Без описания"}</p>
                    <p>
                      <strong>Тип:</strong> Личная заметка
                    </p>
                    <p>
                      <strong>Срочность:</strong> {urgencyLabel(task.urgency_color)}
                    </p>
                    <p>
                      <strong>Предмет:</strong> {task.subject || "Не указан"}
                    </p>
                    <p>
                      <strong>Дедлайн:</strong> {formatDateTime(task.due_at)}
                    </p>
                    <p>
                      <strong>План старта:</strong> {formatDateTime(task.planned_at)}
                    </p>
                    {!!task.steps.length && (
                      <ul>
                        {task.steps.map((step) => (
                          <li key={step.id}>{step.title}</li>
                        ))}
                      </ul>
                    )}
                    <div className="card-actions">
                      <button className="button secondary" onClick={() => void handlePlan(task.id)} disabled={busyTaskId === task.id}>
                        Построить план
                      </button>
                      <button
                        className="button primary"
                        onClick={() => void handleComplete(task.id)}
                        disabled={task.status === "done" || busyTaskId === task.id}
                      >
                        Отметить готовность
                      </button>
                      {task.status === "done" && (
                        <button
                          type="button"
                          className="trash-button"
                          title="Удалить выполненное задание"
                          onClick={() => setDeleteTarget(task)}
                        >
                          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M9 3h6l1 2h4v2h-2v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7H4V5h4l1-2Zm-1 4v13h8V7H8Zm2 2h2v9h-2V9Zm4 0h2v9h-2V9Z" />
                          </svg>
                          Удалить
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {!personalTasks.length && <p>По текущим фильтрам личных заметок нет.</p>}
              </div>
            </section>

            <section className="panel insights-panel fade-up" style={{ animationDelay: "0.25s" }}>
              <h2>ИИ-аналитика</h2>
              <p>
                Сложные темы: <strong>{analytics?.hard_topics.join(", ") || "пока не определены"}</strong>
              </p>
              <ul>
                {(analytics?.recommendations ?? [])
                  .map((tip) => normalizeAnalyticsTip(tip))
                  .filter(Boolean)
                  .map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                {!(analytics?.recommendations ?? []).length && (
                  <li>Добавьте больше задач, чтобы получить персональные советы.</li>
                )}
              </ul>
            </section>
          </>
        )}

        {viewMode === "connections" && (
          <>
            <section className="panel help-panel fade-up" style={{ animationDelay: "0.3s" }}>
              <h2>Помощь, связи и классы</h2>
              <form onSubmit={handleHelp} className="stack-form">
                <select value={helpTaskId} onChange={(event) => setHelpTaskId(event.target.value)}>
                  <option value="">Выберите задачу</option>
                  {tasks.filter((task) => task.origin !== "student").map((task) => (
                    <option key={task.id} value={task.id}>
                      {task.title}
                    </option>
                  ))}
                </select>
                <textarea
                  placeholder="Опишите, что не получается"
                  value={helpQuestion}
                  onChange={(event) => setHelpQuestion(event.target.value)}
                />
                <button className="button ghost" disabled={busyTaskId === "help"}>
                  Отправить запрос
                </button>
              </form>

              <hr />

              <h3>Привязать родителя по email</h3>
              <form onSubmit={handleLinkParent} className="stack-form">
                <input
                  type="email"
                  placeholder="parent@example.com"
                  value={parentEmail}
                  onChange={(event) => setParentEmail(event.target.value)}
                />
                <button
                  className="button secondary"
                  disabled={busyTaskId === "link-parent" || (contacts?.parents.length ?? 0) >= 2}
                >
                  Привязать родителя
                </button>
                <p className="hint-text">Привязано родителей: {contacts?.parents.length ?? 0} / 2</p>
              </form>
              <div className="contact-links-list">
                {(contacts?.parents ?? []).map((parent) => (
                  <div key={parent.id} className="contact-link-item">
                    <div>
                      <strong>{parent.full_name}</strong>
                      <p>{parent.email}</p>
                    </div>
                    <button
                      type="button"
                      className="button ghost"
                      onClick={() => void handleUnlinkParent(parent.email)}
                      disabled={busyTaskId === `unlink-parent-${parent.email}`}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
                {!(contacts?.parents.length ?? 0) && <p>Пока нет привязанных родителей.</p>}
              </div>

              <hr />

              <h3>Классы, куда вас добавили</h3>
              <div className="card-actions" style={{ marginTop: "0.45rem", marginBottom: "0.45rem" }}>
                <button type="button" className="button ghost" onClick={() => void loadDashboard()} disabled={Boolean(busyTaskId)}>
                  Обновить классы
                </button>
              </div>
              <textarea
                placeholder="Сообщение к заявке (необязательно)"
                value={classMessage}
                onChange={(event) => setClassMessage(event.target.value)}
              />
              <div className="table-wrap">
                <table className="class-table">
                  <thead>
                    <tr>
                      <th>Класс</th>
                      <th>Учитель</th>
                      <th>Режим</th>
                      <th>Статус</th>
                      <th>Действие</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classInvites.map((item) => (
                      <tr key={item.id}>
                        <td>{item.class_title}{item.grade ? ` (${item.grade})` : ""}</td>
                        <td>{item.teacher_name}</td>
                        <td>{item.approval_mode === "auto" ? "Авто" : "Ручной"}</td>
                        <td>{classInviteStatusLabel(item)}</td>
                        <td>
                          <button
                            type="button"
                            className="button ghost"
                            onClick={() => void handleJoinClass(item.class_id)}
                            disabled={!item.can_request || busyTaskId === `class-${item.class_id}`}
                          >
                            {item.can_request ? "Подать заявку" : "Ожидание / уже в классе"}
                          </button>
                        </td>
                      </tr>
                    ))}
                    {!classInvites.length && (
                      <tr>
                        <td colSpan={5}>Пока приглашений в классы нет.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel feed-panel fade-up" style={{ animationDelay: "0.35s" }}>
              <h2>Цели от родителей</h2>
              <div className="summary-list">
                {parentGoals.map((goal) => (
                  <article key={goal.id} className="summary-card">
                    <p>
                      <strong>{goal.title}</strong>
                    </p>
                    <p>Поощрение: {goal.reward}</p>
                    <p>Статус: {goal.status === "completed" ? "Выполнена" : "Активна"}</p>
                  </article>
                ))}
                {!parentGoals.length && <p>Пока родительские цели не добавлены.</p>}
              </div>

              <form onSubmit={handleAddGoalEvidence} className="stack-form" style={{ marginTop: "0.8rem" }}>
                <select value={goalTargetId} onChange={(event) => setGoalTargetId(event.target.value)}>
                  <option value="">Выберите цель</option>
                  {parentGoals.map((goal) => (
                    <option key={goal.id} value={goal.id}>
                      {goal.title}
                    </option>
                  ))}
                </select>
                <textarea
                  placeholder="Комментарий к подтверждению"
                  value={goalEvidenceComment}
                  onChange={(event) => setGoalEvidenceComment(event.target.value)}
                />
                <input
                  type="file"
                  accept="image/*,application/pdf,text/plain"
                  onChange={(event) => setGoalEvidenceFile(event.target.files?.[0] ?? null)}
                />
                <button className="button secondary" disabled={busyTaskId === `goal-${goalTargetId}`}>
                  Отправить подтверждение
                </button>
              </form>
            </section>
          </>
        )}
      </div>

      {submissionTask && (
        <div
          className="confirm-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="submission-title"
          onClick={(event) => {
            if (event.target === event.currentTarget && !busyTaskId?.startsWith("submit-")) {
              setSubmissionTask(null);
            }
          }}
        >
          <section className="confirm-dialog">
            <h3 id="submission-title">Сдать решение: {submissionTask.title}</h3>
            <div className="summary-list" style={{ marginBottom: "0.65rem" }}>
              <p>
                <strong>Уже загруженные материалы</strong>
              </p>
              {submissionHistoryLoading && <p>Загружаем материалы...</p>}
              {!submissionHistoryLoading && !submissionHistory.length && <p>Пока ничего не прикреплено.</p>}
              {!submissionHistoryLoading &&
                submissionHistory.map((submission) => (
                  <article key={submission.id} className="summary-card">
                    <p>
                      <strong>{formatDateTime(submission.created_at)}</strong>
                    </p>
                    {submission.text_answer && <p>Текст: {submission.text_answer}</p>}
                    {submission.voice_transcript && <p>Голосовой текст: {submission.voice_transcript}</p>}
                    {!!submission.attachments.length && (
                      <div className="summary-list">
                        {submission.attachments.map((attachment) => (
                          <button
                            key={attachment.id}
                            type="button"
                            className="button ghost"
                            onClick={() => void handleDownloadFile(getAttachmentUrl(attachment.id), attachment.file_name)}
                          >
                            Скачать: {attachment.file_name}
                          </button>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
            </div>
            <form onSubmit={handleSubmitSolution} className="stack-form">
              <textarea
                placeholder="Текст решения"
                value={submissionText}
                onChange={(event) => setSubmissionText(event.target.value)}
              />
              <textarea
                placeholder="Голосовой текст (если продиктовали)"
                value={submissionVoiceText}
                onChange={(event) => setSubmissionVoiceText(event.target.value)}
              />
              <div className="inline-actions">
                <button
                  type="button"
                  className="button ghost"
                  onClick={() => startVoiceCapture("submission")}
                  disabled={voiceListening}
                >
                  {voiceListening ? "Слушаю..." : "Озвучить решение"}
                </button>
              </div>
              <input
                type="file"
                multiple
                accept="image/*,audio/*,application/pdf,text/plain"
                onChange={(event) => setSubmissionFiles(Array.from(event.target.files ?? []))}
              />
              <div className="confirm-actions">
                <button
                  type="button"
                  className="button ghost"
                  onClick={() => setSubmissionTask(null)}
                  disabled={busyTaskId?.startsWith("submit-")}
                >
                  Отмена
                </button>
                <button type="submit" className="button secondary" disabled={busyTaskId?.startsWith("submit-")}>
                  {busyTaskId?.startsWith("submit-") ? "Отправляем..." : "Отправить решение"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {deleteTarget && (
        <div
          className="confirm-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-delete-title"
          onClick={(event) => {
            if (event.target === event.currentTarget && !busyTaskId?.startsWith("delete-")) {
              setDeleteTarget(null);
            }
          }}
        >
          <section className="confirm-dialog">
            <h3 id="confirm-delete-title">Точно удалить выполненное задание?</h3>
            <p>
              Задание <strong>«{deleteTarget.title}»</strong> будет удалено без возможности восстановления.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="button ghost"
                onClick={() => setDeleteTarget(null)}
                disabled={busyTaskId?.startsWith("delete-")}
              >
                Отмена
              </button>
              <button
                type="button"
                className="button danger"
                onClick={() => void handleDeleteDoneTask()}
                disabled={busyTaskId?.startsWith("delete-")}
              >
                {busyTaskId?.startsWith("delete-") ? "Удаляем..." : "Удалить"}
              </button>
            </div>
          </section>
        </div>
      )}

      {reviewsTask && (
        <div
          className="confirm-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reviews-title"
          onClick={(event) => {
            if (event.target === event.currentTarget && !reviewsLoading) {
              setReviewsTask(null);
            }
          }}
        >
          <section className="confirm-dialog">
            <h3 id="reviews-title">Комментарий учителя: {reviewsTask.title}</h3>
            {reviewsLoading && <p>Загружаем комментарии...</p>}
            {!reviewsLoading && !taskReviews.length && <p>Пока комментариев нет.</p>}
            {!reviewsLoading && !!taskReviews.length && (
              <div className="reviews-list">
                {taskReviews.map((review) => (
                  <article key={review.id} className="review-item">
                    <p>
                      <strong>{review.teacher_name}</strong> ({review.teacher_email})
                    </p>
                    <p>
                      Оценка: <strong>{review.score} / 5</strong>
                    </p>
                    <p>{review.comment}</p>
                    <p className="review-date">{formatDateTime(review.created_at)}</p>
                  </article>
                ))}
              </div>
            )}
            <div className="confirm-actions">
              <button type="button" className="button ghost" onClick={() => setReviewsTask(null)} disabled={reviewsLoading}>
                Закрыть
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
