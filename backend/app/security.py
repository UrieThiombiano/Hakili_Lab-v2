"""Durcissement production — miroir des réglages que `hakili/settings.py`
force hors `DEBUG` (`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
`SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_PROXY_SSL_HEADER`). Les cookies
`Secure`/`HttpOnly`/`SameSite` sont déjà posés à l'émission
(`app/auth/deps.py::ouvrir_session`, `app/auth/csrf.py::poser_cookie_csrf`)
— il ne manquait que la redirection HTTPS et l'en-tête HSTS.

Inactif quand `settings.debug` est vrai, comme côté Django : forcer HTTPS en
développement local casserait `http://localhost`.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_HSTS_MAX_AGE = 31_536_000  # 1 an, comme SECURE_HSTS_SECONDS côté Django.


class SecuriteProductionMiddleware:
    """Redirige vers HTTPS (via l'en-tête `X-Forwarded-Proto` posé par nginx
    — même mécanisme que `SECURE_PROXY_SSL_HEADER` côté Django) et pose
    `Strict-Transport-Security` sur chaque réponse, hors DEBUG uniquement."""

    def __init__(self, app: ASGIApp, *, actif: bool) -> None:
        self.app = app
        self.actif = actif

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.actif or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto != "https":
            reponse = RedirectResponse(url=request.url.replace(scheme="https"), status_code=307)
            await reponse(scope, receive, send)
            return

        async def send_avec_hsts(message):
            if message["type"] == "http.response.start":
                en_tetes = list(message.get("headers", []))
                en_tetes.append((b"strict-transport-security", f"max-age={_HSTS_MAX_AGE}; includeSubDomains".encode()))
                message = {**message, "headers": en_tetes}
            await send(message)

        await self.app(scope, receive, send_avec_hsts)
