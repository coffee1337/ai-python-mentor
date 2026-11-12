import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicShell from "../../components/public-shell";
import { skill, skills } from "../../lib/seo";

export function generateStaticParams() {
  return skills.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = skill(slug);
  return item
    ? { title: `Навык: ${item.name}`, description: item.description, alternates: { canonical: `/skills/${item.slug}` } }
    : { title: "Навык не найден" };
}

export default async function SkillPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = skill(slug);
  if (!item) notFound();
  return (
    <PublicShell title={`Навык: ${item.name}`} lead={item.description}>
      <section className="panel">
        <p className="public-meta">{item.category}</p>
        {item.lessons.length ? (
          <ul className="public-list">
            {item.lessons.map((lesson) => (
              <li key={lesson.slug}>
                <Link href={`/concepts/${lesson.slug}`}>{lesson.title}</Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="product-field-hint">
            Темы этого навыка откроются по мере прохождения предыдущих — курс идёт по предпосылкам.
          </p>
        )}
      </section>
    </PublicShell>
  );
}
