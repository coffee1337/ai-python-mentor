import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicShell from "../../components/public-shell";
import { errorPage, errors } from "../../lib/seo";

export function generateStaticParams() {
  return errors.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const item = errorPage(slug);
  return item
    ? { title: `Ошибка: ${item.title}`, description: item.misconception, alternates: { canonical: `/errors/${item.slug}` } }
    : { title: "Ошибка не найдена" };
}

export default async function ErrorDetail({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = errorPage(slug);
  if (!item) notFound();
  return (
    <PublicShell title={item.title} lead={`Тема: ${item.lesson}`}>
      <article className="panel public-article">
        <h2>Что кажется</h2>
        <p>{item.misconception}</p>
        <h2>Как на самом деле</h2>
        <p>{item.correction}</p>
        <p>
          <Link className="button" href={`/concepts/${item.lesson_slug}`}>
            Разобрать тему целиком
          </Link>
        </p>
      </article>
    </PublicShell>
  );
}
