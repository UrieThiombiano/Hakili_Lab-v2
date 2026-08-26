"""Rapport diagnostique des lacunes (module 9) — voir
`app/services/diagnostic_rapport.py`. À la différence du plan (module 6),
n'exclut aucun état : une session vide ou entièrement résolue a quand même
un rapport valide à produire."""
from __future__ import annotations

from decimal import Decimal

from app.services import diagnostic_rapport
from tests.conftest import creer_probleme


def test_construire_groupe_par_etat(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="hypothese", cout="4")
    creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT", etat="confirme", cout="4")

    rapport = diagnostic_rapport.construire(db, session_suivi)

    assert rapport["nb_problemes"] == 2
    etats_presents = {g.etat for g in rapport["groupes"]}
    assert etats_presents == {"hypothese", "confirme"}
    # Ordre de restitution : confirmé avant hypothèse (voir _ORDRE_ETATS).
    assert [g.etat for g in rapport["groupes"]] == ["confirme", "hypothese"]


def test_construire_separe_cout_confirme_et_hypothese(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="hypothese", cout="3")
    creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT", etat="en_remediation", cout="5")

    rapport = diagnostic_rapport.construire(db, session_suivi)

    assert rapport["cout_hypothese"] == Decimal("3")
    assert rapport["cout_confirme"] == Decimal("5")


def test_construire_session_vide_ne_leve_pas(db, session_suivi, referentiel_minimal):
    rapport = diagnostic_rapport.construire(db, session_suivi)
    assert rapport["groupes"] == []
    assert rapport["nb_problemes"] == 0
    assert rapport["cout_confirme"] == Decimal("0")
    assert rapport["cout_hypothese"] == Decimal("0")
