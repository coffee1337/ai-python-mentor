# Browser journey checks

This test package is separate from the web application. Playwright and its
Chromium browser are pinned by `package-lock.json`; they are not runtime
dependencies of the product.

The `Beginner journey and responsive browser UI` CI job builds production Next,
migrates an empty disposable SQLite database, and starts the real web and API
servers on localhost. No API mocks are used. Each viewport gets its own synthetic
account, with no real user credentials, AI provider, message delivery, checkout,
or execution worker.

The journey covers registration, zero-experience onboarding without assessment,
explanation before questions, answer feedback, guided practice, navigation,
learning path, profile persistence, notifications, vacancy analysis, project
artifacts, billing, and recovery pages. It checks 1440×900 and 390×844 layouts,
page overflow, desktop workspace width, heading scale, keyboard focus, mobile
navigation, and browser runtime errors.

CI uploads full-page screenshots for each major screen, failure screenshots,
traces on failure, and the HTML report as `browser-ui-desktop-mobile`. Layout
assertions catch structural regressions; a human must still inspect the PNGs for
visual quality. These screenshots are real browser captures, not mockups.

To rerun, configure `DATABASE_URL` for a disposable migrated database, build
`apps/web` with `NEXT_PUBLIC_API_URL=/api` and
`API_INTERNAL_URL=http://127.0.0.1:8000`, then run in this directory:

```sh
npm ci
npx playwright install --with-deps chromium
npm test
```

The test runner manages localhost servers. It reuses existing servers only
outside CI. Generated results are ignored by git.
