"""Fixtures pytest — base SQLite en mémoire, comme le fait déjà Django côté
tests (`DATABASE_URL="sqlite:///:memory:" python manage.py test`) : la
convention de test de ce projet ne dépend pas d'une vraie base Postgres.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Competence, CoutRemediation, Prerequis, Probleme, Session, TypeErreur

#: Jeton CSRF de test — même valeur en cookie et en en-tête sur chaque
#: `TestClient` (voir `app/auth/csrf.py`, double-submit). Pas un secret, une
#: simple égalité à faire tenir.
JETON_CSRF_TEST = "jeton-csrf-de-test"


def preparer_client_csrf(client) -> None:
    """Pose le cookie CSRF et l'en-tête assorti par défaut sur un
    `TestClient`, une fois — sinon toute requête POST/PUT/PATCH/DELETE des
    suites de tests de routeurs échoue en 403 (`CSRFMiddleware`)."""
    client.cookies.set("csrf_token", JETON_CSRF_TEST)
    client.headers.update({"X-CSRF-Token": JETON_CSRF_TEST})


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def referentiel_minimal(db):
    """Un petit référentiel suffisant pour les tests de service : ATT (non
    remédiable) et CPT (remédiable), deux compétences dont l'une est
    prérequis de l'autre, et un coût précalculé pour (B, CPT)."""
    att = TypeErreur(code="ATT", libelle="Inattention", definition="", signature="", coefficient="0", remediable=False)
    cpt = TypeErreur(code="CPT", libelle="Conceptuelle", definition="", signature="", coefficient="0.7", remediable=True)
    db.add_all([att, cpt])

    a = Competence(code="A", domaine="Activites numeriques", libelle="A", niveau_intro="6eme", volume_horaire="4")
    b = Competence(code="B", domaine="Activites numeriques", libelle="B", niveau_intro="5eme", volume_horaire="6")
    db.add_all([a, b])
    db.flush()

    db.add(Prerequis(competence_id="B", prerequis_id="A"))
    db.add(CoutRemediation(competence_id="B", type_erreur_id="CPT", cout_heures="4"))
    db.commit()
    return {"att": att, "cpt": cpt, "a": a, "b": b}


@pytest.fixture()
def session_suivi(db, referentiel_minimal):
    s = Session(identifiant_hakili="test-eleve")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def creer_probleme(db, session: Session, *, competence_id: str, type_erreur_id: str, etat: str = "hypothese", cout: str = "0") -> Probleme:
    p = Probleme(
        session_id=session.id,
        competence_id=competence_id,
        type_erreur_id=type_erreur_id,
        etat=etat,
        cout_estime=cout,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p
