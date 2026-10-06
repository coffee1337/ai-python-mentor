"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  AuthResponse,
  clearLocalDrafts,
  errorMessage,
} from "../lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function changeMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setError("");
    setFields({});
    setPassword("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setFields({});
    try {
      const result = await api<AuthResponse>("/auth/" + mode, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      clearLocalDrafts();
      router.push(result.onboarding_required ? "/onboarding" : "/dashboard");
    } catch (reason) {
      setError(errorMessage(reason));
      if (reason instanceof ApiError) setFields(reason.fieldErrors);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="entry-shell auth-entry">
      <header className="entry-header">
        <a className="brand" href="/">
          наставник<span className="brand-dot">.</span>
        </a>
        <a href="/">О курсе</a>
      </header>
      <div className="entry-split">
        <section
          className="auth-introduction"
          aria-labelledby="auth-course-heading"
        >
          <span className="page-kicker">Ваш первый шаг в программирование</span>
          <h1 id="auth-course-heading" className="page-heading">
            От первой строки кода
            <br />к серверным приложениям
          </h1>
          <p className="page-subtitle">
            Учитесь Python в понятном порядке: объяснение, пример, небольшая
            практика. Начать можно с нуля.
          </p>
          <div className="auth-course-preview panel">
            <div className="auth-preview-heading">
              <span className="badge">Python → Backend</span>
              <span className="muted">Путь обучения</span>
            </div>
            <ol className="entry-course-steps">
              <li>
                <span>1</span>
                <div>
                  <strong>Основы без спешки</strong>
                  <p>
                    Поймёте, что делает код, прежде чем отвечать на вопросы.
                  </p>
                </div>
              </li>
              <li>
                <span>2</span>
                <div>
                  <strong>Практика по шагам</strong>
                  <p>Разберёте примеры и научитесь решать небольшие задачи.</p>
                </div>
              </li>
              <li>
                <span>3</span>
                <div>
                  <strong>Серверная разработка</strong>
                  <p>Перейдёте к API, базам данных и устройству Backend.</p>
                </div>
              </li>
            </ol>
          </div>
          <div className="auth-mentor-note">
            <span aria-hidden="true">✦</span>
            <p>
              <strong>AI-наставник рядом</strong>
              <br />
              Можно попросить объяснить термин проще или разобрать конкретную
              ошибку. Ваш прогресс подтверждают результаты заданий.
            </p>
          </div>
        </section>
        <section
          className="panel auth-form-panel"
          aria-labelledby="auth-form-heading"
        >
          <div
            className="auth-mode-switch"
            role="group"
            aria-label="Вход или регистрация"
          >
            <button
              type="button"
              aria-pressed={mode === "register"}
              disabled={busy}
              onClick={() => changeMode("register")}
            >
              Регистрация
            </button>
            <button
              type="button"
              aria-pressed={mode === "login"}
              disabled={busy}
              onClick={() => changeMode("login")}
            >
              Вход
            </button>
          </div>
          <h2 id="auth-form-heading" className="panel-heading">
            {mode === "register" ? "Создайте аккаунт" : "С возвращением"}
          </h2>
          <p className="page-subtitle">
            {mode === "register"
              ? "Сохраним ваши уроки и настройки. После регистрации выберете свой темп."
              : "Продолжите с того места, где остановились."}
          </p>
          <form className="settings-form" onSubmit={submit}>
            <label htmlFor="auth-email">
              Email
              <input
                id="auth-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                maxLength={320}
                disabled={busy}
                autoComplete="email"
                placeholder="you@example.com"
                aria-invalid={!!fields.email}
                aria-describedby={fields.email ? "email-error" : undefined}
              />
            </label>
            {fields.email && (
              <p className="form-error" id="email-error">
                {fields.email}
              </p>
            )}
            <label htmlFor="auth-password">
              Пароль
              <input
                id="auth-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                maxLength={256}
                disabled={busy}
                autoComplete={
                  mode === "register" ? "new-password" : "current-password"
                }
                aria-invalid={!!fields.password}
                aria-describedby={
                  fields.password
                    ? "password-error"
                    : mode === "register"
                      ? "password-help"
                      : undefined
                }
              />
            </label>
            {fields.password ? (
              <p className="form-error" id="password-error">
                {fields.password}
              </p>
            ) : (
              mode === "register" && (
                <p className="field-help" id="password-help">
                  Не меньше 8 символов.
                </p>
              )
            )}
            {error && (
              <p className="status-message form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button auth-submit"
              type="submit"
              disabled={busy}
            >
              {busy
                ? "Подождите…"
                : mode === "register"
                  ? "Создать аккаунт"
                  : "Войти"}
              <span aria-hidden="true">→</span>
            </button>
          </form>
          <div className="auth-form-footer">
            {mode === "login" ? (
              <a href="/auth/reset">Забыли пароль?</a>
            ) : (
              <p>
                Уже зарегистрированы?{" "}
                <button
                  className="text-button"
                  type="button"
                  disabled={busy}
                  onClick={() => changeMode("login")}
                >
                  Войти
                </button>
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
