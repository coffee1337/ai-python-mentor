"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, errorMessage, isUnauthorized } from "../lib/api";
import { useUser } from "../lib/use-user";
import AppHeader from "../components/app-header";
import CoursePathSummary from "./course-path-summary";
import KnowledgeCheckSection from "./knowledge-check-section";
import LessonTheory from "./lesson-theory";
import MentorChat from "./mentor-chat";
import ReviewToday from "./review-today";
import HintLadder from "./hint-ladder";
import CodingPractice from "./coding-practice";
import ReflectionSection from "./reflection";
import PersonalizedPlan from "./personalized-plan";
import RichText from "./rich-text";
import { skillLabel } from "./skill-labels";
import type {
  AIPlan,
  CheckQuestion,
  CheckResult,
  Curriculum,
  Lesson,
  MistakeMemory,
  PathSummary,
} from "./lesson-types";

type LessonFlowDraft = { step: 1 | 2 | 3; answers: Record<string, string> };
function flowDraftKey(userId: string, lesson: Lesson) {
  return `mentor.lesson.draft.v3.${userId}.${lesson.id}.${lesson.version ?? "legacy"}.flow`;
}
function readFlowDraft(key: string): LessonFlowDraft | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw || raw.length > 12000) return null;
    const value = JSON.parse(raw);
    if (![1, 2, 3].includes(value?.step) || !value.answers || typeof value.answers !== "object" || Array.isArray(value.answers)) return null;
    return { step: value.step, answers: value.answers };
  } catch { return null; }
}
export default function LearningPage() {
  const router = useRouter();
  const {
    user,
    loading: userLoading,
    error: userError,
    reload: reloadUser,
  } = useUser(true);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [path, setPath] = useState<PathSummary | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [curriculum, setCurriculum] = useState<Curriculum | null>(null);
  const [aiPlan, setAiPlan] = useState<AIPlan | null>(null);
  const [checks, setChecks] = useState<CheckQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [mistakes, setMistakes] = useState<MistakeMemory[] | null>(null);
  const [mistakesError, setMistakesError] = useState("");
  const [mistakesLoading, setMistakesLoading] = useState(true);
  const [error, setError] = useState("");
  const [checkError, setCheckError] = useState("");
  const [checkNeedsReload, setCheckNeedsReload] = useState(false);
  const [checksLoading, setChecksLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [aiPlanError, setAiPlanError] = useState("");
  const [curriculumError, setCurriculumError] = useState("");
  const [plansLoading, setPlansLoading] = useState(true);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [flowReady, setFlowReady] = useState(false);
  const [flowRestored, setFlowRestored] = useState(false);

  function goToStep(next: 1 | 2 | 3) {
    setStep(next);
    window.requestAnimationFrame(() =>
      document.getElementById("lesson-step-heading")?.focus(),
    );
  }

  const refreshPlans = useCallback(async () => {
    setPlansLoading(true);
    const results = await Promise.allSettled([
      api<Curriculum>("/learning/curriculum"),
      api<AIPlan>("/learning/personalized-plan"),
    ]);
    const [curriculumResult, planResult] = results;
    if (curriculumResult.status === "fulfilled") {
      setCurriculum(curriculumResult.value);
      setCurriculumError("");
    } else setCurriculumError(errorMessage(curriculumResult.reason));
    if (planResult.status === "fulfilled") {
      setAiPlan(planResult.value);
      setAiPlanError("");
    } else setAiPlanError(errorMessage(planResult.reason));
    setPlansLoading(false);
  }, []);

  const loadCheck = useCallback(async (lessonId: string, draftAnswers: Record<string, string> = {}) => {
    setChecksLoading(true);
    setCheckError("");
    try {
      const nextChecks = await api<CheckQuestion[]>(
          `/learning/lessons/${encodeURIComponent(lessonId)}/knowledge-check`,
      );
      setChecks(nextChecks);
      setCheckResult(null);
      // Only unanswered choices matching the current public question are restored.
      // Completion, correctness and hint attribution always come from the server.
      setAnswers(Object.fromEntries(nextChecks
        .filter((question) => typeof draftAnswers[question.id] === "string" && question.choices.includes(draftAnswers[question.id]))
        .map((question) => [question.id, draftAnswers[question.id]])));
      setCheckNeedsReload(false);
    } catch (reason) {
      setCheckError(errorMessage(reason));
      setCheckNeedsReload(true);
    } finally {
      setChecksLoading(false);
    }
  }, []);

  const loadMistakes = useCallback(async () => {
    setMistakesLoading(true);
    setMistakesError("");
    try {
      setMistakes(await api<MistakeMemory[]>("/learning/mistakes"));
    } catch (reason) {
      setMistakesError(errorMessage(reason));
    } finally {
      setMistakesLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setFlowReady(false);
    setFlowRestored(false);
    setError("");
    try {
      const nextPath = await api<PathSummary>("/learning/path");
      const requested = new URLSearchParams(window.location.search).get(
        "lesson",
      );
      const nextLesson = await api<Lesson | null>(
        requested
          ? `/learning/lessons/${encodeURIComponent(requested)}`
          : "/learning/next",
      );
      setPath(nextPath);
      setLesson(nextLesson);
      const draft = nextLesson ? readFlowDraft(flowDraftKey(user.id, nextLesson)) : null;
      setStep(draft?.step ?? 1);
      if (nextLesson) await loadCheck(nextLesson.id, draft?.answers);
      else {
        setChecks([]);
        setCheckResult(null);
        setAnswers({});
      }
      setFlowRestored(!!draft && (draft.step !== 1 || Object.keys(draft.answers).length > 0));
      setFlowReady(true);
      void refreshPlans();
    } catch (reason) {
      if (isUnauthorized(reason)) router.replace("/auth");
      else setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [user, loadCheck, refreshPlans, router]);

  useEffect(() => {
    if (user) {
      void load();
      void loadMistakes();
    }
  }, [user, load, loadMistakes]);
  useEffect(() => {
    if (!loading && lesson) headingRef.current?.focus();
  }, [loading, lesson]);
  useEffect(() => {
    if (!user || !lesson || !flowReady || loading || checksLoading || checkNeedsReload) return;
    try {
      const draft: LessonFlowDraft = { step, answers: checkResult ? {} : answers };
      const serialized = JSON.stringify(draft);
      if (serialized.length <= 12000) window.localStorage.setItem(flowDraftKey(user.id, lesson), serialized);
    } catch { /* Optional browser storage must never prevent learning. */ }
  }, [user, lesson, flowReady, loading, checksLoading, checkNeedsReload, step, answers, checkResult]);

  async function afterReview() {
    await Promise.allSettled([refreshPlans(), loadMistakes()]);
  }

  async function submitCheck(event: FormEvent) {
    event.preventDefault();
    if (!lesson || busy || checkNeedsReload) return;
    setBusy(true);
    setCheckError("");
    try {
      const result = await api<CheckResult>(
        `/learning/lessons/${encodeURIComponent(lesson.id)}/knowledge-check`,
        { method: "POST", body: JSON.stringify({ answers }) },
      );
      setCheckResult(result);
      await Promise.allSettled([loadMistakes(), refreshPlans()]);
      try {
        setPath(await api<PathSummary>("/learning/path"));
      } catch {
        setError(
          "Ответ сохранён, но маршрут не обновился. Повторите загрузку маршрута.",
        );
      }
    } catch (reason) {
      setCheckError(errorMessage(reason));
      setCheckNeedsReload(reason instanceof ApiError && reason.status === 409);
      if (reason instanceof ApiError && reason.status === 409) {
        setAnswers({});
        try { window.localStorage.removeItem(flowDraftKey(user!.id, lesson)); } catch { /* Optional storage. */ }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="learning-page-content">
        <header className="page-heading">
          <a className="learning-breadcrumb" href="/learning/path">
            ← Весь учебный путь
          </a>
          <p className="page-kicker">Python · от основ к backend</p>
          <h1 id="lesson-title" tabIndex={-1} ref={headingRef}>
            {lesson?.title ?? "Ваш следующий урок"}
          </h1>
          <p className="page-subtitle">
            Сначала объяснение и пример. Затем короткая проверка. Практикуйте
            новое в своём темпе.
          </p>
          {lesson && (
            <div className="lesson-meta">
              <span className="badge">{skillLabel(lesson.skill_id)}</span>
              <span>Около {lesson.minutes} минут</span>
              <span>
                Урок{" "}
                {path?.lessons.findIndex((item) => item.id === lesson.id) !==
                  -1 && path
                  ? path.lessons.findIndex((item) => item.id === lesson.id) + 1
                  : "курса"}
              </span>
            </div>
          )}
        </header>
        {(userLoading || (loading && user)) && (
          <div
            className="panel learning-loading"
            role="status"
            aria-live="polite"
          >
            <span className="loading-dot" aria-hidden="true" />
            Загружаем материал и ваш маршрут…
          </div>
        )}
        {userError && (
          <div className="status-message" role="alert">
            <p>{userError}</p>
            <button
              className="button-secondary"
              onClick={() => void reloadUser()}
            >
              Повторить загрузку
            </button>
          </div>
        )}
        {error && (
          <div className="status-message" role="alert">
            <p>{error}</p>
            <button
              className="button-secondary"
              disabled={loading}
              onClick={() => void load()}
            >
              Повторить загрузку
            </button>
            <a href="/learning/path">Выбрать доступный урок</a>
          </div>
        )}
        {path?.resume_lesson_id === lesson?.id && lesson && (
          <div className="status-message" role="status">
            <strong>Продолжаем начатый урок</strong>
            <p>
              Вы увидите ту же версию материала и проверки, которую открывали
              раньше. После её завершения маршрут подберёт следующий шаг.
            </p>
          </div>
        )}
        {flowRestored && !loading && lesson && (
          <p className="lesson-draft-note" role="status">
            Восстановлен шаг урока и черновик выбранных ответов на этом устройстве.
            Результат проверки появится после отправки ответов.
          </p>
        )}
        {user && (
          <>
            {lesson && (
              <div className="learning-workspace">
                <article
                  className="panel lesson-workspace"
                  aria-labelledby="lesson-title"
                  aria-busy={busy}
                >
                  <nav className="lesson-steps" aria-label="Шаги урока">
                    {(
                      [
                        {
                          id: 1,
                          title: "Разобраться",
                          detail: "Объяснение и пример",
                        },
                        {
                          id: 2,
                          title: "Проверить понимание",
                          detail: "Вопросы по материалу",
                        },
                        {
                          id: 3,
                          title: "Попрактиковаться",
                          detail: "Закрепление навыка",
                        },
                      ] as const
                    ).map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        className={
                          step === item.id
                            ? "lesson-step lesson-step-active"
                            : "lesson-step"
                        }
                        aria-current={step === item.id ? "step" : undefined}
                        aria-controls="lesson-current-step"
                        onClick={() => goToStep(item.id)}
                      >
                        <span className="lesson-step-number" aria-hidden="true">
                          {item.id}
                        </span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>{item.detail}</small>
                        </span>
                      </button>
                    ))}
                  </nav>
                  <div id="lesson-current-step" className="lesson-current-step">
                    <h2
                      id="lesson-step-heading"
                      className="sr-only"
                      tabIndex={-1}
                    >
                      {step === 1
                        ? "Материал урока"
                        : step === 2
                          ? "Проверка понимания"
                          : "Практика"}
                    </h2>
                    {step === 1 && (
                      <>
                        <LessonTheory lesson={lesson} />
                        <div className="lesson-step-footer">
                          <p>
                            Материал понятен? Вопросы проверят только то, что
                            было в уроке.
                          </p>
                          <button
                            className="button"
                            type="button"
                            onClick={() => goToStep(2)}
                          >
                            Перейти к вопросам →
                          </button>
                        </div>
                      </>
                    )}
                    {step === 2 && (
                      <>
                        <KnowledgeCheckSection
                          questions={checks}
                          answers={answers}
                          onAnswerChange={(questionId, choice) =>
                            setAnswers((current) => ({
                              ...current,
                              [questionId]: choice,
                            }))
                          }
                          result={checkResult}
                          onSubmit={submitCheck}
                          onRetry={() => void loadCheck(lesson.id)}
                          busy={busy}
                          loading={checksLoading}
                          error={checkError}
                          reloadRequired={checkNeedsReload}
                          onReload={() => void loadCheck(lesson.id)}
                        />
                        <details className="lesson-detail">
                          <summary>Нужна подсказка по проверке</summary>
                          <HintLadder
                            key={`hints.${lesson.id}`}
                            lessonId={lesson.id}
                          />
                        </details>
                        <div className="lesson-step-footer">
                          <button
                            className="button-secondary"
                            type="button"
                            onClick={() => goToStep(1)}
                          >
                            ← Вернуться к объяснению
                          </button>
                          <button
                            className="button-secondary"
                            type="button"
                            onClick={() => goToStep(3)}
                          >
                            Открыть практику
                          </button>
                        </div>
                      </>
                    )}
                    {step === 3 && (
                      <>
                        <div className="practice-intro">
                          <span className="badge">Закрепление</span>
                          <h2>Примените то, что разобрали</h2>
                          <p>
                            Проверка выше показывает понимание урока. Здесь
                            можно потренироваться и сохранить ход своих мыслей.
                          </p>
                        </div>
                        {lesson.practice && (
                          <div className="practice-instructions">
                            <h3>Что нужно сделать</h3>
                            {lesson.practice_steps &&
                            lesson.practice_steps.length > 0 ? (
                              <ol>
                                {lesson.practice_steps.map((item, index) => (
                                  <li key={index}>
                                    <RichText text={item} />
                                  </li>
                                ))}
                              </ol>
                            ) : (
                              <RichText text={lesson.practice} />
                            )}
                          </div>
                        )}
                        {lesson.practice_submission_type !== "coding" ? (
                          <div className="guided-reading-note">
                            <h3>Сейчас редактор кода не нужен</h3>
                            <p>
                              Здесь закрепление устроено как чтение и объяснение
                              примера. Выполните шаги выше, предскажите
                              результат и объясните его своими словами. Готовую
                              функцию отправлять не нужно.
                            </p>
                            <button
                              className="button-secondary"
                              type="button"
                              onClick={() => goToStep(2)}
                            >
                              Проверить понимание
                            </button>
                          </div>
                        ) : (
                          <details className="lesson-detail">
                            <summary>
                              Тренировка с кодом · отдельное задание
                            </summary>
                            <CodingPractice
                              key={`coding.${lesson.id}.${user.id}`}
                              lessonId={lesson.id}
                              userId={user.id}
                            />
                          </details>
                        )}
                        <details className="lesson-detail">
                          <summary>
                            Объяснить своими словами · необязательно
                          </summary>
                          <ReflectionSection
                            key={`${lesson.id}.${lesson.version}`}
                            lessonId={lesson.id}
                            version={lesson.version ?? "legacy"}
                            userId={user.id}
                          />
                        </details>
                        <div className="lesson-step-footer">
                          <button
                            className="button-secondary"
                            type="button"
                            onClick={() => goToStep(2)}
                          >
                            ← Вернуться к проверке
                          </button>
                          <a className="button-secondary" href="/learning/path">
                            Посмотреть дальнейший путь
                          </a>
                        </div>
                      </>
                    )}
                  </div>
                </article>
                <aside className="learning-aside" aria-label="Помощь и маршрут">
                  <MentorChat key={lesson.id} lessonId={lesson.id} />
                  {path && (
                    <CoursePathSummary
                      path={path}
                      currentLessonId={lesson.id}
                    />
                  )}
                </aside>
              </div>
            )}
            {!loading && !lesson && !error && (
              <section className="panel empty-state">
                <h2>Выберите следующий шаг</h2>
                <p>
                  Здесь пока нет назначенного урока. Все опубликованные
                  материалы и условия открытия видны в учебном пути.
                </p>
                <a className="button" href="/learning/path">
                  Открыть учебный путь
                </a>
              </section>
            )}
            <section
              className="learning-tools"
              aria-label="Дополнительные инструменты обучения"
            >
              <details className="panel learning-tool">
                <summary>
                  <span>Повторение изученного</span>
                  <small>Короткие вопросы после паузы</small>
                </summary>
                <ReviewToday onReviewPlanChanged={() => void afterReview()} />
              </details>
              <details className="panel learning-tool">
                <summary>
                  <span>Темы, к которым стоит вернуться</span>
                  <small>Объяснения по вашим прошлым ответам</small>
                </summary>
                <div className="learning-tool-body">
                  {mistakesLoading && <p role="status">Загружаем темы…</p>}
                  {mistakesError && (
                    <div role="alert">
                      <p className="form-error">{mistakesError}</p>
                      <button
                        className="button-secondary"
                        onClick={() => void loadMistakes()}
                      >
                        Повторить загрузку
                      </button>
                    </div>
                  )}
                  {!mistakesLoading &&
                    !mistakesError &&
                    mistakes?.length === 0 && (
                      <p className="muted">
                        После проверки здесь появятся темы, которые стоит ещё
                        раз разобрать. Пока сохранённых ошибок нет.
                      </p>
                    )}
                  {mistakes && (
                    <ul className="mistake-memory-list">
                      {mistakes.map((item, index) => (
                        <li key={`${item.remediation_exercise_id}.${index}`}>
                          <strong>Что повторить</strong>
                          <RichText text={item.error_text} />
                          <RichText text={item.remediation_text} />
                          <a
                            href={`/learning?lesson=${encodeURIComponent(item.remediation_exercise_id)}`}
                          >
                            Открыть объяснение →
                          </a>
                          <p className="muted">
                            <time dateTime={item.last_seen_at}>
                              {new Date(item.last_seen_at).toLocaleDateString(
                                "ru-RU",
                              )}
                            </time>
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </details>
              <details className="panel learning-tool">
                <summary>
                  <span>Персональные упражнения от AI</span>
                  <small>Дополнение к основному курсу</small>
                </summary>
                <PersonalizedPlan
                  plan={aiPlan}
                  error={aiPlanError}
                  loading={plansLoading}
                  userId={user.id}
                  onChange={setAiPlan}
                  onReload={() => void refreshPlans()}
                />
              </details>
              <details className="panel learning-tool">
                <summary>
                  <span>План учебной сессии</span>
                  <small>Порядок материалов на сегодня</small>
                </summary>
                <div className="learning-tool-body">
                  {plansLoading && <p role="status">Загружаем план сессии…</p>}
                  {curriculumError && (
                    <div role="alert">
                      <p className="form-error">{curriculumError}</p>
                      <button
                        className="button-secondary"
                        onClick={() => void refreshPlans()}
                      >
                        Повторить загрузку
                      </button>
                    </div>
                  )}
                  {curriculum?.sessions[0] ? (
                    <>
                      <p>
                        {curriculum.sessions[0].planned_minutes} минут ·{" "}
                        {curriculum.sessions[0].rationale}
                      </p>
                      <ol className="session-activities">
                        {curriculum.sessions[0].activities.map(
                          (item, index) => (
                            <li
                              key={
                                item.lesson_id ?? `${item.skill_id}.${index}`
                              }
                            >
                              <span className="badge">
                                {item.kind === "review"
                                  ? "Повторение"
                                  : "Новый материал"}
                              </span>
                              <span>
                                {item.kind === "review" ? (
                                  <a href="/learning/reviews">
                                    Открыть повторение
                                  </a>
                                ) : item.lesson_id ? (
                                  <a
                                    href={`/learning?lesson=${encodeURIComponent(item.lesson_id)}`}
                                  >
                                    {path?.lessons.find(
                                      (entry) => entry.id === item.lesson_id,
                                    )?.title ?? skillLabel(item.skill_id)}
                                  </a>
                                ) : (
                                  "Материал пока не опубликован"
                                )}
                              </span>
                              <span className="muted">
                                {item.estimated_minutes} минут
                              </span>
                            </li>
                          ),
                        )}
                      </ol>
                    </>
                  ) : (
                    !curriculumError && (
                      <p className="muted">
                        Сессия пока не составлена. Основной учебный путь
                        доступен без неё.{" "}
                        <a href="/assessment">Необязательная диагностика</a>{" "}
                        поможет уточнить рекомендации, когда вы освоитесь.
                      </p>
                    )
                  )}
                </div>
              </details>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
