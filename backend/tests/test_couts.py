"""Formule de coût — port de `referentiel/couts.py` (voir `app/services/couts.py`)."""
from __future__ import annotations

from decimal import Decimal

from app.services import couts


def test_arrondir_heures_toujours_vers_le_haut():
    assert couts.arrondir_heures(Decimal("1.1")) == Decimal("2")
    assert couts.arrondir_heures(Decimal("1.9")) == Decimal("2")


def test_arrondir_heures_plancher_1h():
    assert couts.arrondir_heures(Decimal("0.3")) == Decimal("1")


def test_arrondir_heures_plafond_4h():
    assert couts.arrondir_heures(Decimal("10")) == Decimal("4")


def test_arrondir_heures_zero_reste_zero():
    assert couts.arrondir_heures(Decimal("0")) == Decimal("0")
    assert couts.arrondir_heures(Decimal("-1")) == Decimal("0")


def test_cout_remediation_coefficient_nul_att():
    # ATT : coefficient 0 -> 0, jamais le plancher de 1h.
    assert couts.cout_remediation(Decimal("4"), Decimal("0")) == Decimal("0")


def test_cout_remediation_volume_repli_lycee():
    # 4h (repli lycée) x 0.35 (PRQ, exemple du protocole) = 1.4h -> 2h
    assert couts.cout_remediation(couts.VOLUME_REPLI_LYCEE, Decimal("0.35")) == Decimal("2")


def test_cout_precalcule_ligne_absente_rend_zero(db, referentiel_minimal):
    # ATT n'a par construction aucune ligne dans CoutRemediation.
    assert couts.cout_precalcule(db, "B", "ATT") == Decimal("0")


def test_cout_precalcule_ligne_presente(db, referentiel_minimal):
    assert couts.cout_precalcule(db, "B", "CPT") == Decimal("4")
