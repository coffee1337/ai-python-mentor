"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, errorMessage } from "../../lib/api";

export default function VerifyPage() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
    setReady(true);
  }, []);

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api<unknown>("/auth/email-verification/confirm", {
        method: "POST",
        body: JSON.stringify({ token: token.trim() }),
      });
      setDone(true);
      setToken("");
      window.history.replaceState(null, "", window.location.pathname);
    } catch (reason) {
      setError(errorMessage(reason));
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
        <a href="/account">Личный кабинет</a>
      </header>
      <div className="entry-split recovery-layout">
        <section className="auth-introduction">
          <span className="page-kicker">Ваш аккаунт</span>
          <h1 className="page-heading">Подтвердите свою почту</h1>
          <p className="page-subtitle">
            Так мы убедимся, что адрес принадлежит вам. Для подтверждения
            используйте ссылку из письма.
          </p>
          <div className="panel verification-help">
            <h2 className="panel-heading">Не получили письмо?</h2>
            <p>
              Проверьте папку «Спам». Если срок ссылки истёк, запросите новую в
              настройках аккаунта.
            </p>
            <a href="/account">Открыть настройки аккаунта →</a>
          </div>
        </section>
        <section
          className="panel auth-form-panel"
          aria-labelledby="verify-heading"
        >
          <span className="badge">Подтверждение email</span>
          <h2 id="verify-heading" className="panel-heading">
            {done ? "Почта подтверждена" : "Остался один шаг"}
          </h2>
          {error && (
            <p className="status-message form-error" role="alert">
              {error}
            </p>
          )}
          {!ready ? (
            <p className="status-message" role="status">
              Подготавливаем форму…
            </p>
          ) : done ? (
            <>
              <p className="status-message" role="status">
                Email подтверждён. Можно вернуться к обучению.
              </p>
              <a className="button auth-submit" href="/dashboard">
                Продолжить обучение
              </a>
            </>
          ) : (
            <>
              <p className="page-subtitle">
                При открытии ссылки из письма токен заполняется автоматически.
              </p>
              <form className="settings-form" onSubmit={confirm}>
                <label htmlFor="verify-token">
                  Токен подтверждения
                  <input
                    id="verify-token"
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    required
                    maxLength={2000}
                    autoComplete="off"
                    disabled={busy}
                  />
                </label>
                <button
                  className="button auth-submit"
                  type="submit"
                  disabled={busy || !token.trim()}
                >
                  {busy ? "Подтверждаем…" : "Подтвердить email"}
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
