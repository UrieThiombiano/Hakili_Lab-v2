"""
Tests des barèmes v2 (data/knowledge/bareme_socle_*.yaml).

Ces fichiers sont générés par scripts/generer_baremes_socle.py depuis
Referentiel_Socle_v0.xlsx. Les tests ci-dessous verrouillent les propriétés qui
doivent tenir après toute régénération.

Le test le plus important est `test_copie_parfaite_vaut_exactement_20` : une
question de partie A vaut 1/3 de point, non représentable exactement en décimal
(30 × 0,333333 = 9,99999). C'est sans conséquence tant que la note se calcule
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

# Niveaux dont le barème a été reconstruit le 2026-08-12 sur la structure à 3
# parties (Automatismes/Savoir-faire/Raisonnement) des sujets recomposés
# livrés le même jour — voir docs/harmonisation_donnees.md, arbitrage H.
# Les autres niveaux restent sur l'ancienne structure (2 parties, 40 questions)
# tant qu'ils n'ont pas été reconstruits à leur tour.
_NIVEAUX_RECOMPOSES = ("6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD", "tleD")
# Niveaux lycee : barème classeur sur 80, converti /20 par division par 4 (collège : /60, ÷3).
_NIVEAUX_LYCEE = ("2ndeC", "1ereD", "tleD")
_NIVEAUX_HERITES = tuple(n for n in _NIVEAUX if n not in _NIVEAUX_RECOMPOSES)

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


@pytest.mark.parametrize("niveau", _NIVEAUX_HERITES)
def test_40_questions_par_test(niveau: str) -> None:
    data = _charger(niveau)
    assert len(data["questions"]) == 40
    assert data["meta"]["total_questions"] == 40


@pytest.mark.parametrize("niveau", _NIVEAUX_HERITES)
def test_structure_partie_a_et_b(niveau: str) -> None:
    """30 questions courtes en partie A, 10 exercices rédigés en partie B."""
    qs = _charger(niveau)["questions"]
    assert sum(1 for q in qs if q["partie"] == "A") == 30
    assert sum(1 for q in qs if q["partie"] == "B") == 10


# ── Niveaux recomposés (2026-08-12) : structure à 3 parties ───────────────────
# Collège : 16 A (1 pt) + 11 B (2 pts) + 4 problèmes en partie C, chacun
# décomposé en 4 sous-items (Pxa..Pxd) — voir docs/harmonisation_donnees.md,
# arbitrage H, pour le détail de la décomposition et sa justification.

@pytest.mark.parametrize("niveau", _NIVEAUX_RECOMPOSES)
def test_structure_a_3_parties(niveau: str) -> None:
    """Collège : 16 A (1 pt) + 22 pts en B (11 items de 2 pts — parfois décomposés en
    paires de 1 pt quand un item mélange calcul et construction, cf. G7/G9 en 5e,
    voir arbitrage H) + 22 pts en C. Lycée (2ndeC/1ereD/tleD) : 20 A + 28 pts B + 32 pts C."""
    qs = _charger(niveau)["questions"]
    partie_a = [q for q in qs if q["partie"] == "A"]
    partie_b = [q for q in qs if q["partie"] == "B"]
    partie_c = [q for q in qs if q["partie"] == "C"]
    lycee = niveau in _NIVEAUX_LYCEE
    assert len(partie_a) == (20 if lycee else 16)
    assert sum(q["bareme_classeur"] for q in partie_c) == pytest.approx(32.0 if lycee else 22.0)
    assert all(q["bareme_classeur"] == 1.0 for q in partie_a)
    assert sum(q["bareme_classeur"] for q in partie_b) == pytest.approx(28.0 if lycee else 22.0)
    assert all(q["bareme_classeur"] in (1.0, 2.0) for q in partie_b)


@pytest.mark.parametrize("niveau", _NIVEAUX_RECOMPOSES)
def test_sous_items_partie_c_rattaches_a_un_probleme(niveau: str) -> None:
    """Chaque sous-item de partie C porte `probleme_parent` (P1..P4, ou P1..P6 au
    lycée), et les sous-items d'un même problème somment exactement son barème
    total. Le nombre de sous-items par problème suit le nombre de termes du
    barème imprimé dans le corrigé — 4 pour 6e/5e, jusqu'à 6 pour 4e/2ndeC —
    ce n'est pas fixé à 4 partout, voir docs/harmonisation_donnees.md arbitrage H."""
    qs = _charger(niveau)["questions"]
    partie_c = [q for q in qs if q["partie"] == "C"]
    parents = {q["probleme_parent"] for q in partie_c}
    attendu = {"P1", "P2", "P3", "P4", "P5", "P6"} if niveau in _NIVEAUX_LYCEE else {"P1", "P2", "P3", "P4"}
    assert parents == attendu
    petits_problemes = {"P1", "P2", "P3", "P4"} if niveau in _NIVEAUX_LYCEE else {"P1", "P2"}
    for parent in parents:
        sous_items = [q for q in partie_c if q["probleme_parent"] == parent]
        assert 3 <= len(sous_items) <= 6
        total_attendu = 5.0 if parent in petits_problemes else 6.0
        assert sum(q["bareme_classeur"] for q in sous_items) == pytest.approx(total_attendu)


@pytest.mark.parametrize("niveau", _NIVEAUX)
def test_bareme_sur_20(niveau: str) -> None:
    """Décision D-CEO-26 : barème stocké sur 20, converti du classeur par 3 (collège,
    total 60) ou par 4 (lycée, total 80 — arbitrage H, sujets recomposés du 2026-08-12)."""
    data = _charger(niveau)
    lycee_recompose = niveau in _NIVEAUX_LYCEE and niveau in _NIVEAUX_RECOMPOSES
    diviseur = 4.0 if lycee_recompose else 3.0
    total_classeur_attendu = 80.0 if lycee_recompose else 60.0
    assert data["meta"]["bareme_classeur_total"] == pytest.approx(total_classeur_attendu)
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


@pytest.mark.parametrize("niveau", _NIVEAUX_HERITES)
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


@pytest.mark.parametrize("niveau", _NIVEAUX_HERITES)
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


@pytest.mark.parametrize("niveau", _NIVEAUX_RECOMPOSES)
def test_qcm_ont_une_reponse_lisible(niveau: str) -> None:
    """Niveaux recomposés : pas de liste `options` (le corrigé PDF ne détaille pas
    les distracteurs comme le classeur) — `reponse_attendue` porte directement la
    lettre et le texte de la bonne réponse, ex. "d) 500,09"."""
    for q in _charger(niveau)["questions"]:
        if q["format"] != "qcm":
            continue
        assert not q.get("options"), f"{q['code']} : options inattendues sur un niveau recomposé"
        assert q["reponse_attendue"], f"{q['code']} : QCM sans réponse"
        lettre = q["reponse_attendue"].strip()[0].lower()
        assert lettre in "abcd", f"{q['code']} : réponse {q['reponse_attendue']!r} ne commence pas par une lettre"


def test_corriges_manquants_uniquement_hors_qcm() -> None:
    """Arbitrage B : 203/209 corrigés produits (2026-08-07, sujets 6e à tleD).
    Les 6 restants sont exactement les questions de format `construction` —
    laissées de côté tant que l'arbitrage F (diagnostic automatique ou saisie
    humaine sur un tracé) n'est pas tranché. Ce test échouera dès qu'un corrigé
    sera ajouté ou retiré — c'est voulu : il faudra alors mettre à jour le
    compte, ce qui documente la progression."""
    manquants = [
        q
        for niveau in _NIVEAUX
        for q in _charger(niveau)["questions"]
        if not q["reponse_attendue"]
    ]
    assert len(manquants) == 6
    assert all(q["format"] == "construction" for q in manquants)


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


def test_anciens_tests_archives_mais_toujours_resolus() -> None:
    """D-CEO-26 : masqués de la sélection, mais get_test() doit continuer à les
    résoudre — pipeline.py s'en sert pour la classe des copies déjà corrigées."""
    from src.knowledge.test_registry import get_registry

    registry = get_registry()
    anciens = [
        "hakili_3e_v1", "hakili_3e_v2", "hakili_6e_v1",
        "hakili_2ndeC_v1", "hakili_4e_v1", "hakili_tle_v1",
    ]
    for test_id in anciens:
        assert test_id not in registry.available_tests(), f"{test_id} encore proposé"
        test = registry.get_test(test_id)
        assert test is not None, f"{test_id} plus résolvable — casse l'historique"
        assert test.archive is True
        assert test.niveaux, f"{test_id} : niveaux perdus, résolution de classe cassée"
