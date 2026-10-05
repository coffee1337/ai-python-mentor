"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, clearLocalDrafts, errorMessage } from "../../lib/api";

export default function ResetPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(false);
  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") ?? ""); }, []);
  async function request(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(""); setStatus("");
    try { await api<unknown>("/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email: data.get("email") }) }); setStatus("Если аккаунт с таким email существует и доставка настроена, вы получите ссылку для восстановления."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(""); setStatus("");
    try { await api<unknown>("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token: token.trim(), password: data.get("password") }) }); clearLocalDrafts(); setReset(true); setToken(""); setStatus("Пароль изменён. Сессии завершены; войдите с новым паролем."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell"><a className="brand" href="/auth">↗ наставник</a><section className="auth-card"><h1>Восстановление пароля</h1>
    {error && <p className="form-error" role="alert">{error}</p>}{status && <p role="status">{status}</p>}
    {!reset && <><form onSubmit={request}><label>Email<input name="email" type="email" required maxLength={320} autoComplete="email" disabled={busy} /></label><button className="form-button" disabled={busy}>Запросить ссылку</button></form><h2>Уже есть ссылка или токен?</h2><form onSubmit={confirm}><label>Токен восстановления<input value={token} onChange={(event) => setToken(event.target.value)} required maxLength={2000} autoComplete="off" disabled={busy} /></label><label>Новый пароль<input name="password" type="password" required minLength={8} maxLength={256} autoComplete="new-password" disabled={busy} /></label><button className="form-button" disabled={busy}>Сохранить новый пароль</button></form></>}
    <p><a href="/auth">Вернуться ко входу</a></p>
  </section></main>;
}
