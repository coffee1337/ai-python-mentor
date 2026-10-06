"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, clearLocalDrafts, errorMessage } from "../../lib/api";

export default function ResetPage() {
  const [token, setToken] = useState("");
  const [phase, setPhase] = useState<"request" | "confirm">("request");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(false);

  useEffect(() => {
    const linkToken =
      new URLSearchParams(window.location.search).get("token") ?? "";
    setToken(linkToken);
    if (linkToken) setPhase("confirm");
    setReady(true);
  }, []);

  async function request(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api<unknown>("/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email: data.get("email") }),
      });
      setStatus(
        "Если аккаунт с таким email существует и доставка настроена, вы получите ссылку для восстановления. Проверьте также папку «Спам».",
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api<unknown>("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({
          token: token.trim(),
          password: data.get("password"),
        }),
      });
      clearLocalDrafts();
      setReset(true);
      setToken("");
      window.history.replaceState(null, "", window.location.pathname);
      setStatus(
        "Пароль изменён. Войдите с новым паролем, чтобы продолжить обучение.",
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function switchPhase() {
    setPhase(phase === "request" ? "confirm" : "request");
    setError("");
    setStatus("");
  }

  return (
    <main className="entry-shell auth-entry">
      <header className="entry-header">
        <a className="brand" href="/">
          наставник<span className="brand-dot">.</span>
        </a>
        <a href="/auth">Вернуться ко входу</a>
      </header>
      <div className="entry-split recovery-layout">
        <section className="auth-introduction">
          <span className="page-kicker">Доступ к аккаунту</span>
          <h1 className="page-heading">Вернитесь к своим урокам</h1>
          <p className="page-subtitle">
            Восстановите пароль с помощью email, который указали при
            регистрации. Учебные результаты останутся в аккаунте.
          </p>
          <ol className="entry-course-steps recovery-steps">
            <li>
              <span>1</span>
              <div>
                <strong>Запросите ссылку</strong>
                <p>Проверьте почту и папку «Спам».</p>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <strong>Выберите новый пароль</strong>
                <p>Ссылка или токен подтверждают доступ к вашей почте.</p>
              </div>
            </li>
            <li>
              <span>3</span>
              <div>
                <strong>Войдите снова</strong>
                <p>После смены пароля прежние сессии завершаются.</p>
              </div>
            </li>
          </ol>
        </section>
        <section
          className="panel auth-form-panel"
          aria-label="Восстановление пароля"
        >
          <span className="badge">Восстановление доступа</span>
          <h2 className="panel-heading">
            {reset
              ? "Пароль обновлён"
              : phase === "request"
                ? "Забыли пароль?"
                : "Новый пароль"}
          </h2>
          {!reset && (
            <p className="page-subtitle">
              {phase === "request"
                ? "Укажите email аккаунта — отправим ссылку для восстановления, если доставка доступна."
                : "Используйте токен из ссылки восстановления и задайте новый пароль."}
            </p>
          )}
          {error && (
            <p className="status-message form-error" role="alert">
              {error}
            </p>
          )}
          {status && (
            <p className="status-message" role="status">
              {status}
            </p>
          )}
          {!ready ? (
            <p className="status-message" role="status">
              Подготавливаем форму…
            </p>
          ) : reset ? (
            <a className="button auth-submit" href="/auth">
              Войти с новым паролем
            </a>
          ) : phase === "request" ? (
            <form className="settings-form" onSubmit={request}>
              <label htmlFor="reset-email">
                Email аккаунта
                <input
                  id="reset-email"
                  name="email"
                  type="email"
                  required
                  maxLength={320}
                  autoComplete="email"
                  placeholder="you@example.com"
                  disabled={busy}
                />
              </label>
              <button
                className="button auth-submit"
                type="submit"
                disabled={busy}
              >
                {busy ? "Отправляем запрос…" : "Получить ссылку"}
              </button>
            </form>
          ) : (
            <form className="settings-form" onSubmit={confirm}>
              <label htmlFor="reset-token">
                Токен восстановления
                <input
                  id="reset-token"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  required
                  maxLength={2000}
                  autoComplete="off"
                  disabled={busy}
                  aria-describedby="reset-token-help"
                />
                <span id="reset-token-help" className="field-help">
                  При открытии ссылки из письма токен заполняется автоматически.
                </span>
              </label>
              <label htmlFor="reset-password">
                Новый пароль
                <input
                  id="reset-password"
                  name="password"
                  type="password"
                  required
                  minLength={8}
                  maxLength={256}
                  autoComplete="new-password"
                  disabled={busy}
                  aria-describedby="reset-password-help"
                />
                <span id="reset-password-help" className="field-help">
                  Не меньше 8 символов.
                </span>
              </label>
              <button
                className="button auth-submit"
                type="submit"
                disabled={busy || !token.trim()}
              >
                {busy ? "Сохраняем…" : "Сохранить новый пароль"}
              </button>
            </form>
          )}
          {!reset && ready && (
            <div className="auth-form-footer">
              <button
                className="text-button"
                type="button"
                disabled={busy}
                onClick={switchPhase}
              >
                {phase === "request"
                  ? "У меня уже есть ссылка или токен"
                  : "Запросить новую ссылку"}
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
