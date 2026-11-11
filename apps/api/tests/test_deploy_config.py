"""Static guarantees for the production stack.

The build machine has no container runtime, so the deploy artefacts are checked
structurally: every service that must exist, the invariants that must never be
violated (only the proxy publishes ports, the runner carries no database or AI
credentials) and the monitoring configuration that alerts depend on.
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "compose.prod.yml"


def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_every_required_service_is_defined():
    services = compose()["services"]
    required = {"db", "migrate", "seed-check", "api", "execution-worker", "notification-worker",
                "runner", "runner-reaper", "web", "caddy", "prometheus", "grafana"}
    assert required <= set(services), sorted(required - set(services))


def test_only_the_reverse_proxy_publishes_ports():
    for name, service in compose()["services"].items():
        if name == "caddy":
            assert set(service["ports"]) == {"80:80", "443:443"}
        else:
            assert "ports" not in service, f"{name} must not publish ports"


def test_migrations_and_seed_run_before_the_api():
    services = compose()["services"]
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["seed-check"]["command"] == ["python", "-m", "app.seed_check"]
    depends = services["api"]["depends_on"]
    assert depends["migrate"]["condition"] == "service_completed_successfully"
    assert depends["seed-check"]["condition"] == "service_completed_successfully"
    for name in ("api", "runner", "db"):
        assert "healthcheck" in services[name], name


def test_runner_is_isolated_from_application_secrets():
    runner = compose()["services"]["runner"]
    assert runner["env_file"] == ".env.runner"
    blob = json.dumps(runner)
    for forbidden in ("DATABASE_URL", "AI_GATEWAY_API_KEY", "SMTP_PASSWORD", "/var/run/docker.sock"):
        assert forbidden not in blob, forbidden
    assert runner["read_only"] is True
    assert runner["cap_drop"] == ["ALL"]
    assert runner["security_opt"] == ["no-new-privileges:true"]


def test_api_containers_are_hardened():
    for name in ("api", "web", "execution-worker", "notification-worker"):
        service = compose()["services"][name]
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert service["security_opt"] == ["no-new-privileges:true"], name


def test_caddy_serves_tls_and_hides_internal_endpoints():
    config = (ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")
    assert "{$DOMAIN}" in config
    assert "Strict-Transport-Security" in config
    assert "@internal path /metrics /internal/*" in config
    assert "reverse_proxy web:3000" in config


def test_prometheus_scrapes_the_api_and_ships_alerts():
    prometheus = yaml.safe_load((ROOT / "ops" / "prometheus" / "prometheus.yml").read_text(encoding="utf-8"))
    assert prometheus["scrape_configs"][0]["static_configs"][0]["targets"] == ["api:8000"]
    alerts = yaml.safe_load((ROOT / "ops" / "prometheus" / "alerts.yml").read_text(encoding="utf-8"))
    names = {rule["alert"] for group in alerts["groups"] for rule in group["rules"]}
    assert {"ApiDown", "DatabaseDown", "HighErrorRate", "SlowApi", "AiSpendHigh",
            "AiQuotaRejections", "ExecutionQueueBacklog"} <= names


def test_grafana_dashboard_covers_latency_errors_queue_spend_quotas_database():
    dashboard = json.loads((ROOT / "ops" / "grafana" / "dashboards" / "apm.json").read_text(encoding="utf-8"))
    expressions = " ".join(target["expr"] for panel in dashboard["panels"] for target in panel["targets"])
    for expected in ("apm_http_request_duration_seconds_bucket", "apm_http_requests_total{status=~\"5..\"}",
                     "apm_execution_queue_depth", "apm_ai_spend_micro_usd_total",
                     "apm_quota_rejections_total", "apm_db_up"):
        assert expected in expressions, expected


def test_runner_image_services_override_the_entrypoint_not_the_command():
    """The runner image defines ENTRYPOINT, so `command` would be appended.

    A service that tried to start a second process with `command` would silently
    run the HTTP server again — that is how the watchdog once became a second
    server and admission kept expiring.
    """
    compose = yaml.safe_load((ROOT / "compose.prod.yml").read_text(encoding="utf-8"))
    runner_build = compose["services"]["runner"].get("build", {}).get("context")
    offenders = []
    for name, service in compose["services"].items():
        if service.get("build", {}).get("context") != runner_build:
            continue
        if "command" in service and "entrypoint" not in service:
            offenders.append(name)
    assert offenders == [], f"runner-image services must set entrypoint: {offenders}"
