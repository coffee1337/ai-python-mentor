import type { Metadata, Viewport } from "next";
import ServiceWorker from "./components/service-worker";
import "@fontsource-variable/inter";
import "./globals.css";
import StudySessionProvider from "./components/study-session-provider";

export const metadata: Metadata = {
  title: {
    default: "AI Python Mentor — от первой строки до backend",
    template: "%s · AI Python Mentor",
  },
  description:
    "Курс Python с проверкой понимания, задачами с исполнением кода и наставником, который помнит ошибки.",
  manifest: "/manifest.webmanifest",
  applicationName: "AI Python Mentor",
  icons: { icon: "/icon-192.png", apple: "/apple-touch-icon.png" },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Python Mentor" },
};

export const viewport: Viewport = {
  themeColor: "#0f1318",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <StudySessionProvider>{children}</StudySessionProvider>
        <ServiceWorker />
      </body>
    </html>
  );
}
