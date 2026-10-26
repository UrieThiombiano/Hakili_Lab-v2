"""Port de la machine à états `Probleme.changer_etat()` et de l'immutabilité
de `Transition` (`suivi/models.py`, Django).

Rien de tout ça n'est un `CHECK` Postgres côté Django — c'est de la logique
applicative pure (une `dict[str, set[str]]` et une garde sur `save()`). Le
portage est donc mécanique : mêmes règles, même refus, mais en fonctions de
service plutôt qu'en méthodes de modèle, puisque SQLAlchemy (contrairement à
l'ORM actif de Django) sépare délibérément les données du comportement.

**Invariant à ne jamais contourner** : une `Transition` ne s'obtient que par
`changer_etat()`, jamais par un `db.add(Transition(...))` direct ailleurs dans
le code — sans quoi l'historique qui alimente les indicateurs du module 9
devient trouable sans que rien ne le signale.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import Evaluation, Probleme, Transition


def _maintenant() -> datetime:
    """UTC naïf — cohérent avec les colonnes `DateTime` (naïves) du schéma."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ErreurTransition(ValueError):
    """Enchaînement d'état refusé, ou tentative de modifier une transition
    existante — équivalent du `ValidationError` Django ici."""


#: Enchaînements permis. Un problème écarté ou clos est terminal.
#: Copie exacte de `Probleme.TRANSITIONS_PERMISES` (suivi/models.py) — ne pas
#: la faire diverger sans faire diverger l'original, les deux codent la même
#: politique métier tant que la bascule (Phase 4) n'a pas eu lieu.
TRANSITIONS_PERMISES: dict[str, set[str]] = {
    "hypothese": {"confirme", "ecarte"},
    "confirme": {"en_remediation"},
    "en_remediation": {"resolu", "non_resolu"},
    "resolu": {"regresse", "clos"},
    "non_resolu": {"en_remediation"},
    "regresse": {"en_remediation"},
    "ecarte": set(),
    "clos": set(),
}

#: `ATT` (inattention) ne donne jamais lieu à remédiation : seuls ces deux
#: états lui sont permis (`Probleme.clean()` côté Django).
ETATS_ATT_PERMIS = {"hypothese", "ecarte"}


def _valider_att(probleme: Probleme, nouvel_etat: str) -> None:
    if probleme.type_erreur_id == "ATT" and nouvel_etat not in ETATS_ATT_PERMIS:
        raise ErreurTransition(
            "Un problème de type ATT (inattention) ne peut être qu'en "
            "hypothèse ou écarté : il ne donne jamais lieu à remédiation."
        )


def changer_etat(
    db,
    probleme: Probleme,
    nouvel_etat: str,
    *,
    evaluation: Evaluation | None = None,
    commentaire: str = "",
) -> Transition:
    """Change l'état d'un problème et journalise la transition — les deux ou
    aucun (la session SQLAlchemy appelante gère la transaction ; ne pas
    committer ici, comme `@transaction.atomic` laissait Django gérer la
    portée exacte de l'atomicité côté appelant).

    Refuse un enchaînement non prévu par `TRANSITIONS_PERMISES` plutôt que de
    laisser l'historique devenir incohérent — c'est le seul point d'entrée
    autorisé pour modifier `Probleme.etat`.
    """
    ancien = probleme.etat
    if nouvel_etat == ancien:
        raise ErreurTransition(f"Le problème est déjà en état « {ancien} ».")

    permis = TRANSITIONS_PERMISES.get(ancien, set())
    if nouvel_etat not in permis:
        attendu = ", ".join(sorted(permis)) or "aucun (état terminal)"
        raise ErreurTransition(
            f"Transition « {ancien} » → « {nouvel_etat} » non permise. "
            f"États atteignables : {attendu}."
        )

    _valider_att(probleme, nouvel_etat)

    probleme.etat = nouvel_etat
    transition = Transition(
        probleme_id=probleme.id,
        etat_avant=ancien,
        etat_apres=nouvel_etat,
        date=_maintenant(),
        evaluation_id=evaluation.id if evaluation else None,
        commentaire=commentaire,
    )
    db.add(probleme)
    db.add(transition)
    db.flush()
    return transition
