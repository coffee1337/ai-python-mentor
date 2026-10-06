"use client";

import CoursePath from "../learning/course-path";
import { useUser } from "../lib/use-user";
import AppHeader from "../components/app-header";
import AppIcon from "../components/app-icon";
import TodayFocus from "./today-focus";

const milestones = [
  {
    title: "Основы Python",
    detail: "Поймёте, как читать и писать код: от переменных до функций.",
    icon: "code" as const,
  },
  {
    title: "Данные и веб",
    detail:
      "Научитесь работать с данными и разберётесь, как общаются браузер и сервер.",
    icon: "route" as const,
  },
  {
    title: "Свой backend",
    detail: "Перейдёте к API, базам данных, тестам и проектным этапам.",
    icon: "folder" as const,
  },
];

export default function DashboardPage() {
  const { user, loading, error, reload } = useUser();
  const name = user?.profile?.display_name;
  const beginner = user?.profile?.experience_level === "beginner";

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="page-content">
        {!user ? (
          <section className="panel empty-state">
            {loading && <p role="status">Готовим ваше учебное пространство…</p>}
            {error && (
              <>
                <p className="form-error" role="alert">
                  {error}
                </p>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => void reload()}
                >
                  Повторить загрузку
                </button>
              </>
            )}
          </section>
        ) : (
          <>
            <header className="page-heading">
              <div>
                <span className="page-kicker">МОЁ ОБУЧЕНИЕ</span>
                <h1>
                  {name ? `${name}, ваш следующий шаг` : "Ваш следующий шаг"}
                </h1>
                <p className="page-subtitle">
                  {beginner
                    ? "Начнём с самого начала. Опыт в программировании не нужен."
                    : "Продолжайте в своём темпе. Каждый урок объясняет одну тему и даёт возможность попробовать."}
                </p>
              </div>
              <a className="button-secondary" href="/learning/path">
                Программа курса <AppIcon name="arrow" size={16} />
              </a>
            </header>
            {!user.profile?.onboarding_completed ? (
              <section className="panel onboarding-reminder">
                <AppIcon name="route" size={28} />
                <div>
                  <h2>Сначала настроим обучение</h2>
                  <p>
                    Выберите исходный опыт и удобное время. Если ещё не писали
                    код, начнём с первой строки Python.
                  </p>
                </div>
                <a className="button" href="/onboarding">
                  Настроить маршрут <AppIcon name="arrow" size={16} />
                </a>
              </section>
            ) : (
              <div className="dashboard-grid">
                <div className="dashboard-main">
                  <TodayFocus />
                  <CoursePath variant="dashboard" />
                  <section className="panel">
                    <div className="panel-heading">
                      <span className="page-kicker">КУДА ВЕДЁТ КУРС</span>
                      <h2>От кода к работающему приложению</h2>
                      <p className="muted">
                        Python — язык программирования. Backend — серверная
                        часть приложения: она обрабатывает запросы, хранит
                        данные и проверяет доступ.
                      </p>
                    </div>
                    <div className="milestone-grid">
                      {milestones.map((item, index) => (
                        <article className="milestone" key={item.title}>
                          <span className="milestone-icon">
                            <AppIcon name={item.icon} />
                          </span>
                          <span className="milestone-index">
                            Этап {index + 1}
                          </span>
                          <h3>{item.title}</h3>
                          <p>{item.detail}</p>
                        </article>
                      ))}
                    </div>
                  </section>
                </div>
                <aside className="dashboard-aside">
                  <section className="panel learning-rhythm">
                    <span className="page-kicker">ВАШ РИТМ</span>
                    <h2>
                      {user.goal?.weekly_minutes ?? 0}
                      <span> минут в неделю</span>
                    </h2>
                    <p>
                      Начинайте с одного короткого урока. Паузы и повторение —
                      часть обучения.
                    </p>
                    <div className="profile-fact">
                      <span>Исходный опыт</span>
                      <strong>
                        {{
                          beginner: "Начинаю с нуля",
                          student: "Есть базовый опыт",
                          junior: "Пишу программы",
                        }[user.profile?.experience_level ?? ""] ?? "Не указан"}
                      </strong>
                    </div>
                    <div className="profile-fact">
                      <span>Цель</span>
                      <strong>
                        {user.goal?.target_role || "Python Backend"}
                      </strong>
                    </div>
                    <a className="text-button" href="/account">
                      Изменить настройки →
                    </a>
                  </section>
                  <section className="panel tutor-explainer">
                    <span className="tutor-icon">
                      <AppIcon name="sparkles" size={24} />
                    </span>
                    <h2>Зачем здесь AI?</h2>
                    <p>
                      Курс даёт основу, а наставник помогает разобраться именно
                      с вашей трудностью.
                    </p>
                    <ul>
                      <li>Объяснит тему другими словами.</li>
                      <li>Поможет проследить код по строкам.</li>
                      <li>Обсудит вашу ошибку и следующий шаг.</li>
                    </ul>
                    <p className="muted">
                      Чат находится в уроке. Если AI не подключён, уроки и
                      проверки остаются доступны.
                    </p>
                    <a className="button-secondary" href="/learning">
                      Открыть урок <AppIcon name="arrow" size={16} />
                    </a>
                  </section>
                  <section className="panel">
                    <h3>Уже знакомы с Python?</h3>
                    <p className="muted">
                      Необязательная диагностика поможет уточнить маршрут. Для
                      старта с нуля она не нужна.
                    </p>
                    <a className="text-button" href="/assessment">
                      Проверить исходный уровень →
                    </a>
                  </section>
                </aside>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
