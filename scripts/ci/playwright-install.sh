#!/usr/bin/env bash
# Install Playwright browsers without depending on the apt mirrors.
#
# The hosted runner image is built on a moving Ubuntu release and its apt mirrors
# intermittently fail to resolve (security.ubuntu.com, azure.archive.ubuntu.com).
# `--with-deps` pulls font packages we do not need, so the default path installs
# the browser alone, proves it starts, and only falls back to system packages if
# the launch actually fails. Every step is wrapped in `timeout` so a hung mirror
# cannot eat the job's budget.
set -uo pipefail

probe() {
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
}

echo "installing chromium without system packages"
timeout 600 npx playwright install chromium || echo "browser download failed" >&2
if probe; then
  exit 0
fi

echo "chromium needs system libraries; installing them with retries" >&2
for attempt in 1 2 3; do
  if timeout 600 npx playwright install --with-deps chromium; then
    probe && exit 0
  fi
  sudo apt-get -o Acquire::Retries=5 update >/dev/null 2>&1 || true
  sleep $((attempt * 10))
done

echo "chromium could not be started on this runner" >&2
exit 1
