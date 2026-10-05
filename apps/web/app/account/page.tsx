"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "../components/app-header";
import ProfileForm from "../components/profile-form";
import { api, clearLocalDrafts, errorMessage, OnboardingResponse } from "../lib/api";
import { useUser } from "../lib/use-user";

type Session = { id: string; created_at: string; last_seen_at: string; expires_at: string; revoked_at: string | null; is_current: boolean };
type Preferences = { email_enabled: boolean; telegram_enabled: boolean; review_reminders: boolean; telegram_bound: boolean; email_delivery_available: boolean; telegram_delivery_available: boolean };
type BindToken = { token: string; expires_at: string; bot_username: string | null };

export default function AccountPage() {
  const router = useRouter();
  const { user, loading, error: userError, reload, setUser } = useUser();
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [preferenceError, setPreferenceError] = useState("");
  const [error, setError] = useState("");
  const [profileError, setProfileError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState("");
  const [bind, setBind] = useState<BindToken | null>(null);
  const [verificationToken, setVerificationToken] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    const [sessionResult, preferencesResult] = await Promise.allSettled([api<{ sessions: Session[] }>("/me/sessions"), api<Preferences>("/me/notifications")]);
    if (sessionResult.status === "fulfilled") { setSessions(sessionResult.value.sessions); setSessionError(""); }
    else setSessionError(errorMessage(sessionResult.reason));
    if (preferencesResult.status === "fulfilled") { setPreferences(preferencesResult.value); setPreferenceError(""); }
    else setPreferenceError(errorMessage(preferencesResult.reason));
  }, []);
  useEffect(() => { if (user) void loadSettings(); }, [user, loadSettings]);

  async function action(name: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(name);
    setError("");
    setStatus("");
    try { await operation(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy("profile");
    setProfileError("");
    try {
      const response = await api<OnboardingResponse>("/onboarding", { method: "POST", body: JSON.stringify({ display_name: data.get("display_name") || null, experience_level: data.get("experience_level"), target_role: data.get("target_role"), weekly_minutes: Number(data.get("weekly_minutes")), motivation: data.get("motivation") || null }) });
      if (user) setUser({ ...user, profile: response.profile, goal: response.goal });
      setStatus("Настройки обучения сохранены.");
    } catch (reason) { setProfileError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  function savePreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("notifications", async () => {
      setPreferences(await api<Preferences>("/me/notifications", { method: "PATCH", body: JSON.stringify({ email_enabled: data.has("email_enabled"), telegram_enabled: data.has("telegram_enabled"), review_reminders: data.has("review_reminders") }) }));
      setStatus("Предпочтения уведомлений сохранены.");
    });
  }

  function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("delete", async () => {
      await api<void>("/me/delete", { method: "POST", body: JSON.stringify({ password: data.get("password"), confirmation: data.get("confirmation") }) });
      clearLocalDrafts();
      router.replace("/");
    });
  }

  function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("password", async () => {
      await api("/me/password", { method: "POST", body: JSON.stringify({ current_password: data.get("current_password"), password: data.get("password") }) });
      clearLocalDrafts();
      router.replace("/auth");
    });
  }

  return (
    <main className="dashboard-shell"><AppHeader /><section className="dashboard-card">
      <h1>Аккаунт и настройки</h1>
      {loading && <p role="status">Загружаем аккаунт…</p>}
      {userError && <div role="alert"><p>{userError}</p><button className="text-button" onClick={() => void reload()}>Повторить</button></div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {user && <>
        <section className="lesson-subsection"><h2>Ваш учебный маршрут</h2><ProfileForm key={user.id} user={user} busy={!!busy} error={profileError} onSubmit={saveProfile} /></section>
        <section className="lesson-subsection"><h2>Email</h2><p>{user.email}</p><p>{user.email_verified ? "Email подтверждён." : "Email ещё не подтверждён."}</p>
          {!user.email_verified && <button className="text-button" disabled={!!busy} onClick={() => void action("verify", async () => { const result = await api<{ status: string; development_token: string | null }>("/auth/email-verification/request", { method: "POST" }); setVerificationToken(result.development_token); setStatus("Запрос подтверждения принят. Проверьте почту, если доставка настроена."); })}>Отправить подтверждение</button>}
          {verificationToken && <p>Для локального режима разработки: <a href={`/auth/verify?token=${encodeURIComponent(verificationToken)}`}>Подтвердить email</a></p>}
          <details><summary>Изменить пароль</summary><p>После смены пароля все сессии завершатся. Войдите снова с новым паролем.</p><form className="settings-form" onSubmit={changePassword}><label>Текущий пароль<input name="current_password" type="password" required minLength={8} maxLength={256} autoComplete="current-password" disabled={!!busy} /></label><label>Новый пароль<input name="password" type="password" required minLength={8} maxLength={256} autoComplete="new-password" disabled={!!busy} /></label><button className="form-button" disabled={!!busy}>Сохранить новый пароль</button></form></details>
        </section>
        <section className="lesson-subsection"><h2>Уведомления</h2>
          {preferenceError && <div role="alert"><p>{preferenceError}</p><button className="text-button" onClick={() => void loadSettings()}>Повторить загрузку</button></div>}
          {!preferences && !preferenceError && <p role="status">Загружаем предпочтения…</p>}
          {preferences && <>
            <form className="settings-form" key={`${preferences.email_enabled}.${preferences.telegram_enabled}.${preferences.review_reminders}`} onSubmit={savePreferences}>
              <fieldset disabled={!!busy}>
                <label className="check-label"><input name="email_enabled" type="checkbox" defaultChecked={preferences.email_enabled} />Email</label>
                <label className="check-label"><input name="telegram_enabled" type="checkbox" defaultChecked={preferences.telegram_enabled} />Telegram</label>
                <label className="check-label"><input name="review_reminders" type="checkbox" defaultChecked={preferences.review_reminders} />Напоминания о повторениях</label>
              </fieldset>
              <button className="form-button" disabled={!!busy}>Сохранить предпочтения</button>
            </form>
            <p className="muted">Доставка email: {preferences.email_delivery_available ? "подключена" : "не настроена"}. Доставка Telegram: {preferences.telegram_delivery_available ? "подключена" : "не настроена"}.</p>
            <p>{preferences.telegram_bound ? "Telegram привязан." : "Telegram ещё не привязан."}</p>
            {preferences.telegram_bound ? <button className="text-button" disabled={!!busy} onClick={() => void action("telegram", async () => { await api<void>("/me/telegram/unbind", { method: "POST" }); setBind(null); await loadSettings(); setStatus("Telegram отвязан."); })}>Отвязать Telegram</button> : <button className="text-button" disabled={!!busy} onClick={() => void action("telegram", async () => { setBind(await api<BindToken>("/me/telegram/bind-token", { method: "POST" })); })}>Получить код привязки</button>}
            {bind && <div className="review-result"><p>Отправьте команду в личном чате с {bind.bot_username ? `@${bind.bot_username}` : "настроенным ботом"}:</p><code>/start {bind.token}</code><p>Код действует до {new Date(bind.expires_at).toLocaleString("ru-RU")}.</p><button className="text-button" onClick={() => void loadSettings()}>Проверить привязку</button></div>}
          </>}
        </section>
        <section className="lesson-subsection"><h2>Активные сессии</h2>
          {sessionError && <div role="alert"><p>{sessionError}</p><button className="text-button" onClick={() => void loadSettings()}>Повторить загрузку</button></div>}
          {!sessions && !sessionError && <p role="status">Загружаем сессии…</p>}
          {sessions?.length === 0 && <p>Других сессий нет.</p>}
          {sessions && <ul>{sessions.map((session) => <li className="saved-item" key={session.id}><strong>{session.is_current ? "Этот браузер" : "Другая сессия"}</strong><p>Последняя активность: {new Date(session.last_seen_at).toLocaleString("ru-RU")}</p>{session.revoked_at ? <p>Завершена</p> : <button className="text-button" disabled={!!busy} onClick={() => void action("session", async () => { await api<void>(`/me/sessions/${encodeURIComponent(session.id)}/revoke`, { method: "POST" }); if (session.is_current) { clearLocalDrafts(); router.replace("/auth"); } else { await loadSettings(); setStatus("Сессия завершена."); } })}>Завершить сессию</button>}</li>)}</ul>}
        </section>
        <section className="lesson-subsection"><h2>Ваши данные</h2><button className="text-button" disabled={!!busy} onClick={() => void action("export", async () => { const data = await api<unknown>("/me/export"); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = "mentor-account-export.json"; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); setStatus("Экспорт подготовлен для скачивания."); })}>Скачать экспорт данных</button>
          <details><summary>Удалить аккаунт</summary><p>Аккаунт и связанные учебные данные будут удалены. Это действие нельзя отменить. Сначала скачайте экспорт, если хотите сохранить историю.</p><form className="settings-form" onSubmit={deleteAccount}><label>Текущий пароль<input name="password" type="password" required minLength={8} maxLength={256} autoComplete="current-password" disabled={!!busy} /></label><label>Введите DELETE для подтверждения<input name="confirmation" required pattern="DELETE" maxLength={6} autoComplete="off" disabled={!!busy} /></label><button className="form-button" disabled={!!busy}>Удалить мой аккаунт и данные</button></form></details>
        </section>
      </>}
    </section></main>
  );
}
