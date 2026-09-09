"""Point d'injection module 5 dans `app/services/taches.py` — la décision de
générer (ou non) le sujet de confirmation T1 au retour d'une copie T0.

Régression corrigée : réanalyser la copie d'un élève qui a déjà une session
ouverte ne crée aucune hypothèse neuve (`ecriture.crees` vide, tout est « déjà
suivi ») et le sujet T1 n'était alors jamais généré, même quand aucun n'existait.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Correction, Evaluation, Session
from app.services import diagnostic_suivi as diag_suivi
from app.services.diagnostic_suivi import ResultatEcriture


@pytest.fixture()
def _module4_mocke(monkeypatch):
    """Neutralise tout ce qui précède la décision de génération : diagnostic
    contraint, écriture des hypothèses (toujours « rien de neuf »), client IA.
    Reste seul testé : `_ecrire_hypotheses_module4` appelle-t-il
    `_generer_sujet_confirmation` ?"""
    from app.services import taches

    monkeypatch.setattr(taches.diag_ref, "reponses_depuis_correction", lambda *a, **k: {})
    monkeypatch.setattr(taches.diag_ref, "diagnostiquer", lambda *a, **k: object())
    monkeypatch.setattr(taches.diag_suivi, "enregistrer", lambda *a, **k: ResultatEcriture())
    monkeypatch.setattr(taches, "_client_diagnostic_module4", lambda: None)

    appels: list = []
    monkeypatch.setattr(taches, "_generer_sujet_confirmation", lambda db, corr, ev: appels.append(ev))
    return appels


def _resultat_correction():
    class _R:
        grade = object()
        rubric = object()
        errors: list = []
    return _R()


def _correction(db, *, identifiant="eleve-x") -> Correction:
    correction = Correction(
        copy_id="copie-test-1",
        identifiant_hakili=identifiant,
        bareme_id="socle_6eme",
        type_evaluation="T0",
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


def test_session_a_un_sujet_t1(db):
    from app.services.taches import _session_a_un_sujet_t1

    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    db.refresh(session)

    assert _session_a_un_sujet_t1(db, session.id) is False

    db.add(Evaluation(session_id=session.id, type="T0", numero=1, sujet_confirmation=[{"numero": 1}]))
    db.commit()
    assert _session_a_un_sujet_t1(db, session.id) is True


def test_genere_le_sujet_t1_meme_sans_hypothese_neuve(db, _module4_mocke):
    """`ecriture.crees` vide + aucun sujet existant → on génère quand même."""
    from app.services import taches

    correction = _correction(db)
    taches._ecrire_hypotheses_module4(db, correction, _resultat_correction())

    assert len(_module4_mocke) == 1


def test_ne_regenere_pas_si_un_sujet_t1_existe_deja(db, _module4_mocke):
    """`ecriture.crees` vide + un T0 de la session porte déjà un sujet → on
    n'appelle pas le modèle une seconde fois."""
    from app.services import taches

    session = Session(identifiant_hakili="eleve-x")
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(Evaluation(session_id=session.id, type="T0", numero=1, sujet_confirmation=[{"numero": 1}]))
    db.commit()

    correction = _correction(db)
    taches._ecrire_hypotheses_module4(db, correction, _resultat_correction())

    assert _module4_mocke == []
