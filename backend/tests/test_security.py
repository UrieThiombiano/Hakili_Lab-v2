"""`SecuriteProductionMiddleware` (`app/security.py`) — miroir des réglages
Django hors `DEBUG` (`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security import SecuriteProductionMiddleware


def _app(actif: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecuriteProductionMiddleware, actif=actif)

    @app.get("/test")
    def _route() -> dict:
        return {"ok": True}

    return app


def test_inactif_en_debug_ne_redirige_pas_et_ne_pose_pas_hsts():
    client = TestClient(_app(actif=False))
    r = client.get("/test")
    assert r.status_code == 200
    assert "strict-transport-security" not in r.headers


def test_actif_redirige_http_vers_https():
    client = TestClient(_app(actif=True), follow_redirects=False)
    r = client.get("/test")
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://")


def test_actif_pose_hsts_quand_deja_https():
    client = TestClient(_app(actif=True), follow_redirects=False)
    r = client.get("/test", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert "max-age=31536000" in r.headers["strict-transport-security"]
    assert "includeSubDomains" in r.headers["strict-transport-security"]
