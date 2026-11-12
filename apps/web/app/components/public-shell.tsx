import Link from "next/link";
import type { ReactNode } from "react";

export default function PublicShell({
  title,
  lead,
  children,
}: {
  title: string;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <main className="dashboard-shell">
      <header className="public-header">
        <Link className="public-brand" href="/">
          AI Python Mentor
        </Link>
        <nav className="public-nav" aria-label="Публичные разделы">
          <Link href="/concepts">Темы</Link>
          <Link href="/roadmaps">Маршруты</Link>
          <Link href="/errors">Ошибки</Link>
          <Link href="/interviews">Собеседование</Link>
        </nav>
        <Link className="button button-secondary" href="/auth">
          Начать учиться
        </Link>
      </header>
      <div className="page-content">
        <h1 className="page-title">{title}</h1>
        {lead ? <p className="page-lead">{lead}</p> : null}
        {children}
      </div>
    </main>
  );
}
