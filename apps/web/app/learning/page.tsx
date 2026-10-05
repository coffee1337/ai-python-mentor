"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isUnauthorized } from "../lib/api";
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
import type { AIPlan, CheckQuestion, CheckResult, Curriculum, Lesson, MistakeMemory, PathSummary } from "./lesson-types";

export default function LearningPage() {
  const router = useRouter();
  const { user, loading: userLoading, error: userError, reload: reloadUser } = useUser(true);
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
  const [checksLoading, setChecksLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [aiPlanError, setAiPlanError] = useState("");
  const [curriculumError, setCurriculumError] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  const refreshPlans = useCallback(async () => {
    const results = await Promise.allSettled([api<Curriculum>("/learning/curriculum"), api<AIPlan>("/learning/personalized-plan")]);
    const [curriculumResult, planResult] = results;
    if (curriculumResult.status === "fulfilled") { setCurriculum(curriculumResult.value); setCurriculumError(""); }
    else setCurriculumError(errorMessage(curriculumResult.reason));
    if (planResult.status === "fulfilled") { setAiPlan(planResult.value); setAiPlanError(""); }
    else setAiPlanError(errorMessage(planResult.reason));
  }, []);

  const loadCheck = useCallback(async (lessonId: string) => {
    setChecksLoading(true);
    setCheckError("");
    try {
      setChecks(await api<CheckQuestion[]>(`/learning/lessons/${encodeURIComponent(lessonId)}/knowledge-check`));
      setCheckResult(null);
      setAnswers({});
    } catch (reason) { setCheckError(errorMessage(reason)); }
    finally { setChecksLoading(false); }
  }, []);

  const loadMistakes = useCallback(async () => {
    setMistakesLoading(true);
    setMistakesError("");
    try { setMistakes(await api<MistakeMemory[]>("/learning/mistakes")); }
    catch (reason) { setMistakesError(errorMessage(reason)); }
    finally { setMistakesLoading(false); }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextPath = await api<PathSummary>("/learning/path");
      const requested = new URLSearchParams(window.location.search).get("lesson");
      const nextLesson = await api<Lesson | null>(requested ? `/learning/lessons/${encodeURIComponent(requested)}` : "/learning/next");
      setPath(nextPath);
      setLesson(nextLesson);
      if (nextLesson) await loadCheck(nextLesson.id);
      else { setChecks([]); setCheckResult(null); }
      await refreshPlans();
    } catch (reason) {
      if (isUnauthorized(reason)) router.replace("/auth");
      else setError(errorMessage(reason));
    } finally { setLoading(false); }
  }, [loadCheck, refreshPlans, router]);

  useEffect(() => { if (user) { void load(); void loadMistakes(); } }, [user, load, loadMistakes]);
  useEffect(() => { if (!loading && lesson) headingRef.current?.focus(); }, [loading, lesson]);

  async function afterReview() {
    await Promise.allSettled([refreshPlans(), loadMistakes()]);
  }

  async function submitCheck(event: FormEvent) {
    event.preventDefault();
    if (!lesson || busy) return;
    setBusy(true);
    setCheckError("");
    try {
      const result = await api<CheckResult>(`/learning/lessons/${encodeURIComponent(lesson.id)}/knowledge-check`, { method: "POST", body: JSON.stringify({ answers }) });
      setCheckResult(result);
      await Promise.allSettled([loadMistakes(), refreshPlans()]);
      try { setPath(await api<PathSummary>("/learning/path")); }
      catch { setError("Ответ сохранён, но маршрут не обновился. Повторите загрузку маршрута."); }
    } catch (reason) { setCheckError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <section className="dashboard-card">
        <h1>Учебный путь Python</h1>
        {(userLoading || loading && user) && <p role="status">Загружаем урок…</p>}
        {userError && <div role="alert"><p className="form-error">{userError}</p><button className="text-button" onClick={() => void reloadUser()}>Повторить загрузку</button></div>}
        {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={loading} onClick={() => void load()}>Повторить загрузку маршрута</button><p><a href="/learning/path">Выбрать доступный урок</a></p></div>}
        {user && <>
          {path && <CoursePathSummary path={path} currentLessonId={lesson?.id} />}
          {lesson && <article aria-labelledby="lesson-title" aria-busy={busy}>
            <h2 id="lesson-title" tabIndex={-1} ref={headingRef}>{lesson.title}</h2>
            <LessonTheory lesson={lesson} />
            <ReflectionSection key={`${lesson.id}.${lesson.version}`} lessonId={lesson.id} version={lesson.version ?? "legacy"} userId={user.id} />
            <HintLadder key={`hints.${lesson.id}`} lessonId={lesson.id} />
            <KnowledgeCheckSection questions={checks} answers={answers} onAnswerChange={(questionId, choice) => setAnswers((current) => ({ ...current, [questionId]: choice }))} result={checkResult} onSubmit={submitCheck} onRetry={() => void loadCheck(lesson.id)} busy={busy} loading={checksLoading} error={checkError} onReload={() => void loadCheck(lesson.id)} />
            <CodingPractice key={`coding.${lesson.id}.${user.id}`} lessonId={lesson.id} userId={user.id} />
            <MentorChat key={lesson.id} lessonId={lesson.id} />
          </article>}
          {!loading && !lesson && !error && <section className="course-path-state"><h2>Урок пока не назначен</h2><p>Выберите следующий доступный шаг в учебном пути.</p><a className="primary-button" href="/learning/path">Открыть учебный путь</a></section>}
          <ReviewToday onReviewPlanChanged={() => void afterReview()} />
          <section className="lesson-subsection" aria-labelledby="mistake-memory-heading">
            <h2 id="mistake-memory-heading">Темы, к которым стоит вернуться</h2>
            {mistakesLoading && <p role="status">Загружаем темы…</p>}
            {mistakesError && <div role="alert"><p className="form-error">{mistakesError}</p><button className="text-button" onClick={() => void loadMistakes()}>Повторить загрузку тем</button></div>}
            {!mistakesLoading && !mistakesError && mistakes?.length === 0 && <p className="muted">Тем для повторения пока нет. Они появятся после новых ответов.</p>}
            {mistakes && <ul>{mistakes.map((item, index) => <li key={`${item.remediation_exercise_id}.${index}`}><p><strong>Что повторить:</strong> {item.error_text}</p><p>{item.remediation_text}</p><a href={`/learning?lesson=${encodeURIComponent(item.remediation_exercise_id)}`}>Открыть материал для повторения</a><p className="muted"><time dateTime={item.last_seen_at}>{new Date(item.last_seen_at).toLocaleString("ru-RU")}</time></p></li>)}</ul>}
          </section>
          <PersonalizedPlan plan={aiPlan} error={aiPlanError} userId={user.id} onChange={setAiPlan} onReload={() => void refreshPlans()} />
          <section className="lesson-subsection" aria-label="Актуальная учебная сессия">
            <h2>Учебная сессия</h2>
            {curriculumError && <div role="alert"><p className="form-error">{curriculumError}</p><button className="text-button" onClick={() => void refreshPlans()}>Повторить загрузку плана</button></div>}
            {curriculum?.sessions[0] ? <><p>{curriculum.sessions[0].planned_minutes} мин · {curriculum.sessions[0].rationale}</p><ol>{curriculum.sessions[0].activities.map((item, index) => <li className="learning-plan-item" key={item.lesson_id ?? `${item.skill_id}.${index}`}><span>{item.kind === "review" ? "Повторение" : "Новый материал"}</span>{item.kind === "review" ? <a href="#reviews-today">Открыть повторение</a> : item.lesson_id ? <a href={`/learning?lesson=${encodeURIComponent(item.lesson_id)}`}>{path?.lessons.find((entry) => entry.id === item.lesson_id)?.title ?? "Открыть урок"}</a> : <span>Материал пока не опубликован</span>}<span>{item.estimated_minutes} мин</span></li>)}</ol></> : !curriculumError && <p className="muted">Сессия ещё не запланирована. <a href="/assessment">Пройдите диагностику</a>, чтобы уточнить маршрут.</p>}
          </section>
        </>}
      </section>
    </main>
  );
}
