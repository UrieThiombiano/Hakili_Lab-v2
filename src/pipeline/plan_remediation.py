"""
Plan de remédiation : du squelette (`DemandePlan`) au cahier (`PlanRemediation`).

Le squelette est fourni par l'appelant — l'application, qui seule connaît le
référentiel (diagnostic contraint, prérequis, coûts). Ce module ne fait que
demander au modèle le contenu de chaque section et assembler le tout ; il ne
dépend d'aucun framework, comme le reste de `src/pipeline/`.

Les sections sont rédigées en parallèle (une par compétence : une copie faible
en compte une quinzaine). Une section en échec est redemandée ; si elle échoue
à chaque tentative, il n'y a pas de plan — un cahier troué ne serait pas remis
à un élève.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from src.models.domain import (
    SEUIL_SANS_PLAN,
    CompetencePlan,
    ContenuSection,
    DemandePlan,
    PlanRemediation,
    SectionPlanDemande,
)

logger = logging.getLogger(__name__)

#: Appels simultanés au modèle — au-delà, les limites de débit de l'API
#: transforment le gain de temps en relances.
SECTIONS_EN_PARALLELE = 6
#: Tentatives sur le modèle principal, puis une dernière sur le modèle de
#: repli. Chaque nouvelle tentative reçoit le motif du refus précédent : une
#: sortie incomplète (liste vide, exercice manquant) est corrigée, pas
#: retirée au sort.
TENTATIVES_PAR_SECTION = 3


class PlanIncomplet(RuntimeError):
    """Une section n'a pas pu être rédigée : aucun plan n'est produit."""


def plan_requis(note_sur_20: float | None) -> bool:
    """Pas de plan à partir de 19/20 (note imprimée sur le rapport)."""
    return note_sur_20 is None or note_sur_20 < SEUIL_SANS_PLAN


def _motif(erreur: str) -> str:
    """Motif de refus lisible par le modèle : le message de validation, sans
    les liens de documentation de pydantic ni la sortie recopiée."""
    lignes = [l for l in erreur.splitlines()
              if l.strip() and "errors.pydantic.dev" not in l and not l.startswith("tool_block")]
    return "\n".join(lignes)[:1500] or "réponse vide"


def _rediger(client, demande: DemandePlan, section: SectionPlanDemande) -> ContenuSection:
    modeles = [None] * TENTATIVES_PAR_SECTION + [getattr(client, "modele_repli", None)]
    refus = ""
    for tentative, modele in enumerate(modeles, start=1):
        reponse = client.generate_plan_section(demande, section, refus=refus, modele=modele)
        if reponse.success and reponse.data is not None:
            return reponse.data
        refus = _motif(reponse.error or "")
        logger.warning("[%s] Plan — section %d, tentative %d en échec : %s",
                       demande.copy_id, section.ordre, tentative, refus)
    raise PlanIncomplet(f"section {section.ordre} ({section.code_competence}) : {refus}")


def _assembler(section: SectionPlanDemande, contenu: ContenuSection) -> CompetencePlan:
    return CompetencePlan(
        **contenu.model_dump(),
        duree_h=section.duree_h,
        # En-tête de section : les questions en erreur seulement (une question
        # réussie peut figurer dans « Ce que tu as écrit », pas ici).
        questions=[q.code for q in section.questions if not q.reussie],
        prerequis=section.prerequis,
        code_competence=section.code_competence,
    )


def generer_plan(demande: DemandePlan, client) -> PlanRemediation:
    """Rédige toutes les sections puis l'encadré des acquis. Lève
    `PlanIncomplet` si une section n'a pas pu être rédigée ; un encadré des
    acquis en échec est seulement omis."""
    if not demande.sections:
        raise PlanIncomplet("aucune compétence à reprendre")

    with ThreadPoolExecutor(max_workers=SECTIONS_EN_PARALLELE) as pool:
        futurs = [pool.submit(_rediger, client, demande, s) for s in demande.sections]
        acquis_futur = pool.submit(client.generate_plan_acquis, demande) if demande.questions_reussies else None
        contenus = [f.result() for f in futurs]  # lève la première PlanIncomplet
        acquis = []
        if acquis_futur is not None:
            try:
                reponse = acquis_futur.result()
                if reponse.success and reponse.data is not None:
                    acquis = reponse.data.acquis
                else:
                    logger.warning("[%s] Plan — acquis non rédigés : %s", demande.copy_id, reponse.error)
            except Exception as exc:  # noqa: BLE001 — l'encadré est facultatif
                logger.warning("[%s] Plan — acquis non rédigés : %s", demande.copy_id, exc)

    return PlanRemediation(
        copy_id=demande.copy_id,
        eleve_nom=demande.eleve_nom,
        prenom=demande.prenom,
        classe=demande.classe,
        test_libelle=demande.test_libelle,
        date=demande.date,
        acquis=acquis,
        competences=[_assembler(s, c) for s, c in zip(demande.sections, contenus)],
    )
