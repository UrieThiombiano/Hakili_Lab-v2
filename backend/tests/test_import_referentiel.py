"""Port de `importer_referentiel` — vérifié contre un classeur minimal
fabriqué en mémoire (pas le vrai `Referentiel_Socle_v0.xlsx`, 444 lignes),
sur le même principe que les autres tests de service : l'intention du code
Django, pas sa traduction ligne à ligne."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.models import Competence, CoutRemediation, OptionQcm, Prerequis, Question, SignatureErreur, TypeErreur
from app.services.import_referentiel import ErreurImport, importer

_ENTETES = {
    "01_Types_erreur": ["code", "libelle", "definition", "signature", "exemple", "coefficient", "remediable"],
    "02_Competences": ["code", "domaine", "libelle", "description", "niveau_intro", "chapitre_intro", "transversale", "prerequis", "volume_horaire", "source_volume"],
    "04_Questions": ["niveau_test", "code_question", "partie", "bareme_classeur", "format", "code_local", "competence", "competence_secondaire", "objet"],
    "05_Grille_diagnostic": ["niveau_test", "code_question", "competence", "type_erreur", "production_eleve", "interpretation"],
    "06_Distracteurs": ["niveau_test", "code_question", "lettre", "texte", "correcte", "type_erreur", "erreur"],
    "08_Cout_remediation": ["competence", "_", "_", "type_erreur", "_", "_", "cout_heures", "derivation"],
}


def _classeur(tmp_path: Path, donnees: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nom, entetes in _ENTETES.items():
        ws = wb.create_sheet(nom)
        ws.append(entetes)
        for ligne in donnees.get(nom, []):
            ws.append(ligne)
    chemin = tmp_path / "classeur_test.xlsx"
    wb.save(chemin)
    return chemin


def _classeur_valide(tmp_path: Path) -> Path:
    """Un référentiel minimal cohérent : deux types d'erreur (dont ATT, non
    remédiable), trois compétences (A prérequis de B, C sans volume — teste
    le repli lycée), une question QCM et une question rédigée, une
    signature, deux options, un coût."""
    return _classeur(
        tmp_path,
        {
            "01_Types_erreur": [
                ["CPT", "Conceptuelle", "def", "sig", "ex", 0.7, "OUI"],
                ["ATT", "Inattention", "def", "sig", "ex", 0, "NON"],
            ],
            "02_Competences": [
                ["A", "Activites numeriques", "Compétence A", "desc", "6eme", "ch1", "NON", "", 4, "officiel"],
                ["B", "Activites numeriques", "Compétence B", "desc", "5eme", "ch2", "NON", "A", 6, "officiel"],
                ["C", "Activites numeriques", "Compétence lycée", "desc", "2ndeC", "ch3", "NON", "", "non disponible", ""],
            ],
            "04_Questions": [
                ["6eme", "Q1", "A", 1, "qcm", "N-a", "A", "", "2+2 ?"],
                ["6eme", "Q2", "B", 3, "redige", "N-b", "B", "", "Développer (a+b)^2"],
            ],
            "05_Grille_diagnostic": [
                ["6eme", "Q2", "B", "CPT", "a^2+b^2", "oubli du double produit"],
            ],
            "06_Distracteurs": [
                ["6eme", "Q1", "a", "4", "OUI", "", ""],
                ["6eme", "Q1", "b", "3", "NON", "CPT", "erreur de calcul"],
            ],
            "08_Cout_remediation": [
                ["B", "", "", "CPT", "", "", 1.5, "6e ch2 : 6h x 0.7 / 3"],
            ],
        },
    )


def test_importer_ecrit_tout_le_referentiel(db, tmp_path):
    chemin = _classeur_valide(tmp_path)
    rapport = importer(db, chemin)

    assert rapport.n_types == 2
    assert rapport.n_competences == 3
    assert rapport.n_prerequis == 1
    assert rapport.n_questions == 2
    assert rapport.n_signatures == 1
    assert rapport.n_options == 2
    assert rapport.n_qcm_avec_reponse == 1

    assert db.get(TypeErreur, "ATT").remediable is False
    assert db.query(Prerequis).filter_by(competence_id="B", prerequis_id="A").first() is not None


def test_import_repli_lycee_marque_estime(db, tmp_path):
    chemin = _classeur_valide(tmp_path)
    importer(db, chemin)

    c = db.get(Competence, "C")
    assert c.volume_estime is True
    assert c.volume_horaire == 4  # VOLUME_REPLI_LYCEE

    # Coût estimé calculé (pas dans le classeur) pour C x CPT, arrondi.
    cout = db.query(CoutRemediation).filter_by(competence_id="C", type_erreur_id="CPT").first()
    assert cout is not None
    assert cout.estime is True


def test_import_qcm_remplit_reponse_attendue(db, tmp_path):
    chemin = _classeur_valide(tmp_path)
    importer(db, chemin)

    q1 = db.query(Question).filter_by(niveau_test="6eme", code_question="Q1").first()
    assert q1.reponse_attendue == "a"

    options = db.query(OptionQcm).filter_by(question_id=q1.id).all()
    assert len(options) == 2
    bonne = next(o for o in options if o.correcte)
    assert bonne.type_erreur_id is None
    mauvaise = next(o for o in options if not o.correcte)
    assert mauvaise.type_erreur_id == "CPT"


def test_import_refuse_competence_inconnue(db, tmp_path):
    chemin = _classeur(
        tmp_path,
        {
            "01_Types_erreur": [["CPT", "Conceptuelle", "d", "s", "e", 0.7, "OUI"]],
            "02_Competences": [["A", "Activites numeriques", "A", "d", "6eme", "", "NON", "", 4, ""]],
            "04_Questions": [["6eme", "Q1", "A", 1, "qcm", "", "ZZZ", "", "objet"]],
            "05_Grille_diagnostic": [],
            "06_Distracteurs": [],
            "08_Cout_remediation": [],
        },
    )
    with pytest.raises(ErreurImport, match="compétence"):
        importer(db, chemin)

    # Rien n'a été écrit : ni la compétence ni le type d'erreur valides.
    assert db.query(Competence).count() == 0
    assert db.query(TypeErreur).count() == 0


def test_import_a_blanc_ne_ecrit_rien(db, tmp_path):
    chemin = _classeur_valide(tmp_path)
    rapport = importer(db, chemin, a_blanc=True)

    assert rapport.a_blanc is True
    assert rapport.lignes_lues["02_Competences"] == 3
    assert db.query(Competence).count() == 0


def test_import_idempotent(db, tmp_path):
    chemin = _classeur_valide(tmp_path)
    importer(db, chemin)
    importer(db, chemin)

    assert db.query(Competence).count() == 3
    assert db.query(TypeErreur).count() == 2
    assert db.query(Prerequis).count() == 1
    assert db.query(Question).count() == 2


def test_import_bareme_sur_20_selon_le_total_du_test(db, tmp_path):
    """Collège sur 60, lycée sur 80 : le diviseur se déduit du total du test,
    il n'est pas figé à 3. Ici le test 6eme vaut 1 + 3 = 4 points."""
    importer(db, _classeur_valide(tmp_path), corriges={})

    q1 = db.query(Question).filter_by(code_question="Q1").one()
    q2 = db.query(Question).filter_by(code_question="Q2").one()
    assert float(q1.bareme) + float(q2.bareme) == pytest.approx(20.0)
    assert float(q2.bareme) == pytest.approx(15.0)


def test_import_format_accentue_normalise(db, tmp_path):
    """Le classeur v1 écrit « rédigé » ; la base attend `redige`."""
    chemin = _classeur(
        tmp_path,
        {
            "01_Types_erreur": [["CPT", "Conceptuelle", "d", "s", "e", 0.7, "OUI"]],
            "02_Competences": [["A", "Activites numeriques", "A", "d", "6eme", "", "NON", "", 4, ""]],
            "04_Questions": [["6eme", "Q1", "B", 2, "rédigé", "", "A", "", "objet"]],
        },
    )
    importer(db, chemin, corriges={})
    assert db.query(Question).one().format == "redige"


def test_import_reprend_les_corriges_transcrits(db, tmp_path):
    corriges = {"6eme": {"Q2": {"reponse_attendue": "a² + 2ab + b²", "solution": "Barème : 3 pts"}}}
    importer(db, _classeur_valide(tmp_path), corriges=corriges)

    q2 = db.query(Question).filter_by(code_question="Q2").one()
    assert q2.reponse_attendue == "a² + 2ab + b²"
    assert q2.solution == "Barème : 3 pts"
    # QCM : la bonne lettre vient toujours du classeur, pas du fichier de corrigés.
    assert db.query(Question).filter_by(code_question="Q1").one().reponse_attendue == "a"


def test_import_retire_les_questions_des_anciens_sujets(db, tmp_path):
    """Sujet refait : une question absente du nouveau classeur est supprimée,
    avec ses signatures et options (cascade)."""
    importer(db, _classeur_valide(tmp_path), corriges={})
    ancienne = Question(
        niveau_test="6eme", code_question="P4.1", partie="C", format="redige",
        bareme=1, bareme_classeur=3, competence_id="A", objet="ancien problème",
    )
    db.add(ancienne)
    db.commit()

    rapport = importer(db, _classeur_valide(tmp_path), corriges={})

    assert rapport.n_questions_retirees == 1
    assert db.query(Question).filter_by(code_question="P4.1").first() is None
    assert db.query(Question).count() == 2
