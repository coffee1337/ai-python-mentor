import type { Lesson } from "./lesson-types";

type LessonTheoryProps = {
  lesson: Lesson;
};

/**
 * Authored lesson material only. Nothing here is generated at render time and
 * nothing here claims the code was executed — the runner is fail-closed.
 */
export default function LessonTheory({ lesson }: LessonTheoryProps) {
  return (
    <div className="lesson-body">
      {lesson.goal && <p className="lead">{lesson.goal}</p>}
      {lesson.theory ? (
        <>
          <h3>Теория</h3>
          <p>{lesson.theory}</p>
        </>
      ) : (
        lesson.body && <p>{lesson.body}</p>
      )}
      {lesson.example && (
        <>
          <h3>Пример</h3>
          <pre>
            <code>{lesson.example}</code>
          </pre>
        </>
      )}
      {lesson.example_output && (
        <pre>
          <code>{lesson.example_output}</code>
        </pre>
      )}
      {lesson.checkpoint && (
        <>
          <h3>Чекпоинт</h3>
          <p>{lesson.checkpoint.prompt}</p>
          <ul>
            {lesson.checkpoint.choices.map((choice, index) => (
              <li key={choice}>{choice}</li>
            ))}
          </ul>
        </>
      )}
      {lesson.misconception && (
        <>
          <h3>Типичная ошибка</h3>
          <p>{lesson.misconception}</p>
        </>
      )}
      {lesson.misconception_check && (
        <>
          <h3>Проверка понимания</h3>
          <p>{lesson.misconception_check.prompt}</p>
        </>
      )}
      {lesson.practice && (
        <>
          <h3>Практика</h3>
          <p>{lesson.practice}</p>
        </>
      )}
      {lesson.conclusion && (
        <>
          <h3>Вывод</h3>
          <p>{lesson.conclusion}</p>
        </>
      )}
    </div>
  );
}
