import { Fragment, type ReactNode } from "react";
/** Render authored and mentor text as React elements. HTML is always plain text. */
export function InlineText({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`"))
          return <code key={index}>{part.slice(1, -1)}</code>;
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}
export default function RichText({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.trimStart().startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (
        index < lines.length &&
        !lines[index].trimStart().startsWith("```")
      ) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(
        <pre key={blocks.length}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    const listMatch = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.+)$/);
    if (listMatch) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const items: string[] = [];
      const pattern = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*•]\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(pattern);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      const content = items.map((item, itemIndex) => (
        <li key={itemIndex}>
          <InlineText text={item} />
        </li>
      ));
      blocks.push(
        ordered ? (
          <ol key={blocks.length}>{content}</ol>
        ) : (
          <ul key={blocks.length}>{content}</ul>
        ),
      );
      continue;
    }
    if (/^\s*#{1,6}\s/.test(line)) {
      blocks.push(
        <h4 key={blocks.length}>
          <InlineText text={line.replace(/^\s*#{1,6}\s+/, "")} />
        </h4>,
      );
      index += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^\s*(?:```|#{1,6}\s|[-*•]\s|\d+[.)]\s)/.test(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    // Unrecognized Markdown must still consume input; mentor text is untrusted.
    if (paragraph.length === 0) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(
      <p key={blocks.length}>
        <InlineText text={paragraph.join(" ")} />
      </p>,
    );
  }
  return <div className="lesson-rich-text">{blocks}</div>;
}
