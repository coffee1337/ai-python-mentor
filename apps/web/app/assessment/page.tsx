"use client";

import {
  FormEvent,
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type Question = {
  id: string;
  skill_id: string;
  difficulty: number;
  prompt: string;
  code?: string | null;
  choices: string[];
  question_number: number;
  total_questions: number;
};
type AssessmentState = {
  status: string;
  completed: boolean;
  score: number | null;
  answered: number;
  skipped: number;
  question: Question | null;
};
type Answer = { correct: boolean; feedback: string; state: AssessmentState };

function QuestionText({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(`[^`]+`)/g)
        .map((part, index) =>
          part.startsWith("`") && part.endsWith("`") ? (
            <code key={index}>{part.slice(1, -1)}</code>
          ) : (
            <Fragment key={index}>{part}</Fragment>
          ),
        )}
    </>
  );
}

export default function AssessmentPage() {
  const {
    user,
    loading: userLoading,
    error: userError,
    reload,
  } = useUser(true);
  const [state, setState] = useState<AssessmentState | null>(null);
  const [started, setStarted] = useState(false);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const isBeginner = user?.profile?.experience_level === "beginner";
  const load = useCallback(async () => {
    setStarted(true);
    setLoading(true);
    setError("");
    try {
      setState(await api<AssessmentState>("/assessment"));
      setAnswer("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    heading.current?.focus();
  }, [state?.question?.id, state?.completed]);

  async function restart() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setState(
        await api<AssessmentState>("/assessment/restart", { method: "POST" }),
      );
      setAnswer("");
      setFeedback("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!state?.question || busy || !answer) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Answer>("/assessment/answers", {
        method: "POST",
        body: JSON.stringify({ question_id: state.question.id, answer }),
      });
      setState(result.state);
      setFeedback(result.feedback);
      setAnswer("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function skipQuestion() {
    if (!state?.question || busy) return;
    setBusy(true);
    setError("");
    try {
      setState(
        await api<AssessmentState>("/assessment/skip", {
          method: "POST",
          body: JSON.stringify({ question_id: state.question.id }),
        }),
      );
      setFeedback(
        "Вопрос пропущен. Мы не записываем его как ошибку или результат проверки знаний.",
      );
      setAnswer("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const completedSlots = (state?.answered ?? 0) + (state?.skipped ?? 0);

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="page-heading">
        <div>
          <span className="page-kicker">Необязательная диагностика</span>
          <h1>Выберем точку старта</h1>
          <p className="page-subtitle">
            Если уже пробовали Python, короткая проверка поможет найти знакомые
            темы. Учиться можно и без неё.
          </p>
        </div>
      </div>
      <div className="assessment-layout">
        <section
          className="panel assessment-main"
          aria-label="Диагностика знаний Python"
        >
          {userLoading && (
            <p className="status-message" role="status">
              Загружаем аккаунт…
            </p>
          )}
          {userError && (
            <div className="status-message" role="alert">
              <p>{userError}</p>
              <button
                className="button button-secondary"
                onClick={() => void reload()}
              >
                Повторить загрузку
              </button>
            </div>
          )}
          {error && (
            <div className="status-message form-error" role="alert">
              <p>{error}</p>
              <button
                className="button button-secondary"
                disabled={busy || loading}
                onClick={() => void load()}
              >
                Повторить загрузку вопроса
              </button>
            </div>
          )}
          {loading && (
            <p className="status-message" role="status">
              Загружаем вопрос…
            </p>
          )}
          {user && !started && (
            <div className="assessment-welcome">
              <span className="badge">Без оценки и таймера</span>
              <h2 id="assessment-stage-heading" className="panel-heading">
                {isBeginner ? "Начните с объяснений" : "Что вы уже знаете?"}
              </h2>
              <p>
                {isBeginner
                  ? "Вы выбрали обучение с нуля. Вам не нужно угадывать ответы на незнакомые вопросы: первый урок объясняет, что такое программа и как читать простейший код."
                  : "Вопросы касаются основ Python. Не нужно готовиться или искать ответы: проверка нужна, чтобы не повторять уже знакомые темы."}
              </p>
              <ul className="assessment-intro-list">
                <li>Сложность меняется по вашим ответам.</li>
                <li>Если тема незнакома, нажмите «Не знаю — пропустить».</li>
                <li>Пропуск не считается ошибкой и не подтверждает знания.</li>
              </ul>
              <div className="entry-actions">
                {isBeginner ? (
                  <>
                    <a className="button" href="/learning">
                      Открыть первый урок
                    </a>
                    <button
                      className="button button-secondary"
                      disabled={loading}
                      onClick={() => void load()}
                    >
                      Всё же попробовать диагностику
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="button"
                      disabled={loading}
                      onClick={() => void load()}
                    >
                      Начать или продолжить проверку
                    </button>
                    <a className="button button-secondary" href="/learning">
                      Учиться без диагностики
                    </a>
                  </>
                )}
              </div>
            </div>
          )}
          {feedback && !loading && (
            <p className="status-message assessment-feedback" role="status">
              {feedback}
            </p>
          )}
          {state?.completed && !loading ? (
            <div className="assessment-complete">
              <span className="badge">Проверка завершена</span>
              <h2
                id="assessment-stage-heading"
                className="panel-heading"
                tabIndex={-1}
                ref={heading}
              >
                Можно переходить к обучению
              </h2>
              <p>
                Сохранено ответов: <strong>{state.answered}</strong>. Пропущено
                вопросов: <strong>{state.skipped ?? 0}</strong>.
              </p>
              <p className="page-subtitle">
                {state.answered
                  ? "Используем ответы как начальный ориентир. Настоящее освоение тем вы покажете в заданиях курса."
                  : "Ответов для оценки пока нет. Начнём с основ и будем выбирать следующие темы по результатам заданий."}
              </p>
              <div className="entry-actions">
                <a className="button" href="/learning">
                  Продолжить обучение
                </a>
                <button
                  className="button button-secondary"
                  onClick={() => void restart()}
                  disabled={busy}
                >
                  {busy ? "Готовим проверку…" : "Пройти ещё раз"}
                </button>
              </div>
            </div>
          ) : state?.question && !loading ? (
            <form className="assessment-question-form" onSubmit={submit}>
              <div className="assessment-progress">
                <span>Вопрос {state.question.question_number}</span>
                <span>Не более {state.question.total_questions} вопросов</span>
                <progress
                  aria-label="Пройденные вопросы диагностики"
                  value={completedSlots}
                  max={state.question.total_questions}
                />
              </div>
              <h2
                id="assessment-stage-heading"
                className="assessment-question-title"
                tabIndex={-1}
                ref={heading}
              >
                <QuestionText text={state.question.prompt} />
              </h2>
              {state.question.code && <pre className="assessment-code" aria-label="Фрагмент Python для вопроса"><code>{state.question.code}</code></pre>}
              <fieldset className="assessment-choices" disabled={busy}>
                <legend>Выберите один ответ</legend>
                {state.question.choices.map((choice) => (
                  <label
                    className="assessment-choice"
                    key={choice}
                    data-selected={answer === choice}
                  >
                    <input
                      type="radio"
                      name="assessment-answer"
                      value={choice}
                      checked={answer === choice}
                      onChange={() => setAnswer(choice)}
                      required
                    />
                    <span>
                      <QuestionText text={choice} />
                    </span>
                  </label>
                ))}
              </fieldset>
              <div className="assessment-question-actions">
                <button
                  className="button"
                  type="submit"
                  disabled={!answer || busy}
                >
                  {busy ? "Сохраняем…" : "Ответить"}
                </button>
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => void skipQuestion()}
                  disabled={busy}
                >
                  Не знаю — пропустить
                </button>
              </div>
              <p className="field-help">
                Сохранено ответов: {state.answered}. Пропусков:{" "}
                {state.skipped ?? 0}. Проверка не является экзаменом.
              </p>
            </form>
          ) : (
            started &&
            !loading &&
            user &&
            !error && (
              <div className="empty-state">
                <h2 id="assessment-stage-heading" className="panel-heading">
                  Сейчас нет назначенного вопроса
                </h2>
                <p>Можно начать проверку заново или перейти к урокам.</p>
                <div className="entry-actions">
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() => void restart()}
                  >
                    Начать проверку
                  </button>
                  <a className="button button-secondary" href="/learning">
                    Перейти к обучению
                  </a>
                </div>
              </div>
            )
          )}
        </section>
        <aside className="panel assessment-guide">
          <h2 className="panel-heading">Проверка — ориентир</h2>
          <p>
            Она помогает выбрать начало маршрута, а не оценивает вашу
            способность стать разработчиком.
          </p>
          <div className="assessment-guide-divider" />
          <h3>Если вы совсем новичок</h3>
          <p>
            Начните с первого урока. Там сначала объясняется тема, а задания
            проверяют то, что вы уже прочитали.
          </p>
          <a href="/learning">Открыть обучение →</a>
          <h3>Можно остановиться</h3>
          <p>
            Уже отправленные ответы сохранятся. К проверке можно вернуться
            позже.
          </p>
          <a href="/dashboard">Вернуться в кабинет →</a>
        </aside>
      </div>
    </main>
  );
}
