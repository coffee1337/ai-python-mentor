// Server-side error reporting for the Next.js runtime (node and edge).
// Enabled only when SENTRY_DSN is present; never sends user identifiers.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN;

export async function register() {
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.APP_ENV ?? process.env.NODE_ENV,
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0"),
    beforeSend(event) {
      if (event.request) {
        delete event.request.data;
        delete event.request.query_string;
        delete event.request.cookies;
      }
      delete event.user;
      return event;
    },
  });
}

export async function onRequestError(...args: Parameters<typeof Sentry.captureRequestError>) {
  if (!dsn) return;
  Sentry.captureRequestError(...args);
}
