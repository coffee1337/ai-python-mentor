"use client";

import type { PathSummary } from "./lesson-types";

type CoursePathSummaryProps = {
  path: PathSummary;
};

const STATUS_LABELS = {
  completed: "Завершён",
  available: "Доступен",
  locked: "Пока закрыт",
} as const;

/**
 * Compact route summary shown above the lesson. The full interactive route lives
 * in `course-path.tsx`; this block must not duplicate it. Progress is a count of
 * completed lessons, not a mastery percentage.
 */
export default function CoursePathSummary({ path }: CoursePathSummaryProps) {
  if (path.lessons.length === 0) {
    return (
      <section className="lesson-route" aria-labelledby="lesson-route-title">
        <h2 id="lesson-route-title">Ваш маршрут</h2>
        <p role="status">В учебном пути пока нет опубликованных уроков.</p>
        <a className="text-button" href="/learning/path">
          Открыть учебный путь
        </a>
      </section>
    );
  }

  return (
    <section className="lesson-route" aria-labelledby="lesson-route-title">
      <h2 id="lesson-route-title">Ваш маршрут</h2>
      <p>
        Завершено уроков: {path.completed} из {path.total}
      </p>
      <ol>
        {path.lessons.map((item) => (
          <li key={item.id}>
            {item.title} · {item.minutes} мин · {STATUS_LABELS[item.status]}
          </li>
        ))}
      </ol>
      <a className="text-button" href="/learning/path">
        Весь учебный путь
      </a>
    </section>
  );
}
