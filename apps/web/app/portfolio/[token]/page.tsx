"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "../../lib/api";

type Portfolio = {
  title: string;
  summary: string;
  repository_url: string | null;
};

export default function PortfolioPage() {
  const params = useParams<{ token: string }>();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPortfolio(
        await api<Portfolio>(`/portfolio/${encodeURIComponent(params.token)}`),
      );
    } catch (reason) {
      setError(
        errorMessage(
          reason,
          "Портфолио недоступно. Автор мог закрыть доступ или удалить проект.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [params.token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="portfolio-public-shell">
      <header className="portfolio-public-header">
        <a className="brand" href="/">
          ↗ наставник<span className="brand-dot">.</span>
        </a>
        <a className="button button-secondary" href="/auth">
          Начать обучение
        </a>
      </header>
      <div className="portfolio-public-content">
        {loading && (
          <div className="panel product-loading" role="status">
            Загружаем портфолио проекта…
          </div>
        )}
        {error && (
          <section className="panel empty-state" role="alert">
            <span className="product-empty-icon" aria-hidden="true">
              ↗
            </span>
            <h1>Не удалось открыть портфолио</h1>
            <p>{error}</p>
            <button
              className="button button-secondary"
              onClick={() => void load()}
            >
              Повторить загрузку
            </button>
          </section>
        )}
        {portfolio && (
          <article className="panel portfolio-public-card">
            <p className="page-kicker">Портфолио учебного проекта</p>
            <div className="portfolio-public-title">
              <span className="portfolio-project-icon" aria-hidden="true">
                ⌘
              </span>
              <h1>{portfolio.title}</h1>
            </div>
            <section
              className="portfolio-project-description"
              aria-labelledby="portfolio-description-title"
            >
              <h2 id="portfolio-description-title">О проекте</h2>
              <p className="product-preserve-lines">{portfolio.summary}</p>
            </section>
            {portfolio.repository_url && (
              <a
                className="button"
                href={portfolio.repository_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Посмотреть репозиторий <span aria-hidden="true">↗</span>
              </a>
            )}
            <div className="portfolio-public-notice">
              <span className="badge">Учебная работа</span>
              <p>
                Описание предоставлено автором. Публикация не подтверждает
                выполнение кода или профессиональный уровень.
              </p>
            </div>
          </article>
        )}
        <footer className="portfolio-public-footer">
          <p>Учимся создавать понятные и работающие Backend-проекты.</p>
          <a href="/">Узнать о наставнике →</a>
        </footer>
      </div>
    </main>
  );
}
