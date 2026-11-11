#!/usr/bin/env bash
# Install Playwright browsers with a bounded retry.
#
# The hosted runner image is built on a moving Ubuntu release and its apt mirrors
# intermittently fail to resolve (security.ubuntu.com, azure.archive.ubuntu.com).
# A transient DNS failure must not turn the browser suites red, so the install is
# retried and, if only the system packages are unreachable, the browsers are still
# installed and probed before the job gives up.
set -uo pipefail

attempts="${PLAYWRIGHT_INSTALL_ATTEMPTS:-3}"
for attempt in $(seq 1 "$attempts"); do
  echo "playwright install with deps, attempt $attempt/$attempts"
  if npx playwright install --with-deps chromium; then
    exit 0
  fi
  sudo apt-get -o Acquire::Retries=5 update >/dev/null 2>&1 || true
  sleep $((attempt * 15))
done

echo "system dependencies are unreachable; installing browsers only" >&2
npx playwright install chromium || exit 1

# Prove the browser actually starts: a missing shared library fails here, not in a test.
node - <<'NODE'
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  await browser.close();
  console.log('chromium launched');
})().catch((error) => {
  console.error(`chromium failed to launch: ${error.message}`);
  process.exit(1);
});
NODE
