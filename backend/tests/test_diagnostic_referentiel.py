"""Port du moteur de diagnostic contraint (module 4) — voir
`app/services/diagnostic_referentiel.py`, port de `referentiel/diagnostic.py`.
"""
from __future__ import annotations

import pytest

from app.models import Competence, OptionQcm, Prerequis, Question, SignatureErreur, TypeErreur
from app.services import diagnostic_referentiel as diag


@pytest.fixture()
def referentiel_diagnostic(db):
    db.add_all([
        TypeErreur(code="CPT", libelle="Conceptuelle", definition="", signature="", coefficient="0.7", remediable=True),
        TypeErreur(code="ATT", libelle="Inattention", definition="", signature="", coefficient="0", remediable=False),
    ])
    db.add(Competence(code="A", domaine="Activites numeriques", libelle="Prérequis A", niveau_intro="6eme"))
    db.add(Competence(code="B", domaine="Activites numeriques", libelle="Compétence B", niveau_intro="5eme"))
    db.flush()
    db.add(Prerequis(competence_id="B", prerequis_id="A"))

    qcm = Question(
        code_question="Q1", niveau_test="6eme", partie="A", format="qcm",
        bareme="0.333333", bareme_classeur="1", competence_id="B", objet="2+2 ?",
    )
    redige = Question(
        code_question="Q2", niveau_test="6eme", partie="B", format="redige",
        bareme="1", bareme_classeur="3", competence_id="B", objet="Développer (a+b)^2",
    )
    db.add_all([qcm, redige])
    db.flush()

    db.add_all([
        OptionQcm(question_id=qcm.id, lettre="a", texte="4", correcte=True, type_erreur_id=None),
        OptionQcm(question_id=qcm.id, lettre="b", texte="3", correcte=False, type_erreur_id="CPT"),
    ])
    db.add(SignatureErreur(question_id=redige.id, competence_id="B", type_erreur_id="CPT", production_eleve="a^2+b^2", interpretation="oubli du double produit"))
    db.commit()
    return {"qcm": qcm, "redige": redige}


def test_lettre_cochee_reconnait_une_lettre_marquee():
    assert diag.lettre_cochee("b) 4x²+9", {"a", "b", "c"}) == "b"


def test_lettre_cochee_refuse_reponse_ambigue():
    assert diag.lettre_cochee("b et c", {"a", "b", "c"}) is None


def test_diagnostiquer_qcm_bonne_reponse_ne_produit_rien(db, referentiel_diagnostic):
    question = referentiel_diagnostic["qcm"]
    reponse = diag.ReponseEleve(code_question="Q1", contenu="a")
    probleme, motif = diag.diagnostiquer_qcm(db, question, reponse)
    assert probleme is None
    assert motif == ""


def test_diagnostiquer_qcm_mauvaise_reponse_produit_un_probleme(db, referentiel_diagnostic):
    question = referentiel_diagnostic["qcm"]
    reponse = diag.ReponseEleve(code_question="Q1", contenu="b")
    probleme, motif = diag.diagnostiquer_qcm(db, question, reponse)
    assert probleme is not None
    assert probleme.code_competence == "B"
    assert probleme.code_type_erreur == "CPT"


def test_diagnostiquer_qcm_case_vide_signale_sans_deviner(db, referentiel_diagnostic):
    question = referentiel_diagnostic["qcm"]
    reponse = diag.ReponseEleve(code_question="Q1", contenu="", vide=True)
    probleme, motif = diag.diagnostiquer_qcm(db, question, reponse)
    assert probleme is None
    assert "aucune option cochée" in motif


def test_codes_competence_admis_inclut_la_chaine_de_prerequis(db, referentiel_diagnostic):
    question = referentiel_diagnostic["redige"]
    admis = diag.codes_competence_admis(db, question)
    assert admis == ["B", "A"]


def test_preparer_court_circuite_les_qcm(db, referentiel_diagnostic):
    reponses = [diag.ReponseEleve(code_question="Q1", contenu="b")]
    lot = diag.preparer(db, "6eme", reponses)
    assert len(lot.problemes) == 1
    assert lot.charge == []  # rien envoyé au modèle pour un QCM


def test_preparer_ecarte_construction_et_illisible(db, referentiel_diagnostic):
    from app.models import Question as QuestionModel

    construction = QuestionModel(code_question="Q3", niveau_test="6eme", partie="B", format="construction", bareme="1", bareme_classeur="3", competence_id="B", objet="Tracer la perpendiculaire")
    db.add(construction)
    db.commit()

    reponses = [
        diag.ReponseEleve(code_question="Q3", contenu="un tracé"),
        diag.ReponseEleve(code_question="Q2", contenu="[ILLISIBLE]", illisible=True),
    ]
    lot = diag.preparer(db, "6eme", reponses)
    assert "construction géométrique" in lot.ecartees["Q3"]
    assert "non déchiffrée" in lot.ecartees["Q2"]


def test_diagnostiquer_sans_client_ecarte_les_questions_non_qcm(db, referentiel_diagnostic):
    reponses = [diag.ReponseEleve(code_question="Q2", contenu="a^2+b^2")]
    resultat = diag.diagnostiquer(db, niveau_test="6eme", reponses=reponses, client=None, copy_id="test")
    assert resultat.problemes == []
    assert "aucun client" in resultat.questions_ecartees["Q2"]


def test_valider_rejette_competence_hors_liste_admise():
    from src.models.domain import ProblemeDetecte, SortieDiagnosticContraint

    sortie = SortieDiagnosticContraint(problemes=[ProblemeDetecte(code_question="Q2", code_competence="Z", code_type_erreur="CPT", citation="test")])
    retenus, rejets = diag.valider(sortie, {"Q2": {"A", "B"}}, {"CPT", "ATT"})
    assert retenus == []
    assert "non admise" in rejets[0]
