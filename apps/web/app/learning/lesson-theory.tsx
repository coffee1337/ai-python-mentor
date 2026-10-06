import type { Lesson } from "./lesson-types";
import RichText, { InlineText } from "./rich-text";
export default function LessonTheory({ lesson }: { lesson: Lesson }) {
  return (
    <div className="lesson-material">
      <section className="lesson-goal" aria-labelledby="lesson-goal-title">
        <span className="page-kicker">После этого урока</span>
        <h3 id="lesson-goal-title">Что вы научитесь делать</h3>
        <RichText
          text={
            lesson.goal ||
            `Разобраться в теме «${lesson.title}» и проверить понимание на небольших вопросах.`
          }
        />
        {lesson.why_it_matters && (
          <div className="lesson-why">
            <strong>Зачем это нужно</strong>
            <RichText text={lesson.why_it_matters} />
          </div>
        )}
      </section>

      <section aria-labelledby="lesson-explanation-title">
        <h3 id="lesson-explanation-title">Разберёмся по шагам</h3>
        {lesson.theory_sections?.length ? (
          lesson.theory_sections.map((section, index) => (
            <section
              className="lesson-explanation"
              key={`${index}.${section.title}`}
            >
              <h4>
                <span aria-hidden="true">{index + 1}. </span>
                {section.title}
              </h4>
              <RichText text={section.body} />
            </section>
          ))
        ) : (
          <RichText text={lesson.theory || lesson.body} />
        )}
      </section>

      {lesson.example && (
        <section
          className="lesson-example"
          aria-labelledby="lesson-example-title"
        >
          <h3 id="lesson-example-title">Посмотрим на пример</h3>
          <div className="code-block-label">
            <span>Python · пример из урока</span>
            <span>Читайте сверху вниз</span>
          </div>
          <pre className="lesson-code">
            <code>{lesson.example}</code>
          </pre>
          {lesson.example_walkthrough?.length ? (
            <ol className="example-walkthrough">
              {lesson.example_walkthrough.map((item, index) => (
                <li key={`${item.line}.${index}`}>
                  <span className="example-line-label">Строка {item.line}</span>
                  <RichText text={item.explanation} />
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">
              Сравните строки примера с объяснением выше. Непонятную команду
              можно разобрать с наставником справа.
            </p>
          )}
          {lesson.example_output && (
            <div className="example-output">
              <h4>Ожидаемый вывод этого примера</h4>
              <pre>
                <code>{lesson.example_output}</code>
              </pre>
              <p className="muted">
                Это результат из учебного материала. Код на этой странице сейчас
                не запускался.
              </p>
            </div>
          )}
        </section>
      )}

      {lesson.checkpoint && (
        <section className="lesson-pause" aria-labelledby="lesson-pause-title">
          <span className="badge">Без оценки</span>
          <h3 id="lesson-pause-title">Остановитесь на минуту</h3>
          <RichText text={lesson.checkpoint.prompt} />
          {lesson.checkpoint.choices.length > 0 && (
            <ul>
              {lesson.checkpoint.choices.map((choice) => (
                <li key={choice}>
                  <InlineText text={choice} />
                </li>
              ))}
            </ul>
          )}
          <p className="muted">
            Выберите ответ мысленно и попробуйте объяснить его по примеру.
            Следующий шаг проверит понимание и покажет объяснение ответа.
          </p>
        </section>
      )}

      {lesson.misconception && (
        <details className="lesson-detail">
          <summary>На что легко ошибиться</summary>
          <RichText text={lesson.misconception} />
          {lesson.misconception_check && (
            <RichText text={lesson.misconception_check.prompt} />
          )}
        </details>
      )}
      {lesson.glossary && lesson.glossary.length > 0 && (
        <details className="lesson-detail">
          <summary>Новые слова простым языком</summary>
          <dl className="lesson-glossary">
            {lesson.glossary.map((entry) => (
              <div key={entry.term}>
                <dt>{entry.term}</dt>
                <dd>
                  <RichText text={entry.definition} />
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      {lesson.conclusion && (
        <section className="lesson-conclusion">
          <h3>Что стоит запомнить</h3>
          <RichText text={lesson.conclusion} />
        </section>
      )}
    </div>
  );
}
