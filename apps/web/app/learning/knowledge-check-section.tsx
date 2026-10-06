"use client";
import { FormEvent } from "react";
import type { CheckQuestion, CheckResult } from "./lesson-types";
import RichText, { InlineText } from "./rich-text";
type KnowledgeCheckSectionProps = {
  questions: CheckQuestion[];
  answers: Record<string, string>;
  onAnswerChange: (questionId: string, choice: string) => void;
  result: CheckResult | null;
  onSubmit: (event: FormEvent) => void;
  onRetry: () => void;
  busy: boolean;
  loading?: boolean;
  error?: string;
  reloadRequired?: boolean;
  onReload?: () => void;
};
export default function KnowledgeCheckSection({
  questions,
  answers,
  onAnswerChange,
  result,
  onSubmit,
  onRetry,
  busy,
  loading = false,
  error = "",
  reloadRequired = false,
  onReload,
}: KnowledgeCheckSectionProps) {
  const correctCount =
    result?.explanations.filter((item) => item.correct === "true").length ?? 0;
  const incomplete = questions.some((question) => !answers[question.id]);

  return (
    <section
      className="knowledge-check"
      aria-labelledby="knowledge-check-title"
      aria-busy={loading || busy}
    >
      <p className="page-kicker">Шаг 2 · вопросы по уроку</p>
      <h2 id="knowledge-check-title">Проверим понимание</h2>
      <p className="muted">
        Прочитайте вопрос и выберите один ответ. Объяснение можно открыть снова
        в первом шаге. Ошибка покажет, что нужно разобрать подробнее, — это
        часть обучения.
      </p>
      {loading && (
        <p className="status-message" role="status">
          Загружаем вопросы…
        </p>
      )}
      {error && (
        <div className="status-message" role="alert">
          <p>{error}</p>
          {(questions.length === 0 || reloadRequired) && (
            <button
              className="button-secondary"
              type="button"
              disabled={loading || busy}
              onClick={onReload}
            >
              {reloadRequired
                ? "Загрузить проверку заново"
                : "Повторить загрузку вопросов"}
            </button>
          )}
          {reloadRequired && (
            <p className="muted">
              Перед отправкой нужно загрузить проверку заново. После успешной
              загрузки появится новая форма; выбранные варианты сбросятся.
            </p>
          )}
        </div>
      )}
      {!loading && questions.length === 0 && !result && !error && (
        <div className="empty-state">
          <h3>Проверка пока не опубликована</h3>
          <p>
            Материал можно изучать, но завершение урока ещё не подтвердится.
            Выберите другой доступный урок в маршруте.
          </p>
          <a href="/learning/path">Открыть учебный путь</a>
        </div>
      )}
      {!loading && result && (
        <div className="knowledge-result">
          <div
            className={
              result.passed
                ? "check-verdict check-verdict-passed"
                : "check-verdict"
            }
            role="status"
          >
            <strong>
              {result.passed ? "Урок пройден" : "Есть что разобрать ещё раз"}
            </strong>
            <p>
              Верных ответов: {correctCount} из {result.explanations.length}.{" "}
              {result.passed
                ? "Завершение подтверждено проверкой на сервере."
                : "Вернитесь к объяснению, затем попробуйте снова."}
            </p>
          </div>
          <ol className="check-feedback">
            {result.explanations.map((item, index) => (
              <li key={item.question_id}>
                <span className="badge">
                  Вопрос {index + 1} ·{" "}
                  {item.correct === "true" ? "Верно" : "Разберём ответ"}
                </span>
                <RichText
                  text={item.selected_explanation ?? item.explanation}
                />
              </li>
            ))}
          </ol>
          <RichText text={result.recommendation} />
          {!result.passed && (
            <button
              type="button"
              className="button"
              onClick={onRetry}
              disabled={busy}
            >
              Попробовать ещё раз
            </button>
          )}
          {result.passed && result.recommended_lesson_id && (
            <a
              className="button"
              href={`/learning?lesson=${encodeURIComponent(result.recommended_lesson_id)}`}
            >
              Следующий рекомендованный урок →
            </a>
          )}
        </div>
      )}
      {!loading && !result && questions.length > 0 && (
        <form onSubmit={onSubmit} className="knowledge-check-form">
          {questions.map((question, index) => (
            <fieldset
              className="knowledge-question"
              key={question.id}
              disabled={busy}
            >
              <legend>
                <span className="question-number">
                  Вопрос {index + 1} из {questions.length}
                </span>
                <InlineText text={question.prompt} />
              </legend>
              <div className="knowledge-choices">
                {question.choices.map((choice) => (
                  <label
                    key={choice}
                    className={
                      answers[question.id] === choice
                        ? "knowledge-choice knowledge-choice-selected"
                        : "knowledge-choice"
                    }
                  >
                    <input
                      type="radio"
                      name={question.id}
                      value={choice}
                      checked={answers[question.id] === choice}
                      onChange={() => onAnswerChange(question.id, choice)}
                      required
                    />
                    <span>
                      <InlineText text={choice} />
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <div className="check-submit-row">
            <button
              type="submit"
              className="button"
              disabled={busy || incomplete || reloadRequired}
            >
              {busy ? "Проверяем ответы…" : "Проверить ответы"}
            </button>
            <p className="muted">
              {reloadRequired
                ? "Сначала загрузите проверку заново."
                : incomplete
                  ? "Выберите ответ на каждый вопрос."
                  : "После отправки появится объяснение каждого ответа."}
            </p>
          </div>
        </form>
      )}
    </section>
  );
}
