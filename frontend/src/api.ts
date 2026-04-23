import type {
  Analytics,
  AssistantResponse,
  Assignment,
  AssignmentAttachmentsUploadResult,
  ClassInviteStatusRow,
  ClassJoinRequest,
  HelpRequest,
  LinkedStudent,
  ParentFeed,
  ParentGoal,
  ParentGoalEvidence,
  PlanResponse,
  Progress,
  PublicSchoolClass,
  ReminderRunResult,
  SchoolClass,
  SessionData,
  StudentClassInvite,
  StudentContacts,
  Task,
  TaskStatus,
  TaskSubmission,
  TeacherReview,
  TeacherReviewDetails,
  TeacherReviewSuggestion,
  Role,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type RequestOptions = RequestInit & { token?: string; retries?: number; timeoutMs?: number };

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  const isFormData = options.body instanceof FormData;
  if (!isFormData) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const retries = options.retries ?? 0;
  const timeoutMs = options.timeoutMs ?? 18000;
  let response: Response | null = null;
  let lastFetchError: unknown = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      break;
    } catch (error) {
      window.clearTimeout(timeout);
      lastFetchError = error;
      if (attempt < retries) {
        await sleep(350 * (attempt + 1));
        continue;
      }
    }
  }

  if (!response) {
    if (lastFetchError instanceof DOMException && lastFetchError.name === "AbortError") {
      throw new Error("Сервер отвечает слишком долго. Повторите запрос.");
    }
    if (lastFetchError instanceof Error) {
      throw new Error(lastFetchError.message);
    }
    throw new Error("Не удалось выполнить сетевой запрос.");
  }

  if (!response.ok) {
    let details = `HTTP ${response.status}`;
    try {
      const raw = await response.text();
      if (raw) {
        try {
          const body = JSON.parse(raw) as { detail?: unknown };
          if (typeof body?.detail === "string") {
            details = body.detail;
          } else if (Array.isArray(body?.detail)) {
            details = body.detail
              .map((item: { msg?: string }) => item?.msg)
              .filter((item: string | undefined): item is string => Boolean(item))
              .join("; ");
          } else if (body?.detail) {
            details = JSON.stringify(body.detail);
          } else {
            details = raw;
          }
        } catch {
          details = raw;
        }
      }
    } catch {
      details = `HTTP ${response.status}`;
    }
    throw new Error(details);
  }

  return (await response.json()) as T;
}

export function register(payload: {
  email: string;
  password: string;
  full_name: string;
  role: Role;
  class_request_ids?: string[];
}) {
  return request<SessionData>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: { email: string; password: string }) {
  return request<SessionData>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function assistantChat(token: string, payload: { message: string; screen?: string }) {
  return request<AssistantResponse>("/assistant/chat", {
    method: "POST",
    token,
    retries: 0,
    timeoutMs: 120000,
    body: JSON.stringify(payload),
  });
}

export function linkStudentTeacher(token: string, payload: { student_email: string; teacher_email: string }) {
  return request<{ status: string }>("/links/student-teacher", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function linkStudentParent(token: string, payload: { student_email: string; parent_email: string }) {
  return request<{ status: string }>("/links/student-parent", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function unlinkStudentTeacher(token: string, payload: { student_email: string; teacher_email: string }) {
  return request<{ status: string }>("/links/student-teacher", {
    method: "DELETE",
    token,
    body: JSON.stringify(payload),
  });
}

export function unlinkStudentParent(token: string, payload: { student_email: string; parent_email: string }) {
  return request<{ status: string }>("/links/student-parent", {
    method: "DELETE",
    token,
    body: JSON.stringify(payload),
  });
}

export function listStudentTasks(studentId: string, token: string, options?: { sort?: string; include_source?: boolean }) {
  const query = new URLSearchParams();
  if (options?.sort) query.set("sort", options.sort);
  if (typeof options?.include_source === "boolean") query.set("include_source", String(options.include_source));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Task[]>(`/students/${studentId}/tasks${suffix}`, { token });
}

export function getStudentContacts(token: string, studentId: string) {
  return request<StudentContacts>(`/students/${studentId}/contacts`, { token });
}

export function deleteTask(token: string, taskId: string) {
  return request<{ status: string }>(`/tasks/${taskId}`, {
    method: "DELETE",
    token,
  });
}

export function createTask(
  token: string,
  payload: {
    student_id: string;
    title: string;
    description?: string;
    subject?: string;
    due_at?: string | null;
    priority: "low" | "medium" | "high";
  },
) {
  return request<Task>("/tasks", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function extractTask(token: string, studentId: string, text: string) {
  return request<Task>("/tasks/extract", {
    method: "POST",
    token,
    body: JSON.stringify({ student_id: studentId, text }),
  });
}

export function extractTaskPhoto(token: string, studentId: string, photo: File) {
  const form = new FormData();
  form.append("student_id", studentId);
  form.append("photo", photo);
  return request<Task>("/tasks/extract/photo", {
    method: "POST",
    token,
    body: form,
  });
}

export function updateTaskStatus(token: string, taskId: string, status: TaskStatus) {
  return request<Task>(`/tasks/${taskId}/status`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ status }),
  });
}

export function planTask(token: string, taskId: string, adaptive = true) {
  return request<PlanResponse>(`/tasks/${taskId}/plan`, {
    method: "POST",
    token,
    body: JSON.stringify({ adaptive }),
  });
}

export function createTaskSubmission(
  token: string,
  taskId: string,
  payload: { text_answer?: string; voice_transcript?: string; files?: File[] },
) {
  const form = new FormData();
  if (payload.text_answer) form.append("text_answer", payload.text_answer);
  if (payload.voice_transcript) form.append("voice_transcript", payload.voice_transcript);
  for (const file of payload.files ?? []) {
    form.append("files", file);
  }
  return request<TaskSubmission>(`/tasks/${taskId}/submissions`, {
    method: "POST",
    token,
    body: form,
  });
}

export function listTaskSubmissions(token: string, taskId: string) {
  return request<TaskSubmission[]>(`/tasks/${taskId}/submissions`, { token });
}

export function getAttachmentUrl(attachmentId: string) {
  return `${API_BASE}/files/attachments/${attachmentId}`;
}

export function getTaskAttachmentUrl(attachmentId: string) {
  return `${API_BASE}/files/task-attachments/${attachmentId}`;
}

export function runReminders(token: string, studentId?: string) {
  return request<ReminderRunResult>("/reminders/run", {
    method: "POST",
    token,
    body: JSON.stringify({ student_id: studentId ?? null }),
  });
}

export function getProgress(token: string, studentId: string) {
  return request<Progress>(`/students/${studentId}/progress`, { token });
}

export function getAnalytics(token: string, studentId: string) {
  return request<Analytics>(`/students/${studentId}/analytics`, { token });
}

export function createTeacherReview(token: string, payload: { task_id: string; score: number; comment: string }) {
  return request<TeacherReview>("/teacher/reviews", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function suggestTeacherReview(token: string, payload: { task_id: string; submission_id?: string }) {
  return request<TeacherReviewSuggestion>("/teacher/reviews/suggest", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listTaskReviews(token: string, taskId: string) {
  return request<TeacherReviewDetails[]>(`/tasks/${taskId}/reviews`, { token });
}

export function listTeacherStudents(token: string, teacherId: string) {
  return request<LinkedStudent[]>(`/teachers/${teacherId}/students`, { token });
}

export function createAssignment(
  token: string,
  payload: {
    target_class_id?: string;
    target_student_id?: string;
    title: string;
    description?: string;
    subject?: string;
    due_at?: string | null;
    priority: "low" | "medium" | "high";
  },
) {
  return request<Assignment>("/assignments", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function uploadAssignmentAttachments(token: string, assignmentId: string, files: File[]) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  return request<AssignmentAttachmentsUploadResult>(`/assignments/${assignmentId}/attachments`, {
    method: "POST",
    token,
    body: form,
  });
}

export function createSchoolClass(
  token: string,
  payload: { title: string; grade?: string; approval_mode: "auto" | "manual" },
) {
  return request<SchoolClass>("/classes", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listTeacherClasses(token: string) {
  return request<SchoolClass[]>("/teacher/classes", { token });
}

export function listPublicClasses(token: string) {
  return request<PublicSchoolClass[]>("/classes/public", { token });
}

export function listOpenClasses() {
  return request<PublicSchoolClass[]>("/classes/open");
}

export function addClassInvite(token: string, classId: string, studentEmail: string) {
  return request<ClassInvite>(`/classes/${classId}/invites`, {
    method: "POST",
    token,
    body: JSON.stringify({ student_email: studentEmail }),
  });
}

export function addClassMember(token: string, classId: string, studentEmail: string) {
  return request<ClassInviteStatusRow>(`/classes/${classId}/members`, {
    method: "POST",
    token,
    body: JSON.stringify({ student_email: studentEmail }),
  });
}

export interface ClassInvite {
  id: string;
  class_id: string;
  student_email: string;
  created_at: string;
}

export function createClassJoinRequest(token: string, classId: string, message?: string) {
  return request<ClassJoinRequest>(`/classes/${classId}/requests`, {
    method: "POST",
    token,
    body: JSON.stringify({ message }),
  });
}

export function listClassInvites(token: string, classId: string) {
  return request<ClassInviteStatusRow[]>(`/classes/${classId}/invites`, { token });
}

export function removeClassInvite(token: string, classId: string, inviteId: string) {
  return request<{ status: string }>(`/classes/${classId}/invites/${inviteId}`, {
    method: "DELETE",
    token,
  });
}

export function deleteSchoolClass(token: string, classId: string) {
  return request<{ status: string }>(`/classes/${classId}`, {
    method: "DELETE",
    token,
  });
}

export function listMyClassInvites(token: string) {
  return request<StudentClassInvite[]>("/classes/my-invites", { token });
}

export function listClassJoinRequests(
  token: string,
  classId: string,
  status?: "pending" | "approved" | "rejected",
) {
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ClassJoinRequest[]>(`/classes/${classId}/requests${suffix}`, { token });
}

export function decideClassJoinRequest(
  token: string,
  classId: string,
  requestId: string,
  status: "approved" | "rejected",
) {
  return request<ClassJoinRequest>(`/classes/${classId}/requests/${requestId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ status }),
  });
}

export function createHelpRequest(token: string, payload: { task_id: string; question: string }) {
  return request<HelpRequest>("/help-requests", {
    method: "POST",
    token,
    body: JSON.stringify({ create: payload }),
  });
}

export function answerHelpRequest(token: string, payload: { help_request_id: string; answer: string }) {
  return request<HelpRequest>("/help-requests", {
    method: "POST",
    token,
    body: JSON.stringify({ answer: payload }),
  });
}

export function listHelpRequests(
  token: string,
  params: { student_id?: string; teacher_id?: string; status?: "open" | "answered" } = {},
) {
  const query = new URLSearchParams();
  if (params.student_id) query.set("student_id", params.student_id);
  if (params.teacher_id) query.set("teacher_id", params.teacher_id);
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<HelpRequest[]>(`/help-requests${suffix}`, { token });
}

export function getParentFeed(token: string, parentId: string) {
  return request<ParentFeed>(`/parents/${parentId}/feed`, { token });
}

export function createParentGoal(token: string, payload: { student_email: string; title: string; reward: string }) {
  return request<ParentGoal>("/parent/goals", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listParentGoals(token: string, params: { parent_id?: string; student_id?: string } = {}) {
  const query = new URLSearchParams();
  if (params.parent_id) query.set("parent_id", params.parent_id);
  if (params.student_id) query.set("student_id", params.student_id);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ParentGoal[]>(`/parent/goals${suffix}`, { token });
}

export function addParentGoalEvidence(
  token: string,
  goalId: string,
  payload: { task_submission_id?: string; comment?: string; files?: File[] },
) {
  const form = new FormData();
  if (payload.task_submission_id) form.append("task_submission_id", payload.task_submission_id);
  if (payload.comment) form.append("comment", payload.comment);
  for (const file of payload.files ?? []) {
    form.append("files", file);
  }
  return request<ParentGoalEvidence>(`/parent/goals/${goalId}/evidence`, {
    method: "POST",
    token,
    body: form,
  });
}

export function updateParentGoalStatus(token: string, goalId: string, status: "active" | "completed") {
  return request<ParentGoal>(`/parent/goals/${goalId}/status`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ status }),
  });
}
