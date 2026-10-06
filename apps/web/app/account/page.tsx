"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "../components/app-header";
import ProfileForm from "../components/profile-form";
import {
  api,
  clearLocalDrafts,
  errorMessage,
  OnboardingResponse,
} from "../lib/api";
import { useUser } from "../lib/use-user";

type Session = {
  id: string;
  last_seen_at: string;
  revoked_at: string | null;
  is_current: boolean;
};
type Preferences = {
  email_enabled: boolean;
  telegram_enabled: boolean;
  review_reminders: boolean;
  telegram_bound: boolean;
  email_delivery_available: boolean;
  telegram_delivery_available: boolean;
};
type BindToken = {
  token: string;
  expires_at: string;
  bot_username: string | null;
};

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

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
  const [verificationToken, setVerificationToken] = useState<string | null>(
    null,
  );

  const loadSettings = useCallback(async () => {
    const [sessionResult, preferenceResult] = await Promise.allSettled([
      api<{ sessions: Session[] }>("/me/sessions"),
      api<Preferences>("/me/notifications"),
    ]);
    if (sessionResult.status === "fulfilled") {
      setSessions(sessionResult.value.sessions);
      setSessionError("");
    } else {
      setSessionError(errorMessage(sessionResult.reason));
    }
    if (preferenceResult.status === "fulfilled") {
      setPreferences(preferenceResult.value);
      setPreferenceError("");
    } else {
      setPreferenceError(errorMessage(preferenceResult.reason));
    }
  }, []);

  useEffect(() => {
    if (user) void loadSettings();
  }, [user, loadSettings]);

  async function action(name: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(name);
    setError("");
    setStatus("");
    try {
      await operation();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy("");
    }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy("profile");
    setProfileError("");
    setStatus("");
    try {
      const response = await api<OnboardingResponse>("/onboarding", {
        method: "POST",
        body: JSON.stringify({
          display_name: data.get("display_name") || null,
          experience_level: data.get("experience_level"),
          target_role: data.get("target_role"),
          weekly_minutes: Number(data.get("weekly_minutes")),
          motivation: data.get("motivation") || null,
        }),
      });
      if (user)
        setUser({ ...user, profile: response.profile, goal: response.goal });
      setStatus("Настройки обучения сохранены.");
    } catch (reason) {
      setProfileError(errorMessage(reason));
    } finally {
      setBusy("");
    }
  }

  function savePreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("notifications", async () => {
      setPreferences(
        await api<Preferences>("/me/notifications", {
          method: "PATCH",
          body: JSON.stringify({
            email_enabled: data.has("email_enabled"),
            telegram_enabled: data.has("telegram_enabled"),
            review_reminders: data.has("review_reminders"),
          }),
        }),
      );
      setStatus("Предпочтения уведомлений сохранены.");
    });
  }

  function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("password", async () => {
      await api("/me/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: data.get("current_password"),
          password: data.get("password"),
        }),
      });
      clearLocalDrafts();
      router.replace("/auth");
    });
  }

  function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action("delete", async () => {
      await api<void>("/me/delete", {
        method: "POST",
        body: JSON.stringify({
          password: data.get("password"),
          confirmation: data.get("confirmation"),
        }),
      });
      clearLocalDrafts();
      router.replace("/");
    });
  }

  async function requestVerification() {
    const result = await api<{
      status: string;
      development_token: string | null;
    }>("/auth/email-verification/request", { method: "POST" });
    setVerificationToken(result.development_token);
    setStatus(
      "Запрос подтверждения принят. Проверьте почту, если доставка настроена.",
    );
  }

  async function exportData() {
    const data = await api<unknown>("/me/export");
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "mentor-account-export.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus("Экспорт подготовлен для скачивания.");
  }

  const displayName = user?.profile?.display_name || "Ваш профиль";

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">Личный кабинет</p>
            <h1>Аккаунт и настройки</h1>
            <p className="page-subtitle">
              Ваши цели, темп обучения, уведомления и безопасность — в одном
              месте.
            </p>
          </div>
        </header>

        {loading && (
          <div className="panel product-loading" role="status">
            Загружаем ваш аккаунт…
          </div>
        )}
        {userError && (
          <div className="status-message product-error" role="alert">
            <p>{userError}</p>
            <button
              className="button button-secondary"
              onClick={() => void reload()}
            >
              Повторить загрузку
            </button>
          </div>
        )}
        {error && (
          <p className="status-message product-error" role="alert">
            {error}
          </p>
        )}
        {status && (
          <p className="status-message product-success" role="status">
            {status}
          </p>
        )}

        {user && (
          <>
            <section
              className="panel account-overview"
              aria-label="Сводка профиля"
            >
              <span className="account-avatar" aria-hidden="true">
                {displayName.slice(0, 1).toLocaleUpperCase("ru-RU")}
              </span>
              <div className="account-identity">
                <h2>{displayName}</h2>
                <p>{user.email}</p>
              </div>
              <dl className="account-summary">
                <div>
                  <dt>Цель</dt>
                  <dd>{user.goal?.target_role ?? "Пока не выбрана"}</dd>
                </div>
                <div>
                  <dt>Темп</dt>
                  <dd>
                    {user.goal
                      ? `${user.goal.weekly_minutes} мин / неделю`
                      : "Пока не задан"}
                  </dd>
                </div>
              </dl>
            </section>

            <nav
              className="account-section-nav"
              aria-label="Настройки аккаунта"
            >
              <a href="#learning-settings">Обучение</a>
              <a href="#security-settings">Безопасность</a>
              <a href="#notifications-settings">Уведомления</a>
              <a href="#data-settings">Мои данные</a>
            </nav>

            <div className="account-grid">
              <section className="panel" id="learning-settings">
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Обучение</p>
                    <h2>Настроить маршрут под себя</h2>
                  </div>
                </div>
                <p className="product-section-intro">
                  Начинаете с нуля? Так и укажите: маршрут должен знакомить с
                  основами до самостоятельных заданий.
                </p>
                <ProfileForm
                  key={user.id}
                  user={user}
                  busy={!!busy}
                  error={profileError}
                  onSubmit={saveProfile}
                  submitLabel="Сохранить настройки обучения"
                />
              </section>

              <section className="panel" id="security-settings">
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Безопасность</p>
                    <h2>Email и пароль</h2>
                  </div>
                  <span
                    className={`badge ${user.email_verified ? "product-badge-positive" : "product-badge-neutral"}`}
                  >
                    {user.email_verified
                      ? "Email подтверждён"
                      : "Нужно подтвердить"}
                  </span>
                </div>
                <div className="account-email-row">
                  <span>{user.email}</span>
                </div>
                {!user.email_verified && (
                  <>
                    <p className="product-section-intro">
                      Подтверждённый адрес понадобится для восстановления
                      доступа.
                    </p>
                    <button
                      className="button button-secondary"
                      disabled={!!busy}
                      onClick={() => void action("verify", requestVerification)}
                    >
                      {busy === "verify"
                        ? "Отправляем…"
                        : "Отправить письмо подтверждения"}
                    </button>
                  </>
                )}
                {verificationToken && (
                  <p className="status-message">
                    Локальный режим разработки:{" "}
                    <a
                      href={`/auth/verify?token=${encodeURIComponent(verificationToken)}`}
                    >
                      подтвердить email
                    </a>
                    .
                  </p>
                )}
                <div className="product-divider" />
                <h3>Изменить пароль</h3>
                <p className="product-section-intro">
                  После сохранения все сессии завершатся. Войдите снова с новым
                  паролем.
                </p>
                <form className="settings-form" onSubmit={changePassword}>
                  <fieldset disabled={!!busy}>
                    <label>
                      Текущий пароль
                      <input
                        name="current_password"
                        type="password"
                        required
                        minLength={8}
                        maxLength={256}
                        autoComplete="current-password"
                      />
                    </label>
                    <label>
                      Новый пароль
                      <input
                        name="password"
                        type="password"
                        required
                        minLength={8}
                        maxLength={256}
                        autoComplete="new-password"
                      />
                      <span className="product-field-hint">
                        Не менее 8 символов.
                      </span>
                    </label>
                  </fieldset>
                  <button className="button button-secondary" disabled={!!busy}>
                    {busy === "password" ? "Сохраняем…" : "Обновить пароль"}
                  </button>
                </form>
              </section>

              <section className="panel" id="notifications-settings">
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Уведомления</p>
                    <h2>Когда напоминать об обучении</h2>
                  </div>
                </div>
                <p className="product-section-intro">
                  Выберите удобные каналы. Сохранённые предпочтения начинают
                  работать, когда подключена доставка.
                </p>
                {preferenceError && (
                  <div className="status-message product-error" role="alert">
                    <p>{preferenceError}</p>
                    <button
                      className="button button-secondary"
                      disabled={!!busy}
                      onClick={() => void loadSettings()}
                    >
                      Повторить загрузку
                    </button>
                  </div>
                )}
                {!preferences && !preferenceError && (
                  <p role="status">Загружаем предпочтения…</p>
                )}
                {preferences && (
                  <>
                    <form
                      className="settings-form"
                      key={`${preferences.email_enabled}.${preferences.telegram_enabled}.${preferences.review_reminders}`}
                      onSubmit={savePreferences}
                    >
                      <fieldset
                        className="account-preferences"
                        disabled={!!busy}
                      >
                        <label className="account-option">
                          <span>
                            <strong>Письма на email</strong>
                            <small>
                              {preferences.email_delivery_available
                                ? "Доставка подключена"
                                : "Доставка пока не подключена"}
                            </small>
                          </span>
                          <input
                            name="email_enabled"
                            type="checkbox"
                            defaultChecked={preferences.email_enabled}
                          />
                        </label>
                        <label className="account-option">
                          <span>
                            <strong>Сообщения в Telegram</strong>
                            <small>
                              {preferences.telegram_delivery_available
                                ? "Доставка подключена"
                                : "Доставка пока не подключена"}
                            </small>
                          </span>
                          <input
                            name="telegram_enabled"
                            type="checkbox"
                            defaultChecked={preferences.telegram_enabled}
                          />
                        </label>
                        <label className="account-option">
                          <span>
                            <strong>Напоминания о повторении</strong>
                            <small>Помогают вернуться к изученным темам</small>
                          </span>
                          <input
                            name="review_reminders"
                            type="checkbox"
                            defaultChecked={preferences.review_reminders}
                          />
                        </label>
                      </fieldset>
                      <button className="button" disabled={!!busy}>
                        {busy === "notifications"
                          ? "Сохраняем…"
                          : "Сохранить уведомления"}
                      </button>
                    </form>
                    <div className="product-divider" />
                    <div className="product-inline-heading">
                      <h3>Telegram</h3>
                      <span className="badge">
                        {preferences.telegram_bound
                          ? "Привязан"
                          : "Не привязан"}
                      </span>
                    </div>
                    {preferences.telegram_bound ? (
                      <button
                        className="button button-secondary"
                        disabled={!!busy}
                        onClick={() =>
                          void action("telegram", async () => {
                            await api<void>("/me/telegram/unbind", {
                              method: "POST",
                            });
                            setBind(null);
                            await loadSettings();
                            setStatus("Telegram отвязан.");
                          })
                        }
                      >
                        Отвязать Telegram
                      </button>
                    ) : (
                      <button
                        className="button button-secondary"
                        disabled={!!busy}
                        onClick={() =>
                          void action("telegram", async () => {
                            setBind(
                              await api<BindToken>("/me/telegram/bind-token", {
                                method: "POST",
                              }),
                            );
                          })
                        }
                      >
                        {busy === "telegram"
                          ? "Готовим код…"
                          : "Получить код привязки"}
                      </button>
                    )}
                    {bind && (
                      <div className="account-bind-instructions">
                        <p>
                          Отправьте команду в личном чате с{" "}
                          {bind.bot_username
                            ? `@${bind.bot_username}`
                            : "настроенным ботом"}
                          :
                        </p>
                        <code>/start {bind.token}</code>
                        <p className="product-field-hint">
                          Код действует до {formatDate(bind.expires_at)}.
                        </p>
                        <button
                          className="button button-secondary"
                          disabled={!!busy}
                          onClick={() => void loadSettings()}
                        >
                          Проверить привязку
                        </button>
                      </div>
                    )}
                  </>
                )}
              </section>

              <section className="panel" aria-labelledby="sessions-title">
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Доступ к аккаунту</p>
                    <h2 id="sessions-title">Сессии входа</h2>
                  </div>
                </div>
                <p className="product-section-intro">
                  Завершите сессию, если больше не пользуетесь этим браузером.
                </p>
                {sessionError && (
                  <div className="status-message product-error" role="alert">
                    <p>{sessionError}</p>
                    <button
                      className="button button-secondary"
                      disabled={!!busy}
                      onClick={() => void loadSettings()}
                    >
                      Повторить загрузку
                    </button>
                  </div>
                )}
                {!sessions && !sessionError && (
                  <p role="status">Загружаем сессии…</p>
                )}
                {sessions?.length === 0 && (
                  <div className="empty-state">
                    <h3>Нет сохранённых сессий</h3>
                    <p>После входа здесь появятся сведения о доступе.</p>
                  </div>
                )}
                {sessions && (
                  <ul className="account-session-list">
                    {sessions.map((session) => (
                      <li key={session.id}>
                        <div>
                          <div className="product-inline-heading">
                            <strong>
                              {session.is_current
                                ? "Этот браузер"
                                : "Другой вход"}
                            </strong>
                            <span className="badge">
                              {session.revoked_at
                                ? "Завершена"
                                : session.is_current
                                  ? "Текущая сессия"
                                  : "Активна"}
                            </span>
                          </div>
                          <p>
                            Последняя активность:{" "}
                            {formatDate(session.last_seen_at)}
                          </p>
                        </div>
                        {!session.revoked_at && (
                          <button
                            className="button button-secondary"
                            disabled={!!busy}
                            onClick={() =>
                              void action("session", async () => {
                                await api<void>(
                                  `/me/sessions/${encodeURIComponent(session.id)}/revoke`,
                                  { method: "POST" },
                                );
                                if (session.is_current) {
                                  clearLocalDrafts();
                                  router.replace("/auth");
                                } else {
                                  await loadSettings();
                                  setStatus("Сессия завершена.");
                                }
                              })
                            }
                          >
                            Завершить
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <section className="panel account-data-panel" id="data-settings">
              <div>
                <p className="page-kicker">Ваши данные</p>
                <h2>Сохранить историю обучения</h2>
                <p className="product-section-intro">
                  Скачайте профиль, настройки и учебную историю в JSON-файле.
                  Экспорт доступен только вам.
                </p>
              </div>
              <button
                className="button button-secondary"
                disabled={!!busy}
                onClick={() => void action("export", exportData)}
              >
                {busy === "export" ? "Готовим экспорт…" : "Скачать мои данные"}
              </button>
            </section>

            <section
              className="panel account-danger-panel"
              aria-labelledby="delete-account-title"
            >
              <div className="panel-heading">
                <div>
                  <p className="page-kicker">Удаление данных</p>
                  <h2 id="delete-account-title">Удалить аккаунт</h2>
                </div>
              </div>
              <p>
                Аккаунт и связанные учебные данные будут удалены без возможности
                восстановления. Сначала скачайте экспорт, если хотите сохранить
                историю.
              </p>
              <form
                className="settings-form account-delete-form"
                onSubmit={deleteAccount}
              >
                <fieldset disabled={!!busy}>
                  <label>
                    Текущий пароль
                    <input
                      name="password"
                      type="password"
                      required
                      minLength={8}
                      maxLength={256}
                      autoComplete="current-password"
                    />
                  </label>
                  <label>
                    Введите DELETE для подтверждения
                    <input
                      name="confirmation"
                      required
                      pattern="DELETE"
                      maxLength={6}
                      autoComplete="off"
                      placeholder="DELETE"
                    />
                  </label>
                </fieldset>
                <button
                  className="button product-danger-button"
                  disabled={!!busy}
                >
                  {busy === "delete"
                    ? "Удаляем аккаунт…"
                    : "Удалить аккаунт и все данные"}
                </button>
              </form>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
