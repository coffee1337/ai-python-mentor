"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import StudySessionPanel from "../components/study-session-panel";
import { api, errorMessage, isUnauthorized } from "../lib/api";
import { skillLabel } from "../learning/skill-labels";
import type { StudyToday } from "../learning/study-types";

function calendarDate(value: string) {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "Дата недоступна";
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
  });
}

export default function TodayFocus() {
  const router = useRouter();
  const [today, setToday] = useState<StudyToday | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestNumber, setRequestNumber] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void api<StudyToday>("/learning/today", { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setToday(result);
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
  }, [requestNumber, router]);

  const focus = today?.focus.slice(0, 6) ?? [];
  const nextLesson = today?.next_lesson;
  const hasReviews = (today?.due_reviews.length ?? 0) > 0;

  return (
    <>
      <section
        className="panel today-focus"
        aria-labelledby="today-focus-title"
        aria-busy={loading}
      >
        <div className="panel-heading">
          <div>
            <p className="page-kicker">В удобном темпе</p>
            <h2 id="today-focus-title">На сегодня</h2>
          </div>
          <Link className="text-button" href="/learning/progress">
            Мой прогресс →
          </Link>
        </div>

        {loading && (
          <p className="status-message" role="status">
            Готовим следующий шаг и повторения…
          </p>
        )}
        {!loading && error && (
          <div className="status-message product-error" role="alert">
            <p>{error}</p>
            <div className="product-action-row">
              <button
                className="button-secondary"
                type="button"
                onClick={() => setRequestNumber((number) => number + 1)}
              >
                Повторить загрузку
              </button>
              <Link href="/learning/path">Открыть программу курса</Link>
            </div>
          </div>
        )}
        {!loading && !error && today && (
          <>
            <div className="today-primary-action">
              {nextLesson ? (
                <>
                  <div>
                    <span className="badge">
                      {nextLesson.is_resume ? "Начатый урок" : "Следующий урок"}
                    </span>
                    <h3>{nextLesson.title}</h3>
                    <p className="muted">
                      Примерно {nextLesson.minutes} минут. Можно остановиться и
                      продолжить позже.
                    </p>
                  </div>
                  <Link
                    className="button"
                    href={`/learning?lesson=${encodeURIComponent(nextLesson.id)}`}
                  >
                    {nextLesson.is_resume ? "Продолжить урок" : "Открыть урок"} →
                  </Link>
                </>
              ) : hasReviews ? (
                <>
                  <div>
                    <h3>Вернитесь к знакомым темам</h3>
                    <p className="muted">
                      Нового урока сейчас нет. Назначенные повторения помогут
                      восстановить изученное.
                    </p>
                  </div>
                  <Link className="button" href="/learning/reviews">
                    Открыть повторения →
                  </Link>
                </>
              ) : (
                <div className="empty-state">
                  <h3>На сегодня нет назначенных заданий</h3>
                  <p>
                    Можно вернуться к пройденному материалу. Доступные уроки и
                    условия открытия следующих тем есть в программе курса.
                  </p>
                  <Link className="button-secondary" href="/learning/path">
                    Посмотреть программу курса
                  </Link>
                </div>
              )}
            </div>

            <div className="today-review-summary">
              <div>
                <h3>Повторение изученного</h3>
                <p className="muted">
                  {hasReviews
                    ? `Тем для повторения: ${today.due_reviews.length}. Начните, когда удобно; опоздание не является штрафом.`
                    : "На сегодня повторений нет. Они появятся после изучения темы и небольшой паузы."}
                </p>
              </div>
              {hasReviews && nextLesson && (
                <Link className="button-secondary" href="/learning/reviews">
                  Повторить темы
                </Link>
              )}
              {hasReviews && (
                <ul className="today-review-list">
                  {today.due_reviews.slice(0, 3).map((review) => (
                    <li key={review.skill_id}>
                      <strong>{skillLabel(review.skill_id)}</strong>
                      <span className="muted">
                        {review.overdue_days > 0
                          ? "Позже запланированного"
                          : `Запланировано на ${calendarDate(review.scheduled_for)}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {today.due_reviews.length > 3 && (
                <p className="muted">
                  Все назначенные темы доступны на странице повторений.
                </p>
              )}
            </div>

            {focus.length > 0 && (
              <details className="product-disclosure today-session">
                <summary>План короткой учебной сессии</summary>
                <p className="muted">
                  Примерная длительность всего плана: {today.estimated_minutes}
                  {" "}минут.
                  {today.target_minutes > 0 &&
                    ` Ориентир по вашему темпу: ${today.target_minutes} минут.`}
                  {" "}Это оценка времени, а не обязательный срок.
                </p>
                <ol className="today-focus-list">
                  {focus.map((activity, index) => (
                    <li
                      key={`${activity.kind}.${activity.lesson_id ?? activity.skill_id}.${index}`}
                    >
                      <span className="badge">
                        {activity.kind === "review" ? "Повторение" : "Урок"}
                      </span>
                      <div>
                        <strong>{activity.title}</strong>
                        <span className="muted">
                          Примерно {activity.estimated_minutes} минут
                        </span>
                      </div>
                      {activity.kind === "review" ? (
                        <Link href="/learning/reviews">Повторить →</Link>
                      ) : activity.lesson_id ? (
                        <Link
                          href={`/learning?lesson=${encodeURIComponent(activity.lesson_id)}`}
                        >
                          Открыть →
                        </Link>
                      ) : (
                        <span className="muted">Материал пока не опубликован</span>
                      )}
                    </li>
                  ))}
                </ol>
                {today.focus.length > focus.length && (
                  <p className="muted">
                    Показаны первые {focus.length} занятий. Остальные материалы
                    есть в программе курса.
                  </p>
                )}
              </details>
            )}
          </>
        )}
      </section>
      <StudySessionPanel />
    </>
  );
}
