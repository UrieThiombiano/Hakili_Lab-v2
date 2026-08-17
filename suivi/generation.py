"""
Génération à la demande des sujets T3 (vérification après remédiation) et
T4/T5 (contrôle de rétention) — module 5 étendu au-delà de T1.

Miroir de `_generer_sujet_confirmation` (`correction_web/taches.py`), avec une
différence de fond : T1 est généré en sous-produit automatique d'une
correction T0, alors que le timing de T3/T4/T5 (fin de volume horaire,
+45 jours, +3 mois) est une décision humaine — c'est l'enseignant qui déclenche
la génération depuis le profil élève, jamais le pipeline de correction.

Le sujet n'est jamais persisté (pas de `Document`) : les problèmes qu'il cible
peuvent changer d'état entre deux visites, un PDF figé irait vite périmé —
même raison que `suivi/plan.py` / `fiche_remediation` (le plan n'est pas
stocké non plus).
"""
from __future__ import annotations

import logging

from suivi.models import EtatProbleme, Probleme, Session, TypeEvaluation

logger = logging.getLogger(__name__)

#: Problème ciblé par chaque type — respecte strictement
#: `Probleme.TRANSITIONS_PERMISES` (suivi/models.py) : seul un problème
#: `en_remediation` peut avancer vers `resolu`/`non_resolu` (T3), seul un
#: problème `resolu` peut avancer vers `regresse`/`clos` (T4, T5).
ETAT_CIBLE: dict[str, str] = {
    TypeEvaluation.T3: EtatProbleme.EN_REMEDIATION,
    TypeEvaluation.T4: EtatProbleme.RESOLU,
    TypeEvaluation.T5: EtatProbleme.RESOLU,
}


def problemes_a_verifier(session: Session, type_evaluation: str) -> list[Probleme]:
    """Les problèmes que ce type d'évaluation doit recontrôler.

    Lève `ValueError` pour un type sans sujet de vérification (T0, T1 — leurs
    sujets suivent un autre chemin, voir `correction_web/taches.py`).
    """
    etat = ETAT_CIBLE.get(type_evaluation)
    if etat is None:
        raise ValueError(
            f"Pas de sujet de vérification pour le type « {type_evaluation} »."
        )
    return list(
        session.problemes.filter(etat=etat).select_related("competence", "type_erreur")
    )


def _client():
    """Même client best-effort que le module 4 — une clé d'API absente ne doit
    jamais faire planter l'écran qui propose de générer un sujet."""
    try:
        from src.api.claude_client import ClaudeClient

        return ClaudeClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[module 5] Aucun client disponible (%s).", exc)
        return None


def generer_sujet_verification(session: Session, type_evaluation: str):
    """Génère le sujet T3/T4/T5 pour cette session, ou `None` si rien à
    vérifier ou si la génération a échoué.

    Retourne un `VerificationSubject` (`src.models.domain`), prêt pour
    `generate_remediation_pdf`. Best-effort, comme le reste du pipeline de
    génération : appelé depuis une vue, pas depuis la correction, une panne
    ici ne fait rien perdre — elle empêche seulement la génération.
    """
    from src.knowledge.remediation_retriever import get_remediation_retriever
    from src.models.domain import VerificationItem, VerificationRequest
    from src.pipeline.orchestrator import validate_verification

    problemes = problemes_a_verifier(session, type_evaluation)
    if not problemes:
        return None

    client = _client()
    if client is None:
        return None

    # `Session` ne porte pas la classe de l'élève (aucun champ niveau — pas de
    # copie T0 requise pour T3/T4/T5, contrairement au T1 de
    # `correction_web/taches.py`, qui lit `_niveau_test(correction.bareme_id)`).
    # `competence.niveau_intro` reste toujours disponible et pointe vers le
    # livret où la notion est enseignée avec ses exemples complets — reste
    # une entrée valide pour le retriever, dégradée sans erreur si absente
    # (ex. `Primaire`, sans livret de remédiation dédié).
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
        copy_id=f"verif-{session.pk}-{type_evaluation.lower()}",
        type_evaluation=type_evaluation,
        items=[_item(p) for p in problemes],
    )
    reponse = client.generate_verification_subject(request)
    if not reponse.success or reponse.data is None:
        logger.warning(
            "[session %s] Génération %s échouée (%s)",
            session.pk, type_evaluation, reponse.error,
        )
        return None

    validation = validate_verification(reponse.data, request)
    if not validation.valid:
        logger.warning(
            "[session %s] Sujet %s invalide, non produit (%s)",
            session.pk, type_evaluation,
            [i.message for i in validation.issues if i.severity == "error"],
        )
        return None

    logger.info(
        "[session %s] Sujet %s généré — %d problème(s) ciblé(s).",
        session.pk, type_evaluation, len(problemes),
    )
    return validation.data
