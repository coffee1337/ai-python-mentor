import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Наставник — Python Backend",
  description: "Персональный путь обучения Python Backend",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
