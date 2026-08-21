"""Tests d'intégration légers du routeur `/api/admin/*` — miroir de
`suivi_web/views.py::personnel`/`statistiques`. La lecture des Sheets est
substituée (déjà couverte par `tests/test_google_sheets.py`, racine du
dépôt) ; ces tests vérifient le câblage FastAPI/DB et la garde admin.
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.deps import utilisateur_requis
from app.db import get_session
from app.main import app
from app.models import Base, Copie
from src.integrations.google_sheets import GoogleSheetsError
from tests.conftest import preparer_client_csrf

_ADMIN = {"nom": "Test", "prenom": "Admin", "role_enum": "administrateur"}
_ENSEIGNANT = {"nom": "Test", "prenom": "Ens", "role_enum": "enseignant"}


def _client_avec_base(utilisateur=_ADMIN):
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
    app.dependency_overrides[utilisateur_requis] = lambda: utilisateur

    client = TestClient(app)
    preparer_client_csrf(client)
    return client, SessionLocal


def test_personnel_refuse_hors_admin():
    client, _ = _client_avec_base(utilisateur=_ENSEIGNANT)
    r = client.get("/api/admin/personnel")
    assert r.status_code == 403
    app.dependency_overrides.clear()


def test_personnel_trie_comptes_en_defaut_en_premier(monkeypatch):
    client, _ = _client_avec_base()
    import app.routers.admin as admin_mod

    monkeypatch.setattr(
        admin_mod.google_sheets,
        "get_personnel",
        lambda: [
            {"nom": "Zaba", "prenom": "Awa", "role": "enseignant", "pin": "1234", "affectations": [("Centre A", "6e")]},
            {"nom": "Abba", "prenom": "Nadia", "role": "enseignant", "pin": "", "affectations": [("Centre A", "6e")]},
            {"nom": "Kaba", "prenom": "Issa", "role": "invalide", "pin": "1234", "affectations": []},
        ],
    )
    r = client.get("/api/admin/personnel")
    assert r.status_code == 200
    corps = r.json()
    assert corps["lecture_impossible"] is False
    assert corps["probleme"] == 2
    # comptes en défaut (regresse puis stagne) avant le compte actif (progresse)
    assert [l["etat"] for l in corps["lignes"]] == ["regresse", "stagne", "progresse"]
    app.dependency_overrides.clear()


def test_personnel_sheets_indisponible(monkeypatch):
    client, _ = _client_avec_base()
    import app.routers.admin as admin_mod

    def _echec():
        raise GoogleSheetsError("indisponible")

    monkeypatch.setattr(admin_mod.google_sheets, "get_personnel", _echec)
    r = client.get("/api/admin/personnel")
    assert r.status_code == 200
    assert r.json()["lecture_impossible"] is True
    app.dependency_overrides.clear()


def test_statistiques_compte_copies_et_centres(monkeypatch):
    client, SessionLocal = _client_avec_base()
    db = SessionLocal()
    db.add(Copie(copy_id="C1", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 1, 1), notes_finales=12))
    db.commit()

    import app.routers.admin as admin_mod

    monkeypatch.setattr(admin_mod.google_sheets, "get_eleves", lambda: [{"identifiant_hakili": "eleve-1"}])
    monkeypatch.setattr(
        admin_mod.google_sheets,
        "get_centres_derives",
        lambda: {"centre a": {"canonique": "Centre A", "suspect": False, "count": 5}},
    )

    r = client.get("/api/admin/statistiques")
    assert r.status_code == 200
    corps = r.json()
    assert corps["nb_copies"] == 1
    assert corps["nb_eleves"] == 1
    assert corps["centres"] == ["Centre A"]
    assert corps["centres_suspects"] == []
    app.dependency_overrides.clear()
