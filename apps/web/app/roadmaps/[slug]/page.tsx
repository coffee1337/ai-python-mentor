import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicShell from "../../components/public-shell";
import { roadmaps, roadmap } from "../../lib/seo";

export function generateStaticParams() {
  return roadmaps.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = roadmap(slug);
  return item
    ? { title: `Маршрут: ${item.title}`, description: item.outcome, alternates: { canonical: `/roadmaps/${item.slug}` } }
    : { title: "Маршрут не найден" };
}

export default async function RoadmapPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = roadmap(slug);
  if (!item) notFound();
  return (
    <PublicShell title={item.title} lead={item.outcome}>
      <section className="panel">
        <p className="public-meta">
          {item.lessons.length} тем · ≈{item.minutes} минут
        </p>
        <ol className="public-list">
          {item.lessons.map((lesson) => (
            <li key={lesson.slug}>
              <Link href={`/concepts/${lesson.slug}`}>{lesson.title}</Link>
              <span className="public-meta"> · {lesson.minutes} мин</span>
            </li>
          ))}
        </ol>
      </section>
    </PublicShell>
  );
}
