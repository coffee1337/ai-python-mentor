"use client";

import { useEffect, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";

type Overview = {
  lessons: number;
  exercises: number;
  cases: number;
  knowledge_chunks: number;
  healthy: boolean;
  lesson_issues: string[];
  exercise_issues: string[];
};

type Analytics = {
  window_days: number;
  north_star: { weekly_active_learners: number };
  acquisition: { registered: number; total_accounts: number };
  activation: { completed_onboarding: number; rate: number };
  engagement: { lessons_completed: number; coding_runs: number; tutor_messages: number };
  retention: { active_last_7_days: number; rate: number };
  learning: { lessons_per_registered_user: number; runs_per_active_learner: number };
};

type Flag = { flag: string; title: string; percent: number; overrides: { user_id: string; enabled: boolean }[] };

export default function AdminPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      api<Overview>("/admin/content/overview"),
      api<Analytics>("/admin/analytics?days=30"),
      api<{ flags: Flag[] }>("/admin/features"),
    ])
      .then(([content, metrics, state]) => {
        if (!alive) return;
        setOverview(content);
        setAnalytics(metrics);
        setFlags(state.flags);
      })
      .catch((reason) => alive && setError(errorMessage(reason, "Раздел доступен только администратору.")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="page-content">
        <h1 className="page-title">Администрирование</h1>
        {loading ? <p role="status">Загружаем состояние продукта…</p> : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        {overview ? (
          <section className="panel" aria-labelledby="content-title">
            <h2 id="content-title">Контент</h2>
            <p className={overview.healthy ? "product-field-hint" : "form-error"}>
              {overview.healthy
                ? "Проверки контента пройдены: заглушек, пустых полей и заданий без скрытых тестов нет."
                : `Найдено проблем: ${overview.lesson_issues.length + overview.exercise_issues.length}`}
            </p>
            <dl className="admin-metrics">
              <div>
                <dt>Уроки</dt>
                <dd>{overview.lessons}</dd>
              </div>
              <div>
                <dt>Задания</dt>
                <dd>{overview.exercises}</dd>
              </div>
              <div>
                <dt>Тест-кейсы</dt>
                <dd>{overview.cases}</dd>
              </div>
              <div>
                <dt>Фрагменты базы знаний</dt>
                <dd>{overview.knowledge_chunks}</dd>
              </div>
            </dl>
          </section>
        ) : null}

        {analytics ? (
          <section className="panel" aria-labelledby="funnel-title">
            <h2 id="funnel-title">Воронка за {analytics.window_days} дней</h2>
            <dl className="admin-metrics">
              <div>
                <dt>Регистрации</dt>
                <dd>{analytics.acquisition.registered}</dd>
              </div>
              <div>
                <dt>Онбординг</dt>
                <dd>{Math.round(analytics.activation.rate * 100)}%</dd>
              </div>
              <div>
                <dt>Уроки</dt>
                <dd>{analytics.engagement.lessons_completed}</dd>
              </div>
              <div>
                <dt>Запуски кода</dt>
                <dd>{analytics.engagement.coding_runs}</dd>
              </div>
              <div>
                <dt>Активны за неделю</dt>
                <dd>{analytics.north_star.weekly_active_learners}</dd>
              </div>
              <div>
                <dt>Возврат за 7 дней</dt>
                <dd>{Math.round(analytics.retention.rate * 100)}%</dd>
              </div>
            </dl>
            <p className="product-field-hint">
              Все числа считаются из событий продукта: регистрация, онбординг, завершённый урок,
              оценённый запуск кода и вопрос наставнику.
            </p>
          </section>
        ) : null}

        {flags.length > 0 ? (
          <section className="panel" aria-labelledby="flags-title">
            <h2 id="flags-title">Флаги</h2>
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">Флаг</th>
                  <th scope="col">Описание</th>
                  <th scope="col">Раскатка</th>
                  <th scope="col">Исключения</th>
                </tr>
              </thead>
              <tbody>
                {flags.map((item) => (
                  <tr key={item.flag}>
                    <td>
                      <code>{item.flag}</code>
                    </td>
                    <td>{item.title}</td>
                    <td>{item.percent}%</td>
                    <td>{item.overrides.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="product-field-hint">
              Раскатка детерминированная: один и тот же пользователь всегда попадает в одну группу.
              Исключение для пользователя важнее процента.
            </p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
