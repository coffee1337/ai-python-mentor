"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "../lib/api";
import AttemptHistory from "./attempt-history";
import CoursePathSummary from "./course-path-summary";
import KnowledgeCheckSection from "./knowledge-check-section";
import LessonPractice, { SOURCE_LIMIT, STARTER_CODE } from "./lesson-practice";
import LessonTheory from "./lesson-theory";
import MentorChat from "./mentor-chat";
import ReviewToday from "./review-today";
import type {
  AIPlan,
  Attempt,
  CheckQuestion,
  CheckResult,
  Curriculum,
  Lesson,
  MistakeMemory,
  PathSummary,
} from "./lesson-types";

const DRAFT_KEY = "mentor.lesson.draft";

function formatLastSeenAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Дата недоступна"
    : date.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

export default function LearningPage() {
  const router = useRouter();
  const [path, setPath] = useState<PathSummary | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [curriculum, setCurriculum] = useState<Curriculum | null>(null);
  const [aiPlan, setAiPlan] = useState<AIPlan | null>(null);
  const [source, setSource] = useState(STARTER_CODE);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [checks, setChecks] = useState<CheckQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [mistakes, setMistakes] = useState<MistakeMemory[] | null>(null);
  const [mistakesError, setMistakesError] = useState(false);
  const [mistakesLoading, setMistakesLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiPlanError, setAiPlanError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback(async () => {
    const nextPath = await api<PathSummary>("/learning/path");
    try {
      setCurriculum(await api<Curriculum>("/learning/curriculum"));
    } catch {
      setCurriculum(null);
    }
    try {
      setAiPlanError(null);
      setAiPlan(await api<AIPlan>("/learning/personalized-plan"));
    } catch (err) {
      setAiPlan(null);
      setAiPlanError(err instanceof Error ? err.message : "AI-план недоступен");
    }
    const requested =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("lesson")
        : null;
    const nextLesson = requested
      ? await api<Lesson>("/learning/lessons/" + encodeURIComponent(requested))
      : await api<Lesson | null>("/learning/next");
    setPath(nextPath);
    setLesson(nextLesson);
    setFeedback("");
    setCheckResult(null);
    setAnswers({});
    if (nextLesson) {
      setAttempts(
        await api<Attempt[]>("/learning/exercises/" + nextLesson.id + "/attempts"),
      );
      try {
        setChecks(
          await api<CheckQuestion[]>("/learning/lessons/" + nextLesson.id + "/knowledge-check"),
        );
      } catch {
        setChecks([]);
      }
    } else {
      setAttempts([]);
      setChecks([]);
    }
  }, []);

  const loadMistakes = useCallback(async () => {
    setMistakesLoading(true);
    setMistakesError(false);
    try {
      setMistakes(await api<MistakeMemory[]>("/learning/mistakes"));
    } catch {
      setMistakes(null);
      setMistakesError(true);
    } finally {
      setMistakesLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const user = await api<User>("/me");
        if (!user.profile?.onboarding_completed) {
          router.replace("/onboarding");
          return;
        }
        void loadMistakes();
        await load();
      } catch {
        router.replace("/auth");
      } finally {
        setReady(true);
      }
    })();
  }, [router, load, loadMistakes]);

  // Move focus to the lesson heading after load so keyboard and screen reader
  // users are not left at the top of a long page.
  useEffect(() => {
    if (ready && lesson) headingRef.current?.focus();
  }, [ready, lesson]);

  // Draft safety: the editor is controlled, so never drop the learner's text on an
  // accidental reload. Restored only for the same lesson.
  useEffect(() => {
    if (!lesson) return;
    try {
      const raw = window.localStorage.getItem(`${DRAFT_KEY}.${lesson.id}`);
      if (raw && raw.length <= SOURCE_LIMIT) setSource(raw);
    } catch {
      /* storage unavailable: keep the starter code */
    }
  }, [lesson]);

  const handleSourceChange = useCallback(
    (value: string) => {
      setSource(value);
      if (!lesson) return;
      try {
        window.localStorage.setItem(`${DRAFT_KEY}.${lesson.id}`, value);
      } catch {
        /* storage unavailable: the draft is a convenience, not a guarantee */
      }
    },
    [lesson],
  );

  async function submitCode(event: FormEvent) {
    event.preventDefault();
    if (!lesson || busy || !source.trim()) return;
    setBusy(true);
    setError("");
    try {
      const attempt = await api<Attempt>("/learning/exercises/" + lesson.id + "/attempts", {
        method: "POST",
        body: JSON.stringify({ language: "python", mode: "function", source_code: source }),
      });
      setAttempts((current) => [attempt, ...current]);
      setFeedback(
        attempt.result.message ??
          "Попытка сохранена. Проверка runner недоступна и код не выполнялся.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить решение");
    } finally {
      setBusy(false);
    }
  }

  async function submitCheck(event: FormEvent) {
    event.preventDefault();
    if (!lesson || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<CheckResult>(
        "/learning/lessons/" + lesson.id + "/knowledge-check",
        { method: "POST", body: JSON.stringify({ answers }) },
      );
      setCheckResult(result);
      setFeedback(result.recommendation);
      await loadMistakes();
      if (result.passed) setPath(await api<PathSummary>("/learning/path"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось проверить знания");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <a className="brand" href="/dashboard">
          AI-наставник<span className="brand-dot">.</span>
        </a>
        <a href="/dashboard">Дашборд</a>
      </header>
      <section className="dashboard-card">
        <h1>Учебный путь Python</h1>
        <p className="muted">
          Проверка знаний использует только authored-вопросы и обновляет ваш план. Python
          Runner остаётся недоступным и не исполняет код.
        </p>
        <ReviewToday />

        <section aria-labelledby="mistake-memory-heading" className="lesson-subsection">
          <h2 id="mistake-memory-heading">Темы, к которым стоит вернуться.</h2>
          <p className="muted">
            Мы собрали повторяющиеся темы из вашего обучения. Это не оценка — только
            спокойный ориентир для следующего повторения.
          </p>
          {mistakesLoading && (
            <p role="status" aria-live="polite">
              Загружаем темы…
            </p>
          )}
          {!mistakesLoading && mistakesError && (
            <div role="alert">
              <p className="form-error">Не удалось загрузить темы. Попробуйте ещё раз.</p>
              <button
                className="text-button"
                type="button"
                onClick={() => void loadMistakes()}
                aria-label="Повторить загрузку тем"
              >
                Повторить
              </button>
            </div>
          )}
          {!mistakesLoading && !mistakesError && mistakes?.length === 0 && (
            <p role="status" aria-live="polite">
              Пока нет тем для повторения. Здесь появятся темы, к которым полезно вернуться
              после новых ответов.
            </p>
          )}
          {!mistakesLoading && !mistakesError && mistakes && mistakes.length > 0 && (
            <ul aria-label="Список тем, к которым стоит вернуться" aria-live="polite">
              {mistakes.map((item, index) => (
                <li key={`${item.remediation_exercise_id}-${item.last_seen_at}-${index}`}>
                  <p>
                    <strong>Что стоит повторить:</strong> {item.error_text}
                  </p>
                  <p>
                    <strong>Следующий шаг:</strong> {item.remediation_text}
                  </p>
                  <p>
                    <a
                      href={
                        "/learning?lesson=" + encodeURIComponent(item.remediation_exercise_id)
                      }
                    >
                      Открыть материал для повторения
                    </a>
                  </p>
                  <p>
                    <strong>Последний раз:</strong>{" "}
                    <time dateTime={item.last_seen_at}>{formatLastSeenAt(item.last_seen_at)}</time>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        {aiPlan?.status === "ready" && (
          <section aria-label="Персональный план от AI">
            <h2>
              Персональный план от AI{aiPlan.model_id ? ` · ${aiPlan.model_id}` : ""}
            </h2>
            {aiPlan.steps.map((step) => (
              <article key={step.position}>
                <h3>
                  {step.position}. {step.title} · {step.duration_minutes} мин
                </h3>
                <p>{step.explanation}</p>
                <p>
                  <strong>Задание:</strong> {step.exercise.prompt}
                </p>
                {step.exercise.starter_code && (
                  <pre>
                    <code>{step.exercise.starter_code}</code>
                  </pre>
                )}
                {step.exercise.submission_type === "python_code" && (
                  <p className="muted">
                    Код сохранён, но не выполнен: проверка через Runner пока недоступна.
                  </p>
                )}
              </article>
            ))}
          </section>
        )}
        {aiPlanError && (
          <p className="muted" role="status">
            Персональный AI-план сейчас недоступен: {aiPlanError} План ниже построен без
            нейросети — по правилам и вашей истории ответов.
          </p>
        )}
        {!aiPlanError && aiPlan?.status !== "ready" && (
          <p className="muted">
            AI-план пока не готов. Он строится на основе вашей диагностики и доступен из
            дашборда.
          </p>
        )}

        {curriculum?.sessions[0] && (
          <section aria-label="Актуальный учебный план">
            <h2>Актуальная учебная сессия · {curriculum.sessions[0].planned_minutes} мин</h2>
            <p>{curriculum.sessions[0].rationale}</p>
            <ol className="learning-plan-list">
              {curriculum.sessions[0].activities.map((item, index) => (
                <li
                  className={
                    item.kind === "review"
                      ? "learning-plan-item learning-plan-review"
                      : "learning-plan-item"
                  }
                  key={item.lesson_id ?? item.skill_id + index}
                >
                  <span className="learning-plan-kind">
                    {item.kind === "review" ? "ПОВТОРЕНИЕ" : "НОВЫЙ МАТЕРИАЛ"}
                  </span>
                  {item.kind === "review" ? (
                    <a href="#reviews-today">Открыть повторение →</a>
                  ) : item.lesson_id ? (
                    <a href={"/learning?lesson=" + encodeURIComponent(item.lesson_id)}>
                      {item.lesson_id}
                    </a>
                  ) : (
                    item.skill_id
                  )}
                  <span className="learning-plan-meta">
                    {item.estimated_minutes} мин · {item.reason_codes.join(", ")}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}
        {curriculum && curriculum.sessions.length === 0 && (
          <p className="muted">
            Учебная сессия не запланирована: возможно, ещё нет завершённых уроков или
            диагностики. Пройдите диагностику, и план появится здесь.
          </p>
        )}

        {error && (
          <div role="alert">
            <p className="form-error">{error}</p>
            <button type="button" className="text-button" onClick={() => void load()}>
              Повторить
            </button>
          </div>
        )}

        {!path && !error && (
          <p role="status" aria-live="polite">
            Загружаем урок…
          </p>
        )}

        {path && <CoursePathSummary path={path} />}

        {feedback && (
          <p role="status" aria-live="polite">
            {feedback}
          </p>
        )}

        {lesson ? (
          <article aria-labelledby="lesson-title" aria-busy={busy}>
            <h2 id="lesson-title" tabIndex={-1} ref={headingRef}>
              {lesson.title}
            </h2>
            <LessonTheory lesson={lesson} />
            <LessonPractice
              source={source}
              onSourceChange={handleSourceChange}
              onSubmit={submitCode}
              busy={busy}
            />
            <KnowledgeCheckSection
              questions={checks}
              answers={answers}
              onAnswerChange={(questionId, choice) =>
                setAnswers((current) => ({ ...current, [questionId]: choice }))
              }
              result={checkResult}
              onSubmit={submitCheck}
              onRetry={() => {
                setCheckResult(null);
                setAnswers({});
              }}
              busy={busy}
            />
            <AttemptHistory attempts={attempts} />
            <MentorChat key={lesson.id} lessonId={lesson.id} />
          </article>
        ) : (
          path && (
            <section className="course-path-state" aria-labelledby="no-lesson-title">
              <h2 id="no-lesson-title">Урок пока не назначен</h2>
              <p role="status">
                Сервер не вернул доступный урок. Откройте учебный путь и выберите следующий
                шаг.
              </p>
              <a className="primary-button" href="/learning/path">
                Открыть учебный путь <span aria-hidden="true">→</span>
              </a>
            </section>
          )
        )}
      </section>
    </main>
  );
}
