"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "../lib/api";
import MentorChat from "./mentor-chat";

type Path = {
  completed: number; total: number; next_lesson_id: string | null;
  lessons: { id: string; title: string; minutes: number; status: "completed" | "available" | "locked" }[];
};
type Lesson = {
  id: string; title: string; body: string; example: string;
  question: string; choices: string[];
};

export default function LearningPage() {
  const router = useRouter();
  const [path, setPath] = useState<Path | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const nextPath = await api<Path>("/learning/path");
    const nextLesson = await api<Lesson | null>("/learning/next");
    setPath(nextPath); setLesson(nextLesson); setAnswer("");
  }
  useEffect(() => {
    async function start() {
      let user: User;
      try { user = await api<User>("/me"); }
      catch { router.replace("/auth"); return; }
      if (!user.profile?.onboarding_completed) { router.replace("/onboarding"); return; }
      try { await load(); } catch { setError("Не удалось загрузить маршрут. Попробуйте снова."); }
    }
    void start();
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!lesson || busy) return;
    setBusy(true); setError(""); setFeedback("");
    try {
      const result = await api<{ correct: boolean; path: Path }>(`/learning/lessons/${lesson.id}/complete`, {
        method: "POST", body: JSON.stringify({ answer }),
      });
      if (result.correct) {
        setPath(result.path);
        setLesson(null);
        setFeedback("Верно! Завершение сохранено.");
        await load();
      } else {
        setFeedback("Пока неверно. Перечитайте объяснение и попробуйте ещё раз.");
      }
    } catch { setError("Не удалось выполнить запрос. Повторите загрузку или войдите снова."); }
    finally { setBusy(false); }
  }

  return <main className="dashboard-shell">
    <header className="topbar"><a className="brand" href="/dashboard">↗ наставник<span className="brand-dot">.</span></a><a href="/dashboard">Мой профиль</a></header>
    <section className="dashboard-card">
      <h1>Первые шаги в Python</h1>
      <p className="muted">Авторский вводный маршрут, не адаптивная диагностика. Выполнение уроков не является оценкой mastery. Код не исполняется; помощь наставника учитывается отдельно.</p>
      {error && <div role="alert"><p>{error}</p><button disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try { await load(); } catch { setError("Загрузка не удалась. Попробуйте позже."); }
        finally { setBusy(false); }
      }}>Повторить загрузку</button> <a href="/auth">Войти</a></div>}
      {!path && !error && <p role="status">Загружаем маршрут…</p>}
      {path && <>
        <p>Завершено уроков: {path.completed} из {path.total}</p>
        <ol>{path.lessons.map(item => <li key={item.id}>{item.title} · {item.minutes} мин · {
          item.status === "completed" ? "Завершён" : item.status === "available" ? "Следующий" : "После предыдущего урока"
        }</li>)}</ol>
        {feedback && <p role="status">{feedback}</p>}
        {lesson && <article>
          <h2>{lesson.title}</h2><p>{lesson.body}</p><pre><code>{lesson.example}</code></pre>
          <form onSubmit={submit}>
            <fieldset disabled={busy}><legend>{lesson.question}</legend>
              {lesson.choices.map(choice => <label key={choice} style={{ display: "block", margin: "12px 0" }}>
                <input type="radio" name="answer" value={choice} checked={answer === choice} onChange={() => setAnswer(choice)} required /> {choice}
              </label>)}
            </fieldset>
            <button type="submit" disabled={!answer || busy}>{busy ? "Сохраняем…" : "Проверить и завершить урок"}</button>
          </form>
          <MentorChat key={lesson.id} lessonId={lesson.id} />
        </article>}
        {!path.next_lesson_id && <p role="status">Вводный маршрут завершён. Новых уроков пока нет.</p>}
      </>}
    </section>
  </main>;
}
