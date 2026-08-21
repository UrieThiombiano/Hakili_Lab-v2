"""`CSRFMiddleware` (`app/auth/csrf.py`) — double-submit cookie."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.deps import utilisateur_requis
from app.db import get_session
from app.main import app
from app.models import Base

_ADMIN = {"nom": "Test", "prenom": "Admin", "role_enum": "administrateur"}


def _client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_session_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[utilisateur_requis] = lambda: _ADMIN
    return TestClient(app)


def test_post_sans_jeton_csrf_refuse():
    client = _client()
    r = client.post("/api/sessions/jeton-quelconque/inscrire", json={})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]
    app.dependency_overrides.clear()


def test_post_avec_cookie_sans_entete_refuse():
    client = _client()
    client.cookies.set("csrf_token", "abc123")
    r = client.post("/api/sessions/jeton-quelconque/inscrire", json={})
    assert r.status_code == 403
    app.dependency_overrides.clear()


def test_post_avec_entete_ne_correspondant_pas_au_cookie_refuse():
    client = _client()
    client.cookies.set("csrf_token", "abc123")
    r = client.post("/api/sessions/jeton-quelconque/inscrire", json={}, headers={"X-CSRF-Token": "autre-valeur"})
    assert r.status_code == 403
    app.dependency_overrides.clear()


def test_post_avec_cookie_et_entete_assortis_passe_la_verification_csrf():
    client = _client()
    client.cookies.set("csrf_token", "abc123")
    client.headers.update({"X-CSRF-Token": "abc123"})
    # Le jeton invalide (404) prouve que la requête a dépassé le CSRF — sans
    # ça elle se serait arrêtée à 403 avant même d'atteindre la route.
    r = client.post("/api/sessions/jeton-invalide/inscrire", json={})
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_get_n_est_jamais_bloque_par_le_csrf():
    client = _client()
    r = client.get("/api/sessions/jeton-invalide")
    assert r.status_code == 404  # jamais 403
    app.dependency_overrides.clear()


def test_login_est_exempte_du_csrf():
    client = _client()
    # Pas de cookie CSRF posé : /api/auth/login doit rester joignable (401 ou
    # 400 selon le Sheet, jamais 403 CSRF) puisqu'aucune session n'existe
    # encore à ce stade pour porter un jeton.
    r = client.post("/api/auth/login", json={"cle": "", "pin": ""})
    assert r.status_code != 403
    app.dependency_overrides.clear()


def test_acces_libre_court_circuite_le_csrf(monkeypatch):
    # Sans connexion (mode `HAKILI_ACCES_LIBRE`, dev uniquement), aucun cookie
    # CSRF n'a jamais été posé — le vérifier bloquerait toute action.
    import app.auth.csrf as csrf_mod

    monkeypatch.setattr(csrf_mod, "_acces_libre", lambda: True)
    client = _client()
    r = client.post("/api/sessions/jeton-invalide/inscrire", json={})
    assert r.status_code == 404  # dépasse le CSRF, s'arrête au jeton invalide
    app.dependency_overrides.clear()


def test_ouvrir_session_pose_le_cookie_csrf(db):
    from fastapi import Response

    from app.auth.deps import ouvrir_session

    reponse = Response()
    ouvrir_session(db, reponse, {"nom": "X", "prenom": "Y", "role": "administrateur", "roles": ["administrateur"]})
    en_tetes_set_cookie = reponse.headers.getlist("set-cookie")
    assert any("csrf_token=" in c for c in en_tetes_set_cookie)
    # Cookie CSRF pas httpOnly (le frontend doit pouvoir le lire).
    cookie_csrf = next(c for c in en_tetes_set_cookie if c.startswith("csrf_token="))
    assert "httponly" not in cookie_csrf.lower()
