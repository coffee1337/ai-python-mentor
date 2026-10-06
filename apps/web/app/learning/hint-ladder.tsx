"use client";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, errorMessage, newRequestId } from "../lib/api";
import RichText from "./rich-text";
type Hint = { level: number; kind: string; text: string };
type HintProgress = {
  exercise_version: string;
  revealed: Hint[];
  next_level: number | null;
};
const LABELS: Record<string, string> = {
  direction: "Направление",
  concept: "Идея",
  step: "Следующий шаг",
  pseudocode: "Псевдокод",
  solution: "Решение",
};
export default function HintLadder({ lessonId }: { lessonId: string }) {
  const headingId = useId();
  const [progress, setProgress] = useState<HintProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const keys = useRef<Record<string, string>>({});
  const path = `/learning/exercises/${encodeURIComponent(lessonId)}/hints`;
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setProgress(await api<HintProgress>(path));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void load();
  }, [load]);

  async function reveal() {
    if (!progress?.next_level || busy) return;
    setBusy(true);
    setError("");
    const scope = `${progress.exercise_version}:${progress.next_level}`;
    try {
      const hint = await api<Hint>(path, {
        method: "POST",
        headers: {
          "Idempotency-Key":
            keys.current[scope] ?? (keys.current[scope] = newRequestId()),
        },
        body: JSON.stringify({ level: progress.next_level }),
      });
      setProgress((current) =>
        current
          ? {
              ...current,
              revealed: [
                ...current.revealed.filter((item) => item.level !== hint.level),
                hint,
              ],
              next_level: hint.level < 5 ? hint.level + 1 : null,
            }
          : null,
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="hint-ladder"
      aria-labelledby={headingId}
      aria-busy={loading || busy}
    >
      <h3 id={headingId}>Подсказки по шагам</h3>
      <p className="muted">
        Начните с небольшой подсказки. Открытые уровни учитываются отдельно от
        самостоятельного решения.
      </p>
      {loading && <p role="status">Загружаем подсказки…</p>}
      {progress && (
        <ol>
          {progress.revealed.map((hint) => (
            <li key={hint.level}>
              <strong>{LABELS[hint.kind] ?? "Подсказка"}</strong>
              <RichText text={hint.text} />
            </li>
          ))}
        </ol>
      )}
      {progress?.next_level === 5 && (
        <p className="muted">
          Следующий уровень содержит готовое решение. Оно поможет разобрать
          материал, но не подтвердит самостоятельность.
        </p>
      )}
      {!loading &&
        progress &&
        (progress.next_level ? (
          <button
            className="text-button"
            type="button"
            disabled={busy}
            onClick={() => void reveal()}
          >
            {busy
              ? "Открываем…"
              : progress.next_level === 5
                ? "Открыть решение"
                : `Открыть подсказку ${progress.next_level}`}
          </button>
        ) : (
          <p role="status">
            Все уровни открыты. Попробуйте теперь объяснить решение своими
            словами.
          </p>
        ))}
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          <button
            className="text-button"
            type="button"
            disabled={busy || loading}
            onClick={() => void load()}
          >
            Обновить подсказки
          </button>
        </div>
      )}
    </section>
  );
}
