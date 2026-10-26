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


def test_session_detail_expose_le_sujet_t1_telechargeable():
    """Sans ce champ, l'enseignant voit « Déposer la copie T1 » sans jamais
    avoir pu obtenir le sujet à faire passer à l'élève — le document
    `sujet_confirmation` existe pourtant déjà (généré par le module 5)."""
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.models import Copie, Document, Evaluation, Probleme

    db.add(Copie(copy_id="copie-t0-1", identifiant_hakili="eleve-1", classe="5eme", annee_scolaire="2025-2026"))
    db.add(
        Evaluation(
            session_id=session.id,
            type="T0",
            numero=1,
            copy_id="copie-t0-1",
            sujet_confirmation=[{"numero": 1, "topic": "A × CPT", "question": "Développer...", "hint": ""}],
        )
    )
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="hypothese", exercices_confirmation=[1]))
    db.add(Document(copy_id="copie-t0-1", type="sujet_confirmation", fichier=b"%PDF-1.4 sujet T1"))
    db.commit()

    import app.routers.eleves as eleves_router_mod
    eleves_router_mod.eleve_autorise = _override_eleve_autorise

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["sujet_t1_disponible"] is True
    assert corps["sujet_t1_jeton_copie"]

    # Le jeton rendu doit effectivement pointer vers le document généré.
    r2 = client.get(f"/api/eleves/documents/{corps['sujet_t1_jeton_copie']}/sujet_confirmation")
    assert r2.status_code == 200, r2.text
    assert r2.content == b"%PDF-1.4 sujet T1"
    app.dependency_overrides.clear()


def test_session_detail_sujet_t1_absent_sans_evaluation():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["sujet_t1_disponible"] is False
    assert corps["sujet_t1_jeton_copie"] is None
    app.dependency_overrides.clear()


def test_session_detail_expose_plan_provisoire():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="hypothese", cout_estime="4"))
    db.commit()

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}")
    assert r.status_code == 200, r.text
    corps = r.json()
    # Le plan officiel n'inclut pas l'hypothèse ; le provisoire, si.
    assert corps["plan"]["nb_problemes"] == 0
    assert corps["plan_provisoire"]["nb_problemes"] == 1
    app.dependency_overrides.clear()


def test_sujet_test_choisit_le_type_selon_le_profil(monkeypatch):
    """`/sujet-test` choisit T1/T3/T4 selon l'état des lacunes du moment —
    ici un problème `en_remediation` ⇒ T3. La génération elle-même (appel
    modèle) est déjà couverte ailleurs, on ne vérifie que l'aiguillage."""
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="en_remediation"))
    db.commit()

    import app.routers.sessions as sessions_mod
    from fastapi import Response

    capte: dict[str, str] = {}

    def _faux_generer_sujet(jeton_session, type_evaluation, telecharger, db, utilisateur):
        capte["type"] = type_evaluation
        return Response(content=b"%PDF", media_type="application/pdf")

    monkeypatch.setattr(sessions_mod, "generer_sujet", _faux_generer_sujet)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/sujet-test")
    assert r.status_code == 200, r.text
    assert capte["type"] == "T3"
    app.dependency_overrides.clear()


def test_sujet_test_refuse_sans_lacune_a_evaluer():
    client, SessionLocal = _client_avec_base()
    db, session = _seed(SessionLocal)

    from app.auth.tokens import jeton

    r = client.get(f"/api/sessions/{jeton(str(session.id))}/sujet-test")
    assert r.status_code == 400
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
