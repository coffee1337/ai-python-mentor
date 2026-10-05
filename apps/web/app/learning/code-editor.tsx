"use client";

import { useCallback, useEffect, useId, useMemo, useRef } from "react";
import { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import {
  bracketMatching,
  HighlightStyle,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { Compartment, EditorState } from "@codemirror/state";
import {
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightSpecialChars,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

const INDENT = "    ";

export type CodeEditorProps = {
  /** Current code. The component is controlled: it never keeps its own copy. */
  value: string;
  /** Called on every document change with the next value, already truncated to `maxLength`. */
  onChange: (value: string) => void;
  /** Hard limit in characters. Previously held in `textarea.maxLength`. */
  maxLength?: number;
  disabled?: boolean;
  readOnly?: boolean;
  id?: string;
  label: string;
  describedBy?: string;
  /** Short help for screen reader users, e.g. how to indent and how to leave. */
  hint?: string;
};

function trimToLimit(value: string, maxLength: number): string {
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

/**
 * Python code editor for exercise attempts.
 *
 * Runner is fail-closed: this editor only collects the submission text. It never
 * claims the code was executed and adds no client-side correctness checks — the
 * server decides whether an attempt is right.
 *
 * Built on CodeMirror 6 core packages directly (no wrapper, no bundled
 * basic-setup) so the lesson page does not pay for search, lint and completion UI
 * it will never expose.
 */
export default function CodeEditor({
  value,
  onChange,
  maxLength = 20000,
  disabled = false,
  readOnly = false,
  id,
  label,
  describedBy,
  hint,
}: CodeEditorProps) {
  const generatedId = useId();
  const editorId = id ?? `code-editor-${generatedId}`;
  const labelId = `${editorId}-label`;
  const hintId = hint ? `${editorId}-hint` : undefined;
  const counterId = `${editorId}-counter`;
  const describedByValue = [describedBy, hintId, counterId].filter(Boolean).join(" ");

  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const maxLengthRef = useRef(maxLength);
  maxLengthRef.current = maxLength;

  // `disabled` / `readOnly` live in their own compartment so toggling them
  // reconfigures the live editor instead of recreating it and losing history.
  const editableCompartment = useMemo(() => new Compartment(), []);

  // Highlighting is built from the project palette instead of a bundled editor
  // theme, so the code surface reads as part of the same visual system.
  // Every colour below is checked for WCAG AA (>= 4.5:1) against the editor
  // surface `#ffffff`: the accent `--green-deep` (#6f9142) only reaches 3.62:1
  // and is darkened to #4a6b2c / #456231 for text use. `--danger` (#9a5148) is
  // kept, it reaches 5.76:1. Decoration (caret, active line, selection) is not
  // text and is held to the 3:1 non-text minimum instead.
  const highlightStyle = useMemo(
    () =>
      HighlightStyle.define([
        { tag: [t.keyword, t.modifier, t.controlKeyword], color: "#4a6b2c" },
        { tag: [t.name, t.function(t.variableName), t.labelName], color: "#1f332b" },
        { tag: [t.variableName, t.propertyName], color: "#33463d" },
        { tag: [t.typeName, t.className, t.namespace], color: "#4a6b2c" },
        { tag: [t.number, t.bool, t.null, t.atom], color: "#9a5148" },
        { tag: [t.string, t.special(t.string)], color: "#456231" },
        { tag: [t.comment, t.lineComment, t.blockComment, t.docComment], color: "#5c6a63", fontStyle: "italic" },
        { tag: [t.operator, t.operatorKeyword, t.punctuation, t.bracket], color: "#33463d" },
        { tag: [t.separator, t.meta], color: "#5c6a63" },
        { tag: t.invalid, color: "#9a5148" },
      ]),
    [],
  );

  // Python indentation comes from `:` + Enter and from Tab. The indent unit must be
  // four spaces to match PEP 8.
  const extensions = useMemo(
    () => [
      python(),
      indentUnit.of(INDENT),
      EditorState.tabSize.of(4),
      EditorState.allowMultipleSelections.of(true),
      editableCompartment.of(EditorView.editable.of(true)),
      lineNumbers(),
      highlightActiveLine(),
      highlightSpecialChars(),
      history(),
      drawSelection(),
      dropCursor(),
      rectangularSelection(),
      indentOnInput(),
      bracketMatching(),
      closeBrackets(),
      syntaxHighlighting(highlightStyle, { fallback: true }),
      EditorView.lineWrapping,
      EditorView.contentAttributes.of({
        "aria-labelledby": labelId,
        ...(describedByValue ? { "aria-describedby": describedByValue } : {}),
        "data-testid": "code-editor-content",
      }),
      keymap.of([
        ...closeBracketsKeymap,
        ...defaultKeymap,
        ...historyKeymap,
        indentWithTab,
      ]),
      EditorView.updateListener.of((update) => {
        if (!update.docChanged) return;
        // The limit is enforced here rather than through a native `maxlength`
        // attribute, because CodeMirror renders a contenteditable surface. Any
        // overflow is truncated and pushed back into the document by the
        // controlled sync effect below.
        onChangeRef.current(
          trimToLimit(update.state.doc.toString(), maxLengthRef.current),
        );
      }),
    ],
    [highlightStyle, labelId, describedByValue, editableCompartment],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const view = new EditorView({
      parent: container,
      state: EditorState.create({ doc: value, extensions }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Recreated only when the extension set changes; `value` is synced separately
    // below so the caret is not reset on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extensions]);

  // Controlled sync: push external value changes (new lesson, restored draft) into
  // the editor document.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    const anchor = Math.min(view.state.selection.main.anchor, value.length);
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      selection: { anchor },
    });
  }, [value]);

  // `disabled` and `readOnly` must block editing without recreating the editor.
  useEffect(() => {
    viewRef.current?.dispatch({
      effects: editableCompartment.reconfigure(EditorView.editable.of(!disabled && !readOnly)),
    });
  }, [disabled, readOnly, editableCompartment]);

  const isAtLimit = value.length >= maxLength;

  return (
    <div className="code-editor-field" data-disabled={disabled || undefined}>
      <span className="code-editor-label" id={labelId}>
        {label}
      </span>
      <div
        className="code-editor-surface"
        id={editorId}
        ref={containerRef}
        data-testid="code-editor"
        data-disabled={disabled || undefined}
        aria-disabled={disabled || undefined}
      >
        {/* The editable surface is created by CodeMirror inside the wrapper above.
            This element is only a no-JS fallback; it disappears once the editor
            mounts, so the label is bound to the real `cm-content` node. */}
        <noscript>
          <textarea
            className="code-editor"
            id={`${editorId}-fallback`}
            defaultValue={value}
            maxLength={maxLength}
            spellCheck={false}
            readOnly={disabled || readOnly}
            aria-describedby={describedByValue || undefined}
          />
        </noscript>
      </div>
      <div className="code-editor-footer">
        <p className="code-editor-hint" id={hintId}>
          {hint ??
            "Отступы 4 пробела. С клавиатуры: Tab и Shift+Tab меняют отступ, Esc возвращает фокус на страницу."}
        </p>
        <p className="code-editor-counter" id={counterId} data-at-limit={isAtLimit || undefined}>
          {value.length} из {maxLength} символов
        </p>
      </div>
    </div>
  );
}
