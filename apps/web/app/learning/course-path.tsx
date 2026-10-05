"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type LessonStatus = "completed" | "available" | "locked";

type LearningPathResponse = {
  title: string;
  completed: number;
  total: number;
  next_lesson_id: string | null;
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

type PhaseSummary = {
  id: number;
  title: string;
  summary: string;
  status: LessonStatus;
  completed: number;
  total: number;
  next_lesson_id: string | null;
};

type LearningPlanResponse = {
  status: "ready" | "assessment_required";
  recommendation: string;
  recommended_lesson_id: string | null;
  items: {
    lesson_id: string;
    title: string;
    status: string;
    rationale: string;
  }[];
};

type CoursePathProps = {
  variant: "dashboard" | "full";
};

const PHASE_LABELS: Record<string, string> = {
  completed: "Пройдена",
  available: "Открыта",
  locked: "Пока закрыта",
};

function PhaseOverview({ phases }: { phases: PhaseSummary[] }) {
  const published = phases.filter((phase) => phase.total > 0);
  if (published.length === 0) return null;

  return (
    <section className="course-phases" aria-labelledby="phases-title">
      <h3 id="phases-title" className="course-phases-title">
        Этапы курса
      </h3>
      <p className="course-path-intro">
        Этапы открываются по мере прохождения предыдущих. Процент mastery не
        показываем: видно, сколько уроков этапа уже закрыто.
      </p>
      <ol className="course-phases-list">
        {published.map((phase) => (
          <li
            className={`course-phase-item course-phase-item-${phase.status}`}
            key={phase.id}
          >
            <div className="course-phase-item-heading">
              <span className="course-phase-index" aria-hidden="true">
                {String(phase.id).padStart(2, "0")}
              </span>
              <div>
                <h4>{phase.title}</h4>
                <p className="muted">{phase.summary}</p>
              </div>
              <span className={`course-phase-status course-phase-status-${phase.status}`}>
                {phase.status === "completed" ? <span aria-hidden="true">✓ </span> : null}
                {PHASE_LABELS[phase.status]}
              </span>
            </div>
            <p className="course-phase-count">
              Закрыто уроков: {phase.completed} из {phase.total}
            </p>
            {phase.status === "available" && phase.next_lesson_id ? (
              <a href={`/learning?lesson=${encodeURIComponent(phase.next_lesson_id)}`}>
                Начать этап <span aria-hidden="true">→</span>
              </a>
            ) : null}
            {phase.status === "locked" ? (
              <p className="course-path-lock-note">
                Этап откроется после прохождения предыдущего.
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function CoursePath({ variant }: CoursePathProps) {
  const [path, setPath] = useState<LearningPathResponse | null>(null);
  const [plan, setPlan] = useState<LearningPlanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [requestNumber, setRequestNumber] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setHasError(false);

    void Promise.all([
      api<LearningPathResponse>("/learning/path"),
      api<LearningPlanResponse>("/learning/plan"),
    ])
      .then(([nextPath, nextPlan]) => {
        if (!current) return;
        setPath(nextPath);
        setPlan(nextPlan);
      })
      .catch(() => {
        if (current) setHasError(true);
      })
      .finally(() => {
        if (current) setLoading(false);
      });

    return () => {
      current = false;
    };
  }, [requestNumber]);

  function retry() {
    setRequestNumber((number) => number + 1);
  }

  const compact = variant === "dashboard";
  const nextLesson =
    path?.lessons.find(
      (lesson) => lesson.id === path.next_lesson_id && lesson.status === "available",
    ) ?? null;
  const nextPlanItem = nextLesson
    ? plan?.items.find((item) => item.lesson_id === nextLesson.id)
    : null;
  const hasLessons = Boolean(path && path.lessons.length > 0);

  if (loading) {
    return (
      <section className="course-path" aria-labelledby={compact ? "continue-title" : "path-title"}>
        {compact ? <h2 id="continue-title">Продолжить обучение</h2> : <h1 id="path-title">Учебный путь Python</h1>}
        <p role="status" aria-live="polite">Загружаем учебный путь…</p>
      </section>
    );
  }

  if (hasError || !path || !plan) {
    return (
      <section className="course-path" aria-labelledby={compact ? "continue-title" : "path-title"}>
        {compact ? <h2 id="continue-title">Продолжить обучение</h2> : <h1 id="path-title">Учебный путь Python</h1>}
        <div className="course-path-state" role="alert">
          <p className="form-error">Не удалось загрузить учебный путь. Попробуйте ещё раз.</p>
          <button className="text-button" type="button" onClick={retry}>
            Повторить
          </button>
        </div>
      </section>
    );
  }

  const routeSummary =
    path.total > 0 ? (
      <p className="course-path-summary">
        Завершено {path.completed} из {path.total} уроков
      </p>
    ) : null;

  if (compact) {
    return (
      <section className="course-path course-path-compact" aria-labelledby="continue-title">
        <div className="course-path-heading">
          <div>
            <span className="eyebrow"><i aria-hidden="true" /> ВАШ УЧЕБНЫЙ ПУТЬ</span>
            <h2 id="continue-title">Продолжить обучение</h2>
          </div>
          {routeSummary}
        </div>

        {!hasLessons ? (
          <div className="course-path-state">
            <p role="status">В учебном пути пока нет опубликованных уроков.</p>
            {plan.status === "assessment_required" && (
              <a className="primary-button" href="/assessment">
                Начать диагностику <span aria-hidden="true">↗</span>
              </a>
            )}
          </div>
        ) : plan.status === "assessment_required" ? (
          <div className="course-path-recommendation">
            <p>{plan.recommendation}</p>
            <a className="primary-button" href="/assessment">
              Начать диагностику <span aria-hidden="true">↗</span>
            </a>
          </div>
        ) : nextLesson ? (
          <div className="course-path-recommendation">
            <p className="course-path-next-label">СЛЕДУЮЩИЙ ДОСТУПНЫЙ УРОК</p>
            <h3>{nextLesson.title}</h3>
            {nextPlanItem?.rationale ? (
              <p className="muted">{nextPlanItem.rationale}</p>
            ) : (
              <p className="muted">Следующий доступный урок в вашем маршруте.</p>
            )}
            <p className="course-path-duration">{nextLesson.minutes} мин</p>
            <a className="primary-button" href={`/learning?lesson=${encodeURIComponent(nextLesson.id)}`}>
              Продолжить <span aria-hidden="true">↗</span>
            </a>
          </div>
        ) : (
          <p className="course-path-state" role="status">
            {path.lessons.every((lesson) => lesson.status === "completed")
              ? plan.recommendation
              : "Сейчас нет доступного урока; подробная причина блокировки не передана сервером."}
          </p>
        )}

        <PhaseOverview phases={path.phases ?? []} />

        <a className="course-path-all-link" href="/learning/path">
          Весь учебный путь <span aria-hidden="true">→</span>
        </a>
      </section>
    );
  }

  return (
    <section className="course-path" aria-labelledby="path-title">
      <span className="eyebrow"><i aria-hidden="true" /> ВАШ МАРШРУТ</span>
      <h1 id="path-title">Учебный путь Python</h1>
      {routeSummary}
      <p className="course-path-intro">
        Уроки показаны в порядке маршрута. Следующий шаг откроется после необходимых основ.
      </p>

      <PhaseOverview phases={path.phases ?? []} />

      {plan.status === "assessment_required" && (
        <aside className="course-path-notice">
          <p>{plan.recommendation}</p>
          <a href="/assessment">Перейти к диагностике →</a>
        </aside>
      )}

      {!hasLessons ? (
        <p className="course-path-state" role="status">
          В учебном пути пока нет опубликованных уроков.
        </p>
      ) : (
        <ol className="course-path-list" aria-label="Уроки в порядке прохождения">
          {path.lessons.map((lesson, index) => {
            const isNext = lesson.id === path.next_lesson_id;
            return (
              <li
                className={`course-path-item course-path-item-${lesson.status}${isNext ? " course-path-item-next" : ""}`}
                key={lesson.id}
                aria-posinset={index + 1}
                aria-setsize={path.lessons.length}
              >
                <span className="course-path-number" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="course-path-item-content">
                  <div className="course-path-item-heading">
                    <h2>{lesson.title}</h2>
                    <span className={`course-path-status course-path-status-${lesson.status}`}>
                      {lesson.status === "completed" && <span aria-hidden="true">✓ </span>}
                      {lesson.status === "completed"
                        ? "Завершён"
                        : lesson.status === "available"
                          ? "Доступен"
                          : "Пока закрыт"}
                    </span>
                  </div>
                  <p className="course-path-duration">{lesson.minutes} мин</p>
                  {lesson.status === "locked" ? (
                    <p className="course-path-lock-note">
                      Урок пока недоступен по текущим условиям маршрута.
                    </p>
                  ) : (
                    <a
                      className={isNext ? "course-path-action course-path-action-primary" : "course-path-action"}
                      href={`/learning?lesson=${encodeURIComponent(lesson.id)}`}
                    >
                      {lesson.status === "completed"
                        ? "Повторить урок"
                        : isNext
                          ? "Начать урок"
                          : "Открыть урок"}
                      <span aria-hidden="true"> →</span>
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {hasLessons && plan.status === "ready" && !path.next_lesson_id && (
        <p className="course-path-state" role="status">
          {path.lessons.every((lesson) => lesson.status === "completed")
            ? plan.recommendation
            : "Сейчас нет доступного урока; подробная причина блокировки не передана сервером."}
        </p>
      )}
    </section>
  );
}

export default CoursePath;
