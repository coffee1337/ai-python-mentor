import type { Metadata } from "next";
import CoursePath from "../course-path";

export const metadata: Metadata = {
  title: "Учебный путь — Наставник Python",
};

export default function LearningPathPage() {
  return (
    <main className="dashboard-shell course-path-page">
      <header className="topbar">
        <a className="brand" href="/dashboard">
          ↗ наставник<span className="brand-dot">.</span>
        </a>
        <a className="text-button" href="/dashboard">На dashboard</a>
      </header>
      <CoursePath variant="full" />
    </main>
  );
}
