import Link from "next/link";
import type { Metadata } from "next";
import PublicShell from "../components/public-shell";
import { concepts } from "../lib/seo";

export const metadata: Metadata = {
  title: "Темы курса Python — от переменных до backend",
  description:
    "90 тем курса Python: переменные, коллекции, функции, ошибки, API и базы данных. Краткое объяснение каждой темы и переход к уроку.",
  alternates: { canonical: "/concepts" },
};

export default function ConceptsIndex() {
  return (
    <PublicShell
      title="Темы курса"
      lead="Каждая тема — один урок с теорией, примером, проверкой понимания и заданием с исполнением кода."
    >
      <ul className="public-grid">
        {concepts.map((concept) => (
          <li key={concept.slug} className="panel public-card">
            <Link href={`/concepts/${concept.slug}`}>
              <strong>{concept.title}</strong>
            </Link>
            <p className="product-field-hint">{concept.summary}</p>
            <p className="public-meta">
              {concept.skill} · {concept.minutes} мин
            </p>
          </li>
        ))}
      </ul>
    </PublicShell>
  );
}
