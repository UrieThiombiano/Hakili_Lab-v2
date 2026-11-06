"""Cycle de décision d'une session — port de `Session.calculer_palier()`,
`etablir_le_plan()`, `inscrire()` (voir `app/services/session_service.py`)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import session_service as svc
from tests.conftest import creer_probleme


def test_seuil_palier_bornes():
    # Fonction pure extraite de `calculer_palier` — réutilisée par
    # `plan.py::construire()` pour le plan provisoire (hypothèses, pas de
    # coût confirmé à interroger).
    assert svc._seuil_palier(Decimal("7.99")) == "A"
    assert svc._seuil_palier(Decimal("8")) == "B"
    assert svc._seuil_palier(Decimal("20")) == "B"
    assert svc._seuil_palier(Decimal("20.01")) == "C"


def test_calculer_palier_borne_a(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="7.99")
    assert svc.calculer_palier(db, session_suivi) == "A"


def test_calculer_palier_borne_b_incluse(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="20")
    assert svc.calculer_palier(db, session_suivi) == "B"


def test_calculer_palier_c_au_dela_de_20(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="20.01")
    assert svc.calculer_palier(db, session_suivi) == "C"


def test_inscrire_refuse_sans_probleme_confirme(db, session_suivi, referentiel_minimal):
    with pytest.raises(svc.ErreurSession):
        svc.inscrire(db, session_suivi)


def test_inscrire_refuse_palier_c_sans_motif(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="25")
    with pytest.raises(svc.ErreurSession):
        svc.inscrire(db, session_suivi)


def test_inscrire_palier_c_avec_motif_et_forcer(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="25")
    svc.inscrire(db, session_suivi, forcer=True, motif="dérogation famille")
    assert session_suivi.etat == "remediation"
    assert session_suivi.palier == "C"


def test_inscrire_forcer_sans_motif_refuse(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="25")
    with pytest.raises(svc.ErreurSession):
        svc.inscrire(db, session_suivi, forcer=True, motif="   ")


def test_inscrire_palier_b_bascule_problemes_en_remediation(db, session_suivi, referentiel_minimal):
    p = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="10")
    svc.inscrire(db, session_suivi)
    db.refresh(p)
    assert p.etat == "en_remediation"
    assert len(p.transitions) == 1


def test_inscrire_deja_inscrit_refuse(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="10")
    svc.inscrire(db, session_suivi)
    with pytest.raises(svc.ErreurSession):
        svc.inscrire(db, session_suivi)


def test_session_corpus_refuse_inscription(db, session_suivi, referentiel_minimal):
    session_suivi.corpus_reference = True
    db.add(session_suivi)
    db.commit()
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="10")
    with pytest.raises(svc.ErreurSession):
        svc.inscrire(db, session_suivi)


def test_etablir_le_plan_sans_confirme_donne_sans_suite(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="hypothese", cout="10")
    svc.etablir_le_plan(db, session_suivi)
    assert session_suivi.etat == "sans_suite"
    assert session_suivi.date_cloture is not None


def test_etablir_le_plan_palier_c_donne_hors_dispositif(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="25")
    svc.etablir_le_plan(db, session_suivi)
    assert session_suivi.etat == "hors_dispositif"


def test_etablir_le_plan_palier_ab_donne_attente_inscription(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="5")
    svc.etablir_le_plan(db, session_suivi)
    assert session_suivi.etat == "attente_inscription"
