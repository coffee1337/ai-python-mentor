"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "../../components/app-header";
import { api, errorMessage, isUnauthorized } from "../../lib/api";
import { useUser } from "../../lib/use-user";
import type {
  StudyActivity,
  StudyProgress,
  StudyProgressSkill,
} from "../study-types";

type SkillFilter = "observed" | "all" | "unobserved";

const ACTIVITY_LABELS: Record<StudyActivity["kind"], string> = {
  lesson: "Урок",
  assessment: "Диагностика",
  knowledge_check: "Проверка понимания",
  coding: "Отправка кода",
  review: "Повторение",
};

const OUTCOME_LABELS: Record<string, string> = {
  completed: "Урок пройден",
  passed: "Проверка пройдена",
  failed: "Есть что разобрать ещё раз",
  correct: "Верный ответ",
  partial: "Частично верный ответ",
  incorrect: "Стоит вернуться к объяснению",
  saved: "Материал сохранён",
  submitted: "Материал отправлен",
  unavailable: "Код сохранён без исполнения",
  pending: "Ожидает обработки",
  queued: "Ожидает обработки",
  running: "Обрабатывается",
  recorded: "Результат записан",
  replayed: "Ранее сохранённый результат",
  timeout: "Превышено время проверки",
  resource_violation: "Превышен лимит ресурсов",
  runner_error: "Проверка недоступна",
  cancelled: "Проверка отменена",
};

function localDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата недоступна";
  return date.toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function calendarDate(value: string) {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "Дата недоступна";
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
  });
}

function localDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата недоступна";
  return date.toLocaleDateString("ru-RU", { dateStyle: "medium" });
}

function hasObservations(skill: StudyProgressSkill) {
  return skill.acquisition_observations > 0 || skill.review_observations > 0;
}

function modelScore(value: number | null) {
  return value === null ? "Нет данных" : `${Math.round(value * 100)} / 100`;
}

function SkillMaterial({ skill }: { skill: StudyProgressSkill }) {
  if (!skill.lesson_id || !skill.lesson_status) {
    return (
      <span className="muted">Материал пока не опубликован</span>
    );
  }
  if (skill.lesson_status === "locked") {
    return (
      <>
        <span className="badge">Сначала основы</span>
        <a href="/learning/path">Посмотреть условия открытия</a>
      </>
    );
  }
  return (
    <a href={`/learning?lesson=${encodeURIComponent(skill.lesson_id)}`}>
      {skill.lesson_status === "completed"
        ? "Вернуться к уроку"
        : "Открыть урок"} →
    </a>
  );
}

export default function ProgressPage() {
  const router = useRouter();
  const { user, loading: userLoading, error: userError, reload } = useUser(true);
  const [days, setDays] = useState<7 | 30>(7);
  const [data, setData] = useState<StudyProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestNumber, setRequestNumber] = useState(0);
  const [query, setQuery] = useState("");
  const [skillFilter, setSkillFilter] = useState<SkillFilter>("observed");

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const parameters = new URLSearchParams({
      days: String(days),
      utc_offset_minutes: String(-new Date().getTimezoneOffset()),
    });
    void api<StudyProgress>(`/learning/progress?${parameters}`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((reason) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(reason)) router.replace("/auth");
        else setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [user, days, requestNumber, router]);

  const visibleSkills = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("ru-RU");
    return (data?.skills ?? []).filter((skill) => {
      const observed = hasObservations(skill);
      if (skillFilter === "observed" && !observed) return false;
      if (skillFilter === "unobserved" && observed) return false;
      return (
        !normalized ||
        `${skill.name} ${skill.skill_id}`
          .toLocaleLowerCase("ru-RU")
          .includes(normalized)
      );
    });
  }, [data, query, skillFilter]);

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page study-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">Ваш учебный опыт</p>
            <h1>Мой прогресс</h1>
            <p className="page-subtitle">
              Пройденные уроки, учебные наблюдения и возвращение к знакомым
              темам. Здесь видны записанные результаты вашего обучения.
            </p>
          </div>
          <div className="product-action-row">
            <a className="button-secondary" href="/learning/reviews">
              Повторения
            </a>
            <a className="button" href="/learning">
              Продолжить обучение →
            </a>
          </div>
        </header>

        {userLoading && (
          <p className="panel product-loading" role="status">
            Готовим ваше учебное пространство…
          </p>
        )}
        {userError && (
          <div className="status-message product-error" role="alert">
            <p>{userError}</p>
            <button
              className="button-secondary"
              type="button"
              disabled={userLoading}
              onClick={() => void reload()}
            >
              Повторить загрузку аккаунта
            </button>
          </div>
        )}

        {user && (
          <>
            <div className="study-period-bar">
              <fieldset className="study-period-controls">
                <legend>Период активности</legend>
                <div className="product-action-row">
                  {([7, 30] as const).map((option) => (
                    <button
                      className={
                        days === option ? "button" : "button-secondary"
                      }
                      type="button"
                      key={option}
                      aria-pressed={days === option}
                      onClick={() => setDays(option)}
                    >
                      {option} дней
                    </button>
                  ))}
                </div>
              </fieldset>
              {!loading && !error && data && (
                <p className="muted">
                  {calendarDate(data.window.start_date)} —{" "}
                  {calendarDate(data.window.end_date)}. Дни показаны по вашему
                  часовому поясу.
                </p>
              )}
            </div>

            {loading && (
              <p
                className="panel product-loading"
                role="status"
                aria-live="polite"
              >
                Загружаем прогресс за {days} дней…
              </p>
            )}
            {!loading && error && (
              <div className="status-message product-error" role="alert">
                <p>{error}</p>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => setRequestNumber((number) => number + 1)}
                >
                  Повторить загрузку прогресса
                </button>
              </div>
            )}

            {!loading && !error && data && (
              <>
                <section aria-labelledby="progress-overview-title">
                  <div className="product-section-heading">
                    <h2 id="progress-overview-title">Всё обучение</h2>
                  </div>
                  <dl className="study-summary-grid">
                    <div className="panel study-summary-card">
                      <dt>Пройдено уроков</dt>
                      <dd>
                        {data.totals.completed_lessons} из{" "}
                        {data.totals.total_lessons}
                      </dd>
                    </div>
                    <div className="panel study-summary-card">
                      <dt>Тем с учебными наблюдениями</dt>
                      <dd>{data.totals.observed_skills}</dd>
                    </div>
                    <div className="panel study-summary-card">
                      <dt>Тем для повторения сегодня</dt>
                      <dd>
                        <a
                          href="/learning/reviews"
                          aria-label={`Тем для повторения сегодня: ${data.totals.due_reviews}. Открыть повторения.`}
                        >
                          {data.totals.due_reviews} →
                        </a>
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="panel" aria-labelledby="progress-period-title">
                  <div className="panel-heading">
                    <div>
                      <p className="page-kicker">
                        Последние {data.window.days} дней
                      </p>
                      <h2 id="progress-period-title">Изучение и повторение</h2>
                    </div>
                    <span className="badge">
                      Дней с активностью: {data.period.active_days}
                    </span>
                  </div>
                  <p className="product-section-intro">
                    Учебные наблюдения — записи о работе с отдельными навыками.
                    Одна проверка может дать несколько записей. Изучение новой
                    темы и повторение после паузы учитываются отдельно.
                  </p>
                  <dl className="study-evidence-grid">
                    <div>
                      <dt>Наблюдения при изучении</dt>
                      <dd>{data.period.acquisition_observations}</dd>
                    </div>
                    <div>
                      <dt>Без раскрытых подсказок</dt>
                      <dd>{data.period.independent_observations}</dd>
                    </div>
                    <div>
                      <dt>С раскрытыми подсказками</dt>
                      <dd>{data.period.assisted_observations}</dd>
                    </div>
                    <div>
                      <dt>Наблюдения при повторении</dt>
                      <dd>{data.period.review_observations}</dd>
                    </div>
                  </dl>
                  <p className="muted">
                    За период пройдено уроков: {data.period.lessons_completed}.
                    {" "}Попыток проверки понимания: {data.period.checks_attempted},
                    {" "}из них успешных: {data.period.checks_passed}.
                    {" "}Отправок кода: {data.period.coding_submissions}.
                    {" "}Отправка кода сама по себе не подтверждает освоение темы.
                  </p>
                  {data.period.active_days === 0 && (
                    <div className="empty-state">
                      <h3>За этот период пока нет учебных событий</h3>
                      <p>
                        После проверки урока или повторения здесь появятся
                        записанные результаты. Начните с доступного материала.
                      </p>
                      <a className="button-secondary" href="/learning/path">
                        Выбрать урок
                      </a>
                    </div>
                  )}
                  <details
                    className="product-disclosure"
                    open={days === 7 ? true : undefined}
                  >
                    <summary>Активность по дням</summary>
                    <ul
                      className="study-day-grid"
                      aria-label="Учебные события по дням"
                    >
                      {data.days.map((day) => {
                        const hasActivity = day.activity_count > 0;
                        const hasLearningCounts =
                          day.lessons_completed > 0 ||
                          day.acquisition_observations > 0 ||
                          day.review_observations > 0 ||
                          day.coding_submissions > 0;
                        return (
                          <li className="study-day" key={day.date}>
                            <time dateTime={day.date}>
                              {calendarDate(day.date)}
                            </time>
                            {hasActivity ? (
                              <>
                                <p className="muted">
                                  Записано событий: {day.activity_count}
                                </p>
                                {!hasLearningCounts && (
                                  <p className="muted">
                                    Учебное событие может не добавлять новых
                                    наблюдений по навыку.
                                  </p>
                                )}
                                <ul>
                                  {day.lessons_completed > 0 && (
                                    <li>Уроков пройдено: {day.lessons_completed}</li>
                                  )}
                                  {day.acquisition_observations > 0 && (
                                    <li>
                                      Наблюдений при изучении:{" "}
                                      {day.acquisition_observations}
                                    </li>
                                  )}
                                  {day.independent_observations > 0 && (
                                    <li>
                                      Без подсказок: {day.independent_observations}
                                    </li>
                                  )}
                                  {day.assisted_observations > 0 && (
                                    <li>
                                      С подсказками: {day.assisted_observations}
                                    </li>
                                  )}
                                  {day.review_observations > 0 && (
                                    <li>
                                      Наблюдений при повторении:{" "}
                                      {day.review_observations}
                                    </li>
                                  )}
                                  {day.coding_submissions > 0 && (
                                    <li>Отправок кода: {day.coding_submissions}</li>
                                  )}
                                </ul>
                              </>
                            ) : (
                              <p className="muted">Нет записанных событий</p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                </section>

                <section className="panel" aria-labelledby="progress-skills-title">
                  <div className="panel-heading">
                    <div>
                      <p className="page-kicker">Карта тем</p>
                      <h2 id="progress-skills-title">Что уже наблюдалось в обучении</h2>
                    </div>
                  </div>
                  <p className="product-section-intro">
                    Наличие наблюдений показывает опыт работы с темой.
                    Отсутствие записей означает, что данных пока нет.
                  </p>
                  <div className="study-skill-controls settings-form">
                    <label htmlFor="study-skill-search">
                      Найти тему
                      <input
                        id="study-skill-search"
                        type="search"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Например, функции или SQL"
                      />
                    </label>
                    <label htmlFor="study-skill-filter">
                      Показать темы
                      <select
                        id="study-skill-filter"
                        value={skillFilter}
                        onChange={(event) =>
                          setSkillFilter(event.target.value as SkillFilter)
                        }
                      >
                        <option value="observed">С учебными наблюдениями</option>
                        <option value="all">Все темы курса</option>
                        <option value="unobserved">Пока без наблюдений</option>
                      </select>
                    </label>
                  </div>
                  <p className="muted" role="status" aria-live="polite">
                    Показано тем: {visibleSkills.length} из {data.skills.length}.
                  </p>
                  {visibleSkills.length === 0 ? (
                    <div className="empty-state">
                      <h3>
                        {data.skills.length === 0
                          ? "Темы пока не опубликованы"
                          : query
                            ? "Темы не найдены"
                            : "В этой группе пока нет тем"}
                      </h3>
                      <p>
                        {data.skills.length === 0
                          ? "Продолжайте обучение: новые материалы будут появляться в программе курса."
                          : query
                          ? "Попробуйте другое название или покажите все темы курса."
                          : "Можно посмотреть все темы курса и выбрать доступный урок."}
                      </p>
                      {data.skills.length > 0 && (query || skillFilter !== "all") && (
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => {
                            setQuery("");
                            setSkillFilter("all");
                          }}
                        >
                          Показать все темы
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="study-table-wrap">
                      <table className="study-skill-table">
                        <caption className="sr-only">
                          Учебные наблюдения по темам и доступные материалы
                        </caption>
                        <thead>
                          <tr>
                            <th scope="col">Тема</th>
                            <th scope="col">При изучении</th>
                            <th scope="col">При повторении</th>
                            <th scope="col">Следующее повторение</th>
                            <th scope="col">Материал</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleSkills.map((skill) => (
                            <tr key={skill.skill_id}>
                              <th scope="row">
                                <strong>{skill.name}</strong>
                                <span className="muted">
                                  {skill.last_observed_at
                                    ? `Последняя запись: ${localDateTime(skill.last_observed_at)}`
                                    : "Наблюдений пока нет"}
                                </span>
                                <details className="study-model-details">
                                  <summary>Ориентиры модели</summary>
                                  <p className="muted">
                                    Приблизительные сигналы на основе учебных
                                    данных, а не абсолютный уровень навыка.
                                  </p>
                                  <dl>
                                    <div>
                                      <dt>Понимание</dt>
                                      <dd>{modelScore(skill.knowledge_score)}</dd>
                                    </div>
                                    <div>
                                      <dt>Практика</dt>
                                      <dd>{modelScore(skill.practice_score)}</dd>
                                    </div>
                                    <div>
                                      <dt>Самостоятельность</dt>
                                      <dd>{modelScore(skill.independent_score)}</dd>
                                    </div>
                                    <div>
                                      <dt>Сохранность после паузы</dt>
                                      <dd>{modelScore(skill.retention_score)}</dd>
                                    </div>
                                  </dl>
                                </details>
                              </th>
                              <td data-label="При изучении">{skill.acquisition_observations}</td>
                              <td data-label="При повторении">{skill.review_observations}</td>
                              <td data-label="Следующее повторение">
                                {skill.next_review_at ? (
                                  <time dateTime={skill.next_review_at}>
                                    {localDate(skill.next_review_at)}
                                  </time>
                                ) : (
                                  <span className="muted">Пока не назначено</span>
                                )}
                              </td>
                              <td className="study-material-cell" data-label="Материал">
                                <SkillMaterial skill={skill} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>

                <section className="panel" aria-labelledby="progress-activity-title">
                  <div className="panel-heading">
                    <div>
                      <p className="page-kicker">История за выбранный период</p>
                      <h2 id="progress-activity-title">Последние учебные события</h2>
                    </div>
                  </div>
                  {data.recent_activity.length === 0 ? (
                    <div className="empty-state">
                      <h3>За этот период событий пока нет</h3>
                      <p>
                        Здесь появятся пройденные уроки, проверки, отправки кода
                        и повторения.
                      </p>
                    </div>
                  ) : (
                    <>
                      <p className="product-section-intro">
                        До 50 последних событий. Время показано в часовом поясе
                        вашего устройства.
                      </p>
                      <ol className="study-activity-list">
                        {data.recent_activity.slice(0, 50).map((activity, index) => (
                          <li
                            key={`${activity.kind}.${activity.occurred_at}.${index}`}
                          >
                            <div className="study-activity-main">
                              <span className="badge">
                                {ACTIVITY_LABELS[activity.kind]}
                              </span>
                              <h3>{activity.title}</h3>
                              <p>
                                {OUTCOME_LABELS[activity.outcome] ??
                                  "Учебное событие записано"}
                              </p>
                              <div className="study-activity-notes">
                                {activity.assisted !== null && (
                                  <span className="muted">
                                    {activity.assisted
                                      ? "С раскрытыми подсказками"
                                      : "Без раскрытых подсказок"}
                                    {activity.hint_count !== null && activity.hint_count > 0
                                      ? ` · открыто уровней: ${activity.hint_count}`
                                      : ""}
                                  </span>
                                )}
                                <span className="muted">
                                  {activity.evidence_recorded
                                    ? "Учебное наблюдение записано"
                                    : "Событие не добавило учебного наблюдения"}
                                </span>
                              </div>
                            </div>
                            <div className="study-activity-meta">
                              <time dateTime={activity.occurred_at}>
                                {localDateTime(activity.occurred_at)}
                              </time>
                              {activity.lesson_id && (
                                <a
                                  href={`/learning?lesson=${encodeURIComponent(activity.lesson_id)}`}
                                >
                                  К уроку →
                                </a>
                              )}
                            </div>
                          </li>
                        ))}
                      </ol>
                    </>
                  )}
                  <p className="muted">
                    Данные обновлены:{" "}
                    <time dateTime={data.as_of}>
                      {localDateTime(data.as_of)}
                    </time>.
                  </p>
                </section>
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}
