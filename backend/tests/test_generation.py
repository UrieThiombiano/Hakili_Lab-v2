"""`app/services/generation.py` — génération à la demande des sujets T3/T4/T5
et persistance du sujet en attente de dépôt (module 5, suite). Le client IA
et `RemediationRetriever` ne sont pas exercés ici (voir
`test_diagnostic_suivi.py` et `test_routers_corrections.py` pour ce qui suit
le dépôt) — ce qui est testé, c'est la correspondance sujet ↔ problèmes.
"""
from __future__ import annotations

from app.models import Probleme, Session
from app.services import generation
from src.models.domain import Exercise, VerificationSubject


def _sujet(*exercices: Exercise, type_evaluation: str = "T3") -> VerificationSubject:
    return VerificationSubject(copy_id="verif-1", type_evaluation=type_evaluation, exercises=list(exercices))


def test_problemes_a_verifier_filtre_par_etat_cible(db, referentiel_minimal):
    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    en_remediation = Probleme(session_id=session.id, competence_id="B", type_erreur_id="CPT", etat="en_remediation")
    hypothese = Probleme(session_id=session.id, competence_id="A", type_erreur_id="CPT", etat="hypothese")
    db.add_all([en_remediation, hypothese])
    db.commit()

    problemes = generation.problemes_a_verifier(db, session, "T3")
    assert [p.id for p in problemes] == [en_remediation.id]


def test_persister_sujet_verification_relie_les_problemes_par_topic(db, referentiel_minimal):
    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    probleme = Probleme(session_id=session.id, competence_id="B", type_erreur_id="CPT", etat="en_remediation")
    db.add(probleme)
    db.commit()

    topic = f"{probleme.competence.libelle} × {probleme.type_erreur.libelle}"
    sujet = _sujet(
        Exercise(number=1, topic=topic, question="Développer (2x-3)^2", hint=""),
        Exercise(number=2, topic=topic, question="Développer (3a-4b)^2", hint=""),
    )

    generation.persister_sujet_verification(db, session, "T3", sujet)

    db.refresh(probleme)
    db.refresh(session)
    assert probleme.exercices_verification == [1, 2]
    assert session.sujet_verification_type == "T3"
    assert session.sujet_verification_exercices == [
        {"numero": 1, "topic": topic, "question": "Développer (2x-3)^2", "hint": ""},
        {"numero": 2, "topic": topic, "question": "Développer (3a-4b)^2", "hint": ""},
    ]


def test_persister_sujet_verification_ignore_un_topic_non_couvert(db, referentiel_minimal):
    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    probleme = Probleme(session_id=session.id, competence_id="B", type_erreur_id="CPT", etat="en_remediation")
    db.add(probleme)
    db.commit()

    sujet = _sujet(Exercise(number=1, topic="Un autre problème × MOD", question="...", hint=""))
    generation.persister_sujet_verification(db, session, "T3", sujet)

    db.refresh(probleme)
    assert probleme.exercices_verification == []


def test_persister_sujet_verification_ecrase_une_generation_precedente(db, referentiel_minimal):
    """Régénérer avant dépôt remplace le sujet en attente — pas de rang
    fantôme, aucune accumulation (voir le plan : l'`Evaluation` réelle n'est
    créée qu'au dépôt, jamais à la génération)."""
    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    probleme = Probleme(session_id=session.id, competence_id="B", type_erreur_id="CPT", etat="en_remediation")
    db.add(probleme)
    db.commit()
    topic = f"{probleme.competence.libelle} × {probleme.type_erreur.libelle}"

    generation.persister_sujet_verification(db, session, "T3", _sujet(Exercise(number=1, topic=topic, question="v1", hint="")))
    generation.persister_sujet_verification(db, session, "T3", _sujet(Exercise(number=7, topic=topic, question="v2", hint="")))

    db.refresh(probleme)
    db.refresh(session)
    assert probleme.exercices_verification == [7]
    assert session.sujet_verification_exercices == [{"numero": 7, "topic": topic, "question": "v2", "hint": ""}]
