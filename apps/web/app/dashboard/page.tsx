"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import CoursePath from "../learning/course-path";
import { api, User } from "../lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api<User>("/me")
      .then(setUser)
      .catch(() => router.replace("/auth"));
  }, [router]);

  async function logout() {
    try {
      await api<void>("/auth/logout", { method: "POST" });
      router.replace("/");
    } catch {
      setError("Не удалось завершить сессию. Попробуйте ещё раз.");
    }
  }

  if (!user) {
    return (
      <main className="auth-shell">
        <p role="status" aria-live="polite">Загружаем ваш маршрут…</p>
      </main>
    );
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <a className="brand" href="/">
          ↗ наставник<span className="brand-dot">.</span>
        </a>
        <button className="text-button" type="button" onClick={() => void logout()}>
          Выйти
        </button>
      </header>

      <section className="dashboard-card">
        <span className="eyebrow"><i aria-hidden="true" /> ВАШ ПРОФИЛЬ</span>
        <h1>
          Добро пожаловать
          {user.profile?.display_name ? `, ${user.profile.display_name}` : ""}.
        </h1>
        <p className="auth-lead">
          Цель: <strong>{user.goal?.target_role ?? "настроить цель"}</strong>
        </p>

        <div className="dashboard-meta" aria-label="Параметры обучения">
          <div>
            <b>{user.goal?.weekly_minutes ?? 0}</b>
            <span>минут в неделю</span>
          </div>
          <div>
            <b>{user.profile?.experience_level ?? "—"}</b>
            <span>текущий уровень</span>
          </div>
        </div>

        {error && <p className="form-error" role="alert">{error}</p>}

        {!user.profile?.onboarding_completed ? (
          <>
            <p className="muted">Завершите настройку, чтобы собрать учебный маршрут.</p>
            <a href="/onboarding">Завершить настройку →</a>
          </>
        ) : (
          <CoursePath variant="dashboard" />
        )}
      </section>
    </main>
  );
}
