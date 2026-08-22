"""Tests d'intégration du routeur `/api/sessions/*` — vérifie le câblage
FastAPI (auth, DB, sérialisation) par-dessus la couche service déjà testée
unitairement (`test_session_service.py`, `test_etats.py`). L'auth Sheets est
substituée (dépendance FastAPI) : ce n'est pas son objet ici, elle est déjà
couverte par `tests/test_google_sheets.py` (racine du dépôt).
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.deps import utilisateur_requis
from app.db import get_session
from app.main import app
from app.models import Base, Competence, CoutRemediation, Probleme, Session, TypeErreur
from tests.conftest import preparer_client_csrf

_ADMIN = {"nom": "Test", "prenom": "Admin", "role_enum": "administrateur"}


def _override_eleve_autorise(utilisateur, identifiant):
    # Bypass Sheets : n'importe quel identifiant est "autorisé" en test.
    return {"nom": "Eleve", "prenom": "Test", "identifiant_hakili": identifiant}


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

    # `eleve_autorise` n'est pas une dépendance FastAPI (fonction appelée
    # directement dans les routeurs) : on patche le module importé par
    # `app.services.eleves`, pas une override de dépendance.
    import app.services.eleves as eleves_mod
    import app.routers.sessions as sessions_mod

    eleves_mod.eleve_autorise = _override_eleve_autorise
    sessions_mod.eleve_autorise = _override_eleve_autorise

    client = TestClient(app)
    preparer_client_csrf(client)
    return client, SessionLocal


def _seed(SessionLocal):
    db = SessionLocal()
    db.add(TypeErreur(code="CPT", libelle="Conceptuelle", definition="", signature="", coefficient="0.7", remediable=True))
    db.add(Competence(code="A", domaine="Activites numeriques", libelle="A", niveau_intro="6eme", volume_horaire="4"))
    db.commit()
    db.add(CoutRemediation(competence_id="A", type_erreur_id="CPT", cout_heures="4"))
    session = Session(identifiant_hakili="eleve-1")
    db.add(session)
    db.commit()
    db.refresh(session)
    return db, session


def test_session_detail_vide():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert r.status_code == 200
    corps = r.json()
    assert corps["etat"] == "diagnostic"
    assert corps["plan"]["nb_problemes"] == 0
    app.dependency_overrides.clear()


def test_trancher_t1_confirme_un_probleme():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="hypothese")
    db.add(p)
    db.commit()
    db.refresh(p)

    from app.auth.tokens import jeton

    r = client.post(
        f"/api/sessions/{jeton(str(session.id))}/trancher/T1",
        json={"decisions": {p.id: "confirme"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["compte"] == {"confirme": 1}

    r2 = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert len(r2.json()["hypotheses"]) == 0
    app.dependency_overrides.clear()


def test_trancher_t3_resout_un_probleme_en_remediation():
    """Port de `trancher_evaluation` T3 — seul un problème `en_remediation`
    peut avancer, vers `resolu` ou `non_resolu` (`_REGLES_VERDICT`)."""
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="en_remediation")
    db.add(p)
    db.commit()
    db.refresh(p)

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/trancher/T3", json={"decisions": {p.id: "resolu"}})
    assert r.status_code == 200, r.text
    assert r.json()["compte"] == {"resolu": 1}

    r2 = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert len(r2.json()["en_remediation"]) == 0
    assert len(r2.json()["resolus"]) == 1
    app.dependency_overrides.clear()


def test_trancher_t4_fait_regresser_un_probleme_resolu():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="resolu")
    db.add(p)
    db.commit()
    db.refresh(p)

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/trancher/T4", json={"decisions": {p.id: "regresse"}})
    assert r.status_code == 200, r.text
    assert r.json()["compte"] == {"regresse": 1}

    r2 = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert len(r2.json()["regresses"]) == 1
    app.dependency_overrides.clear()


def test_trancher_t5_clot_un_probleme_resolu():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="resolu")
    db.add(p)
    db.commit()
    db.refresh(p)

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/trancher/T5", json={"decisions": {p.id: "clos"}})
    assert r.status_code == 200, r.text
    assert r.json()["compte"] == {"clos": 1}
    app.dependency_overrides.clear()


def test_trancher_t4_refuse_une_decision_hors_regle():
    """`_REGLES_VERDICT["T4"]` n'admet que `regresse` (pas `clos`, réservé à
    T5) — une décision hors liste est simplement ignorée (`corps.decisions.get(...) in regles["options"]`), pas d'erreur, mais rien n'avance."""
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="resolu")
    db.add(p)
    db.commit()
    db.refresh(p)

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/trancher/T4", json={"decisions": {p.id: "clos"}})
    assert r.status_code == 200, r.text
    assert r.json()["compte"] == {}
    db.refresh(p)
    assert p.etat == "resolu"
    app.dependency_overrides.clear()


def test_inscrire_sans_probleme_confirme_refuse():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/inscrire", json={})
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_inscrire_avec_probleme_confirme():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="confirme", cout_estime="4")
    db.add(p)
    db.commit()

    from app.auth.tokens import jeton

    r = client.post(f"/api/sessions/{jeton(str(session.id))}/inscrire", json={})
    assert r.status_code == 200, r.text
    assert r.json()["nb_problemes_en_remediation"] == 1

    r2 = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert r2.json()["etat"] == "remediation"
    app.dependency_overrides.clear()


def test_plan_remediation_sans_probleme_confirme_refuse():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/plan")
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_plan_remediation_genere_un_pdf(tmp_path):
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="confirme", cout_estime="4"))
    db.commit()

    from src.core.config import settings

    settings.runs_dir = str(tmp_path)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/plan")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    app.dependency_overrides.clear()


def test_fiche_travail_sans_matiere_disponible_404(monkeypatch):
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="confirme", cout_estime="4")
    db.add(p)
    db.commit()
    db.refresh(p)

    import app.services.fiche_remediation as fiche_service

    monkeypatch.setattr(
        "src.knowledge.remediation_retriever.get_remediation_retriever",
        lambda: type("R", (), {"get_by_competence": staticmethod(lambda code, niveau: None)})(),
    )

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/problemes/{p.id}/fiche")
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_fiche_travail_genere_puis_corrigee(tmp_path, monkeypatch):
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    p = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="confirme", cout_estime="4")
    db.add(p)
    db.commit()
    db.refresh(p)

    class _Chunk:
        methode = {"titre": "Méthode", "etapes": ["Étape 1"]}
        retenir = ["Retenir 1"]
        exemple_resolu = "Exemple"
        erreurs_frequentes = [{"erreur": "Erreur X", "correction": "Correction X"}]
        declic = "Déclic"

        def exercices_gradues(self, repartition):
            return [{"numero": 1, "etoiles": 1, "enonce": "2+2=?", "correction": "4"}]

    monkeypatch.setattr(
        "src.knowledge.remediation_retriever.get_remediation_retriever",
        lambda: type("R", (), {"get_by_competence": staticmethod(lambda code, niveau: _Chunk())})(),
    )

    from src.core.config import settings

    settings.runs_dir = str(tmp_path)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/problemes/{p.id}/fiche")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"

    r2 = client.patch(
        f"/api/sessions/{jeton(str(session.id))}/problemes/{p.id}/fiche",
        json={
            "objectif": "Objectif corrigé",
            "prerequis_a_verifier": [],
            "methode": {"titre": "M", "etapes": ["e1"]},
            "retenir": [],
            "exemple_resolu": None,
            "erreurs_frequentes": [],
            "declic": None,
            "deroule_minutes": {},
            "exercices": [],
            "critere_reussite": "Critère corrigé",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["version"] == "corrigee"

    from app.models import FicheRemediation

    fiche = db.query(FicheRemediation).filter(FicheRemediation.competence_id == "A").first()
    assert fiche.version == "corrigee"
    assert fiche.contenu["objectif"] == "Objectif corrigé"
    app.dependency_overrides.clear()


def test_jeton_invalide_donne_404():
    client, SessionLocal = _client_avec_base()
    r = client.get("/api/sessions/jeton-invalide")
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_sans_authentification_donne_401(monkeypatch):
    # `acces_libre()` lit `settings.debug`/`settings.hakili_acces_libre`, qui
    # viennent du vrai `.env` partagé avec Django dès que ce test tourne
    # depuis la racine du dépôt (où `.env` existe — il vaut `true` en dev).
    # Le figer ici rend le test hermétique au lieu de dépendre du CWD depuis
    # lequel pytest est invoqué.
    from app.auth import deps as auth_deps

    monkeypatch.setattr(auth_deps, "acces_libre", lambda: False)

    client, SessionLocal = _client_avec_base()
    app.dependency_overrides.pop(utilisateur_requis, None)
    r = client.get("/api/sessions/jeton-invalide")
    assert r.status_code == 401
    app.dependency_overrides.clear()
