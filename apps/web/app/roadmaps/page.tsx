import Link from "next/link";
import type { Metadata } from "next";
import PublicShell from "../components/public-shell";
import { roadmaps } from "../lib/seo";

export const metadata: Metadata = {
  title: "Маршруты обучения Python",
  description: "Три этапа курса: первые программы, основа Python и Python Backend. Что входит в каждый и сколько времени занимает.",
  alternates: { canonical: "/roadmaps" },
};

export default function RoadmapsIndex() {
  return (
    <PublicShell title="Маршруты" lead="Курс идёт тремя этапами. Маршрут — это этап целиком, с составом и временем.">
      <ul className="public-grid">
        {roadmaps.map((roadmap) => (
          <li key={roadmap.slug} className="panel public-card">
            <Link href={`/roadmaps/${roadmap.slug}`}>
              <strong>{roadmap.title}</strong>
            </Link>
            <p className="product-field-hint">{roadmap.outcome}</p>
            <p className="public-meta">
              {roadmap.lessons.length} тем · ≈{roadmap.minutes} мин
            </p>
          </li>
        ))}
      </ul>
    </PublicShell>
  );
}
