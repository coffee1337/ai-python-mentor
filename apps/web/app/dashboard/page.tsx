"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "../lib/api";

export default function DashboardPage() {
  const router = useRouter(); const [user, setUser] = useState<User | null>(null);
  useEffect(() => { api<User>("/me").then(setUser).catch(() => router.replace("/auth")); }, [router]);
  async function logout() { await api<void>("/auth/logout", { method: "POST" }); router.replace("/"); }
  if (!user) return <main className="auth-shell"><p>Загружаем ваш маршрут…</p></main>;
  return <main className="dashboard-shell"><header className="topbar"><a className="brand" href="/">↗ наставник<span className="brand-dot">.</span></a><button className="text-button" onClick={logout}>Выйти</button></header><section className="dashboard-card"><span className="eyebrow"><i /> ВАШ МАРШРУТ</span><h1>Добро пожаловать{user.profile?.display_name ? ", " + user.profile.display_name : ""}.</h1><p className="auth-lead">Цель: <strong>{user.goal?.target_role ?? "настроить цель"}</strong></p><div className="dashboard-meta"><div><b>{user.goal?.weekly_minutes ?? 0}</b><span>минут в неделю</span></div><div><b>{user.profile?.experience_level ?? "—"}</b><span>текущий уровень</span></div></div><p className="muted">Начните с короткого авторского маршрута по основам Python.</p><a href={user.profile?.onboarding_completed ? "/learning" : "/onboarding"}>{user.profile?.onboarding_completed ? "Продолжить обучение →" : "Завершить настройку →"}</a></section></main>;
}
