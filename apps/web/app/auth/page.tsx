"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, AuthResponse, clearLocalDrafts, errorMessage } from "../lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setFields({});
    try {
      const result = await api<AuthResponse>("/auth/" + mode, { method: "POST", body: JSON.stringify({ email, password }) });
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
    <main className="auth-shell">
      <a className="brand" href="/">↗ наставник<span className="brand-dot">.</span></a>
      <section className="auth-card">
        <span className="eyebrow">ПЕРВЫЙ ШАГ</span>
        <h1>{mode === "register" ? "Начните свой путь." : "С возвращением."}</h1>
        <p className="auth-lead">{mode === "register" ? "Создайте аккаунт — затем настроим маршрут под вашу цель." : "Войдите, чтобы продолжить обучение."}</p>
        <form onSubmit={submit}>
          <label>Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={320} disabled={busy} autoComplete="email" aria-invalid={!!fields.email} aria-describedby={fields.email ? "email-error" : undefined} />
          </label>
          {fields.email && <p className="form-error" id="email-error">{fields.email}</p>}
          <label>Пароль
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} maxLength={256} disabled={busy} autoComplete={mode === "register" ? "new-password" : "current-password"} aria-invalid={!!fields.password} aria-describedby={fields.password ? "password-error" : undefined} />
          </label>
          {fields.password && <p className="form-error" id="password-error">{fields.password}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button form-button" disabled={busy}>{busy ? "Подождите…" : mode === "register" ? "Создать аккаунт" : "Войти"}<span aria-hidden="true">↗</span></button>
        </form>
        <button className="text-button" type="button" disabled={busy} onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); setFields({}); }}>
          {mode === "register" ? "Уже есть аккаунт? Войти" : "Нет аккаунта? Зарегистрироваться"}
        </button>
        <p><a href="/auth/reset">Забыли пароль?</a></p>
      </section>
    </main>
  );
}
