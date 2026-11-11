"""ASVS level 2 controls that need an explicit regression test."""
from test_auth import client, csrf


def test_short_password_is_rejected_by_the_api(client):
    for password in ("short", "elevenchars"):
        response = client.post("/auth/register", json={
            "email": f"weak-{len(password)}@example.invalid", "password": password})
        assert response.status_code == 422, response.text


def test_twelve_character_password_is_accepted(client):
    response = client.post("/auth/register", json={
        "email": "asvs-password@example.invalid", "password": "twelve-chars-ok"})
    assert response.status_code in {200, 201}, response.text


def test_login_attempts_are_throttled_per_account(client):
    client.post("/auth/register", json={
        "email": "throttle@example.invalid", "password": "Throttle-Password-2026"})
    statuses = [
        client.post("/auth/login", json={
            "email": "throttle@example.invalid", "password": "wrong-password-here"}).status_code
        for _ in range(30)
    ]
    assert 429 in statuses, statuses
    # The throttled account cannot be used to probe passwords any further.
    assert statuses[-1] == 429
