"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, errorMessage } from "../../lib/api";
export default function VerifyPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") ?? ""); }, []);
  async function confirm(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api<unknown>("/auth/email-verification/confirm", { method: "POST", body: JSON.stringify({ token: token.trim() }) }); setDone(true); setToken(""); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell"><a className="brand" href="/">↗ наставник</a><section className="auth-card"><h1>Подтверждение email</h1>{error && <p className="form-error" role="alert">{error}</p>}{done ? <p role="status">Email подтверждён. <a href="/account">Открыть аккаунт</a></p> : <form onSubmit={confirm}><label>Токен подтверждения<input value={token} onChange={(event) => setToken(event.target.value)} required maxLength={2000} autoComplete="off" disabled={busy} /></label><button className="form-button" disabled={busy || !token.trim()}>{busy ? "Подтверждаем…" : "Подтвердить email"}</button></form>}</section></main>;
}
