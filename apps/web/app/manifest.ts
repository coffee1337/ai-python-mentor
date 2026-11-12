import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AI Python Mentor — от первой строки до backend",
    short_name: "Python Mentor",
    description:
      "Курс Python с проверкой понимания, задачами с исполнением кода и наставником, который помнит ошибки.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#0f1318",
    theme_color: "#0f1318",
    lang: "ru",
    orientation: "portrait-primary",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Продолжить урок", url: "/learning" },
      { name: "Прогресс", url: "/dashboard" },
    ],
  };
}
