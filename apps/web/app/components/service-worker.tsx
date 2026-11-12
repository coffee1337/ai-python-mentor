"use client";

import { useEffect } from "react";

export default function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    const timer = window.setTimeout(() => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* Offline shell is an enhancement; learning works without it. */
      });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, []);
  return null;
}
