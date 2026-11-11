"""Security headers, request limits and prompt-injection boundaries."""
from test_auth import client


def test_api_responses_carry_security_headers(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["permissions-policy"].startswith("camera=()")


def test_hsts_only_over_tls(client):
    assert "strict-transport-security" not in client.get("/health").headers


def test_oversized_body_is_rejected_before_validation(client):
    response = client.post("/auth/login", content=b"x" * (200 * 1024),
                           headers={"Content-Type": "application/json"})
    assert response.status_code in {400, 413}
    assert "x" * 100 not in response.text


def test_private_endpoints_are_not_cacheable(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers.get("cache-control") == "no-store"
