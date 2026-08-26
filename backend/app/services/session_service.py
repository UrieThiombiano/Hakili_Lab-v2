"""Port de `Session.calculer_palier()`, `etablir_le_plan()`, `inscrire()`,
`cloturer()`, `abandonner()` (`suivi/models.py`, Django) — le cycle de décision
d'un parcours élève. Voir le fichier d'origine pour la justification de chaque
règle (protocole-v2.md §7 pour le palier, D-CEO-34 pour les 7 états de
session) ; ce module reproduit le comportement, pas l'exposé.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session as SQLASession

from app.models import ETATS_SESSION_TERMINES, Probleme, Session
from app.services import etats


class ErreurSession(ValueError):
    """Décision refusée sur une session — équivalent du `ValidationError`
    Django ici (palier C non motivé, session déjà terminée, etc.)."""


def _refuser_si_corpus(session: Session) -> None:
    """Une session de corpus n'est le parcours de personne (module 3) : ni
    plan ni inscription ne peuvent en sortir."""
    if session.corpus_reference:
        raise ErreurSession(
            "Cette session appartient au corpus de référence (module 3) : "
            "elle sert à mesurer le diagnostic, pas à accompagner un élève. "
            "Ni plan ni inscription ne peuvent en sortir."
        )


def cout_total_confirme(db: SQLASession, session: Session) -> Decimal:
    """Somme des coûts des problèmes confirmés — base du choix de palier."""
    total = (
        db.query(func.sum(Probleme.cout_estime))
        .filter(Probleme.session_id == session.id, Probleme.etat == "confirme")
        .scalar()
    )
    return Decimal(total) if total is not None else Decimal("0")


def cout_total_hypothese(db: SQLASession, session: Session) -> Decimal:
    """Somme des coûts des lacunes encore à l'état d'hypothèse (avant T1)."""
    total = (
        db.query(func.sum(Probleme.cout_estime))
        .filter(Probleme.session_id == session.id, Probleme.etat == "hypothese")
        .scalar()
    )
    return Decimal(total) if total is not None else Decimal("0")


def _seuil_palier(total: Decimal) -> str:
    """Seuils de palier (protocole §7), en fonction pure — réutilisée par
    `calculer_palier` (coût confirmé) et par `plan.py::construire()` (coût
    des étapes réellement listées, y compris pour le plan provisoire basé
    sur des hypothèses)."""
    if total < 8:
        return "A"
    if total <= 20:
        return "B"
    return "C"


def calculer_palier(db: SQLASession, session: Session) -> str:
    """Palier d'après le coût total des problèmes confirmés (protocole §7)."""
    return _seuil_palier(cout_total_confirme(db, session))


def etablir_le_plan(db: SQLASession, session: Session) -> Session:
    """Après T1 : fige le palier et oriente la session.

    Trois issues distinctes : aucun problème confirmé → sortie sans
    remédiation (bon résultat) ; palier C → hors dispositif ; sinon → en
    attente de la décision d'inscription.
    """
    _refuser_si_corpus(session)
    confirmes = (
        db.query(Probleme)
        .filter(Probleme.session_id == session.id, Probleme.etat == "confirme")
        .count()
    )
    if not confirmes:
        session.palier = ""
        session.etat = "sans_suite"
        session.date_cloture = date.today()
        db.add(session)
        db.flush()
        return session

    session.palier = calculer_palier(db, session)
    if session.palier == "C":
        session.etat = "hors_dispositif"
        session.date_cloture = date.today()
    else:
        session.etat = "attente_inscription"
    db.add(session)
    db.flush()
    return session


def inscrire(db: SQLASession, session: Session, *, forcer: bool = False, motif: str = "") -> Session:
    """Inscrit l'élève au programme — la décision humaine du cycle. Bascule
    tous les problèmes confirmés en remédiation, chacun via `etats.changer_etat`
    (donc chacun avec sa `Transition`).

    Refuse le palier C sans décision explicite et motivée — proposer un
    parcours court à plus de 20h de lacunes garantit un échec visible, qui
    coûte plus cher au centre qu'un refus argumenté.
    """
    _refuser_si_corpus(session)
    if session.etat == "remediation":
        raise ErreurSession("Cet élève est déjà inscrit au programme.")

    # `hors_dispositif` est terminal, mais c'est justement l'état où une
    # dérogation se demande : on le laisse passer jusqu'au garde-fou du
    # palier C, dont le message explique quoi faire.
    if session.etat in ETATS_SESSION_TERMINES and session.etat != "hors_dispositif":
        raise ErreurSession(f"Session « {session.etat} » : elle ne peut plus recevoir d'inscription.")

    confirmes = (
        db.query(Probleme)
        .filter(Probleme.session_id == session.id, Probleme.etat == "confirme")
        .all()
    )
    if not confirmes:
        raise ErreurSession(
            "Aucun problème confirmé : il n'y a rien à remédier. Le test de "
            "confirmation doit avoir eu lieu avant l'inscription."
        )

    palier = session.palier or calculer_palier(db, session)
    if palier == "C" and not forcer:
        total = cout_total_confirme(db, session)
        raise ErreurSession(
            f"Palier C — {total:g} h de remédiation estimées. Cet élève ne "
            "relève pas d'une remédiation courte, mais d'un accompagnement "
            "régulier. Inscrire malgré tout demande une décision explicite "
            "et un motif."
        )
    if forcer and not motif.strip():
        raise ErreurSession("Passer outre demande un motif : il sera conservé dans l'historique.")

    session.palier = palier
    session.etat = "remediation"
    session.date_inscription = date.today()
    # La session repart : une date de clôture posée par l'orientation hors
    # dispositif n'a plus lieu d'être, et la contrainte l'interdit.
    session.date_cloture = None
    db.add(session)
    db.flush()

    commentaire = f"Inscription au programme (palier {palier})"
    if forcer:
        commentaire += f" — passage outre : {motif.strip()}"
    for probleme in confirmes:
        etats.changer_etat(db, probleme, "en_remediation", commentaire=commentaire)

    return session


def cloturer(db: SQLASession, session: Session) -> Session:
    """Ferme le cycle après T5."""
    if session.etat in ETATS_SESSION_TERMINES:
        raise ErreurSession("Cette session est déjà terminée.")
    session.etat = "close"
    session.date_cloture = date.today()
    db.add(session)
    db.flush()
    return session


def abandonner(db: SQLASession, session: Session, motif: str = "") -> Session:
    if session.etat in ETATS_SESSION_TERMINES:
        raise ErreurSession("Cette session est déjà terminée.")
    session.etat = "abandonnee"
    session.date_cloture = date.today()
    db.add(session)
    db.flush()
    return session
