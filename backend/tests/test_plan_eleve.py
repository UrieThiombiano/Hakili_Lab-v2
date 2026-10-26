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


# ── Hors référentiel de questions : T1/T3 (libellés), mode libre (sans ancrage) ─

from src.models.domain import ClaudeResponse, SortieDiagnosticContraint  # noqa: E402


def _copie_libre(items: list[tuple[str, str]], reussies: set[str]) -> tuple[CopyGrade, Rubric]:
    rubric = Rubric(subject="mathematics", total_points=len(items),
                    items=[RubricItem(id=i, label=label) for i, label in items])
    grade = CopyGrade(copy_id="c2", total_score=0, total_possible=len(items), questions=[
        QuestionGrade(rubric_item_id=i, score=1.0 if i in reussies else 0.0, confidence=1, comment="",
                      observed_answer=f"réponse {i}", correct_answer=f"attendu {i}", requires_review=False)
        for i, _ in items
    ])
    return grade, rubric


class _ClientSansAncrage:
    def __init__(self, problemes: list[dict]):
        self.problemes = problemes
        self.appels: list[dict] = []

    def diagnose_unanchored(self, **kwargs):
        self.appels.append(kwargs)
        return ClaudeResponse(success=True, data=SortieDiagnosticContraint(problemes=self.problemes),
                              confidence=1, raw_response="")


def test_niveau_de_classe():
    assert plan_eleve.niveau_de_classe("2nde C") == "2ndeC"
    assert plan_eleve.niveau_de_classe("1ère D") == "1ereD"
    assert plan_eleve.niveau_de_classe("Tle D") == "tleD"
    assert plan_eleve.niveau_de_classe("") == plan_eleve.NIVEAU_PAR_DEFAUT


def test_sujet_t1_rattache_par_libelle_sans_modele(db, referentiel):
    grade, rubric = _copie_libre(
        [("1", "Radicaux × Conceptuelle"), ("2", "Second degré × Procédurale"), ("3", "Vecteurs × Conceptuelle")],
        reussies={"3"},
    )
    client = _ClientSansAncrage([])
    diagnostic = plan_eleve.diagnostic_hors_referentiel(
        db, copy_id="c2", classe="1ère D", evaluation="Test de confirmation",
        grade=grade, rubric=rubric, client=client,
    )
    assert client.appels == []  # tout rattaché : aucun appel de modèle
    assert {(p.code_question, p.code_competence, p.code_type_erreur) for p in diagnostic.problemes} == {
        ("1", "RAD", "CPT"), ("2", "EQ2", "PRC"),
    }
    demande = plan_eleve.demande_plan(
        db, copy_id="c2", nom="Nikiema", prenom="K. Amale", titre_test="Test de confirmation en 1ère D",
        niveau_test="", grade=grade, rubric=rubric, diagnostic=diagnostic,
    )
    assert [s.code_competence for s in demande.sections] == ["RAD", "EQ2"]
    assert demande.classe == "1ère D" and demande.test_libelle == "test de confirmation en 1ère D"


def test_mode_libre_diagnostic_sans_ancrage_au_niveau_de_l_eleve(db, referentiel):
    grade, rubric = _copie_libre([("Ex1", "Calculer √12 + √27"), ("Ex2", "Résoudre x² − 5x + 6 = 0")], reussies=set())
    client = _ClientSansAncrage([
        {"code_question": "Ex1", "code_competence": "RAD", "code_type_erreur": "PRC", "citation": "réponse Ex1"},
        {"code_question": "Ex2", "code_competence": "EQ2", "code_type_erreur": "CPT", "citation": "réponse Ex2"},
    ])
    diagnostic = plan_eleve.diagnostic_hors_referentiel(
        db, copy_id="c2", classe="1ère D", evaluation="Évaluation",
        grade=grade, rubric=rubric, client=client,
    )
    appel = client.appels[0]
    # Programme de la classe compris (EQ2 introduite en 1ère D), pas seulement l'antérieur.
    assert {c["code"] for c in appel["catalogue"]} == {"RAD", "EQ2", "VEC"}
    assert appel["evaluation"] == "Évaluation"
    assert appel["productions"][0]["enonce"] == "Calculer √12 + √27 — réponse attendue : attendu Ex1"
    assert [p.code_competence for p in diagnostic.problemes] == ["RAD", "EQ2"]


def test_code_hors_catalogue_rejete_en_mode_libre(db, referentiel):
    grade, rubric = _copie_libre([("Ex1", "Une question")], reussies=set())
    client = _ClientSansAncrage([
        {"code_question": "Ex1", "code_competence": "INVENTE", "code_type_erreur": "PRC", "citation": "x"},
    ])
    diagnostic = plan_eleve.diagnostic_hors_referentiel(
        db, copy_id="c2", classe="2nde C", evaluation="Évaluation", grade=grade, rubric=rubric, client=client,
    )
    assert diagnostic.problemes == [] and diagnostic.rejets
