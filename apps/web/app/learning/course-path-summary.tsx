import type { PathSummary } from "./lesson-types";
export default function CoursePathSummary({
  path,
  currentLessonId,
}: {
  path: PathSummary;
  currentLessonId?: string;
}) {
  const currentIndex = path.lessons.findIndex(
    (item) => item.id === currentLessonId,
  );
  const next = path.lessons.find(
    (item) => item.id === path.next_lesson_id && item.id !== currentLessonId,
  );
  return (
    <section
      className="panel lesson-route"
      aria-labelledby="lesson-route-title"
    >
      <p className="page-kicker">Ваш маршрут</p>
      <h2 id="lesson-route-title">Шаг за шагом</h2>
      {path.total > 0 ? (
        <>
          <p>
            Пройдено {path.completed} из {path.total} уроков
          </p>
          <progress
            aria-label="Пройденные уроки курса"
            value={path.completed}
            max={path.total}
          />
          {currentIndex >= 0 && (
            <p className="muted">
              Сейчас вы изучаете урок {currentIndex + 1}:{" "}
              {path.lessons[currentIndex].title}.
            </p>
          )}
          {next && (
            <div className="lesson-route-next">
              <span className="badge">Следующий доступный</span>
              <p>{next.title}</p>
              <a href={`/learning?lesson=${encodeURIComponent(next.id)}`}>
                Открыть урок →
              </a>
            </div>
          )}
        </>
      ) : (
        <p role="status">Материалы пока не опубликованы.</p>
      )}
      <a className="button-secondary" href="/learning/path">
        Весь учебный путь
      </a>
    </section>
  );
}
