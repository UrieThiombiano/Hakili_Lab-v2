"""Rapport diagnostique des lacunes (module 9, restitution) — le document
imprimable qui manquait au diagnostic structuré (module 4) : celui-ci écrit
des `Probleme` en base (fiable, voir `diagnostic_referentiel.py`), mais rien
ne les mettait en forme pour un enseignant ou un parent avant ce module.

À la différence du plan (`app/services/plan.py::construire()`, module 6),
qui n'inclut QUE les problèmes confirmés/en remédiation, ce rapport montre
TOUTE la session — hypothèses non encore tranchées comprises — groupée par
état, avec l'historique daté des transitions. Pas de tri topologique par
prérequis ici : ce n'est pas un plan de travail, c'est un état des lieux.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session as SQLASession

from app.models import Probleme, Session, SignatureErreur

#: Ordre de restitution : des lacunes qui comptent le plus (déjà remédiées
#: ou en cours) vers celles qui restent à trancher, en terminant sur ce qui
#: a été écarté — un enseignant qui lit le rapport veut d'abord savoir où en
#: est l'élève, pas la liste brute des hypothèses.
_ORDRE_ETATS = ["resolu", "en_remediation", "confirme", "regresse", "non_resolu", "hypothese", "ecarte", "clos"]

_LIBELLES_ETAT = {
    "hypothese": "Lacune détectée, pas encore confirmée",
    "confirme": "Confirmée par le test T1",
    "ecarte": "Écartée par le test T1 (fausse alerte)",
    "en_remediation": "En cours de remédiation",
    "resolu": "Résolue",
    "non_resolu": "Non résolue après remédiation",
    "regresse": "Réapparue après une résolution",
    "clos": "Clôturée",
}


@dataclass
class LigneDiagnostic:
    """Une lacune, avec de quoi comprendre où elle en est."""

    probleme: Probleme
    interpretation: str
    date_detection: datetime | None
    date_dernier_changement: datetime | None

    @property
    def competence(self):
        return self.probleme.competence

    @property
    def type_erreur(self):
        return self.probleme.type_erreur


@dataclass
class GroupeEtat:
    etat: str
    libelle: str
    lignes: list[LigneDiagnostic] = field(default_factory=list)


def _interpretation(db: SQLASession, competence_id: str, type_erreur_id: str) -> str:
    """Même logique que `sessions.py::_interpretation_generale` — une seule
    signature suffit à expliquer la lacune, pas la fiche de séance complète."""
    signature = (
        db.query(SignatureErreur)
        .filter(SignatureErreur.competence_id == competence_id, SignatureErreur.type_erreur_id == type_erreur_id)
        .first()
    )
    return signature.interpretation if signature else ""


def construire(db: SQLASession, session: Session) -> dict:
    """État des lieux complet des lacunes d'une session, groupé par état.

    Contrairement à `plan.py::construire()`, ne filtre RIEN par état — un
    rapport diagnostique a du sens même pour une session où rien n'est
    encore confirmé (juste après T0), ou où tout a déjà été résolu."""
    problemes = db.query(Probleme).filter(Probleme.session_id == session.id).all()

    groupes: dict[str, GroupeEtat] = {
        etat: GroupeEtat(etat=etat, libelle=_LIBELLES_ETAT[etat]) for etat in _ORDRE_ETATS
    }

    for probleme in problemes:
        transitions = probleme.transitions  # déjà triées par date (relationship order_by)
        date_detection = transitions[0].date if transitions else None
        date_dernier_changement = transitions[-1].date if transitions else None

        ligne = LigneDiagnostic(
            probleme=probleme,
            interpretation=_interpretation(db, probleme.competence_id, probleme.type_erreur_id),
            date_detection=date_detection,
            date_dernier_changement=date_dernier_changement,
        )
        groupes.setdefault(probleme.etat, GroupeEtat(etat=probleme.etat, libelle=_LIBELLES_ETAT.get(probleme.etat, probleme.etat))).lignes.append(ligne)

    groupes_non_vides = [groupes[etat] for etat in _ORDRE_ETATS if groupes[etat].lignes]
    # Un état imprévu (pas dans _ORDRE_ETATS) ne doit pas disparaître du rapport.
    groupes_non_vides += [g for etat, g in groupes.items() if etat not in _ORDRE_ETATS and g.lignes]

    cout_confirme = sum((Decimal(p.cout_estime) for p in problemes if p.etat in ("confirme", "en_remediation")), Decimal("0"))
    cout_hypothese = sum((Decimal(p.cout_estime) for p in problemes if p.etat == "hypothese"), Decimal("0"))

    return {
        "groupes": groupes_non_vides,
        "nb_problemes": len(problemes),
        "cout_confirme": cout_confirme,
        "cout_hypothese": cout_hypothese,
    }
