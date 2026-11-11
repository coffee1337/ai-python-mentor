"""Security headers for every API response.

The API is normally reached through the reverse proxy, but it must stay safe on
its own: a JSON API never needs to render a document, so the policy can be
strict. HSTS is only sent over TLS, otherwise a developer on http://localhost
would pin the scheme for the whole host.
"""
from __future__ import annotations

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": API_CSP,
}


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in STATIC_HEADERS.items():
                    if name.lower().encode() not in existing:
                        headers.append((name.lower().encode(), value.encode()))
                if scope.get("scheme") == "https" and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security",
                                    b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_with_headers)
