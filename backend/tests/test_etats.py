"""Machine à états `Probleme.changer_etat()` — port de
`suivi/models.py::Probleme.TRANSITIONS_PERMISES` (voir `app/services/etats.py`).
"""
from __future__ import annotations

import pytest

from app.services import etats
from tests.conftest import creer_probleme


def test_transition_permise_ecrit_etat_et_transition(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT")
    t = etats.changer_etat(db, p, "confirme")
    assert p.etat == "confirme"
    assert t.etat_avant == "hypothese"
    assert t.etat_apres == "confirme"


def test_transition_non_permise_refusee(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT")
    with pytest.raises(etats.ErreurTransition):
        etats.changer_etat(db, p, "resolu")  # hypothese -> resolu n'existe pas
    assert p.etat == "hypothese"


def test_meme_etat_refuse(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT")
    with pytest.raises(etats.ErreurTransition):
        etats.changer_etat(db, p, "hypothese")


def test_etat_terminal_ecarte_ne_transite_plus(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT")
    etats.changer_etat(db, p, "ecarte")
    with pytest.raises(etats.ErreurTransition):
        etats.changer_etat(db, p, "confirme")


def test_cycle_complet_hypothese_a_clos(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT")
    for etat in ["confirme", "en_remediation", "resolu", "clos"]:
        etats.changer_etat(db, p, etat)
    assert p.etat == "clos"
    assert len(p.transitions) == 4


def test_att_ne_peut_etre_que_hypothese_ou_ecarte(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="ATT")
    with pytest.raises(etats.ErreurTransition):
        etats.changer_etat(db, p, "confirme")


def test_att_peut_etre_ecarte(db, session_suivi):
    p = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="ATT")
    t = etats.changer_etat(db, p, "ecarte")
    assert t.etat_apres == "ecarte"
