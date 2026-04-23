import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  createParentGoal,
  getParentFeed,
  linkStudentParent,
  listParentGoals,
  updateParentGoalStatus,
} from "../api";
import { formatDateTime } from "../date";
import { ToastViewport } from "./ToastViewport";
import type { ParentFeed, ParentGoal, SessionData } from "../types";

interface ParentDashboardProps {
  session: SessionData;
}

export function ParentDashboard({ session }: ParentDashboardProps) {
  const [feed, setFeed] = useState<ParentFeed | null>(null);
  const [goals, setGoals] = useState<ParentGoal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [studentEmail, setStudentEmail] = useState("");
  const [goalStudentEmail, setGoalStudentEmail] = useState("");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalReward, setGoalReward] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [feedData, goalsData] = await Promise.all([
        getParentFeed(session.access_token, session.user.id),
        listParentGoals(session.access_token, { parent_id: session.user.id }),
      ]);
      setFeed(feedData);
      setGoals(goalsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить данные родителя");
    }
  }, [session.access_token, session.user.id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!info && !error) return;
    const timer = window.setTimeout(() => {
      setInfo(null);
      setError(null);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [info, error]);

  async function handleLinkStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!studentEmail.trim()) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await linkStudentParent(session.access_token, {
        student_email: studentEmail.trim().toLowerCase(),
        parent_email: session.user.email,
      });
      setStudentEmail("");
      setInfo("Ученик успешно подключен.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось подключить ученика");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goalStudentEmail.trim() || !goalTitle.trim() || !goalReward.trim()) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await createParentGoal(session.access_token, {
        student_email: goalStudentEmail.trim().toLowerCase(),
        title: goalTitle.trim(),
        reward: goalReward.trim(),
      });
      setGoalTitle("");
      setGoalReward("");
      setInfo("Цель создана и отправлена ученику.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать цель");
    } finally {
      setBusy(false);
    }
  }

  async function handleGoalComplete(goalId: string) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await updateParentGoalStatus(session.access_token, goalId, "completed");
      setInfo("Цель отмечена выполненной.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить статус цели");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ToastViewport
        items={[
          ...(error ? [{ id: "parent-error", kind: "error" as const, text: error }] : []),
          ...(info ? [{ id: "parent-info", kind: "success" as const, text: info }] : []),
        ]}
        onClose={(id) => {
          if (id === "parent-error") setError(null);
          if (id === "parent-info") setInfo(null);
        }}
      />

      <div className="dashboard-grid parent-layout">
        <section className="panel guide-panel fade-up full-width">
        <h2>Маршрут родителя</h2>
        <ol className="guide-list">
          <li>Подключите ученика по email.</li>
          <li>Создайте цель и поощрение.</li>
          <li>После подтверждения от ученика отметьте цель выполненной.</li>
          <li>Контролируйте сигналы по дедлайнам и просрочкам.</li>
        </ol>
        </section>

        <section className="panel metrics-panel fade-up">
        <h2>Подключить ученика</h2>
        <form onSubmit={handleLinkStudent} className="stack-form">
          <input
            type="email"
            placeholder="student@example.com"
            value={studentEmail}
            onChange={(event) => setStudentEmail(event.target.value)}
          />
          <button className="button ghost" disabled={busy}>
            Подключить
          </button>
        </form>

        <hr />

        <h2>Цели и поощрения</h2>
        <form onSubmit={handleCreateGoal} className="stack-form">
          <input
            type="email"
            placeholder="Почта ученика"
            value={goalStudentEmail}
            onChange={(event) => setGoalStudentEmail(event.target.value)}
          />
          <input
            placeholder="Цель (например, закрыть неделю без просрочек)"
            value={goalTitle}
            onChange={(event) => setGoalTitle(event.target.value)}
          />
          <input
            placeholder="Поощрение (например, 100 рублей)"
            value={goalReward}
            onChange={(event) => setGoalReward(event.target.value)}
          />
          <button className="button secondary" disabled={busy}>
            Создать цель
          </button>
        </form>

        <div className="summary-list" style={{ marginTop: "0.65rem" }}>
          {goals.map((goal) => (
            <article key={goal.id} className="summary-card">
              <p>
                <strong>{goal.title}</strong>
              </p>
              <p>Поощрение: {goal.reward}</p>
              <p>Статус: {goal.status === "completed" ? "Выполнена" : "Активна"}</p>
              <div className="card-actions">
                <button
                  type="button"
                  className="button ghost"
                  onClick={() => void handleGoalComplete(goal.id)}
                  disabled={busy || goal.status === "completed"}
                >
                  Отметить выполненной
                </button>
              </div>
            </article>
          ))}
          {!goals.length && <p>Пока нет целей.</p>}
        </div>
        </section>

        <section className="panel feed-panel fade-up" style={{ animationDelay: "0.1s" }}>
        <h2>Прогресс и сигналы</h2>
        <div className="summary-list">
          {(feed?.student_summaries ?? []).map((summary) => (
            <article key={summary.student_id} className="summary-card">
              <p>
                <strong>Ученик:</strong> {summary.student_id.slice(0, 8)}...
              </p>
              <p>
                Выполнено {summary.completed_tasks} из {summary.total_tasks}
              </p>
              <p>Баллы: {summary.points_total}</p>
              <p>Просрочки: {summary.overdue_tasks}</p>
              <div className="progress-bar">
                <div style={{ width: `${Math.min(summary.completion_rate, 100)}%` }} />
              </div>
            </article>
          ))}
          {!feed?.student_summaries.length && <p>Пока данных о прогрессе нет.</p>}
        </div>

        <hr />

        <ul className="notification-feed">
          {(feed?.notifications ?? []).map((item) => (
            <li key={item.id}>
              <p>{item.message}</p>
              <span>{formatDateTime(item.created_at)}</span>
            </li>
          ))}
          {!feed?.notifications.length && <p>Новых уведомлений нет.</p>}
        </ul>
        </section>
      </div>
    </>
  );
}
