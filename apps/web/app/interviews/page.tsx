import Link from "next/link";
import type { Metadata } from "next";
import PublicShell from "../components/public-shell";
import { interviews } from "../lib/seo";

export const metadata: Metadata = {
  title: "Собеседование junior Python backend: вопросы и разбор",
  description: "Что спрашивают на собеседовании junior backend: язык, базы данных, API, чтение кода, тесты и поведенческая часть.",
  alternates: { canonical: "/interviews" },
};

export default function InterviewsIndex() {
  return (
    <PublicShell
      title="Собеседование junior backend"
      lead="Наборы вопросов с разбором: что проверяет интервьюер, типичная ошибка ответа и как выглядит хороший ответ."
    >
      <ul className="public-grid">
        {interviews.map((guide) => (
          <li key={guide.slug} className="panel public-card">
            <Link href={`/interviews/${guide.slug}`}>
              <strong>{guide.title}</strong>
            </Link>
            <p className="product-field-hint">{guide.intro}</p>
            <p className="public-meta">{guide.questions.length} вопроса</p>
          </li>
        ))}
      </ul>
    </PublicShell>
  );
}
