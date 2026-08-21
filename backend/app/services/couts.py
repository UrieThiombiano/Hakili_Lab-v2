"""Port fidèle de `referentiel/couts.py` (Django) — même formule, mêmes
bornes, même arrondi. Voir le fichier d'origine pour la justification complète
de chaque choix (décision du 2026-08-01 sur l'arrondi, D-CEO-29 sur le volume
de repli lycée) ; ce module ne répète que ce que le code doit faire, pas
pourquoi.

    coût = volume horaire × coefficient du type d'erreur
    arrondi à l'heure entière supérieure, plancher 1 h, plafond 4 h
    (un coefficient nul — ATT — donne 0, hors bornes, délibérément)
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from sqlalchemy.orm import Session as SQLASession

from app.models import CoutRemediation

#: Volume horaire de repli, en heures — médiane des volumes réels du collège.
VOLUME_REPLI_LYCEE = Decimal("4")

#: Bornes du protocole (§4).
COUT_PLANCHER = Decimal("1")
COUT_PLAFOND = Decimal("4")


def arrondir_heures(valeur: Decimal) -> Decimal:
    """Ramène un coût à l'heure entière supérieure, dans les bornes du
    protocole. Un coût nul (ATT) reste nul — hors bornes, délibérément."""
    valeur = Decimal(valeur)
    if valeur <= 0:
        return Decimal("0")
    entier = valeur.to_integral_value(rounding=ROUND_CEILING)
    return max(COUT_PLANCHER, min(COUT_PLAFOND, entier))


def cout_remediation(volume_horaire: Decimal, coefficient: Decimal) -> Decimal:
    """Coût d'un problème, arrondi et borné. Coefficient nul (ATT) → 0, seul
    cas délibérément hors de [plancher, plafond]."""
    if coefficient <= 0:
        return Decimal("0")
    return arrondir_heures(Decimal(volume_horaire) * Decimal(coefficient))


def cout_precalcule(db: SQLASession, code_competence: str, code_type_erreur: str) -> Decimal:
    """Coût d'un couple compétence × type d'erreur, lu dans `CoutRemediation`.

    Une ligne absente n'est pas une anomalie (`ATT` n'en a aucune par
    construction) : renvoie 0 plutôt que de lever, comme côté Django.
    """
    ligne = (
        db.query(CoutRemediation)
        .filter(
            CoutRemediation.competence_id == code_competence,
            CoutRemediation.type_erreur_id == code_type_erreur,
        )
        .first()
    )
    return Decimal(ligne.cout_heures) if ligne else Decimal("0")
