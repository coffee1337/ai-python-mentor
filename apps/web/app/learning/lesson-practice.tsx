"use client";
import dynamic from "next/dynamic";
import { FormEvent } from "react";
// The editor is only needed once a learner reaches the submission block, so it is
// loaded on demand. This keeps the lesson page's initial payload small; the
// fallback mirrors the editor's layout so the form does not jump.
const CodeEditor = dynamic(() => import("./code-editor"), {
  ssr: false,
  loading: () => (
    <p className="code-editor-loading" role="status" aria-live="polite">
      Загружаем редактор кода…
    </p>
  ),
});
export const SOURCE_LIMIT = 20000;
const STARTER_CODE = "def solve():\n    # Напишите решение\n    pass\n";
type LessonPracticeProps = {
  source: string;
  onSourceChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  busy: boolean;
  disabled?: boolean;
  executionConfigured?: boolean;
};
/**
 * Code submission block. The runner is fail-closed, so the button saves an
 * attempt and the copy says exactly that: no execution, no correctness verdict.
 * The editor enforces the 20 000 character limit; this component adds no
 * client-side checks that could contradict the server.
 */
export default function LessonPractice({
  source,
  onSourceChange,
  onSubmit,
  busy,
  disabled = false,
  executionConfigured = false,
}: LessonPracticeProps) {
  return (
    <form onSubmit={onSubmit} className="lesson-practice">
      <h3>Ваше решение</h3>
      <CodeEditor
        id="source-code"
        label="Python-код"
        value={source}
        onChange={onSourceChange}
        maxLength={SOURCE_LIMIT}
        disabled={busy || disabled}
        describedBy="runner-status-note"
        hint="Отступы 4 пробела. С клавиатуры: Tab и Shift+Tab меняют отступ, Esc, затем Tab — выйти из редактора."
      />
      <p className="muted" id="runner-status-note">
        {executionConfigured
          ? "Код будет отправлен в изолированную очередь проверки. Результат определяет сервер; возможны ограничения времени и ресурсов."
          : "Запуск кода сейчас недоступен. Попытка сохранится, но правильность решения и освоение темы не будут подтверждены."}
      </p>
      <button
        type="submit"
        className="button"
        disabled={disabled || busy || !source.trim()}
      >
        {busy
          ? "Сохраняем…"
          : executionConfigured
            ? "Отправить на проверку"
            : "Сохранить попытку"}
      </button>
    </form>
  );
}
export { STARTER_CODE };
