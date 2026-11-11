// Browser error reporting. Disabled unless NEXT_PUBLIC_SENTRY_DSN is set, so a
// plain `npm run dev` never talks to a third party. Personal data is off and
// the navigation breadcrumb keeps no query strings (a lesson URL can carry an
// identifier).
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0"),
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
