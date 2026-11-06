"""Port de `suivi/generation.py` — génération à la demande des sujets T3
(vérification après remédiation) et T4/T5 (contrôle de rétention). Miroir de
`_generer_sujet_confirmation` (`app/services/taches.py`), avec une
différence de fond : le timing de T3/T4/T5 est une décision humaine — c'est
l'enseignant qui déclenche la génération depuis le profil élève, jamais le
pipeline de correction.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy.orm import Session as SQLASession

from app.models import Evaluation, Probleme, Session

logger = logging.getLogger(__name__)

#: Problème ciblé par chaque type — respecte strictement
#: `etats.TRANSITIONS_PERMISES` : seul un problème `en_remediation` peut
#: avancer vers `resolu`/`non_resolu` (T3), seul un problème `resolu` peut
#: avancer vers `regresse`/`clos` (T4, T5).
ETAT_CIBLE: dict[str, str] = {"T3": "en_remediation", "T4": "resolu", "T5": "resolu"}


def problemes_a_verifier(db: SQLASession, session: Session, type_evaluation: str) -> list[Probleme]:
    """Lève `ValueError` pour un type sans sujet de vérification (T0, T1 —
    leur sujet suit un autre chemin, voir `app/services/taches.py`)."""
    etat = ETAT_CIBLE.get(type_evaluation)
    if etat is None:
        raise ValueError(f"Pas de sujet de vérification pour le type « {type_evaluation} ».")
    return db.query(Probleme).filter(Probleme.session_id == session.id, Probleme.etat == etat).all()


def _client():
    try:
        from src.api.claude_client import ClaudeClient

        return ClaudeClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[module 5] Aucun client disponible (%s).", exc)
        return None


def generer_sujet_verification(db: SQLASession, session: Session, type_evaluation: str):
    """Génère le sujet T3/T4/T5 pour cette session, ou `None` si rien à
    vérifier ou si la génération a échoué. Best-effort — une panne ici
    empêche seulement la génération, elle ne fait rien perdre."""
    from src.knowledge.remediation_retriever import get_remediation_retriever
    from src.models.domain import VerificationItem, VerificationRequest
    from src.pipeline.orchestrator import validate_verification

    problemes = problemes_a_verifier(db, session, type_evaluation)
    if not problemes:
        return None

    client = _client()
    if client is None:
        return None

    retriever = get_remediation_retriever()

    def _item(p: Probleme) -> VerificationItem:
        niveau = p.competence.niveau_intro
        chunk = retriever.get_by_competence(p.competence.code, niveau)
        return VerificationItem(
            competence_label=p.competence.libelle,
            type_erreur_label=p.type_erreur.libelle,
            contexte=p.justification,
            competence_code=p.competence.code,
            niveau=niveau,
            reference_pedagogique=chunk.to_context_text() if chunk else None,
        )

    request = VerificationRequest(
        copy_id=f"verif-{session.id}-{type_evaluation.lower()}",
        type_evaluation=type_evaluation,
        items=[_item(p) for p in problemes],
    )
    reponse = client.generate_verification_subject(request)
    if not reponse.success or reponse.data is None:
        logger.warning("[session %s] Génération %s échouée (%s)", session.id, type_evaluation, reponse.error)
        return None

    validation = validate_verification(reponse.data, request)
    if not validation.valid:
        logger.warning(
            "[session %s] Sujet %s invalide, non produit (%s)",
            session.id, type_evaluation, [i.message for i in validation.issues if i.severity == "error"],
        )
        return None

    logger.info("[session %s] Sujet %s généré — %d problème(s) ciblé(s).", session.id, type_evaluation, len(problemes))
    return validation.data


def persister_sujet_verification(db: SQLASession, session: Session, type_evaluation: str, sujet) -> None:
    """Enregistre le sujet T3/T4/T5 comme « en attente de dépôt » et relie
    chaque problème ciblé à ses numéros d'exercice, par correspondance de
    `topic` — même mécanisme que `_persister_sujet_confirmation` (module 5,
    T1), jamais par position dans la liste, plus fragile.

    Contrairement à T1, il n'y a pas d'`Evaluation` existante sur laquelle
    poser le sujet à cet instant : il est porté par `Session` et écrasé à
    chaque régénération (un seul sujet en attente à la fois). L'`Evaluation`
    réelle n'est créée qu'au dépôt de la copie corrigée
    (`app/services/taches.py::_trancher_verification_module5`), pour que le
    rang (`numero`) ne soit jamais consommé par une génération jamais
    déposée."""
    problemes = problemes_a_verifier(db, session, type_evaluation)

    numeros_par_topic: dict[str, list[int]] = defaultdict(list)
    for exercice in sujet.exercises:
        numeros_par_topic[exercice.topic].append(exercice.number)

    for probleme in problemes:
        topic = f"{probleme.competence.libelle} × {probleme.type_erreur.libelle}"
        numeros = numeros_par_topic.get(topic)
        if not numeros:
            continue
        probleme.exercices_verification = numeros
        db.add(probleme)

    session.sujet_verification_type = type_evaluation
    session.sujet_verification_exercices = [
        {"numero": e.number, "topic": e.topic, "question": e.question, "hint": e.hint} for e in sujet.exercises
    ]
    db.add(session)
    db.commit()


# ── Sujet de confirmation T1 à la demande ────────────────────────────────────
# Le pipeline génère un T1 automatiquement à la fin d'un T0
# (`taches._generer_sujet_confirmation`). Ces deux fonctions font la même
# chose mais depuis le parcours, à la demande de l'enseignant et à partir des
# hypothèses **actuellement** ouvertes — régénérées à chaque appel, elles
# tiennent compte des hypothèses écartées ou confirmées entre-temps.


def generer_sujet_confirmation(db: SQLASession, session: Session):
    """Rend `(sujet, hypotheses)` ou `None` — sujet T1 (2 questions par
    hypothèse, discrimine chaque lacune) construit sur les problèmes encore à
    l'état `hypothese`. Best-effort : une panne de génération rend `None`."""
    from src.knowledge.remediation_retriever import get_remediation_retriever
    from src.models.domain import ConfirmationHypothesis, ConfirmationRequest
    from src.pipeline.orchestrator import validate_confirmation

    hypotheses = db.query(Probleme).filter(Probleme.session_id == session.id, Probleme.etat == "hypothese").all()
    if not hypotheses:
        return None

    client = _client()
    if client is None:
        return None

    retriever = get_remediation_retriever()

    def _hypothese(p: Probleme) -> ConfirmationHypothesis:
        niveau = p.competence.niveau_intro
        chunk = retriever.get_by_competence(p.competence.code, niveau) if niveau else None
        return ConfirmationHypothesis(
            competence_label=p.competence.libelle,
            type_erreur_label=p.type_erreur.libelle,
            justification=p.justification,
            is_att=p.type_erreur_id == "ATT",
            competence_code=p.competence.code,
            niveau=niveau or None,
            reference_pedagogique=chunk.to_context_text() if chunk else None,
        )

    request = ConfirmationRequest(copy_id=f"t1-{session.id}", hypotheses=[_hypothese(p) for p in hypotheses])
    reponse = client.generate_confirmation_subject(request)
    if not reponse.success or reponse.data is None:
        logger.warning("[session %s] Génération T1 (à la demande) échouée (%s)", session.id, reponse.error)
        return None

    validation = validate_confirmation(reponse.data, request)
    if not validation.valid:
        logger.warning(
            "[session %s] Sujet T1 (à la demande) invalide, non produit (%s)",
            session.id, [i.message for i in validation.issues if i.severity == "error"],
        )
        return None

    logger.info("[session %s] Sujet T1 (à la demande) généré — %d hypothèse(s).", session.id, len(hypotheses))
    return validation.data, hypotheses


def persister_sujet_confirmation(db: SQLASession, session: Session, sujet, hypotheses: list[Probleme], student_name: str = "") -> None:
    """Attache le sujet T1 à la dernière évaluation T0 de la session et relie
    chaque hypothèse à ses numéros d'exercice (correspondance de `topic`, comme
    `taches._persister_sujet_confirmation`) — pour que le dépôt de la copie T1
    puisse trancher automatiquement. Régénérer avant dépôt remplace l'ancien,
    **y compris le PDF stocké** (`document` type `sujet_confirmation`), pour
    que le lien de téléchargement et les numéros d'exercice ne divergent pas."""
    evaluation = (
        db.query(Evaluation)
        .filter(Evaluation.session_id == session.id, Evaluation.type == "T0")
        .order_by(Evaluation.date.desc(), Evaluation.numero.desc())
        .first()
    )
    if evaluation is None:
        logger.warning("[session %s] Sujet T1 non persisté — aucune évaluation T0.", session.id)
        return

    numeros_par_topic: dict[str, list[int]] = defaultdict(list)
    for exercice in sujet.exercises:
        numeros_par_topic[exercice.topic].append(exercice.number)

    for probleme in hypotheses:
        topic = f"{probleme.competence.libelle} × {probleme.type_erreur.libelle}"
        numeros = numeros_par_topic.get(topic)
        if not numeros:
            continue
        probleme.exercices_confirmation = numeros
        db.add(probleme)

    evaluation.sujet_confirmation = [
        {"numero": e.number, "topic": e.topic, "question": e.question, "hint": e.hint} for e in sujet.exercises
    ]
    db.add(evaluation)
    db.commit()

    # PDF stocké : régénéré et remplacé (`ajouter_document` remplace) pour rester
    # aligné sur les `exercices_confirmation` qu'on vient d'écrire. Best-effort —
    # une panne ici ne perd pas le sujet, seulement son lien de téléchargement.
    if evaluation.copy_id:
        try:
            from pathlib import Path

            from src.core.config import settings
            from src.pipeline.depot import depot
            from src.pipeline.pdf_remediation_html import generate_remediation_pdf

            pdf_path = Path(settings.runs_dir) / evaluation.copy_id / "sujet_confirmation.pdf"
            generate_remediation_pdf(
                output_path=pdf_path,
                copy_id=evaluation.copy_id,
                student_name=student_name,
                remediation_subject=sujet,
            )
            depot().ajouter_document(
                copy_id=evaluation.copy_id, type_document="sujet_confirmation", contenu=pdf_path.read_bytes()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[session %s] Sujet T1 : PDF stocké non mis à jour (%s)", session.id, exc)
