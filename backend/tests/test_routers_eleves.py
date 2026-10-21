"""Tests d'intégration légers du routeur `/api/eleves/*` — la lecture des
Sheets (`get_accessible_eleves`, `get_eleve_by_identifiant`) est substituée :
elle est déjà couverte par `tests/test_google_sheets.py` (racine du dépôt),
ce n'est pas l'objet de ces tests, qui vérifient le câblage FastAPI/DB.
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
from tests.conftest import preparer_client_csrf

_ADMIN = {"nom": "Test", "prenom": "Admin", "role_enum": "administrateur"}
_ELEVE = {"identifiant_hakili": "eleve-1", "nom": "Sanou", "prenom": "Feryel"}


def _client_avec_base():
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

    import app.routers.eleves as eleves_mod

    eleves_mod.eleves_accessibles = lambda utilisateur: [_ELEVE]
    eleves_mod.eleve_autorise = lambda utilisateur, identifiant: _ELEVE

    client = TestClient(app)
    preparer_client_csrf(client)
    return client, SessionLocal


def test_accueil_sans_copie():
    client, SessionLocal = _client_avec_base()
    r = client.get("/api/eleves")
    assert r.status_code == 200
    corps = r.json()
    assert corps["lecture_impossible"] is False
    assert len(corps["lignes"]) == 1
    assert corps["lignes"][0]["tendance"] == "insuffisant"
    app.dependency_overrides.clear()


def test_accueil_calcule_tendance_avec_copies():
    client, SessionLocal = _client_avec_base()
    db = SessionLocal()
    db.add(Copie(copy_id="C1", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 1, 1), notes_finales=8))
    db.add(Copie(copy_id="C2", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 2, 1), notes_finales=14))
    db.commit()

    r = client.get("/api/eleves")
    assert r.status_code == 200
    ligne = r.json()["lignes"][0]
    assert ligne["tendance"] == "progresse"  # écart +6 >= SEUIL_TENDANCE (1.0)
    assert ligne["nb_copies"] == 2
    assert ligne["derniere_note"] == 14
    app.dependency_overrides.clear()


def test_eleve_detail_jeton_invalide():
    client, SessionLocal = _client_avec_base()
    r = client.get("/api/eleves/jeton-invalide")
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_eleve_detail_avec_copie():
    client, SessionLocal = _client_avec_base()
    db = SessionLocal()
    db.add(Copie(copy_id="C1", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 1, 1), notes_finales=12))
    db.commit()

    from app.auth.tokens import jeton

    r = client.get(f"/api/eleves/{jeton('eleve-1')}")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["nb_copies"] == 1
    assert corps["entrees"][0]["copy_id"] == "C1"
    app.dependency_overrides.clear()


def test_supprimer_document_retire_la_ligne_et_les_fichiers(tmp_path, monkeypatch):
    from app.auth.tokens import jeton
    from app.models import Correction, Document
    from src.core.config import settings

    monkeypatch.setattr(settings, "runs_dir", str(tmp_path))
    dossier = tmp_path / "C1"
    (dossier / "depot").mkdir(parents=True)
    (dossier / "depot" / "copie.pdf").write_bytes(b"%PDF scan")
    rapport = dossier / "rapport.pdf"
    rapport.write_bytes(b"%PDF rapport")

    client, SessionLocal = _client_avec_base()
    db = SessionLocal()
    db.add(Copie(copy_id="C1", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 1, 1), notes_finales=12))
    db.add(Document(copy_id="C1", type="scan", fichier=b"%PDF scan"))
    db.add(Document(copy_id="C1", type="rapport", fichier=b"%PDF rapport"))
    db.add(Correction(copy_id="C1", identifiant_hakili="eleve-1", bareme_id="socle_6eme", resultat={"pdf_path": str(rapport)}))
    db.commit()

    r = client.delete(f"/api/eleves/documents/{jeton('C1')}/rapport")
    assert r.status_code == 200, r.text
    assert not rapport.exists()
    restants = [d.type for d in SessionLocal().query(Document).filter(Document.copy_id == "C1")]
    assert restants == ["scan"]
    assert SessionLocal().get(Copie, "C1") is not None  # la copie et sa note restent

    r = client.delete(f"/api/eleves/documents/{jeton('C1')}/scan")
    assert r.status_code == 200, r.text
    assert not (dossier / "depot").exists()

    r = client.delete(f"/api/eleves/documents/{jeton('C1')}/scan")
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_supprimer_document_ignore_un_chemin_hors_du_dossier_de_la_copie(tmp_path, monkeypatch):
    from app.auth.tokens import jeton
    from app.models import Correction, Document
    from src.core.config import settings

    monkeypatch.setattr(settings, "runs_dir", str(tmp_path / "runs"))
    ailleurs = tmp_path / "ailleurs.pdf"
    ailleurs.write_bytes(b"x")

    client, SessionLocal = _client_avec_base()
    db = SessionLocal()
    db.add(Copie(copy_id="C1", identifiant_hakili="eleve-1", classe="6eA", annee_scolaire="2025-2026", date_soumission=date(2026, 1, 1)))
    db.add(Document(copy_id="C1", type="rapport", fichier=b"x"))
    db.add(Correction(copy_id="C1", identifiant_hakili="eleve-1", bareme_id="socle_6eme", resultat={"pdf_path": str(ailleurs)}))
    db.commit()

    assert client.delete(f"/api/eleves/documents/{jeton('C1')}/rapport").status_code == 200
    assert ailleurs.exists()
    app.dependency_overrides.clear()
