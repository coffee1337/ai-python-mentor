import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./globals.css";
import StudySessionProvider from "./components/study-session-provider";

export const metadata: Metadata = {
  title: "Наставник — Python Backend",
  description: "Персональный путь обучения Python Backend",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body><StudySessionProvider>{children}</StudySessionProvider></body>
    </html>
  );
}
