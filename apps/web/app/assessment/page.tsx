"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type Question = { id: string; skill_id: string; difficulty: number; prompt: string; choices: string[]; question_number: number; total_questions: number };
type State = { status: string; completed: boolean; score: number | null; answered: number; question: Question | null };
type Answer = { correct: boolean; feedback: string; state: State };
export default function AssessmentPage() {
  const { user, loading: userLoading, error: userError, reload } = useUser(true);
  const [state, setState] = useState<State | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setState(await api<State>("/assessment")); setAnswer(""); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user, load]);
  useEffect(() => { heading.current?.focus(); }, [state?.question?.id]);
  async function restart() {
    setBusy(true);
    setError("");
    try { setState(await api<State>("/assessment/restart", { method: "POST" })); setAnswer(""); setFeedback(""); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!state?.question || busy || !answer) return;
    setBusy(true);
    setError("");
    try { const result = await api<Answer>("/assessment/answers", { method: "POST", body: JSON.stringify({ question_id: state.question.id, answer }) }); setState(result.state); setFeedback(result.feedback); setAnswer(""); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <main className="dashboard-shell"><AppHeader /><section className="auth-card">
    <span className="eyebrow">ДИАГНОСТИКА</span><h1>Определим точку старта.</h1>
    <p className="auth-lead">Это короткая адаптивная проверка. Она помогает выбрать начало маршрута и не является экзаменом или оценкой профессионального уровня.</p>
    {(userLoading || user && loading) && <p role="status">Загружаем вопрос…</p>}
    {userError && <div role="alert"><p>{userError}</p><button className="text-button" onClick={() => void reload()}>Повторить загрузку аккаунта</button></div>}
    {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={busy || loading} onClick={() => void load()}>Обновить текущий вопрос</button></div>}
    {feedback && <p role="status">{feedback}</p>}
    {state?.completed ? <><p role="status">Диагностика завершена. Верных ответов: {Math.round((state.score ?? 0) * 100)}%. Это результат этой проверки, а не процент освоения профессии.</p><p>Ответов сохранено: {state.answered}.</p><button className="primary-button" onClick={() => void restart()} disabled={busy}>{busy ? "Готовим диагностику…" : "Пройти ещё раз"}</button><p><a href="/learning">Перейти к обучению</a></p></> : state?.question ? <form onSubmit={submit}><p>Вопрос {state.question.question_number} из {state.question.total_questions}</p><h2 tabIndex={-1} ref={heading}>{state.question.prompt}</h2><fieldset disabled={busy}><legend>Выберите ответ</legend>{state.question.choices.map((choice) => <label className="choice" key={choice}><input type="radio" name="assessment-answer" value={choice} checked={answer === choice} onChange={() => setAnswer(choice)} required />{choice}</label>)}</fieldset><button className="form-button" disabled={!answer || busy}>{busy ? "Сохраняем…" : "Ответить"}</button></form> : !loading && user && !error && <p>Вопрос пока не назначен. <button className="text-button" disabled={busy} onClick={() => void restart()}>Начать новую диагностику</button></p>}
  </section></main>;
}
