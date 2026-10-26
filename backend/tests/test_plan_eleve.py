"""Squelette du plan de remédiation d'une copie (`app/services/plan_eleve.py`)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Competence, CoutRemediation, Prerequis, Question, SignatureErreur, TypeErreur
from app.services import plan_eleve
from src.models.domain import (
    CopyGrade,
    DiagnosticContraint,
    ProblemeDetecte,
    QuestionGrade,
    Rubric,
    RubricItem,
    TeacherDecision,
)


@pytest.fixture()
def referentiel(db):
    db.add_all([
        TypeErreur(code="CPT", libelle="Conceptuelle", definition="Concept mal compris", signature="", coefficient="0.7", remediable=True),
        TypeErreur(code="PRC", libelle="Procédurale", definition="", signature="", coefficient="0.5", remediable=True),
        TypeErreur(code="ATT", libelle="Inattention", definition="", signature="", coefficient="0", remediable=False),
    ])
    db.add_all([
        Competence(code="RAD", domaine="Num", libelle="Radicaux", niveau_intro="3eme", volume_horaire="4"),
        Competence(code="EQ2", domaine="Num", libelle="Second degré", niveau_intro="1ereD", volume_horaire="6"),
        Competence(code="VEC", domaine="Geo", libelle="Vecteurs", niveau_intro="2ndeC", volume_horaire="5"),
    ])
    db.flush()
    db.add(Prerequis(competence_id="EQ2", prerequis_id="RAD"))
    db.add_all([
        CoutRemediation(competence_id="RAD", type_erreur_id="CPT", cout_heures="1"),
        CoutRemediation(competence_id="EQ2", type_erreur_id="PRC", cout_heures="3"),
        # Aucun coût pour (VEC, CPT) : recalculé par la formule, 5 × 0,7 → 4 h.
    ])
    for code, comp in (("N1", "RAD"), ("L1", "EQ2"), ("L2", "EQ2"), ("G1", "VEC"), ("G2", "VEC")):
        db.add(Question(code_question=code, niveau_test="1ereD", partie="A", format="redige",
                        bareme="1", bareme_classeur="1", competence_id=comp, objet=code))
    db.flush()
    q_l1 = db.query(Question).filter_by(code_question="L1").one()
    db.add(SignatureErreur(question_id=q_l1.id, competence_id="EQ2", type_erreur_id="PRC",
                           production_eleve="Δ = b² + 4ac", interpretation="signe du discriminant"))
    db.commit()


def _copie(reussies: set[str]) -> tuple[CopyGrade, Rubric]:
    codes = ["N1", "L1", "L2", "G1", "G2"]
    rubric = Rubric(subject="mathematics", total_points=5,
                    items=[RubricItem(id=c, label=f"Question {c}") for c in codes])
    grade = CopyGrade(copy_id="c1", total_score=0, total_possible=5, questions=[
        QuestionGrade(rubric_item_id=c, score=1.0 if c in reussies else 0.0, confidence=1, comment=f"commentaire {c}",
                      observed_answer="" if c == "L2" else f"réponse {c}", correct_answer=f"attendu {c}",
                      requires_review=False)
        for c in codes
    ])
    return grade, rubric


def _probleme(question: str, competence: str, type_erreur: str) -> ProblemeDetecte:
    return ProblemeDetecte(code_question=question, code_competence=competence,
                           code_type_erreur=type_erreur, citation=f"lu sur {question}")


def _demande(db, problemes, reussies=frozenset({"G2"})):
    grade, rubric = _copie(set(reussies))
    return plan_eleve.demande_plan(
        db, copy_id="c1", nom="Nikiema", prenom="K. Amale",
        titre_test="Test diagnostique d'entrée en 1ère D", niveau_test="1ereD",
        grade=grade, rubric=rubric,
        diagnostic=DiagnosticContraint(copy_id="c1", niveau_test="1ereD", problemes=problemes),
    )


def test_ordre_prerequis_durees_et_questions(db, referentiel):
    demande = _demande(db, [
        _probleme("L1", "EQ2", "PRC"),
        _probleme("N1", "RAD", "CPT"),
        _probleme("G1", "VEC", "CPT"),
        _probleme("L2", "EQ2", "ATT"),  # non remédiable : ignoré
    ])
    # RAD avant EQ2 (prérequis) ; à égalité, la compétence introduite le plus tôt.
    assert [s.code_competence for s in demande.sections] == ["RAD", "VEC", "EQ2"]
    rad, vec, eq2 = demande.sections
    assert [s.ordre for s in demande.sections] == [1, 2, 3]
    assert eq2.prerequis == [1] and eq2.libelles_prerequis == ["Radicaux"]
    assert (rad.duree_h, vec.duree_h, eq2.duree_h) == (1.0, 4.0, 3.0)
    assert [t.code for t in eq2.types_erreur] == ["PRC"]
    assert eq2.signatures == ["Δ = b² + 4ac → signe du discriminant"]

    # L1 vient du problème ; L2 (problème ATT ignoré) n'a plus de problème
    # remédiable mais reste rattachée à EQ2, sa compétence principale.
    assert [q.code for q in eq2.questions] == ["L1", "L2"]
    assert eq2.questions[0].citation == "lu sur L1"
    assert eq2.questions[1].reponse_eleve == "—"
    # G2 réussie, compétence principale VEC : montrée dans la section VEC.
    assert [(q.code, q.reussie) for q in vec.questions] == [("G1", False), ("G2", True)]


def test_identite_et_libelles(db, referentiel):
    demande = _demande(db, [_probleme("N1", "RAD", "CPT")])
    assert demande.eleve_nom == "NIKIEMA K. Amale"
    assert demande.prenom == "K. Amale"
    assert demande.classe == "1ère D"
    assert demande.test_libelle == "test diagnostique d'entrée en 1ère D"
    assert [q.code for q in demande.questions_reussies] == ["G2"]


def test_aucun_probleme_remediable_aucune_section(db, referentiel):
    assert _demande(db, [_probleme("N1", "RAD", "ATT")]).sections == []


def test_decision_enseignant_prime_sur_la_note_ia(db, referentiel):
    grade, rubric = _copie(set())
    grade.questions[0].teacher_decision = TeacherDecision.refused
    grade.questions[0].teacher_score = 1.0
    questions = plan_eleve._questions_de_la_copie(grade, rubric)
    assert questions["N1"].reussie and not questions["L1"].reussie


def test_date_fr():
    assert plan_eleve.date_fr(date(2026, 10, 24)) == "24 octobre 2026"
