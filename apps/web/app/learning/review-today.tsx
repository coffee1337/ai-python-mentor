"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

type ReviewQuestion = {
  id: string;
  prompt: string;
  choices: string[];
};

type ReviewItem = {
  review_token: string;
  skill_id: string;
  scheduled_for: string;
  overdue_days: number;
  questions: ReviewQuestion[];
};

type ReviewsResponse = {
  as_of: string;
  items: ReviewItem[];
};

type ReviewResult = {
  status: "recorded" | "replayed";
  outcome: "correct" | "partial" | "incorrect";
  schedule_applied: boolean;
  same_day: boolean;
  next_review_at: string | null;
};

type ReviewTodayProps = {
  onReviewPlanChanged?: () => void;
};

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "дата недоступна";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function formatCalendarDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return "дата недоступна";
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function dayWord(days: number): string {
  if (days % 10 === 1 && days % 100 !== 11) return "день";
  if (days % 10 >= 2 && days % 10 <= 4 && (days % 100 < 10 || days % 100 >= 20)) return "дня";
  return "дней";
}

function outcomeCopy(outcome: ReviewResult["outcome"]): string {
  if (outcome === "correct") return "Получилось восстановить решение.";
  if (outcome === "partial") return "Часть решения восстановилась. Можно вернуться к теме ещё раз.";
  return "Сегодня решение не вспомнилось. Это не штраф; материал можно освежить и попробовать позже.";
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `review-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ReviewToday({ onReviewPlanChanged }: ReviewTodayProps) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [results, setResults] = useState<Record<string, ReviewResult>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [lastCompletedSkill, setLastCompletedSkill] = useState<string | null>(null);
  const resultRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const idempotencyKeys = useRef<Record<string, string>>({});

  async function loadReviews() {
    setLoading(true);
    setLoadError(false);
    try {
      const response = await api<ReviewsResponse>("/learning/reviews/today");
      setItems(response.items);
      setAnswers({});
      setResults({});
    } catch {
      setItems(null);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReviews();
  }, []);

  useEffect(() => {
    if (!lastCompletedSkill) return;
    resultRefs.current[lastCompletedSkill]?.focus();
  }, [lastCompletedSkill]);

  function updateAnswer(skillId: string, questionId: string, answer: string) {
    setAnswers((current) => ({
      ...current,
      [skillId]: { ...current[skillId], [questionId]: answer },
    }));
  }

  async function submitReview(event: FormEvent<HTMLFormElement>, item: ReviewItem) {
    event.preventDefault();
    if (submitting || results[item.skill_id]) return;

    setSubmitting(item.skill_id);
    setSubmitError(false);
    try {
      const result = await api<ReviewResult>("/learning/reviews/today/complete", {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKeys.current[item.skill_id] ?? (idempotencyKeys.current[item.skill_id] = newIdempotencyKey()),
        },
        body: JSON.stringify({
          review_token: item.review_token,
          answers: answers[item.skill_id] ?? {},
        }),
      });
      setResults((current) => ({ ...current, [item.skill_id]: result }));
      setLastCompletedSkill(item.skill_id);
      onReviewPlanChanged?.();
    } catch {
      setSubmitError(true);
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <section className="review-today" id="reviews-today" aria-labelledby="reviews-today-heading" aria-busy={loading}>
      <div className="review-today-heading">
        <div>
          <p className="eyebrow">ПОВТОРЕНИЕ</p>
          <h2 id="reviews-today-heading">Повторить сегодня</h2>
        </div>
        <p className="review-today-note">
          Это короткая проверка уже знакомого навыка после паузы. Она помогает понять, что сохранилось, а что стоит
          освежить. Это не новый урок и не оценка вас.
        </p>
      </div>

      {loading && (
        <p className="review-status" role="status" aria-live="polite">
          Загружаем повторения…
        </p>
      )}

      {!loading && loadError && (
        <div className="review-state" role="alert">
          <p>Не удалось загрузить или сохранить повторение. Попробуйте ещё раз.</p>
          <button className="text-button" type="button" onClick={() => void loadReviews()}>
            Повторить загрузку
          </button>
        </div>
      )}

      {!loading && !loadError && items?.length === 0 && (
        <p className="review-state" role="status" aria-live="polite">
          На сегодня повторений нет. Можно продолжить новый материал или вернуться позже.
        </p>
      )}

      {!loading && !loadError && items && items.length > 0 && (
        <div className="review-list">
          {submitError && (
            <div className="review-state" role="alert">
              <p>Не удалось сохранить ответ. Ваши ответы остались в форме — попробуйте ещё раз.</p>
            </div>
          )}
          {items.map((item) => {
            const result = results[item.skill_id];
            const itemAnswers = answers[item.skill_id] ?? {};
            const isSubmitting = submitting === item.skill_id;
            const hasAllAnswers = item.questions.every((question) => itemAnswers[question.id]);
            const isOverdue = item.overdue_days > 0;

            return (
              <article className="review-card" key={item.skill_id}>
                <div className="review-card-header">
                  <div>
                    <p className="review-kind">Повторение</p>
                    <h3>Тема, к которой стоит вернуться</h3>
                  </div>
                  <span className={isOverdue ? "review-due review-due-overdue" : "review-due"}>
                    {isOverdue ? "Позже запланированного" : "Пора вернуться к теме"}
                  </span>
                </div>

                <p className="review-explanation">
                  {isOverdue
                    ? `Повторение позже запланированного на ${item.overdue_days} ${dayWord(item.overdue_days)}. Это не штраф — начните, когда будет удобно.`
                    : `Повторение запланировано на ${formatCalendarDate(item.scheduled_for)}.`}
                </p>

                {result ? (
                  <div
                    className="review-result"
                    ref={(node) => {
                      resultRefs.current[item.skill_id] = node;
                    }}
                    tabIndex={-1}
                    role="status"
                    aria-live="polite"
                  >
                    <strong>Повторение записано.</strong>
                    <p>{outcomeCopy(result.outcome)}</p>
                    <p>
                      Повторение показывает сохранность ранее изученного навыка. Оно не заменяет проверку нового
                      материала и не добавляет credit за освоение новой темы.
                    </p>
                    {result.same_day && !result.schedule_applied ? (
                      <p>
                        Сегодняшний ориентир уже был обновлён, поэтому следующая дата не изменилась.
                      </p>
                    ) : result.next_review_at ? (
                      <p>Следующий ориентир: примерно {formatDate(result.next_review_at)}.</p>
                    ) : null}
                  </div>
                ) : (
                  <form onSubmit={(event) => void submitReview(event, item)}>
                    {item.questions.map((question, questionIndex) => {
                      const inputGroup = `${item.skill_id}-${question.id}`;
                      return (
                        <fieldset className="review-question" key={question.id} disabled={isSubmitting}>
                          <legend>
                            {questionIndex + 1}. {question.prompt}
                          </legend>
                          <div className="review-choices">
                            {question.choices.map((choice) => (
                              <label className="review-choice" key={choice} htmlFor={`${inputGroup}-${choice}`}>
                                <input
                                  id={`${inputGroup}-${choice}`}
                                  name={inputGroup}
                                  type="radio"
                                  value={choice}
                                  checked={itemAnswers[question.id] === choice}
                                  onChange={() => updateAnswer(item.skill_id, question.id, choice)}
                                />
                                <span>{choice}</span>
                              </label>
                            ))}
                          </div>
                        </fieldset>
                      );
                    })}
                    <button className="review-submit" type="submit" disabled={isSubmitting || !hasAllAnswers}>
                      {isSubmitting ? "Сохраняем…" : "Сохранить ответы"}
                    </button>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
