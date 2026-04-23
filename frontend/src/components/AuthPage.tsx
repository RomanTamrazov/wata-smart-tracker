import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { listOpenClasses, login, register } from "../api";
import type { PublicSchoolClass, Role, SessionData } from "../types";

interface AuthPageProps {
  onAuthed: (session: SessionData) => void;
}

const roleTitles: Record<Role, string> = {
  student: "Ученик",
  teacher: "Учитель",
  parent: "Родитель",
};

export function AuthPage({ onAuthed }: AuthPageProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const presetMode = searchParams.get("mode") === "register" ? "register" : "login";

  const [mode, setMode] = useState<"login" | "register">(presetMode);
  const [role, setRole] = useState<Role>("student");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [openClasses, setOpenClasses] = useState<PublicSchoolClass[]>([]);
  const [selectedClassIds, setSelectedClassIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const heading = useMemo(
    () => (mode === "register" ? "Создать аккаунт" : "Вход в аккаунт"),
    [mode],
  );

  function validateInputs(): string | null {
    const normalizedEmail = email.trim().toLowerCase();
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    if (!emailPattern.test(normalizedEmail)) {
      return "Введите корректный email.";
    }
    if (password.trim().length < 8) {
      return "Пароль должен содержать минимум 8 символов.";
    }
    if (mode === "register") {
      const normalizedFullName = fullName.trim().replace(/\s+/g, " ");
      const fullNamePattern = /^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,39}\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,39}(?:\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,39})?$/;
      if (!fullNamePattern.test(normalizedFullName)) {
        return "Укажите имя и фамилию буквами, например: Роман Тамразов.";
      }
    }
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const validationError = validateInputs();
    if (validationError) {
      setError(validationError);
      return;
    }
    setIsLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const normalizedName = fullName.trim().replace(/\s+/g, " ");
      const session =
        mode === "register"
          ? await register({
            email: normalizedEmail,
            password,
            full_name: normalizedName,
            role,
            class_request_ids: selectedClassIds,
          })
          : await login({ email: normalizedEmail, password });

      onAuthed(session);
      navigate(`/dashboard/${session.user.role}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка авторизации");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadOpenClasses() {
    try {
      const classes = await listOpenClasses();
      setOpenClasses(classes);
    } catch {
      setOpenClasses([]);
    }
  }

  useEffect(() => {
    if (mode === "register") {
      void loadOpenClasses();
    }
  }, [mode]);

  return (
    <div className="page login-page">
      <section className="auth-panel fade-up">
        <p className="badge">Безопасный вход</p>
        <h1>{heading}</h1>
        <p>
          Регистрируйтесь по email. Именно на эту почту будут приходить напоминания о задачах и
          сигналы о дедлайнах.
        </p>

        <div className="auth-mode-switch">
          <button
            type="button"
            className={`button ${mode === "login" ? "primary" : "ghost"}`}
            onClick={() => setMode("login")}
          >
            Вход
          </button>
          <button
            type="button"
            className={`button ${mode === "register" ? "secondary" : "ghost"}`}
            onClick={() => setMode("register")}
          >
            Регистрация
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "register" && (
            <label>
              Роль
              <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
                {(Object.keys(roleTitles) as Role[]).map((item) => (
                  <option key={item} value={item}>
                    {roleTitles[item]}
                  </option>
                ))}
              </select>
            </label>
          )}

          {mode === "register" && (
            <label>
              Имя и фамилия
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Например, Илья Петров"
                required
              />
            </label>
          )}

          {mode === "register" && !!openClasses.length && (
            <label>
              Классы (по желанию)
              <div className="class-select-list">
                {openClasses.map((item) => {
                  const checked = selectedClassIds.includes(item.id);
                  return (
                    <label key={item.id} className="class-select-item">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          if (event.target.checked) {
                            setSelectedClassIds((prev) => [...prev, item.id]);
                          } else {
                            setSelectedClassIds((prev) => prev.filter((id) => id !== item.id));
                          }
                        }}
                      />
                      <span>
                        {item.title} · {item.teacher_name} ({item.approval_mode === "auto" ? "авто" : "ручной"})
                      </span>
                    </label>
                  );
                })}
              </div>
            </label>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
            />
          </label>

          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Минимум 8 символов"
              minLength={8}
              required
            />
          </label>

          <button className="button primary" disabled={isLoading}>
            {isLoading ? "Подождите..." : mode === "register" ? "Создать аккаунт" : "Войти"}
          </button>
        </form>

        {error && <p className="error-text">{error}</p>}

        <div className="auth-links">
          <Link to="/">Вернуться на главную</Link>
        </div>
      </section>
    </div>
  );
}
