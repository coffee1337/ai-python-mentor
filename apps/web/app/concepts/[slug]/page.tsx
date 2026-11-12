import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicShell from "../../components/public-shell";
import { SITE, concept, concepts, skill } from "../../lib/seo";

export function generateStaticParams() {
  return concepts.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = concept(slug);
  if (!item) return { title: "Тема не найдена" };
  return {
    title: `${item.title} — тема курса Python`,
    description: item.summary,
    alternates: { canonical: `/concepts/${item.slug}` },
    openGraph: { title: item.title, description: item.summary, type: "article" },
  };
}

export default async function ConceptPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = concept(slug);
  if (!item) notFound();
  const related = skill(item.skill_id.replace(/\./g, "-"));
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "LearningResource",
    name: item.title,
    description: item.summary,
    inLanguage: "ru",
    educationalLevel: item.difficulty,
    timeRequired: `PT${item.minutes}M`,
    url: `${SITE}/concepts/${item.slug}`,
    isAccessibleForFree: true,
    provider: { "@type": "Organization", name: "AI Python Mentor" },
  };
  return (
    <PublicShell title={item.title} lead={item.summary}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <article className="panel public-article">
        <p className="public-meta">
          {item.skill} · {item.minutes} мин · {item.difficulty}
        </p>
        <p>{item.body}</p>
        <p>
          <Link className="button" href={`/auth?next=/learning/${item.slug}`}>
            Пройти тему с проверкой
          </Link>
        </p>
      </article>
      {related && related.lessons.length > 1 ? (
        <section className="panel">
          <h2>Ещё по навыку «{related.name}»</h2>
          <ul>
            {related.lessons
              .filter((lesson) => lesson.slug !== item.slug)
              .map((lesson) => (
                <li key={lesson.slug}>
                  <Link href={`/concepts/${lesson.slug}`}>{lesson.title}</Link>
                </li>
              ))}
          </ul>
        </section>
      ) : null}
    </PublicShell>
  );
}
