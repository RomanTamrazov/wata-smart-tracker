import { Link } from "react-router-dom";

export function LandingPage() {
  return (
    <div className="page landing">
      <header className="hero">
        <p className="badge">WATA Smart Tracker</p>
        <h1>Умный трекер учебного порядка</h1>
        <p>
          Цельный сервис для ученика, учителя и родителя: задачи, напоминания, прогресс,
          помощь, классы, OCR и ИИ-поддержка прямо в локальном контуре.
        </p>
        <div className="hero-actions">
          <Link to="/auth?mode=register" className="button primary">
            Зарегистрироваться
          </Link>
          <Link to="/auth?mode=login" className="button ghost">
            Уже есть аккаунт
          </Link>
        </div>
      </header>

      <section className="role-grid">
        <article className="role-card student-card fade-up" style={{ animationDelay: "0.05s" }}>
          <h2>Ученик</h2>
          <p>Управляй задачами, получай план выполнения, собирай баллы и держи прогресс под контролем.</p>
          <p className="hint">Шаги: создать задачу → построить ИИ-план → выполнить → получить баллы.</p>
        </article>

        <article className="role-card teacher-card fade-up" style={{ animationDelay: "0.15s" }}>
          <h2>Учитель</h2>
          <p>Проверяй результаты, отвечай на запросы помощи и давай точечную обратную связь.</p>
          <p className="hint">Подключи ученика по email и работай с его задачами в одном окне.</p>
        </article>

        <article className="role-card parent-card fade-up" style={{ animationDelay: "0.25s" }}>
          <h2>Родитель</h2>
          <p>Следи за прогрессом и получай сигналы по просрочкам и критичным задачам вовремя.</p>
          <p className="hint">Уведомления приходят в ленту и на email.</p>
        </article>
      </section>
    </div>
  );
}
