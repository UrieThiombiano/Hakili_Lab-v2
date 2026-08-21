"""Port de l'écriture en base des problèmes du module 4 et de la
confirmation automatique T1 (module 5) — voir
`app/services/diagnostic_suivi.py`, port de `suivi/diagnostic.py`.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Probleme, Session
from app.services import diagnostic_suivi as diag_suivi
from src.models.domain import CopyGrade, DiagnosticContraint, ProblemeDetecte, QuestionGrade, SourceProbleme


def test_resoudre_ou_creer_session_cree_si_aucune_ouverte(db, referentiel_minimal):
    session = diag_suivi.resoudre_ou_creer_session(db, "eleve-x")
    assert session.identifiant_hakili == "eleve-x"
    assert session.id is not None


def test_resoudre_ou_creer_session_reutilise_la_session_ouverte(db, referentiel_minimal):
    s1 = diag_suivi.resoudre_ou_creer_session(db, "eleve-x")
    s2 = diag_suivi.resoudre_ou_creer_session(db, "eleve-x")
    assert s1.id == s2.id


def test_resoudre_ou_creer_session_ignore_le_corpus(db, referentiel_minimal):
    corpus = Session(identifiant_hakili="eleve-x", corpus_reference=True)
    db.add(corpus)
    db.commit()
    session = diag_suivi.resoudre_ou_creer_session(db, "eleve-x")
    assert session.id != corpus.id
    assert session.corpus_reference is False


def test_preparer_evaluation_attribue_le_rang(db, referentiel_minimal):
    e1 = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T3", copy_id="c1")
    e2 = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T3", copy_id="c2")
    assert e1.numero == 1
    assert e2.numero == 2
    assert e1.session_id == e2.session_id


def test_enregistrer_ecrit_en_hypothese(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T0", copy_id="c1")
    diagnostic = DiagnosticContraint(
        copy_id="c1", niveau_test="6eme",
        problemes=[ProblemeDetecte(code_question="Q1", code_competence="B", code_type_erreur="CPT", citation="a^2+b^2", source=SourceProbleme.qcm)],
    )
    resultat = diag_suivi.enregistrer(db, evaluation, diagnostic)
    assert len(resultat.crees) == 1
    assert resultat.crees[0].etat == "hypothese"
    assert resultat.crees[0].cout_estime == 4  # CoutRemediation(B, CPT) = 4 dans la fixture
    assert resultat.deja_suivis == []


def test_enregistrer_fusionne_deux_citations_du_meme_couple(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T0", copy_id="c1")
    diagnostic = DiagnosticContraint(
        copy_id="c1", niveau_test="6eme",
        problemes=[
            ProblemeDetecte(code_question="Q1", code_competence="B", code_type_erreur="CPT", citation="premiere citation", source=SourceProbleme.qcm),
            ProblemeDetecte(code_question="Q2", code_competence="B", code_type_erreur="CPT", citation="deuxieme citation", source=SourceProbleme.modele),
        ],
    )
    resultat = diag_suivi.enregistrer(db, evaluation, diagnostic)
    assert len(resultat.crees) == 1  # un seul Probleme, deux citations fusionnées
    assert "premiere citation" in resultat.crees[0].justification
    assert "deuxieme citation" in resultat.crees[0].justification


def test_enregistrer_signale_les_couples_deja_suivis(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T0", copy_id="c1")
    db.add(Probleme(session_id=evaluation.session_id, competence_id="B", type_erreur_id="CPT", etat="hypothese"))
    db.commit()

    diagnostic = DiagnosticContraint(copy_id="c1", niveau_test="6eme", problemes=[ProblemeDetecte(code_question="Q1", code_competence="B", code_type_erreur="CPT", citation="x", source=SourceProbleme.qcm)])
    resultat = diag_suivi.enregistrer(db, evaluation, diagnostic)
    assert resultat.crees == []
    assert len(resultat.deja_suivis) == 1


def test_enregistrer_refuse_une_evaluation_du_corpus(db, referentiel_minimal):
    from app.models import Evaluation

    session = Session(identifiant_hakili="eleve-x", corpus_reference=True)
    db.add(session)
    db.commit()
    evaluation = Evaluation(session_id=session.id, type="T0", corpus_reference=True, tague_par="x", date_tagage=date(2026, 1, 1))
    db.add(evaluation)
    db.commit()

    diagnostic = DiagnosticContraint(copy_id="c1", niveau_test="6eme", problemes=[])
    with pytest.raises(diag_suivi.ErreurDiagnostic):
        diag_suivi.enregistrer(db, evaluation, diagnostic)


def _grade(reussi_1: bool, reussi_2: bool) -> CopyGrade:
    return CopyGrade(
        copy_id="c1", total_score=0, total_possible=2,
        questions=[
            QuestionGrade(rubric_item_id="1", score=1.0 if reussi_1 else 0.0, confidence=0.9, comment="", observed_answer="x", requires_review=False),
            QuestionGrade(rubric_item_id="2", score=1.0 if reussi_2 else 0.0, confidence=0.9, comment="", observed_answer="y", requires_review=False),
        ],
    )


def test_confirmer_depuis_correction_confirme_si_une_question_ratee(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T1", copy_id="c1")
    probleme = Probleme(session_id=evaluation.session_id, competence_id="B", type_erreur_id="CPT", etat="hypothese", exercices_confirmation=[1, 2])
    db.add(probleme)
    db.commit()

    resultat = diag_suivi.confirmer_depuis_correction(db, evaluation, _grade(reussi_1=True, reussi_2=False))
    assert len(resultat.confirmes) == 1
    db.refresh(probleme)
    assert probleme.etat == "confirme"


def test_confirmer_depuis_correction_ecarte_si_tout_reussi(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T1", copy_id="c1")
    probleme = Probleme(session_id=evaluation.session_id, competence_id="B", type_erreur_id="CPT", etat="hypothese", exercices_confirmation=[1, 2])
    db.add(probleme)
    db.commit()

    resultat = diag_suivi.confirmer_depuis_correction(db, evaluation, _grade(reussi_1=True, reussi_2=True))
    assert len(resultat.ecartes) == 1
    db.refresh(probleme)
    assert probleme.etat == "ecarte"


def test_confirmer_depuis_correction_att_toujours_ecarte(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T1", copy_id="c1")
    probleme = Probleme(session_id=evaluation.session_id, competence_id="B", type_erreur_id="ATT", etat="hypothese", exercices_confirmation=[1])
    db.add(probleme)
    db.commit()

    resultat = diag_suivi.confirmer_depuis_correction(db, evaluation, _grade(reussi_1=False, reussi_2=False))
    assert len(resultat.ecartes) == 1
    assert resultat.confirmes == []


def test_confirmer_depuis_correction_ignore_hypotheses_sans_exercices(db, referentiel_minimal):
    evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili="eleve-x", type_evaluation="T1", copy_id="c1")
    probleme = Probleme(session_id=evaluation.session_id, competence_id="B", type_erreur_id="CPT", etat="hypothese", exercices_confirmation=[])
    db.add(probleme)
    db.commit()

    resultat = diag_suivi.confirmer_depuis_correction(db, evaluation, _grade(reussi_1=False, reussi_2=False))
    assert resultat.confirmes == []
    assert resultat.ecartes == []
    db.refresh(probleme)
    assert probleme.etat == "hypothese"
