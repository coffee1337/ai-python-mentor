"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, clearLocalDrafts } from "../lib/api";
import AppIcon, { type IconName } from "./app-icon";
import { useStudySession } from "./study-session-provider";

const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboard", label: "Моё обучение", icon: "home" },
  { href: "/learning/path", label: "Программа курса", icon: "route" },
  { href: "/learning", label: "Текущий урок", icon: "book" },
  { href: "/learning/progress", label: "Мой прогресс", icon: "route" },
  { href: "/learning/reviews", label: "Повторения", icon: "check" },
  { href: "/learning/sessions", label: "История занятий", icon: "book" },
  { href: "/projects", label: "Мои проекты", icon: "folder" },
  { href: "/jobs", label: "Карьерная цель", icon: "briefcase" },
];
const settings: { href: string; label: string; icon: IconName }[] = [
  { href: "/account", label: "Личный кабинет", icon: "user" },
  { href: "/billing", label: "Тариф и подписка", icon: "wallet" },
];

export default function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { clear: clearStudySession } = useStudySession();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const current = [...navigation, ...settings].find(
    (item) => pathname === item.href,
  );

  useEffect(() => {
    if (!open || !sidebar.current) return;
    const media = window.matchMedia("(max-width: 900px)");
    if (!media.matches) { setOpen(false); return; }
    const panel = sidebar.current;
    const siblings = Array.from(panel.parentElement?.children ?? [])
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node !== panel && !node.classList.contains("sidebar-backdrop"));
    const previousInert = siblings.map((node) => node.inert);
    const previousOverflow = document.body.style.overflow;
    siblings.forEach((node) => { node.inert = true; });
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(panel.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex="0"]',
    )).filter((node) => node.getClientRects().length > 0);
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
      }
      if (event.key === "Tab") {
        const elements = focusable();
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (!first) return;
        if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
          event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
          event.preventDefault(); first.focus();
        }
      }
    };
    const onResize = () => { if (!media.matches) setOpen(false); };
    document.addEventListener("keydown", onKeyDown);
    media.addEventListener("change", onResize);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      media.removeEventListener("change", onResize);
      siblings.forEach((node, index) => { node.inert = previousInert[index]; });
      document.body.style.overflow = previousOverflow;
      if (menuButton.current?.isConnected && media.matches) menuButton.current.focus();
    };
  }, [open]);

  async function logout() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api<void>("/auth/logout", { method: "POST" });
      clearStudySession();
      clearLocalDrafts();
      router.replace("/auth");
    } catch {
      setError("Не удалось выйти. Повторите попытку.");
    } finally {
      setBusy(false);
    }
  }

  function links(items: typeof navigation) {
    return items.map((item) => (
      <Link
        className={`sidebar-link${pathname === item.href ? " is-active" : ""}`}
        href={item.href}
        key={item.href}
        aria-current={pathname === item.href ? "page" : undefined}
        onClick={() => setOpen(false)}
      >
        <AppIcon name={item.icon} />
        <span>{item.label}</span>
      </Link>
    ));
  }

  return (
    <>
      <a className="skip-link" href="#workspace-content">
        К содержимому
      </a>
      {open && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Закрыть навигацию"
          tabIndex={-1}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        className={`app-sidebar${open ? " is-open" : ""}`}
        id="app-navigation"
        aria-label="Главная навигация"
      >
        <button
          className="sidebar-close"
          type="button"
          aria-label="Свернуть навигацию"
          onClick={() => setOpen(false)}
        >
          <AppIcon name="close" size={18} />
        </button>
        <Link
          className="brand"
          href="/dashboard"
          onClick={() => setOpen(false)}
        >
          <span className="brand-mark">
            <AppIcon name="code" size={18} />
          </span>
          наставник<span className="brand-dot">.</span>
        </Link>
        <div className="sidebar-course">
          <span className="badge">ВАШ КУРС</span>
          <strong>Python Backend</strong>
          <span>От первой строки до своего API</span>
        </div>
        <nav className="sidebar-nav" aria-label="Обучение">
          <span className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</span>
          {links(navigation)}
        </nav>
        <nav className="sidebar-nav sidebar-settings" aria-label="Настройки">
          <span className="nav-label">АККАУНТ</span>
          {links(settings)}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help">
            <AppIcon name="sparkles" />
            <div>
              <strong>Учитесь с наставником</strong>
              <p>Задавайте вопросы по теме прямо на странице урока.</p>
            </div>
          </div>
          <button
            className="sidebar-link logout-button"
            onClick={() => void logout()}
            disabled={busy}
            type="button"
          >
            <AppIcon name="logout" />
            <span>{busy ? "Выходим…" : "Выйти из аккаунта"}</span>
          </button>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </aside>
      <header className="workspace-bar">
        <div className="workspace-location">
          <button
            ref={menuButton}
            className="mobile-menu-button"
            type="button"
            aria-expanded={open}
            aria-controls="app-navigation"
            aria-label={open ? "Закрыть меню" : "Открыть меню"}
            onClick={() => setOpen(!open)}
          >
            <AppIcon name={open ? "close" : "menu"} />
          </button>
          <span>Python Backend</span>
          <span className="breadcrumb-separator" aria-hidden="true">
            /
          </span>
          <strong>
            {current?.label ??
              (pathname === "/assessment"
                ? "Настройка уровня"
                : "Учебное пространство")}
          </strong>
        </div>
        <Link
          className="workspace-profile"
          href="/account"
          aria-label="Открыть личный кабинет"
        >
          <AppIcon name="user" size={18} />
          <span>Мой профиль</span>
        </Link>
      </header>
      <span className="skip-target" id="workspace-content" tabIndex={-1} />
    </>
  );
}
