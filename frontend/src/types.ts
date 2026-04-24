export type Role = "student" | "teacher" | "parent";

export interface User {
  id: string;
  role: Role;
  full_name: string;
  email: string;
}

export interface LoginContext {
  student_ids: string[];
  teacher_ids: string[];
  parent_ids: string[];
  class_ids: string[];
}

export interface SessionData {
  access_token: string;
  user: User;
  context: LoginContext;
}

export interface LinkedStudent {
  id: string;
  full_name: string;
  email: string;
}

export interface LinkedUser {
  id: string;
  full_name: string;
  email: string;
}

export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";
export type TaskUrgency = "blue" | "orange" | "red";
export type TaskOrigin = "student" | "teacher" | "parent";

export interface TaskStep {
  id: string;
  task_id: string;
  title: string;
  order_index: number;
  is_done: boolean;
}

export interface TaskAttachment {
  id: string;
  task_id: string;
  file_name: string;
  file_path: string;
  mime_type?: string | null;
  size_bytes: number;
  created_at: string;
}

export interface Task {
  id: string;
  student_id: string;
  created_by_id: string;
  title: string;
  description?: string | null;
  subject?: string | null;
  priority: TaskPriority;
  source: string;
  status: TaskStatus;
  due_at?: string | null;
  planned_at?: string | null;
  recommended_interval_hours: number;
  missed_reminders: number;
  assigned_by_role?: Role | null;
  assigned_by_user_id?: string | null;
  assignment_id?: string | null;
  origin: TaskOrigin;
  educational_validated: boolean;
  educational_reason?: string | null;
  urgency_color: TaskUrgency;
  created_at: string;
  completed_at?: string | null;
  attachments: TaskAttachment[];
  steps: TaskStep[];
}

export interface PlanResponse {
  task_id: string;
  planned_at?: string | null;
  interval_hours: number;
  steps: TaskStep[];
  provider: string;
}

export interface Progress {
  student_id: string;
  student_name?: string | null;
  total_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  completion_rate: number;
  points_total: number;
  active_goal?: string | null;
  goal_progress_rate: number;
}

export interface Analytics {
  student_id: string;
  hard_topics: string[];
  recommendations: string[];
  upcoming_high_priority: number;
}

export interface ReminderRunResult {
  processed_tasks: number;
  reminders_sent: number;
  escalations_sent: number;
}

export interface TeacherReview {
  id: string;
  task_id: string;
  teacher_id: string;
  score: number;
  comment: string;
  created_at: string;
}

export interface TeacherReviewDetails {
  id: string;
  task_id: string;
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  score: number;
  comment: string;
  created_at: string;
}

export interface TeacherReviewSuggestion {
  id: string;
  task_id: string;
  teacher_id: string;
  submission_id?: string | null;
  suggested_score: number;
  summary: string;
  issues: string[];
  recommendation: string;
  provider: string;
  created_at: string;
}

export interface HelpRequest {
  id: string;
  task_id: string;
  student_id: string;
  teacher_id: string;
  question: string;
  status: "open" | "answered";
  answer?: string | null;
  created_at: string;
  answered_at?: string | null;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  task_id?: string | null;
  type: string;
  message: string;
  created_at: string;
  is_read: boolean;
}

export interface ParentFeed {
  parent_id: string;
  student_summaries: Progress[];
  notifications: NotificationItem[];
}

export interface StudentContacts {
  student_id: string;
  teachers: LinkedUser[];
  parents: LinkedUser[];
}

export interface AssistantResponse {
  reply: string;
  suggested_actions: string[];
  provider: string;
}

export interface SchoolClass {
  id: string;
  teacher_id: string;
  title: string;
  grade?: string | null;
  approval_mode: "auto" | "manual";
  is_active: boolean;
  created_at: string;
  member_count: number;
  pending_requests_count: number;
}

export interface PublicSchoolClass {
  id: string;
  title: string;
  grade?: string | null;
  approval_mode: "auto" | "manual";
  teacher_name: string;
  is_invited: boolean;
}

export interface ClassJoinRequest {
  id: string;
  class_id: string;
  student_id: string;
  student_email: string;
  status: "pending" | "approved" | "rejected";
  message?: string | null;
  decided_by_user_id?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export type ClassInviteStatus = "invited" | "pending" | "approved" | "member" | "rejected";

export interface ClassInviteStatusRow {
  id: string;
  class_id: string;
  student_email: string;
  student_id?: string | null;
  student_full_name?: string | null;
  status: ClassInviteStatus;
  is_member: boolean;
  invite_created_at: string;
  request_id?: string | null;
  request_created_at?: string | null;
  request_decided_at?: string | null;
}

export interface StudentClassInvite {
  id: string;
  class_id: string;
  class_title: string;
  grade?: string | null;
  teacher_name: string;
  approval_mode: "auto" | "manual";
  invited_at: string;
  request_status: "none" | "pending" | "approved" | "rejected";
  is_member: boolean;
  can_request: boolean;
}

export interface Assignment {
  id: string;
  teacher_id: string;
  class_id?: string | null;
  target_student_id?: string | null;
  title: string;
  description?: string | null;
  subject?: string | null;
  due_at?: string | null;
  priority: TaskPriority;
  created_at: string;
  created_tasks: number;
}

export interface AssignmentAttachmentsUploadResult {
  status: string;
  assignment_id: string;
  attached_files: number;
}

export interface SubmissionAttachment {
  id: string;
  submission_id: string;
  file_name: string;
  file_path: string;
  mime_type?: string | null;
  size_bytes: number;
  created_at: string;
}

export interface TaskSubmission {
  id: string;
  task_id: string;
  student_id: string;
  text_answer?: string | null;
  voice_transcript?: string | null;
  created_at: string;
  attachments: SubmissionAttachment[];
}

export interface ParentGoal {
  id: string;
  parent_id: string;
  student_id: string;
  title: string;
  reward: string;
  status: "active" | "completed";
  created_at: string;
  completed_at?: string | null;
}

export interface ParentGoalEvidence {
  id: string;
  parent_goal_id: string;
  student_id: string;
  task_submission_id?: string | null;
  comment?: string | null;
  attachment_path?: string | null;
  created_at: string;
}
