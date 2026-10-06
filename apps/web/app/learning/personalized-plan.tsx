"use client";
import dynamic from "next/dynamic";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, newRequestId } from "../lib/api";
import type { AIPlan } from "./lesson-types";
import RichText from "./rich-text";
import { skillLabel } from "./skill-labels";
const CodeEditor = dynamic(() => import("./code-editor"), {
  ssr: false,
  loading: () => <p role="status">Загружаем редактор…</p>,
});
type GeneratedAttempt = {
  id: string;
  status: string;
  feedback: {
    message: string;
    advisory?: boolean;
    mastery_credit?: boolean | string;
    verdict?: string;
    job_path?: string;
    execution_status?: string;
  };
  coding_status?: string;
  result?: { message?: string; tests_passed?: number; tests_total?: number };
  created_at: string;
};
type Step = AIPlan["steps"][number];
const VERDICTS: Record<string, string> = {
  meets_criteria: "Ответ соответствует критериям по мнению AI",
  needs_revision: "Есть что уточнить",
  uncertain: "AI не смог дать уверенный разбор",
};
function GeneratedExercise({
  step,
  generationId,
  userId,
}: {
  step: Step;
  generationId: string;
  userId: string;
}) {
  const [answer, setAnswer] = useState(step.exercise.starter_code ?? "");
  const [attempts, setAttempts] = useState<GeneratedAttempt[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [waiting, setWaiting] = useState<string | null>(null);
  const [stopped, setStopped] = useState(false);
  const pending = useRef<{ key: string; answer: string } | null>(null);
  const path = `/learning/personalized-plan/${encodeURIComponent(generationId)}/steps/${step.position}/attempts`;
  const draftKey = `mentor.generated.draft.v2.${userId}.${generationId}.${step.position}`;
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setAttempts(await api<GeneratedAttempt[]>(path));
      setError("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(draftKey);
      if (raw !== null && raw.length <= 20000) setAnswer(raw);
    } catch {
      /* Storage optional. */
    }
    void load();
  }, [draftKey, load]);
  useEffect(() => {
    if (!waiting || stopped) return;
    const controller = new AbortController();
    const started = Date.now();
    let checking = false;
    const timer = window.setInterval(async () => {
      if (checking) return;
      if (Date.now() - started > 90000) {
        setStopped(true);
        return;
      }
      checking = true;
      try {
        const job = await api<{ status: string }>(waiting, {
          signal: controller.signal,
        });
        if (
          !controller.signal.aborted &&
          !["queued", "running"].includes(job.status)
        ) {
          setWaiting(null);
          await load();
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(errorMessage(reason));
          setStopped(true);
        }
      } finally {
        checking = false;
      }
    }, 2000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [waiting, stopped, load]);
  function change(value: string) {
    setAnswer(value);
    pending.current = null;
    try {
      window.localStorage.setItem(draftKey, value);
    } catch {
      /* Storage optional. */
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !answer.trim()) return;
    setBusy(true);
    setError("");
    pending.current ??= { key: newRequestId(), answer };
    try {
      const result = await api<GeneratedAttempt>(path, {
        method: "POST",
        body: JSON.stringify({
          answer: pending.current.answer,
          idempotency_key: pending.current.key,
        }),
      });
      setAttempts((current) =>
        [result, ...current.filter((item) => item.id !== result.id)].slice(
          0,
          20,
        ),
      );
      pending.current = null;
      if (
        result.feedback.job_path?.startsWith("/learning/jobs/") &&
        ["queued", "running"].includes(
          result.coding_status ?? result.feedback.execution_status ?? "",
        )
      ) {
        setWaiting(result.feedback.job_path);
        setStopped(false);
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article
      className="saved-item"
      aria-labelledby={`generated-step-${step.position}`}
    >
      <div className="generated-step-meta">
        <span className="badge">{skillLabel(step.skill_id)}</span>
        <span className="muted">Около {step.duration_minutes} минут</span>
      </div>
      <h3 id={`generated-step-${step.position}`}>
        {step.position}. {step.title}
      </h3>
      <RichText text={step.explanation} />
      <h4>Что нужно сделать</h4>
      <RichText text={step.exercise.prompt} />
      {step.exercise.constraints.length > 0 && (
        <>
          <h4>Ограничения</h4>
          <ul>
            {step.exercise.constraints.map((constraint) => (
              <li key={constraint}>{constraint}</li>
            ))}
          </ul>
        </>
      )}
      <form className="settings-form" onSubmit={submit}>
        {step.exercise.submission_type === "python_code" ? (
          <CodeEditor
            id={`generated-code-${step.position}`}
            label="Python-код для этого задания"
            value={answer}
            onChange={change}
            maxLength={20000}
            disabled={busy || !!waiting}
          />
        ) : (
          <label>
            Ваш ответ
            <textarea
              value={answer}
              onChange={(event) => change(event.target.value)}
              required
              maxLength={20000}
              rows={6}
              disabled={busy}
            />
          </label>
        )}
        <p className="muted">
          {step.exercise.submission_type === "python_code"
            ? "Условия проверки кода зависят от этого задания и доступности безопасного запуска. Сохранённая попытка ещё не означает правильное решение."
            : "Нейросеть предлагает разбор ответа. Он не заменяет проверку основного курса и не меняет подтверждённый прогресс."}
        </p>
        <button
          className="button"
          disabled={busy || !!waiting || !answer.trim()}
        >
          {busy ? "Сохраняем…" : "Сохранить и разобрать ответ"}
        </button>
      </form>
      {waiting && <p role="status">Ожидаем результат проверки кода…</p>}
      {stopped && waiting && (
        <p>
          Автоматическое ожидание завершено.{" "}
          <button className="text-button" onClick={() => setStopped(false)}>
            Продолжить ожидание
          </button>
        </p>
      )}
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          <button
            className="text-button"
            disabled={loading || busy}
            onClick={() => void load()}
          >
            Обновить историю ответов
          </button>
        </div>
      )}
      {loading && <p role="status">Загружаем историю ответов…</p>}
      {!loading && attempts.length === 0 && !error && (
        <p className="muted">Сохранённых ответов пока нет.</p>
      )}
      {attempts.length > 0 && (
        <div aria-live="polite">
          {attempts.map((attempt) => (
            <div className="review-result" key={attempt.id}>
              {attempt.feedback.verdict && (
                <strong>
                  {VERDICTS[attempt.feedback.verdict] ?? "Результат разбора"}
                </strong>
              )}
              <p>{attempt.feedback.message}</p>
              {attempt.result?.message && <p>{attempt.result.message}</p>}
              {typeof attempt.result?.tests_total === "number" &&
                attempt.result.tests_total > 0 && (
                  <p>
                    Тесты: {attempt.result.tests_passed} из{" "}
                    {attempt.result.tests_total}.
                  </p>
                )}
              {attempt.feedback.advisory && (
                <p className="muted">
                  Рекомендация AI; самостоятельное освоение не подтверждено.
                </p>
              )}
              <time dateTime={attempt.created_at}>
                {new Date(attempt.created_at).toLocaleString("ru-RU")}
              </time>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
export default function PersonalizedPlan({
  plan,
  error,
  loading = false,
  userId,
  onChange,
  onReload,
}: {
  plan: AIPlan | null;
  error: string;
  loading?: boolean;
  userId: string;
  onChange: (plan: AIPlan) => void;
  onReload: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [generationError, setGenerationError] = useState("");
  async function generate() {
    setBusy(true);
    setGenerationError("");
    try {
      onChange(
        await api<AIPlan>("/learning/personalized-plan/generate", {
          method: "POST",
        }),
      );
    } catch (reason) {
      setGenerationError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="lesson-subsection"
      aria-labelledby="personalized-plan-title"
    >
      <h2 id="personalized-plan-title">Дополнительная практика от AI</h2>
      {loading && <p role="status">Загружаем персональные упражнения…</p>}
      <p className="muted">
        Основной курс объясняет тему и проверяет знания. Здесь нейросеть может
        предложить дополнительные упражнения по вашим потребностям и разобрать
        текстовый ответ.
      </p>
      {(error || generationError) && (
        <div role="alert">
          <p className="form-error">{generationError || error}</p>
          <p className="muted">
            AI сейчас не ответил. Основной курс, примеры и проверка понимания
            остаются доступными.
          </p>
          <button
            className="button-secondary"
            disabled={busy}
            onClick={onReload}
          >
            Обновить план
          </button>
        </div>
      )}
      {plan?.warning && (
        <p className="review-state" role="status">
          {plan.warning}
        </p>
      )}
      {plan?.generated_at && (
        <p className="muted">
          Составлен:{" "}
          <time dateTime={plan.generated_at}>
            {new Date(plan.generated_at).toLocaleString("ru-RU")}
          </time>
          .
        </p>
      )}
      <button
        className="button-secondary"
        type="button"
        disabled={busy || loading}
        onClick={() => void generate()}
      >
        {busy
          ? "Составляем упражнения…"
          : plan?.status === "ready"
            ? "Обновить упражнения"
            : "Подобрать упражнения"}
      </button>
      {!loading && plan?.status !== "ready" && (
        <p className="muted">
          Подбор упражнений требует завершённой{" "}
          <a href="/assessment">необязательной диагностики</a> и подключённого
          AI. Первый урок и основной маршрут работают без них.
        </p>
      )}
      {plan?.status === "ready" &&
        plan.steps.map((step) => (
          <details
            className="lesson-detail generated-step"
            key={`${plan.generation_id ?? "legacy"}.${step.position}`}
          >
            <summary>
              {step.position}. {step.title} · {step.duration_minutes} минут
            </summary>
            {plan.generation_id ? (
              <GeneratedExercise
                step={step}
                generationId={plan.generation_id}
                userId={userId}
              />
            ) : (
              <article className="saved-item">
                <h3>{step.title}</h3>
                <RichText text={step.explanation} />
                <RichText text={step.exercise.prompt} />
                <p className="muted">
                  Для сохранения ответов обновите упражнения.
                </p>
              </article>
            )}
          </details>
        ))}
    </section>
  );
}
