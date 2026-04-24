import { useMemo, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { AuthPage } from "./components/AuthPage";
import { AiAssistantWidget } from "./components/AiAssistantWidget";
import { LandingPage } from "./components/LandingPage";
import { ParentDashboard } from "./components/ParentDashboard";
import { StudentDashboard } from "./components/StudentDashboard";
import { TeacherDashboard } from "./components/TeacherDashboard";
import { roleLabel } from "./labels";
import type { Role, SessionData } from "./types";

const STORAGE_KEY = "wata_session";
const TELEGRAM_BOT_USERNAME = (import.meta.env.VITE_TELEGRAM_BOT_USERNAME ?? "").trim().replace(/^@/, "");
const TELEGRAM_BOT_URL = (
  import.meta.env.VITE_TELEGRAM_BOT_URL
  ?? (TELEGRAM_BOT_USERNAME ? `https://t.me/${TELEGRAM_BOT_USERNAME}` : "/api/v1/system/telegram")
).trim();

function readSession(): SessionData | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionData;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

function writeSession(session: SessionData | null) {
  if (!session) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

interface ShellProps {
  session: SessionData | null;
  onLogout: () => void;
  children: ReactNode;
}

function Shell({ session, onLogout, children }: ShellProps) {
  const location = useLocation();
  const showTopBar = location.pathname.startsWith("/dashboard");
  const screen = useMemo(() => {
    if (location.pathname.includes("student")) return "student-dashboard";
    if (location.pathname.includes("teacher")) return "teacher-dashboard";
    if (location.pathname.includes("parent")) return "parent-dashboard";
    return "landing";
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <div className="background-layer" />
      {showTopBar && session && (
        <header className="top-bar">
          <div>
            <p className="badge">{roleLabel(session.user.role)}</p>
            <h1>{session.user.full_name}</h1>
            <small>{session.user.email}</small>
          </div>
          <div className="top-bar-actions">
            <a className="button ghost" href={TELEGRAM_BOT_URL} target="_blank" rel="noreferrer">
              Telegram-бот
            </a>
            <button className="button ghost" onClick={onLogout}>
              Выйти
            </button>
          </div>
        </header>
      )}
      <main>{children}</main>
      {session && <AiAssistantWidget token={session.access_token} screen={screen} />}
    </div>
  );
}

function RoleGuard({ session, role, children }: { session: SessionData | null; role: Role; children: ReactNode }) {
  if (!session) return <Navigate to="/auth?mode=login" replace />;
  if (session.user.role !== role) return <Navigate to={`/dashboard/${session.user.role}`} replace />;
  return <>{children}</>;
}

export default function App() {
  const navigate = useNavigate();
  const [session, setSession] = useState<SessionData | null>(() => readSession());

  const activeRole = useMemo(() => session?.user.role ?? null, [session]);

  function handleAuthed(next: SessionData) {
    setSession(next);
    writeSession(next);
  }

  function handleLogout() {
    setSession(null);
    writeSession(null);
    navigate("/");
  }

  return (
    <Shell session={session} onLogout={handleLogout}>
      <Routes>
        <Route
          path="/"
          element={activeRole ? <Navigate to={`/dashboard/${activeRole}`} replace /> : <LandingPage />}
        />
        <Route path="/auth" element={<AuthPage onAuthed={handleAuthed} />} />

        <Route
          path="/dashboard/student"
          element={
            <RoleGuard session={session} role="student">
              <StudentDashboard session={session as SessionData} />
            </RoleGuard>
          }
        />
        <Route
          path="/dashboard/teacher"
          element={
            <RoleGuard session={session} role="teacher">
              <TeacherDashboard session={session as SessionData} />
            </RoleGuard>
          }
        />
        <Route
          path="/dashboard/parent"
          element={
            <RoleGuard session={session} role="parent">
              <ParentDashboard session={session as SessionData} />
            </RoleGuard>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
