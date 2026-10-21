"""Module 7 — la fiche de travail : une séance prête à l'emploi pour le
tuteur, pour UN problème (compétence × type d'erreur) réellement confirmé.

À ne pas confondre avec `app/services/plan.py` (module 6) : le plan dit
*quoi* travailler et dans quel ordre pour une session donnée ; la fiche dit
*comment* travailler un problème donné — méthode, exemple résolu, exercices
gradués, critère de réussite. `src/pipeline/pdf_plan_html.py` s'appelait
jusqu'ici « la fiche de remédiation (module 7) » alors qu'il ne produit que
le plan chiffré : la confusion vient d'un nom, pas d'un doublon fonctionnel
(voir D-CEO-43, `docs/decision_register.md`).

Contrairement au plan (recalculé à chaque demande) et aux sujets T1/T3/T4/T5
(un LLM les rédige et cache la correction), la fiche de travail :
- est cataloguée par couple **compétence × type d'erreur × niveau**, pas par
  élève ni par session — deux élèves avec le même problème reçoivent la même
  fiche (guide-v2.md, module 7 : « le catalogue ») ;
- n'appelle jamais de modèle : méthode, exemple travaillé et exercices
  viennent tous de `remediation/` via `RemediationRetriever` (D-CEO-41),
  jamais inventés ;
- montre la correction des exercices en clair — ce document est lu par un
  tuteur, jamais transmis à un élève tel quel, à la différence des sujets
  T1/T3/T4/T5.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session as SQLASession

from app.models import Competence, FicheRemediation, Prerequis, Probleme, TypeErreur

#: Répartition des exercices gradués par étoile — 2 faciles, 2 moyens, 1
#: difficile : de quoi vérifier l'acquisition puis pousser un peu, sans
#: transformer la fiche en série d'exercices qu'un tuteur n'aura pas le temps
#: de dérouler en séance.
REPARTITION_EXERCICES: dict[int, int] = {1: 2, 2: 2, 3: 1}

#: Déroulé minuté par défaut, en minutes — une séance de remédiation type
#: pour un seul problème (guide-v2.md, module 7 : « un déroulé minuté »).
DEROULE_MINUTES: dict[str, int] = {
    "verification_prerequis": 5,
    "rappel_methode": 10,
    "exemple_commente": 10,
    "exercices_gradues": 25,
    "bilan": 5,
}


class ErreurFicheIndisponible(Exception):
    """Aucune matière de remédiation pour ce couple compétence × niveau —
    le rapprochement `remediation/` (D-CEO-41) ne le couvre pas encore.
    Refuser plutôt que produire une fiche creuse : même principe que le
    palier C, « le dire clairement plutôt que vendre un plan voué à
    l'échec »."""


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prerequis_a_verifier(db: SQLASession, competence_id: str) -> list[Competence]:
    """Prérequis directs de la compétence, à vérifier en ouverture de séance
    — tous les prérequis déclarés, pas seulement ceux également en
    difficulté (différence avec `plan.py::EtapePlan.prerequis_aussi_en_difficulte`,
    qui ordonne le plan plutôt que préparer une séance)."""
    liens = db.query(Prerequis).filter(Prerequis.competence_id == competence_id).all()
    return [lien.prerequis for lien in liens]


def _critere_reussite(nb_exercices: int) -> str:
    if nb_exercices == 0:
        return "L'élève explique la méthode avec ses mots et refait l'exemple travaillé sans aide."
    seuil = max(nb_exercices - 1, 1)
    pluriel = "s" if seuil > 1 else ""
    return (
        f"L'élève résout seul, sans consulter la correction, au moins "
        f"{seuil} exercice{pluriel} sur {nb_exercices} parmi ceux ci-dessus."
    )


def construire_contenu(db: SQLASession, competence: Competence, type_erreur: TypeErreur, niveau: str) -> dict:
    """Assemble le contenu structuré d'une fiche pour ce couple. Ne persiste
    rien — `obtenir_ou_generer()` décide si le résultat doit être catalogué.

    `contenu["matiere_disponible"]` est `False` quand `RemediationRetriever`
    ne couvre pas ce couple : le contenu est alors incomplet à dessein, et
    l'appelant doit refuser de le cataloguer (voir `ErreurFicheIndisponible`)."""
    from src.knowledge.remediation_retriever import get_remediation_retriever

    chunk = get_remediation_retriever().get_by_competence(competence.code, niveau)
    exercices = chunk.exercices_gradues(REPARTITION_EXERCICES) if chunk else []

    return {
        "objectif": (
            f"Être capable de : {competence.libelle} — sans retomber dans "
            f"l'erreur « {type_erreur.libelle} »."
        ),
        "competence_code": competence.code,
        "competence_libelle": competence.libelle,
        "type_erreur_code": type_erreur.code,
        "type_erreur_libelle": type_erreur.libelle,
        "niveau": niveau,
        "prerequis_a_verifier": [
            {"code": c.code, "libelle": c.libelle} for c in _prerequis_a_verifier(db, competence.code)
        ],
        "methode": chunk.methode if chunk else None,
        "retenir": chunk.retenir if chunk else [],
        "exemple_resolu": chunk.exemple_resolu if chunk else None,
        "erreurs_frequentes": chunk.erreurs_frequentes if chunk else [],
        "declic": chunk.declic if chunk else None,
        "deroule_minutes": DEROULE_MINUTES,
        "exercices": exercices,
        "critere_reussite": _critere_reussite(len(exercices)),
        "matiere_disponible": chunk is not None,
    }


def obtenir_ou_generer(db: SQLASession, probleme: Probleme) -> FicheRemediation:
    """Rend la fiche cataloguée pour ce problème, la crée si elle n'existe
    pas encore. Lève `ErreurFicheIndisponible` si `remediation/` ne couvre
    pas ce couple à ce niveau.

    Ne régénère **jamais** une fiche déjà cataloguée, y compris `generee` :
    la matière de remédiation peut évoluer (nouveaux modules rapprochés),
    mais une session en cours doit toujours voir la même fiche que celle
    distribuée au tuteur — pas une version qui change sous ses pieds.
    `corriger()` est le seul chemin qui écrase, et seulement vers `corrigee`.
    """
    niveau = probleme.competence.niveau_intro
    fiche = (
        db.query(FicheRemediation)
        .filter(
            FicheRemediation.competence_id == probleme.competence_id,
            FicheRemediation.type_erreur_id == probleme.type_erreur_id,
            FicheRemediation.niveau == niveau,
        )
        .first()
    )
    if fiche is not None:
        return fiche

    contenu = construire_contenu(db, probleme.competence, probleme.type_erreur, niveau)
    if not contenu["matiere_disponible"]:
        raise ErreurFicheIndisponible(
            f"Aucune matière de remédiation pour {probleme.competence_id} "
            f"({niveau}) — le rapprochement remediation/ ne la couvre pas encore."
        )

    fiche = FicheRemediation(
        competence_id=probleme.competence_id,
        type_erreur_id=probleme.type_erreur_id,
        niveau=niveau,
        contenu=contenu,
        version="generee",
    )
    db.add(fiche)
    db.commit()
    db.refresh(fiche)
    return fiche


def corriger(db: SQLASession, fiche: FicheRemediation, contenu: dict, tuteur: str) -> FicheRemediation:
    """La version corrigée par le tuteur remplace la version générée dans le
    catalogue (guide-v2.md, module 7). Pas d'historique conservé : un seul
    contenu fait foi à la fois, comme `Probleme` ne garde pas ses anciens
    états ailleurs que dans `Transition`."""
    fiche.contenu = contenu
    fiche.version = "corrigee"
    fiche.corrigee_par = tuteur
    fiche.date_correction = _utcnow_naive()
    db.commit()
    db.refresh(fiche)
    return fiche
