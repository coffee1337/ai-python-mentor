import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicShell from "../../components/public-shell";
import { interview, interviews } from "../../lib/seo";

export function generateStaticParams() {
  return interviews.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = interview(slug);
  return item
    ? { title: item.title, description: item.intro, alternates: { canonical: `/interviews/${item.slug}` } }
    : { title: "Разбор не найден" };
}

export default async function InterviewGuide({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = interview(slug);
  if (!item) notFound();
  return (
    <PublicShell title={item.title} lead={item.intro}>
      <div className="public-stack">
        {item.questions.map((entry) => (
          <article key={entry.question} className="panel public-article">
            <h2>{entry.question}</h2>
            <p>
              <strong>Что проверяют:</strong> {entry.checks}
            </p>
            <p>
              <strong>Типичная ошибка:</strong> {entry.mistake}
            </p>
            <p>
              <strong>Как ответить:</strong> {entry.answer}
            </p>
          </article>
        ))}
      </div>
    </PublicShell>
  );
}
