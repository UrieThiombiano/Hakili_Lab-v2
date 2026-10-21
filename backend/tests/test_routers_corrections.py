"""Tests d'intégration du routeur `/api/corrections/*` — le pipeline IA
(`src.pipeline.pipeline.run_transcription/run_grading/run_phase_b`) est
substitué par de faux résultats minimaux : ce n'est pas son objet ici
(couvert par `tests/` à la racine du dépôt, avec de vrais clients mockés) —
ce qui est testé, c'est l'orchestration FastAPI (état de `Correction`,
enchaînement transcription→relecture→correction→validation→diagnostic,
auth, accès). Le thread d'arrière-plan est rendu synchrone en test
(`taches._dans_un_thread` patché) pour un résultat déterministe.
"""
from __future__ import annotations

from pathlib import Path

import app.services.taches as taches_mod
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.deps import utilisateur_requis
from app.db import get_session
from app.main import app
from app.models import Base
from tests.conftest import preparer_client_csrf

_ADMIN = {"nom": "Test", "prenom": "Admin", "role_enum": "administrateur", "roles": ["administrateur"]}
_ELEVE = {"identifiant_hakili": "eleve-1", "nom": "Sanou", "prenom": "Feryel"}


def _pipeline_result(*, copy_id: str, avec_transcription=True, avec_grade=False, erreurs=None):
    from src.models.domain import CopyGrade, IngestionResult, PageTranscription, QuestionGrade, TranscriptionResult
    from src.pipeline.pipeline import PipelineResult

    ingestion = IngestionResult(copy_id=copy_id, total_pages=1, pages=[], output_dir=Path("."))
    transcription = None
    if avec_transcription:
        transcription = TranscriptionResult(
            copy_id=copy_id,
            global_quality="good",
            pages=[PageTranscription(page_number=1, content="reponse initiale", confidence=0.9)],
        )
    grade = None
    if avec_grade:
        grade = CopyGrade(
            copy_id=copy_id,
            total_score=1.0,
            total_possible=1.0,
            questions=[QuestionGrade(rubric_item_id="1", score=1.0, confidence=0.9, comment="", observed_answer="reponse", requires_review=False)],
        )
    return PipelineResult(copy_id=copy_id, student_name="Feryel Sanou", ingestion=ingestion, transcription=transcription, grade=grade, errors=list(erreurs or []))


def _client_avec_base(tmp_path):
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

    import app.routers.corrections as corrections_mod
    import app.services.corrections as services_corrections
    import app.services.eleves as eleves_mod

    corrections_mod.get_accessible_eleves = lambda utilisateur: [_ELEVE]
    services_corrections.get_eleve_by_identifiant = lambda identifiant: _ELEVE
    services_corrections.can_access_eleve = lambda db, utilisateur, eleve: True
    # `soumettre_confirmation` (contrairement au reste du routeur) passe par
    # `app.services.eleves.eleve_autorise` — module distinct de
    # `app.services.corrections`, à substituer séparément.
    eleves_mod.eleve_autorise = lambda utilisateur, identifiant: _ELEVE

    # Threads synchrones, sur la même base de test (pas celle par défaut de
    # `app.db`) + dossier de dépôt isolé par test.
    taches_mod._dans_un_thread = lambda cible, *args: cible(*args)
    taches_mod.SessionLocal = SessionLocal

    from src.core.config import settings

    settings.runs_dir = str(tmp_path)

    client = TestClient(app)
    preparer_client_csrf(client)
    return client, SessionLocal


def test_flux_complet_t0_libre(tmp_path, monkeypatch):
    client, SessionLocal = _client_avec_base(tmp_path)

    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True))

    # Étape 1 : dépôt (mode libre, sujet requis)
    copie = ("copie.pdf", b"%PDF-1.4 faux contenu", "application/pdf")
    sujet = ("sujet.pdf", b"%PDF-1.4 faux sujet", "application/pdf")
    r = client.post(
        "/api/corrections",
        data={"eleve": "eleve-1", "test": "libre", "type_evaluation": "T0", "instructions": ""},
        files=[("copie", copie), ("sujet", sujet)],
    )
    assert r.status_code == 200, r.text
    jeton_copie = r.json()["jeton"]

    # La transcription (mockée) a déjà tourné en synchrone -> relecture.
    r2 = client.get(f"/api/corrections/{jeton_copie}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["etat"] == "relecture"
    assert r2.json()["resultat"]["transcription"]["pages"][0]["content"] == "reponse initiale"

    # Étape 2 : validation de la transcription -> lance la correction (mockée).
    # `run_grading` reçoit le résultat déjà édité par l'enseignant
    # (`valider_transcription`) : le mock doit le conserver, pas en fabriquer
    # un nouveau — sinon le test ne vérifie rien de l'édition de transcription.
    def _fausse_correction(**kw):
        resultat = kw["result"]
        from src.models.domain import CopyGrade, QuestionGrade

        resultat.grade = CopyGrade(
            copy_id=resultat.copy_id,
            total_score=1.0,
            total_possible=1.0,
            questions=[QuestionGrade(rubric_item_id="1", score=1.0, confidence=0.9, comment="", observed_answer="reponse", requires_review=False)],
        )
        return resultat

    monkeypatch.setattr(pipeline_mod, "run_grading", _fausse_correction)

    # `_dans_un_thread` est synchrone en test, mais le thread écrit via sa
    # PROPRE session (comme en production, où il tourne après la réponse) :
    # la réponse de la requête qui déclenche le thread reflète l'état juste
    # avant son exécution, pas après — comme le ferait un vrai thread
    # asynchrone. On revérifie donc par un GET, ce qu'un client réel ferait
    # en pollant (`taches.py`, même modèle que côté Django).
    r3 = client.post(f"/api/corrections/{jeton_copie}/transcription", json={"pages": {1: "reponse corrigee par l'enseignant"}})
    assert r3.status_code == 200, r3.text

    r3b = client.get(f"/api/corrections/{jeton_copie}")
    assert r3b.json()["etat"] == "validation"
    assert r3b.json()["resultat"]["transcription"]["pages"][0]["content"] == "reponse corrigee par l'enseignant"

    # Étape 3 : validation des notes -> lance le diagnostic (mockée, sans référentiel -> pas de module 4).
    monkeypatch.setattr(pipeline_mod, "run_phase_b", lambda **kw: kw["result"])

    r4 = client.post(f"/api/corrections/{jeton_copie}/notes", json={"decisions": {"1": {"decision": "accepted"}}})
    assert r4.status_code == 200, r4.text

    r4b = client.get(f"/api/corrections/{jeton_copie}")
    assert r4b.json()["etat"] == "terminee"
    assert r4b.json()["resultat"]["grade"]["final_score"] == 1.0
    # Mode libre : le bareme_id ne commence pas par "socle_", le module 4 ne
    # tourne jamais (`taches.py::_ecrire_hypotheses_module4`) — pas de
    # session, et `run_phase_b` mocké n'ajoute aucun document.
    assert r4b.json()["documents"] == []
    assert r4b.json()["jeton_session"] is None

    app.dependency_overrides.clear()


def test_statut_expose_documents_et_session_existants(tmp_path, monkeypatch):
    """Sans ces champs, l'écran de résultat n'a aucun moyen de savoir quels
    documents existent vraiment (l'ancien lien « Plan de remédiation »
    pointait presque toujours vers un document jamais généré) ni qu'un
    parcours (session) existe déjà pour cet élève."""
    client, SessionLocal = _client_avec_base(tmp_path)

    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True))

    r = client.post(
        "/api/corrections",
        data={"eleve": "eleve-1", "test": "libre", "type_evaluation": "T0", "instructions": ""},
        files=[("copie", ("copie.pdf", b"%PDF-1.4", "application/pdf")), ("sujet", ("sujet.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    jeton_copie = r.json()["jeton"]

    from app.auth.tokens import valeur_depuis_jeton
    from app.models import Document, Session

    copy_id = valeur_depuis_jeton(jeton_copie)
    db = SessionLocal()
    db.add(Document(copy_id=copy_id, type="rapport", fichier=b"%PDF-1.4"))
    db.add(Session(identifiant_hakili="eleve-1"))
    db.commit()
    db.close()

    r2 = client.get(f"/api/corrections/{jeton_copie}")
    assert r2.status_code == 200, r2.text
    corps = r2.json()
    assert corps["documents"] == ["rapport"]
    assert corps["jeton_session"]

    app.dependency_overrides.clear()


def test_transcription_echouee_passe_en_echec(tmp_path, monkeypatch):
    client, SessionLocal = _client_avec_base(tmp_path)
    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=False, erreurs=["transcription impossible"]))

    copie = ("copie.pdf", b"%PDF-1.4 faux contenu", "application/pdf")
    sujet = ("sujet.pdf", b"%PDF-1.4 faux sujet", "application/pdf")
    r = client.post(
        "/api/corrections",
        data={"eleve": "eleve-1", "test": "libre", "type_evaluation": "T0"},
        files=[("copie", copie), ("sujet", sujet)],
    )
    jeton_copie = r.json()["jeton"]

    r2 = client.get(f"/api/corrections/{jeton_copie}")
    assert r2.json()["etat"] == "echec"
    assert r2.json()["echouee"] is True
    app.dependency_overrides.clear()


def test_fichier_format_refuse(tmp_path):
    client, SessionLocal = _client_avec_base(tmp_path)
    copie = ("copie.exe", b"binaire", "application/octet-stream")
    r = client.post("/api/corrections", data={"eleve": "eleve-1", "test": "libre"}, files=[("copie", copie)])
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_eleve_hors_perimetre_refuse():
    client, SessionLocal = _client_avec_base(Path("."))
    import app.routers.corrections as corrections_mod

    corrections_mod.get_accessible_eleves = lambda utilisateur: []
    copie = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post("/api/corrections", data={"eleve": "eleve-inconnu", "test": "libre"}, files=[("copie", copie)])
    assert r.status_code == 400
    app.dependency_overrides.clear()


class _FausseRubric:
    """Duck-type minimal de `HakiliTest` (`src/knowledge/test_registry.py`) —
    seuls `.rubric`/`.subject_text`/`.official_answers` sont lus par
    `taches.lancer_phase_a_complete`."""

    def __init__(self):
        from src.models.domain import Rubric

        self.rubric = Rubric(subject="mathematics", total_points=1.0, items=[])
        self.subject_text = ""
        self.official_answers = ""


def test_lot_apparie_par_nom_de_fichier_et_lance_phase_a_complete(tmp_path, monkeypatch):
    """Port du scénario `correction_web/views.py::lot` : une copie nommée
    avec le nom+prénom de l'élève est appariée automatiquement (rien deviné
    côté client) et enchaîne transcription+correction sans écran de
    relecture — mais le tableau de validation, lui, reste dû (D-CEO-16)."""
    client, SessionLocal = _client_avec_base(tmp_path)

    import src.knowledge.test_registry as registry_mod
    import src.pipeline.pipeline as pipeline_mod

    fausse_registry = type("R", (), {"get_test": staticmethod(lambda test_id: _FausseRubric() if test_id == "socle_6eme" else None)})()
    monkeypatch.setattr(registry_mod, "get_registry", lambda: fausse_registry)
    monkeypatch.setattr(
        pipeline_mod,
        "run_phase_a",
        lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True, avec_grade=True),
    )

    fichier_apparie = ("Sanou_Feryel.pdf", b"%PDF-1.4", "application/pdf")
    fichier_orphelin = ("Personne_Inconnue.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(
        "/api/corrections/lot",
        data={"test": "socle_6eme", "instructions": ""},
        files=[("copies", fichier_apparie), ("copies", fichier_orphelin)],
    )
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["lancees"] == 1
    assert len(corps["ecartees"]) == 1
    assert "introuvable ou ambigu" in corps["ecartees"][0]

    r2 = client.get("/api/corrections")
    assert len(r2.json()) == 1
    assert r2.json()[0]["etat"] == "validation"  # phase A complète, mais le tableau de validation reste dû
    app.dependency_overrides.clear()


def test_lot_sans_test_selectionne_refuse(tmp_path):
    client, SessionLocal = _client_avec_base(tmp_path)
    fichier = ("Sanou_Feryel.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post("/api/corrections/lot", data={"test": "inconnu"}, files=[("copies", fichier)])
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_soumettre_confirmation_t1_sans_sujet_disponible_refuse(tmp_path):
    """Port de `suivi_web/views.py::soumettre_confirmation` — sans sujet T1
    persisté (`Evaluation.sujet_confirmation`) ni hypothèse couverte
    (`Probleme.exercices_confirmation`), le dépôt est refusé au profit de la
    saisie manuelle depuis l'écran de parcours."""
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Session

    session = Session(identifiant_hakili="eleve-1")
    db.add(session)
    db.commit()
    db.refresh(session)

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/confirmation/{jeton(str(session.id))}", files=[("copie", fichier)])
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_soumettre_confirmation_t1_lance_la_transcription(tmp_path, monkeypatch):
    """Avec un sujet T1 persisté et une hypothèse couverte, le dépôt crée
    une `Correction` T1 dont le barème reprend les exercices du sujet
    (`RubricItem.id` = numéro d'exercice — la correspondance posée par
    `taches.py::_persister_sujet_confirmation`, pas devinée après coup)."""
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Evaluation, Probleme, Session

    session = Session(identifiant_hakili="eleve-1")
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        Evaluation(
            session_id=session.id,
            type="T0",
            numero=1,
            sujet_confirmation=[
                {"numero": 1, "topic": "Compétence A × CPT", "question": "Développer...", "hint": ""},
                {"numero": 2, "topic": "Compétence A × CPT", "question": "Réduire...", "hint": ""},
            ],
        )
    )
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="hypothese", exercices_confirmation=[1, 2]))
    db.commit()

    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True))

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/confirmation/{jeton(str(session.id))}", files=[("copie", fichier)])
    assert r.status_code == 200, r.text
    jeton_copie = r.json()["jeton"]

    r2 = client.get(f"/api/corrections/{jeton_copie}")
    assert r2.json()["etat"] == "relecture"

    from app.models import Correction

    correction = db.query(Correction).filter_by(copy_id=r2.json()["resultat"]["copy_id"]).first()
    assert correction.type_evaluation == "T1"
    app.dependency_overrides.clear()


def test_soumettre_verification_t3_sans_sujet_en_attente_refuse(tmp_path):
    """Sans `Session.sujet_verification_*` posé par
    `generation.persister_sujet_verification` (déclenché au téléchargement du
    sujet, `GET /sessions/{jeton}/sujets/T3`), le dépôt ciblé est refusé."""
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Session

    session = Session(identifiant_hakili="eleve-1")
    db.add(session)
    db.commit()
    db.refresh(session)

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/verification/{jeton(str(session.id))}/T3", files=[("copie", fichier)])
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_soumettre_verification_t3_type_different_de_celui_en_attente_refuse(tmp_path):
    """Un sujet T4 en attente ne peut pas être déposé comme T3 — protège
    contre un dépôt tardif après qu'un autre sujet a été régénéré entre
    temps."""
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Session

    session = Session(
        identifiant_hakili="eleve-1",
        sujet_verification_type="T4",
        sujet_verification_exercices=[{"numero": 1, "topic": "Compétence A × CPT", "question": "...", "hint": ""}],
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/verification/{jeton(str(session.id))}/T3", files=[("copie", fichier)])
    assert r.status_code == 400
    assert "T4" in r.json()["detail"]
    app.dependency_overrides.clear()


def test_soumettre_verification_t3_lance_la_transcription(tmp_path, monkeypatch):
    """Avec un sujet T3 en attente, le dépôt crée une `Correction` T3 dont le
    barème reprend les exercices posés par `persister_sujet_verification`."""
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Probleme, Session

    session = Session(
        identifiant_hakili="eleve-1",
        sujet_verification_type="T3",
        sujet_verification_exercices=[
            {"numero": 1, "topic": "Compétence A × CPT", "question": "Développer...", "hint": ""},
            {"numero": 2, "topic": "Compétence A × CPT", "question": "Réduire...", "hint": ""},
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="en_remediation", exercices_verification=[1, 2]))
    db.commit()

    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True))

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/verification/{jeton(str(session.id))}/T3", files=[("copie", fichier)])
    assert r.status_code == 200, r.text
    jeton_copie = r.json()["jeton"]

    r2 = client.get(f"/api/corrections/{jeton_copie}")
    assert r2.json()["etat"] == "relecture"

    from app.models import Correction

    correction = db.query(Correction).filter_by(copy_id=r2.json()["resultat"]["copy_id"]).first()
    assert correction.type_evaluation == "T3"
    app.dependency_overrides.clear()


def test_soumettre_verification_type_invalide_404(tmp_path):
    client, SessionLocal = _client_avec_base(tmp_path)
    db = SessionLocal()

    from app.models import Session

    session = Session(identifiant_hakili="eleve-1")
    db.add(session)
    db.commit()
    db.refresh(session)

    from app.auth.tokens import jeton

    fichier = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    r = client.post(f"/api/corrections/verification/{jeton(str(session.id))}/T1", files=[("copie", fichier)])
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_liste_corrections(tmp_path, monkeypatch):
    client, SessionLocal = _client_avec_base(tmp_path)
    import src.pipeline.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "run_transcription", lambda **kw: _pipeline_result(copy_id=kw["copy_id"], avec_transcription=True))

    copie = ("copie.pdf", b"%PDF-1.4", "application/pdf")
    sujet = ("sujet.pdf", b"%PDF-1.4", "application/pdf")
    client.post("/api/corrections", data={"eleve": "eleve-1", "test": "libre"}, files=[("copie", copie), ("sujet", sujet)])

    r = client.get("/api/corrections")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["eleve_nom"] == "Sanou"
    app.dependency_overrides.clear()
