"""
Plan de remédiation : du squelette (`DemandePlan`) au cahier (`PlanRemediation`).

Le squelette est fourni par l'appelant — l'application, qui seule connaît le
référentiel (diagnostic contraint, prérequis, coûts). Ce module ne fait que
demander au modèle le contenu de chaque section et assembler le tout ; il ne
dépend d'aucun framework, comme le reste de `src/pipeline/`.

Les sections sont rédigées en parallèle (une par compétence : une copie faible
en compte une quinzaine). Un cahier troué ne serait pas remis à un élève : une
section qui n'aboutit pas empêche le plan, donc tout est fait pour qu'elle
aboutisse, en quatre niveaux :

1. la structure est imposée par le schéma de l'outil, en mode strict (cinq
   emplacements d'exercice, aucun texte obligatoire vide) ;
2. une tentative refusée est redemandée avec le motif du refus ; une réponse
   coupée faute de place, avec un budget doublé ; la dernière tentative passe
   par le modèle de repli (aussi tout de suite après un refus de sécurité) ;
3. les sections encore en échec sont reprises une fois, après une pause, une
   fois toutes les autres écrites — une indisponibilité passagère de l'API
   ne coûte pas le plan ;
4. si une section échoue malgré tout, les sections écrites ne sont pas
   perdues : `PlanIncomplet` les porte, et `generer_plan(..., deja=…)` ne
   rédige plus que les manquantes (reprise à la demande de l'enseignant).
"""
from __future__ import annotations

import logging
import time
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
#: Tentatives sur le modèle principal, avant une dernière sur le modèle de repli.
TENTATIVES_PAR_SECTION = 3
#: Budget de sortie d'une section, doublé après une réponse coupée.
BUDGET_SECTION = 32000
BUDGET_SECTION_MAX = 64000
#: Pause avant de reprendre les sections en échec (secondes).
PAUSE_AVANT_REPRISE = 60.0


class PlanIncomplet(RuntimeError):
    """Une section n'a pas pu être rédigée : aucun plan n'est produit. Les
    sections rédigées (`contenus`, par numéro d'ordre) et l'encadré des
    acquis sont conservés pour une reprise."""

    def __init__(self, message: str, contenus: dict[int, ContenuSection] | None = None,
                 acquis: list[str] | None = None):
        super().__init__(message)
        self.contenus = contenus or {}
        self.acquis = acquis or []


def plan_requis(note_sur_20: float | None) -> bool:
    """Pas de plan à partir de 19/20 (note imprimée sur le rapport)."""
    return note_sur_20 is None or note_sur_20 < SEUIL_SANS_PLAN


def _motif(erreur: str) -> str:
    """Motif de refus lisible par le modèle : le message de validation, sans
    les liens de documentation de pydantic ni la sortie recopiée."""
    lignes = [l for l in erreur.splitlines()
              if l.strip() and "errors.pydantic.dev" not in l and not l.startswith("tool_block")]
    motif = "\n".join(lignes)[:1500] or "réponse vide"
    if "stop_reason=max_tokens" in motif:
        motif += ("\nTa réponse a été coupée avant l'appel de l'outil, faute de place : "
                  "réfléchis plus brièvement et appelle l'outil plus tôt.")
    elif "stop_reason=end_turn" in motif:
        motif += "\nTu as répondu en texte : la section doit être rendue par l'appel de l'outil."
    return motif


def _rediger(client, demande: DemandePlan, section: SectionPlanDemande) -> ContenuSection:
    """Toutes les tentatives d'une section ; lève `PlanIncomplet` si aucune
    n'aboutit."""
    repli = getattr(client, "modele_repli", None)
    refus, budget, sur_repli = "", BUDGET_SECTION, False
    for tentative in range(1, TENTATIVES_PAR_SECTION + 2):
        derniere = tentative == TENTATIVES_PAR_SECTION + 1
        modele = repli if (derniere or sur_repli) else None
        reponse = client.generate_plan_section(demande, section, refus=refus, modele=modele, max_tokens=budget)
        if reponse.success and reponse.data is not None:
            return reponse.data
        erreur = reponse.error or ""
        refus = _motif(erreur)
        if "stop_reason=max_tokens" in erreur:
            budget = BUDGET_SECTION_MAX
        if "stop_reason=refusal" in erreur:
            sur_repli = True  # le classifieur refusera encore : autre modèle tout de suite
        logger.warning("[%s] Plan — section %d, tentative %d en échec : %s",
                       demande.copy_id, section.ordre, tentative, refus)
        if derniere or (sur_repli and modele == repli):
            break
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


def _rediger_toutes(pool: ThreadPoolExecutor, client, demande: DemandePlan,
                    sections: list[SectionPlanDemande]) -> tuple[dict[int, ContenuSection], dict[int, str]]:
    futurs = {s.ordre: pool.submit(_rediger, client, demande, s) for s in sections}
    contenus: dict[int, ContenuSection] = {}
    echecs: dict[int, str] = {}
    for ordre, futur in futurs.items():
        try:
            contenus[ordre] = futur.result()
        except PlanIncomplet as exc:
            echecs[ordre] = str(exc)
    return contenus, echecs


def generer_plan(demande: DemandePlan, client, deja: dict[int, ContenuSection] | None = None,
                 acquis_deja: list[str] | None = None) -> PlanRemediation:
    """Rédige les sections (sauf celles de `deja`, déjà rédigées) puis
    l'encadré des acquis. Lève `PlanIncomplet` si une section n'a pas pu
    être rédigée, avec les sections écrites ; un encadré des acquis en échec
    est seulement omis."""
    if not demande.sections:
        raise PlanIncomplet("aucune compétence à reprendre")

    contenus: dict[int, ContenuSection] = dict(deja or {})
    a_rediger = [s for s in demande.sections if s.ordre not in contenus]

    with ThreadPoolExecutor(max_workers=SECTIONS_EN_PARALLELE) as pool:
        acquis_futur = (pool.submit(client.generate_plan_acquis, demande)
                        if demande.questions_reussies and not acquis_deja else None)
        nouveaux, echecs = _rediger_toutes(pool, client, demande, a_rediger)
        contenus.update(nouveaux)
        if echecs:
            logger.warning("[%s] Plan — %d section(s) en échec, reprise dans %.0f s : %s",
                           demande.copy_id, len(echecs), PAUSE_AVANT_REPRISE, ", ".join(map(str, echecs)))
            time.sleep(PAUSE_AVANT_REPRISE)
            nouveaux, echecs = _rediger_toutes(
                pool, client, demande, [s for s in demande.sections if s.ordre in echecs])
            contenus.update(nouveaux)

        acquis = list(acquis_deja or [])
        if acquis_futur is not None:
            try:
                reponse = acquis_futur.result()
                if reponse.success and reponse.data is not None:
                    acquis = reponse.data.acquis
                else:
                    logger.warning("[%s] Plan — acquis non rédigés : %s", demande.copy_id, reponse.error)
            except Exception as exc:  # noqa: BLE001 — l'encadré est facultatif
                logger.warning("[%s] Plan — acquis non rédigés : %s", demande.copy_id, exc)

    if echecs:
        raise PlanIncomplet("; ".join(echecs.values()), contenus=contenus, acquis=acquis)

    return PlanRemediation(
        copy_id=demande.copy_id,
        eleve_nom=demande.eleve_nom,
        prenom=demande.prenom,
        classe=demande.classe,
        test_libelle=demande.test_libelle,
        date=demande.date,
        acquis=acquis,
        competences=[_assembler(s, contenus[s.ordre]) for s in demande.sections],
    )
