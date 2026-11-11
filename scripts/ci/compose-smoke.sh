#!/usr/bin/env bash
# Compose smoke: bring the production stack up and prove the critical paths.
#
# The build is the real compose.prod.yml; only TLS is switched to Caddy's internal
# CA because CI has no public domain. Everything else — migrations, seeding, the
# runner handshake, routing, headers, port exposure — is exercised as in production.
set -uo pipefail

COMPOSE="docker compose -f compose.prod.yml -f compose.ci.yml --env-file .env.prod"
BASE="https://localhost:8443"
API="$BASE/api"
CA="ops/runner-config/caddy-root.crt"
FAILURES=0

log() { printf '\n=== %s\n' "$*"; }
fail() { FAILURES=$((FAILURES + 1)); printf 'FAIL %s\n' "$*"; }
ok() { printf 'ok   %s\n' "$*"; }

wait_healthy() {
  log "waiting for healthchecks"
  for _ in $(seq 1 120); do
    local unhealthy
    unhealthy=$($COMPOSE ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep -E 'starting|unhealthy' | wc -l)
    if [ "$unhealthy" -eq 0 ] && $COMPOSE ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep -q 'running'; then
      # migrate and seed-check are one-shot containers: they must have exited 0.
      if $COMPOSE ps --all --format '{{.Service}} {{.ExitCode}}' | grep -E '^(migrate|seed-check) ' | grep -qv ' 0$'; then
        fail "migrations or seed check exited non-zero"
        return 1
      fi
      ok "all services healthy"
      return 0
    fi
    sleep 5
  done
  fail "services did not become healthy in time"
  $COMPOSE ps --all
  return 1
}

expect() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then ok "$label ($actual)"; else fail "$label: expected $expected, got $actual"; fi
}

curl_() { curl -s -o /dev/null -w '%{http_code}' --cacert "$CA" "$@"; }

main() {
  # Caddy's internal CA is generated on first start; trust it for every probe.
  mkdir -p ops/runner-config
  $COMPOSE cp caddy:/data/caddy/pki/authorities/local/root.crt "$CA" >/dev/null 2>&1 \
    || fail "caddy root certificate is unavailable"

  wait_healthy || return 1

  log "public surface"
  expect "web root" 200 "$(curl_ "$BASE/")"
  expect "api health" 200 "$(curl_ "$API/health")"
  expect "metrics hidden" 404 "$(curl_ "$BASE/metrics")"
  expect "internal runner path hidden" 404 "$(curl_ "$BASE/internal/v1/runner/executions")"

  log "security headers"
  local headers
  headers=$(curl -s -I --cacert "$CA" "$BASE/")
  for header in strict-transport-security x-content-type-options x-frame-options referrer-policy; do
    if printf '%s' "$headers" | tr 'A-Z' 'a-z' | grep -q "^$header:"; then ok "header $header"; else fail "missing header $header"; fi
  done
  if printf '%s' "$headers" | tr 'A-Z' 'a-z' | grep -q '^server: caddy'; then fail "server banner leaks proxied runtime"; else ok "server banner hidden"; fi

  log "ports"
  local published
  published=$(ss -ltnH 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ' ')
  for port in 8443 80 443; do
    if printf '%s' "$published" | grep -qw "$port"; then ok "port $port published (proxy)"; fi
  done
  for port in 5432 8000 8443 3000; do
    if printf '%s' "$published" | grep -qw "$port" && [ "$port" != "8443" ]; then fail "internal port $port is published"; fi
  done
  if docker port "$(docker compose -f compose.prod.yml -f compose.ci.yml --env-file .env.prod ps -q db)" >/dev/null 2>&1 \
     && [ -n "$(docker port "$($COMPOSE ps -q db)")" ]; then fail "database exposes a host port"; else ok "database is internal only"; fi

  log "account journey"
  local jar
  jar=$(mktemp)
  local email="smoke-$RANDOM@example.com"
  expect "register" 201 "$(curl_ -c "$jar" -X POST "$API/auth/register" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"Correct-Horse-Battery-9\"}")"
  local csrf
  csrf=$(awk '/mentor_csrf/ {print $7}' "$jar")
  expect "onboarding" 200 "$(curl_ -b "$jar" -c "$jar" -X POST "$API/onboarding" -H 'Content-Type: application/json' \
    -H "X-CSRF-Token: $csrf" -d '{"experience_level":"beginner","target_role":"Python backend","weekly_minutes":180}')"
  expect "next lesson" 200 "$(curl_ -b "$jar" "$API/learning/next")"

  log "public portfolio"
  local project public_token
  project=$(curl -s --cacert "$CA" -b "$jar" -X POST "$API/projects" -H 'Content-Type: application/json' \
    -H "X-CSRF-Token: $csrf" -d '{"template_id":"expense-cli-v1"}')
  local project_id
  project_id=$(printf '%s' "$project" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
  if [ -z "$project_id" ]; then
    fail "project was not created: $project"
  else
    public_token=$(curl -s --cacert "$CA" -b "$jar" -X PATCH "$API/projects/$project_id/portfolio" \
      -H 'Content-Type: application/json' -H "X-CSRF-Token: $csrf" \
      -d '{"published":true,"title":"Учебный проект","summary":"Смоук-публикация портфолио в compose-стеке.","repository_url":null}' \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("public_path") or "").rsplit("/",1)[-1])' 2>/dev/null)
    if [ -z "$public_token" ]; then
      fail "portfolio was not published"
    else
      expect "public portfolio page" 200 "$(curl_ "$BASE/portfolio/$public_token")"
      expect "portfolio api is public" 200 "$(curl_ "$API/portfolio/$public_token")"
    fi
  fi

  log "code execution through the runner"
  local capabilities
  capabilities=$(curl -s --cacert "$CA" -b "$jar" "$API/learning/execution-capabilities")
  if printf '%s' "$capabilities" | grep -q '"configured":true'; then
    ok "runner is configured for the API"
  else
    fail "runner is not configured: $capabilities"
    $COMPOSE exec -T api sh -c 'ls -la /etc/ai-tutor/api; python -c "import os;print({k: bool(os.getenv(k)) for k in (\"RUNNER_URL\",\"RUNNER_AUTH_TOKEN\",\"RUNNER_CA_FILE\",\"RUNNER_CLIENT_CERT_FILE\",\"RUNNER_CLIENT_KEY_FILE\",\"RUNNER_VERIFIED_POLICY_FILE\",\"EXECUTION_JOBS_ENABLED\")})"' || true
  fi
  local payload='{"language":"python","mode":"function","source_code":"def solve(payload):\n    return payload[\"start\"] + payload[\"increment\"]\n"}'
  local job
  job=$(curl -s --cacert "$CA" -b "$jar" -X POST "$API/learning/exercises/variables-v1-code/jobs" \
    -H 'Content-Type: application/json' -H "X-CSRF-Token: $csrf" -H "Idempotency-Key: smoke-$RANDOM" -d "$payload")
  local job_id status=""
  job_id=$(printf '%s' "$job" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
  if [ -z "$job_id" ]; then
    fail "job was not accepted: $job"
  else
    for _ in $(seq 1 30); do
      status=$(curl -s --cacert "$CA" -b "$jar" "$API/learning/jobs/$job_id" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
      case "$status" in finished|failed|unavailable|error) break;; esac
      sleep 2
    done
    expect "job finished" finished "$status"
  fi

  log "telegram webhook refuses unsigned traffic"
  expect "webhook without secret" 503 "$(curl_ -X POST "$API/telegram/webhook/deadbeef" -H 'Content-Type: application/json' -d '{}')"


  log "restart safety"
  $COMPOSE restart api >/dev/null 2>&1
  sleep 12
  expect "api healthy after restart" 200 "$(curl_ "$API/health")"
  expect "session survives restart" 200 "$(curl_ -b "$jar" "$API/learning/next")"

  rm -f "$jar"
  return 0
}

status=0
main || status=1
if [ "$status" -ne 0 ] || [ "$FAILURES" -ne 0 ]; then
  log "diagnostics"
  echo "--- api -> runner TLS probe"
  $COMPOSE exec -T api python - <<'PROBE' 2>&1 | tail -5
import os
import ssl

import httpx

ctx = ssl.create_default_context(cafile=os.environ["RUNNER_CA_FILE"])
ctx.load_cert_chain(os.environ["RUNNER_CLIENT_CERT_FILE"], os.environ["RUNNER_CLIENT_KEY_FILE"])
try:
    with httpx.Client(verify=ctx, timeout=5) as client:
        print("tls_probe_status", client.get(os.environ["RUNNER_URL"]).status_code)
except Exception as error:  # noqa: BLE001 - the class is the diagnostic
    print("tls_probe_failed", type(error).__name__, str(error)[:120])
PROBE
  for service in runner-reaper runner api execution-worker; do
    echo "--- $service"
    $COMPOSE logs --no-color --tail 60 "$service" 2>&1 | tail -60
  done
fi
if [ "$FAILURES" -ne 0 ]; then status=1; fi
log "result"
if [ "$status" -eq 0 ]; then echo "COMPOSE SMOKE: ok"; else echo "COMPOSE SMOKE: $FAILURES failure(s)"; fi
exit "$status"
