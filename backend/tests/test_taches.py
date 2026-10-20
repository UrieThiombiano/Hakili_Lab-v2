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
from app.services import taches
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


def test_libelles_questions_du_test_t0():
    """Le générateur T1 reçoit l'énoncé de la question ratée, pas seulement
    l'intitulé de compétence (G6 = volume de pyramide, recette du 2026-10-17)."""
    libelles = taches._libelles_questions("socle_3eme")
    assert "N1" in libelles and "-20/4" in libelles["N1"]
    assert taches._libelles_questions("") == {}
    assert taches._libelles_questions("test_inexistant") == {}


# ── Note T0 < 10/20 : pas de sujet T1 (D-CEO-46) ─────────────────────────────


def _resultat_note(note: float):
    class _Grade:
        final_score_on_20 = note

    class _R:
        grade = _Grade()
        rubric = object()
        errors: list = []
    return _R()


def test_sous_10_pas_de_sujet_t1_mais_confirmation_d_office(db, _module4_mocke, monkeypatch):
    from app.services import taches

    confirmations: list = []
    monkeypatch.setattr(
        taches.diag_suivi, "confirmer_sans_t1",
        lambda db, ev, note: confirmations.append(note) or diag_suivi.ResultatConfirmation(),
    )

    taches._ecrire_hypotheses_module4(db, _correction(db), _resultat_note(9.5))

    assert _module4_mocke == []
    assert confirmations == [9.5]


def test_a_10_et_plus_le_sujet_t1_est_genere(db, _module4_mocke, monkeypatch):
    from app.services import taches

    monkeypatch.setattr(taches.diag_suivi, "confirmer_sans_t1", lambda *a: pytest.fail("pas de confirmation d'office à 10/20"))

    taches._ecrire_hypotheses_module4(db, _correction(db), _resultat_note(10.0))

    assert len(_module4_mocke) == 1
