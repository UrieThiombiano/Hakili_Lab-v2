"""
Tests des barèmes v2 (data/knowledge/bareme_socle_*.yaml).

Ces fichiers sont générés par scripts/generer_baremes_socle.py depuis
data/referentiel/Referentiel_Urie_v1.xlsx et data/knowledge/corriges_socle.yaml.
Les tests ci-dessous verrouillent les propriétés qui doivent tenir après toute
régénération.

Le test le plus important est `test_copie_parfaite_vaut_exactement_20` : une
question de partie A vaut 1/3 de point, non représentable exactement en décimal
(16 × 0,333333 = 5,333328). C'est sans conséquence tant que la note se calcule
contre la somme réelle des max_score — mais un total déclaré utilisé comme
dénominateur ferait réapparaître le bug constaté sur les anciens barèmes, où une
copie parfaite valait 18,5/20. Voir docs/harmonisation_donnees.md §4 et §5.1.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_KB_DIR = Path(__file__).parent.parent / "data" / "knowledge"

_NIVEAUX = ("6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD", "tleD")

# Batterie allégée du 2026-10-06 (Referentiel_Urie_v1.xlsx), qui remplace les
# sujets du 2026-08-12 jugés trop longs. Trois parties partout :
#   collège : 16 A × 1 pt + 11 B × 2 pts + 3 problèmes en C (7 + 7 + 8)  = 60
#   lycée   : 20 A × 1 pt + 14 B × 2 pts + 4 problèmes en C (4 × 8)      = 80
# chaque problème découpé en 3 sous-questions P1.1, P1.2, P1.3 (2 + 2 + 3 ou 2 + 3 + 3).
_NIVEAUX_LYCEE = ("2ndeC", "1ereD", "tleD")

# Classe canonique attendue par test — doit être reconnue par normalize_classe,
# sinon resolve_classe refuse d'écrire la classe en base.
_CLASSE_ATTENDUE = {
    "6eme": "6e", "5eme": "5e", "4eme": "4e", "3eme": "3e",
    "2ndeC": "2nde", "1ereD": "1ere", "tleD": "Tle",
}

_TYPES_ERREUR = {"PRQ", "CPT", "MOD", "PRC", "CNS", "RED", "ATT"}
_FORMATS = {"qcm", "court", "redige", "construction"}


def _charger(niveau: str) -> dict:
    path = _KB_DIR / f"bareme_socle_{niveau}.yaml"
    assert path.exists(), f"{path.name} absent — lancer scripts/generer_baremes_socle.py"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_structure_a_3_parties(niveau: str) -> None:
    qs = _charger(niveau)["questions"]
    lycee = niveau in _NIVEAUX_LYCEE
    partie_a = [q for q in qs if q["partie"] == "A"]
    partie_b = [q for q in qs if q["partie"] == "B"]
    partie_c = [q for q in qs if q["partie"] == "C"]
    assert len(partie_a) == (20 if lycee else 16)
    assert len(partie_b) == (14 if lycee else 11)
    assert len(partie_c) == (12 if lycee else 9)
    assert all(q["bareme_classeur"] == 1.0 for q in partie_a)
    assert all(q["bareme_classeur"] == 2.0 for q in partie_b)
    assert sum(q["bareme_classeur"] for q in partie_c) == pytest.approx(32.0 if lycee else 22.0)
    assert _charger(niveau)["meta"]["total_questions"] == len(qs)


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_sous_questions_partie_c_rattachees_a_un_probleme(niveau: str) -> None:
    """P2.3 porte `probleme_parent: P2` ; 3 sous-questions par problème, et le
    barème d'un problème est celui du corrigé (7, 7, 8 au collège ; 8 au lycée)."""
    partie_c = [q for q in _charger(niveau)["questions"] if q["partie"] == "C"]
    lycee = niveau in _NIVEAUX_LYCEE
    parents = sorted({q["probleme_parent"] for q in partie_c})
    assert parents == (["P1", "P2", "P3", "P4"] if lycee else ["P1", "P2", "P3"])
    attendu = {"P1": 8, "P2": 8, "P3": 8, "P4": 8} if lycee else {"P1": 7, "P2": 7, "P3": 8}
    for parent in parents:
        sous = [q for q in partie_c if q["probleme_parent"] == parent]
        assert [q["code"] for q in sous] == [f"{parent}.{i}" for i in (1, 2, 3)]
        assert sum(q["bareme_classeur"] for q in sous) == pytest.approx(attendu[parent])


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_bareme_sur_20(niveau: str) -> None:
    """Décision D-CEO-26 : barème stocké sur 20, converti du classeur par 3
    (collège, total 60) ou par 4 (lycée, total 80)."""
    data = _charger(niveau)
    lycee = niveau in _NIVEAUX_LYCEE
    diviseur = 4.0 if lycee else 3.0
    assert data["meta"]["bareme_classeur_total"] == pytest.approx(80.0 if lycee else 60.0)
    assert sum(q["bareme"] for q in data["questions"]) == pytest.approx(20.0, abs=1e-4)
    for q in data["questions"]:
        assert q["bareme"] == pytest.approx(q["bareme_classeur"] / diviseur, abs=1e-6)


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_classe_reconnue_par_le_normaliseur(niveau: str) -> None:
    """`meta.classe` alimente HakiliTest.niveaux, que resolve_classe utilise comme
    garde-fou : une valeur non reconnue empêcherait d'écrire la classe en base."""
    from src.core.classe_normalizer import normalize_classe

    classe = _charger(niveau)["meta"]["classe"]
    assert classe == _CLASSE_ATTENDUE[niveau]
    assert normalize_classe(classe) == classe


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_codes_uniques_et_champs_valides(niveau: str) -> None:
    qs = _charger(niveau)["questions"]
    codes = [q["code"] for q in qs]
    assert len(set(codes)) == len(codes), "codes de question dupliqués"
    for q in qs:
        assert q["format"] in _FORMATS, f"{q['code']} : format inconnu {q['format']!r}"
        assert q["competence"], f"{q['code']} : compétence manquante"
        assert q["objet"], f"{q['code']} : intitulé manquant"


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_qcm_ont_leur_bonne_reponse(niveau: str) -> None:
    """Les QCM sont corrigeables sans appel LLM : une lettre cochée suffit."""
    for q in _charger(niveau)["questions"]:
        if q["format"] != "qcm":
            continue
        options = q.get("options") or []
        assert options, f"{q['code']} : QCM sans options"
        correctes = [o for o in options if o["correcte"]]
        assert len(correctes) == 1, f"{q['code']} : {len(correctes)} bonnes réponses"
        assert q["reponse_attendue"] == correctes[0]["lettre"]


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_distracteurs_tagues_par_un_type_ferme(niveau: str) -> None:
    """Chaque mauvaise option porte un type d'erreur de la liste fermée — c'est ce
    qui permet au module 4 de diagnostiquer un QCM sans interprétation."""
    for q in _charger(niveau)["questions"]:
        for o in q.get("options") or []:
            if o["correcte"]:
                continue
            assert o.get("type_erreur") in _TYPES_ERREUR, (
                f"{q['code']} option {o['lettre']} : type {o.get('type_erreur')!r} "
                "hors de la liste fermée"
            )


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_chaque_question_a_son_corrige(niveau: str) -> None:
    """Les 282 questions de la batterie allégée ont une réponse attendue
    (constructions comprises) et une ligne « si l'élève échoue », transcrites
    des corrigés PDF enseignant dans corriges_socle.yaml."""
    for q in _charger(niveau)["questions"]:
        assert q["reponse_attendue"], f"{q['code']} : pas de réponse attendue"
        assert q["si_echoue"], f"{q['code']} : pas de « si l'élève échoue »"


def test_corriges_sans_code_orphelin() -> None:
    """Une entrée de corriges_socle.yaml sans question correspondante signale un
    code mal recopié — elle serait ignorée en silence par le générateur."""
    corriges = yaml.safe_load((_KB_DIR / "corriges_socle.yaml").read_text(encoding="utf-8"))["corriges"]
    for niveau in _NIVEAUX:
        codes = {q["code"] for q in _charger(niveau)["questions"]}
        orphelins = set(corriges.get(niveau, {})) - codes
        assert not orphelins, f"{niveau} : codes inconnus {sorted(orphelins)}"


# ── Le test central : la note d'une copie parfaite ────────────────────────────

@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_copie_parfaite_vaut_exactement_20(niveau: str) -> None:
    from src.knowledge.test_registry import get_registry
    from src.models.domain import CopyGrade, QuestionGrade, TeacherDecision

    test = get_registry().get_test(f"socle_{niveau}")
    assert test is not None

    questions = [
        QuestionGrade(
            rubric_item_id=item.id,
            score=item.max_score,
            confidence=1.0,
            comment="",
            observed_answer="",
            requires_review=False,
            teacher_decision=TeacherDecision.accepted,
        )
        for item in test.rubric.items
    ]
    grade = CopyGrade(
        copy_id="test",
        total_score=sum(i.max_score for i in test.rubric.items),
        total_possible=test.rubric.total_points,
        questions=questions,
    ).compute_final_score()

    assert grade.final_score_on_20 == pytest.approx(20.0)


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_copie_nulle_vaut_zero(niveau: str) -> None:
    from src.knowledge.test_registry import get_registry
    from src.models.domain import CopyGrade, QuestionGrade, TeacherDecision

    test = get_registry().get_test(f"socle_{niveau}")
    questions = [
        QuestionGrade(
            rubric_item_id=item.id,
            score=0.0,
            confidence=1.0,
            comment="",
            observed_answer="",
            requires_review=False,
            teacher_decision=TeacherDecision.accepted,
        )
        for item in test.rubric.items
    ]
    grade = CopyGrade(
        copy_id="test",
        total_score=0.0,
        total_possible=test.rubric.total_points,
        questions=questions,
    ).compute_final_score()

    assert grade.final_score_on_20 == pytest.approx(0.0)


# ── Registre : actifs vs archivés ─────────────────────────────────────────────

def test_les_7_tests_socle_sont_proposes() -> None:
    from src.knowledge.test_registry import get_registry

    disponibles = get_registry().available_tests()
    for niveau in _NIVEAUX:
        assert f"socle_{niveau}" in disponibles


def test_seuls_les_tests_du_16_octobre_sont_au_catalogue() -> None:
    """Décision du 2026-10-16 : seuls les 7 tests de la batterie allégée sont
    utilisés ; les anciens (v1, sujets longs d'août) sont retirés, pas archivés."""
    from src.knowledge.test_registry import get_registry

    registry = get_registry()
    attendus = {f"socle_{niveau}" for niveau in _NIVEAUX}
    assert set(registry.all_tests()) == attendus
    assert set(registry.available_tests()) == attendus
    assert registry.get_test("hakili_3e_v1") is None


def test_pdf_imprimables_du_16_octobre_presents() -> None:
    """Le sujet et le corrigé imprimables de chaque test sont servis par l'API."""
    from src.knowledge.test_registry import get_registry

    for test in get_registry().all_tests().values():
        assert test.sujet_pdf is not None and test.sujet_pdf.exists(), test.bareme_id
        assert test.corrige_pdf is not None and test.corrige_pdf.exists(), test.bareme_id
