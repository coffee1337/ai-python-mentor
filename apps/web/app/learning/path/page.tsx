import type { Metadata } from "next";
import AppHeader from "../../components/app-header";
import CoursePath from "../course-path";
export const metadata: Metadata = { title: "Учебный путь — Наставник Python" };
export default function LearningPathPage() {
  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="learning-page-content">
        <CoursePath variant="full" />
      </div>
    </main>
  );
}
