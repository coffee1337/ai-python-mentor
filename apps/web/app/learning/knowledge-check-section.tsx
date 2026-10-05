"use client";

import { FormEvent } from "react";
import type { CheckQuestion, CheckResult } from "./lesson-types";

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
  onReload?: () => void;
};

/**
 * Authored knowledge check. Per the project invariant the server decides what is
 * correct, so this component only renders the verdict it was given and never
 * grades locally. The score is shown as a count of correct answers, not as a
 * mastery percentage: mastery is a model estimate, not a level of the learner.
 */
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
  onReload,
}: KnowledgeCheckSectionProps) {
  if (loading || error) {
    return <section aria-label="Проверка знаний"><h3>Проверка усвоения</h3>
      {loading && <p role="status">Загружаем вопросы…</p>}
      {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" type="button" disabled={loading} onClick={onReload}>Повторить загрузку вопросов</button></div>}
    </section>;
  }
  if (questions.length === 0 && !result) {
    return (
      <section aria-label="Проверка знаний">
        <h3>Проверка усвоения</h3>
        <p role="status">
          Для этого урока ещё нет вопросов. Проверка появится, когда наставник
          опубликует вопросы.
        </p>
      </section>
    );
  }

  if (result) {
    const correctCount = result.explanations.filter((item) => item.correct === "true").length;
    return (
      <section aria-label="Проверка знаний">
        <h3>Проверка усвоения</h3>
        <p role="status">
          Верных ответов: {correctCount} из {result.explanations.length}.{" "}
          {result.passed
            ? "Урок засчитан как пройденный."
            : "Пока недостаточно правильных ответов."}
        </p>
        <ul>
          {result.explanations.map((item) => (
            <li key={item.question_id}>
              {item.correct === "true" ? "Верно. " : "Ответ неверный. "}
              {item.selected_explanation ?? item.explanation}
            </li>
          ))}
        </ul>
        <p className="muted">{result.recommendation}</p>
        {!result.passed && (
          <button type="button" className="text-button" onClick={onRetry} disabled={busy}>
            Повторить проверку
          </button>
        )}
        {result.passed && result.recommended_lesson_id && (
          <p>
            <a href={"/learning?lesson=" + encodeURIComponent(result.recommended_lesson_id)}>
              Открыть следующий рекомендованный урок →
            </a>
          </p>
        )}
      </section>
    );
  }

  const incomplete = questions.some((question) => !answers[question.id]);

  return (
    <section aria-label="Проверка знаний">
      <h3>Проверка усвоения</h3>
      <form onSubmit={onSubmit}>
        {questions.map((question) => (
          <fieldset key={question.id} disabled={busy}>
            <legend>{question.prompt}</legend>
            {question.choices.map((choice) => (
              <label key={choice} className="knowledge-choice">
                <input
                  type="radio"
                  name={question.id}
                  value={choice}
                  checked={answers[question.id] === choice}
                  onChange={() => onAnswerChange(question.id, choice)}
                  required
                />
                {" "}
                {choice}
              </label>
            ))}
          </fieldset>
        ))}
        <button type="submit" className="form-button" disabled={busy || incomplete}>
          {busy ? "Проверяем…" : "Проверить усвоение"}
        </button>
      </form>
    </section>
  );
}
