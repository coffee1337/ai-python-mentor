"use client";
import { useEffect, useState } from "react";
import { api, errorMessage } from "../lib/api";
type LessonStatus = "completed" | "available" | "locked";
type PhaseSummary = {
  id: number;
  title: string;
  summary: string;
  status: LessonStatus;
  completed: number;
  total: number;
  next_lesson_id: string | null;
};
type LearningPathResponse = {
  title: string;
  completed: number;
  total: number;
  next_lesson_id: string | null;
  resume_lesson_id?: string | null;
  phases: PhaseSummary[];
  lessons: {
    id: string;
    title: string;
    minutes: number;
    status: LessonStatus;
    completed_at: string | null;
    phase: number | null;
  }[];
};
type LearningPlanResponse = {
  status: "ready" | "assessment_required";
  recommendation: string;
  recommended_lesson_id: string | null;
  learning_mode?: "starter" | "assessed";
  assessment_optional?: boolean;
  resume_lesson_id?: string | null;
  items: {
    lesson_id: string;
    title: string;
    status: string;
    rationale: string;
  }[];
};
const STATUS_LABELS: Record<LessonStatus, string> = {
  completed: "Пройден",
  available: "Доступен",
  locked: "Позже",
};
export default function CoursePath({
  variant,
}: {
  variant: "dashboard" | "full";
}) {
  const [path, setPath] = useState<LearningPathResponse | null>(null);
  const [plan, setPlan] = useState<LearningPlanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestNumber, setRequestNumber] = useState(0);
  const [activePhase, setActivePhase] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<LessonStatus | "all">("all");
  const compact = variant === "dashboard";

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void Promise.all([
      api<LearningPathResponse>("/learning/path", {
        signal: controller.signal,
      }),
      api<LearningPlanResponse>("/learning/plan", {
        signal: controller.signal,
      }),
    ])
      .then(([nextPath, nextPlan]) => {
        if (controller.signal.aborted) return;
        setPath(nextPath);
        setPlan(nextPlan);
        const next = nextPath.lessons.find(
          (lesson) => lesson.id === nextPath.next_lesson_id,
        );
        setActivePhase(
          next
            ? (next.phase ?? 0)
            : (nextPath.phases?.find((phase) => phase.status === "available")
                ?.id ?? null),
        );
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [requestNumber]);

  const nextLesson =
    path?.lessons.find(
      (lesson) =>
        lesson.id === (plan?.recommended_lesson_id ?? path.next_lesson_id) &&
        lesson.status !== "locked",
    ) ??
    path?.lessons.find(
      (lesson) =>
        lesson.id === path.next_lesson_id && lesson.status === "available",
    );
  const nextPlanItem = plan?.items.find(
    (item) => item.lesson_id === nextLesson?.id,
  );
  const foundations =
    path?.lessons.filter((lesson) => lesson.phase === null) ?? [];
  const foundationPhase: PhaseSummary[] = foundations.length
    ? [
        {
          id: 0,
          title: "Основы Python",
          summary:
            "От первой строки и переменных до функций, коллекций и работы с файлами.",
          status: foundations.every((lesson) => lesson.status === "completed")
            ? "completed"
            : foundations.some((lesson) => lesson.status === "available")
              ? "available"
              : "locked",
          completed: foundations.filter(
            (lesson) => lesson.status === "completed",
          ).length,
          total: foundations.length,
          next_lesson_id:
            foundations.find((lesson) => lesson.status === "available")?.id ??
            null,
        },
      ]
    : [];
  const phases = [...foundationPhase, ...(path?.phases ?? [])].filter(
    (phase) => phase.total > 0,
  );
  const visibleLessons =
    path?.lessons.filter(
      (lesson) => (activePhase === null || (lesson.phase ?? 0) === activePhase)
        && (statusFilter === "all" || lesson.status === statusFilter)
        && lesson.title.toLocaleLowerCase("ru-RU").includes(query.trim().toLocaleLowerCase("ru-RU")),
    ) ?? [];

  return (
    <section
      className={
        compact
          ? "panel course-path course-path-compact"
          : "course-path course-path-full"
      }
      aria-labelledby={compact ? "continue-title" : "path-title"}
      aria-busy={loading}
    >
      <header className={compact ? "panel-heading" : "page-heading"}>
        <div>
          <p className="page-kicker">
            {compact ? "Ваш следующий шаг" : "Python → Python Backend"}
          </p>
          {compact ? (
            <h2 id="continue-title">Продолжить обучение</h2>
          ) : (
            <h1 id="path-title">Ваш учебный путь</h1>
          )}
        </div>
        {!compact && (
          <p className="page-subtitle">
            Начните с того, как читать программу. Затем научитесь писать свой
            код, работать с данными и создавать backend — часть приложения,
            которая отвечает на запросы и хранит данные.
          </p>
        )}
      </header>
      {loading && (
        <p className="status-message" role="status">
          Загружаем учебный путь…
        </p>
      )}
      {error && (
        <div className="status-message" role="alert">
          <p>{error}</p>
          <button
            className="button-secondary"
            type="button"
            onClick={() => setRequestNumber((number) => number + 1)}
          >
            Повторить загрузку
          </button>
          <a href="/auth">Войти в аккаунт</a>
        </div>
      )}
      {!loading && !error && path && plan && (
        <>
          {path.total > 0 && (
            <div className="path-progress">
              <span>
                Пройдено{" "}
                <strong>
                  {path.completed} из {path.total}
                </strong>{" "}
                уроков
              </span>
              <progress
                aria-label="Пройденные уроки"
                value={path.completed}
                max={path.total}
              />
            </div>
          )}
          {(path.resume_lesson_id ?? plan.resume_lesson_id) ? (
            <div className="course-next-lesson">
              <div>
                <span className="badge">Начатый ранее урок</span>
                <h3>Продолжить открытый урок</h3>
                <p>
                  У вас сохранён урок предыдущей версии. Продолжите тот же
                  материал и проверку. Сохранённые попытки и открытые подсказки
                  останутся в истории этого урока.
                </p>
              </div>
              <a
                className="button"
                href={`/learning?lesson=${encodeURIComponent((path.resume_lesson_id ?? plan.resume_lesson_id)!)}`}
              >
                Продолжить начатое →
              </a>
            </div>
          ) : nextLesson ? (
            <div className="course-next-lesson">
              <div>
                <span className="badge">
                  {path.completed === 0
                    ? "Начните здесь"
                    : "Рекомендуемый урок"}
                </span>
                <h3>{nextLesson.title}</h3>
                <p>
                  {nextPlanItem?.rationale ||
                    plan.recommendation ||
                    "Сначала прочитайте объяснение и пример, затем ответьте на небольшие вопросы."}
                </p>
                <p className="muted">
                  Около {nextLesson.minutes} минут ·{" "}
                  {plan.learning_mode === "starter"
                    ? "Маршрут с нуля"
                    : "Основной курс"}
                </p>
              </div>
              <a
                className="button"
                href={`/learning?lesson=${encodeURIComponent(nextLesson.id)}`}
              >
                {path.completed === 0
                  ? "Открыть первый урок"
                  : "Продолжить урок"}{" "}
                →
              </a>
            </div>
          ) : (
            <div className="empty-state">
              <h3>
                {path.lessons.length === 0
                  ? "Уроки пока не опубликованы"
                  : path.lessons.every(
                        (lesson) => lesson.status === "completed",
                      )
                    ? "Все доступные уроки пройдены"
                    : "Следующий урок пока закрыт"}
              </h3>
              <p>
                {path.lessons.length === 0
                  ? "Здесь появятся материалы курса после публикации."
                  : plan.recommendation}
              </p>
              {plan.status === "assessment_required" && (
                <a className="button-secondary" href="/assessment">
                  Уточнить маршрут
                </a>
              )}
            </div>
          )}
          {compact ? (
            <div className="course-path-bottom">
              <p className="muted">
                Основы Python → работа с данными → backend и проекты. Никаких
                знаний для первого урока не требуется.
              </p>
              <a className="text-button" href="/learning/path">
                Посмотреть весь маршрут →
              </a>
            </div>
          ) : (
            <>
              {plan.learning_mode === "starter" && (
                <div className="course-starter-notice">
                  <strong>Можно учиться без диагностики</strong>
                  <p>
                    Начальный маршрут объясняет всё с нуля. Если вы уже пишете
                    код, необязательная диагностика поможет выбрать подходящую
                    точку старта.
                  </p>
                  <a href="/assessment">Уточнить, что я уже знаю →</a>
                </div>
              )}
              {phases.length > 0 && (
                <section
                  className="course-phases"
                  aria-labelledby="phases-title"
                >
                  <div className="panel-heading">
                    <h2 id="phases-title">Этапы обучения</h2>
                    <button
                      className="button-secondary"
                      type="button"
                      aria-pressed={activePhase === null}
                      onClick={() => setActivePhase(null)}
                    >
                      Все уроки
                    </button>
                  </div>
                  <div className="course-phase-grid">
                    {phases.map((phase, index) => (
                      <button
                        type="button"
                        key={phase.id}
                        className={
                          activePhase === phase.id
                            ? "course-phase-card course-phase-card-active"
                            : "course-phase-card"
                        }
                        aria-pressed={activePhase === phase.id}
                        onClick={() => setActivePhase(phase.id)}
                      >
                        <span className="course-phase-top">
                          <span className="course-phase-index">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="badge">
                            {phase.status === "completed"
                              ? "Пройден"
                              : phase.status === "available"
                                ? "Открыт"
                                : "Позже"}
                          </span>
                        </span>
                        <strong>{phase.title}</strong>
                        <span className="course-phase-description">
                          {phase.summary}
                        </span>
                        <span className="course-phase-count">
                          {phase.completed} из {phase.total} уроков пройдено
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
              <section
                className="panel path-lessons-panel"
                aria-labelledby="path-lessons-title"
              >
                <div className="panel-heading">
                  <div>
                    <h2 id="path-lessons-title">
                      {activePhase === null
                        ? "Все уроки курса"
                        : (phases.find((phase) => phase.id === activePhase)
                            ?.title ?? "Уроки этапа")}
                    </h2>
                    <p className="muted">
                      Уроки открываются после необходимых основ. Пройденный
                      материал можно повторить.
                    </p>
                  </div>
                  <span className="badge">{visibleLessons.length} уроков</span>
                </div>
                <div className="course-search-controls settings-form">
                  <label htmlFor="course-search">Найти урок
                    <input id="course-search" type="search" value={query}
                      placeholder="Например, функции или базы данных"
                      onChange={(event) => { setQuery(event.target.value); setActivePhase(null); }} />
                  </label>
                  <div>
                    <label htmlFor="course-status">Статус урока</label>
                    <select id="course-status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as LessonStatus | "all")}>
                      <option value="all">Все статусы</option>
                      <option value="available">Доступные</option>
                      <option value="completed">Пройденные</option>
                      <option value="locked">Откроются позже</option>
                    </select>
                  </div>
                </div>
                <p className="muted" role="status">Найдено уроков: {visibleLessons.length}.</p>
                {visibleLessons.length === 0 ? (
                  <div className="empty-state">
                  <p>
                    По этим условиям уроки не найдены. Попробуйте другое название или статус.
                  </p>
                  <button type="button" className="button-secondary" onClick={() => { setQuery(""); setStatusFilter("all"); setActivePhase(null); }}>Сбросить фильтры</button>
                  </div>
                ) : (
                  <ol className="course-path-list">
                    {visibleLessons.map((lesson) => (
                      <li
                        className={`course-path-item course-path-item-${lesson.status}`}
                        key={lesson.id}
                      >
                        <span className="course-path-number" aria-hidden="true">
                          {lesson.status === "completed"
                            ? "✓"
                            : String(
                                path.lessons.findIndex(
                                  (item) => item.id === lesson.id,
                                ) + 1,
                              ).padStart(2, "0")}
                        </span>
                        <div className="course-path-item-content">
                          <h3>{lesson.title}</h3>
                          <p className="muted">
                            Около {lesson.minutes} минут
                            {lesson.status === "locked"
                              ? " · сначала пройдите предыдущие основы"
                              : " · объяснение, пример и проверка"}
                          </p>
                        </div>
                        <span
                          className={`badge path-status path-status-${lesson.status}`}
                        >
                          {STATUS_LABELS[lesson.status]}
                        </span>
                        {lesson.status !== "locked" && (
                          <a
                            className="button-secondary"
                            href={`/learning?lesson=${encodeURIComponent(lesson.id)}`}
                          >
                            {lesson.status === "completed"
                              ? "Повторить"
                              : "Открыть"}
                            <span className="sr-only">: {lesson.title}</span>
                          </a>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          )}
        </>
      )}
    </section>
  );
}
