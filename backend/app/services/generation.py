"""Port de `suivi/generation.py` — génération à la demande des sujets T3
(vérification après remédiation) et T4/T5 (contrôle de rétention). Miroir de
`_generer_sujet_confirmation` (`app/services/taches.py`), avec une
différence de fond : le timing de T3/T4/T5 est une décision humaine — c'est
l'enseignant qui déclenche la génération depuis le profil élève, jamais le
pipeline de correction.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session as SQLASession

from app.models import Probleme, Session

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
