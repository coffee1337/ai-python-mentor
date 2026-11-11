"""Validate the ops configuration with the real tools, not by eyeballing YAML.

Uses promtool and caddy when they are installed; each check prints its own
verdict and the script exits non-zero if any installed tool rejects a file.
Missing tools are reported as skipped, never as passed.

    python scripts/validate-ops.py [--promtool PATH] [--caddy PATH]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], env: dict | None = None) -> tuple[bool, str]:
    result = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def validate_prometheus(promtool: str) -> bool:
    config = ROOT / "ops" / "prometheus" / "prometheus.yml"
    alerts = ROOT / "ops" / "prometheus" / "alerts.yml"
    # The container path cannot exist on the host; rewrite it to the real file.
    rewritten = config.read_text(encoding="utf-8").replace(
        "/etc/prometheus/alerts.yml", str(alerts))
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
        handle.write(rewritten)
        temporary = handle.name
    try:
        ok_config, output_config = run([promtool, "check", "config", temporary])
        ok_rules, output_rules = run([promtool, "check", "rules", str(alerts)])
    finally:
        os.unlink(temporary)
    print(("PASS" if ok_config else "FAIL") + " prometheus.yml")
    if not ok_config:
        print(output_config)
    print(("PASS" if ok_rules else "FAIL") + " alerts.yml")
    if not ok_rules:
        print(output_rules)
    return ok_config and ok_rules


def validate_caddy(caddy: str) -> bool:
    env = {**os.environ, "DOMAIN": "mentor.example.com", "ACME_EMAIL": "owner@example.com"}
    ok, output = run([caddy, "validate", "--config", str(ROOT / "ops" / "Caddyfile"),
                      "--adapter", "caddyfile"], env=env)
    print(("PASS" if ok else "FAIL") + " Caddyfile")
    if not ok:
        print(output)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promtool")
    parser.add_argument("--caddy")
    args = parser.parse_args()
    promtool = args.promtool or shutil.which("promtool")
    caddy = args.caddy or shutil.which("caddy")
    failures = 0
    if promtool:
        failures += 0 if validate_prometheus(promtool) else 1
    else:
        print("SKIP prometheus: promtool not installed")
    if caddy:
        failures += 0 if validate_caddy(caddy) else 1
    else:
        print("SKIP Caddyfile: caddy not installed")
    if not promtool and not caddy:
        print("nothing validated; install promtool and caddy to run the checks")
        return 0
    print("RESULT:", "ok" if failures == 0 else "failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
