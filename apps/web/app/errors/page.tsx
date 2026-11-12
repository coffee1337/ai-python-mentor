import Link from "next/link";
import type { Metadata } from "next";
import PublicShell from "../components/public-shell";
import { errors } from "../lib/seo";

export const metadata: Metadata = {
  title: "Частые ошибки новичков в Python",
  description: "Типичные заблуждения из курса: что думает новичок, почему это не так и как правильно.",
  alternates: { canonical: "/errors" },
};

export default function ErrorsIndex() {
  return (
    <PublicShell title="Частые ошибки" lead="Заблуждения, с которыми новички приходят чаще всего, и короткое объяснение, почему это не так.">
      <ul className="public-grid">
        {errors.map((item) => (
          <li key={item.slug} className="panel public-card">
            <Link href={`/errors/${item.slug}`}>
              <strong>{item.title}</strong>
            </Link>
            <p className="public-meta">Тема: {item.lesson}</p>
          </li>
        ))}
      </ul>
    </PublicShell>
  );
}
