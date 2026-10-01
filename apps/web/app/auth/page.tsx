"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, AuthResponse } from "../lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<AuthResponse>("/auth/" + mode, { method: "POST", body: JSON.stringify({ email, password }) });
      router.push(result.onboarding_required ? "/onboarding" : "/dashboard");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось войти");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-shell"><a className="brand" href="/">↗ наставник<span className="brand-dot">.</span></a><section className="auth-card"><span className="eyebrow"><i /> ПЕРВЫЙ ШАГ</span><h1>{mode === "register" ? "Начните свой путь." : "С возвращением."}</h1><p className="auth-lead">{mode === "register" ? "Создайте аккаунт — затем настроим маршрут под вашу цель." : "Войдите, чтобы продолжить обучение."}</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></label><label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={mode === "register" ? "new-password" : "current-password"} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button form-button" disabled={busy}>{busy ? "Подождите…" : mode === "register" ? "Создать аккаунт" : "Войти"}<span>↗</span></button></form><button className="text-button" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); }}>{mode === "register" ? "Уже есть аккаунт? Войти" : "Нет аккаунта? Зарегистрироваться"}</button></section></main>;
}
