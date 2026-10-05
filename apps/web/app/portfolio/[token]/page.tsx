"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, errorMessage } from "../../lib/api";
type Portfolio = { title: string; summary: string; repository_url: string | null };
export default function PortfolioPage() {
  const params = useParams<{ token: string }>();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setPortfolio(await api<Portfolio>(`/portfolio/${encodeURIComponent(params.token)}`)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [params.token]);
  useEffect(() => { void load(); }, [load]);
  return <main className="dashboard-shell"><header className="topbar"><a className="brand" href="/">↗ наставник</a></header><article className="dashboard-card">{loading && <p role="status">Загружаем портфолио…</p>}{error && <div role="alert"><p>{error}</p><button className="text-button" onClick={() => void load()}>Повторить</button></div>}{portfolio && <><p className="eyebrow">ПОРТФОЛИО УЧЕБНОГО ПРОЕКТА</p><h1>{portfolio.title}</h1><p className="preserve-lines">{portfolio.summary}</p>{portfolio.repository_url && <p><a href={portfolio.repository_url} target="_blank" rel="noopener noreferrer">Открыть репозиторий</a></p>}<p className="muted">Описание предоставлено автором проекта. Публикация не подтверждает выполнение кода или профессиональный уровень.</p></>}</article></main>;
}
