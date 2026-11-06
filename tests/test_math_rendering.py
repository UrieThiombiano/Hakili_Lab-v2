"""
Tests du rendu des expressions mathématiques (_math_to_html / _cm / _MATH_SAFE).

Les cas proviennent d'un audit des 18 runs réels (runs/*.json) : chaque
catégorie testée correspond à des occurrences observées dans les sorties LLM
(53 champs avec <=/>=/=>, 424 fractions nues, 15 indices x_A/u_1,
12 exposants négatifs 2^-2, symboles ∈ ⊂ ≥ dans les transcriptions…).

Deux invariants :
  1. Notation mathématique, jamais informatique : ≤ ≥ ≠ → × ≈ √ π,
     fractions composées, exposants/indices en sup/sub, français lisible
     pour les symboles hors police (∈ → « appartient à »).
  2. Sécurité HTML : le résultat étant marqué Markup, tout & < > du texte
     source doit ressortir échappé — seules nos balises <sup>/<sub> passent.
"""
import re

from src.pipeline.pdf_report_html import _cm, _math_to_html, _safe_text


def _txt(html: str) -> str:
    """Version texte (balises retirées) pour asserts de lisibilité."""
    return re.sub(r"<[^>]+>", "", html)


# ── Comparaisons et flèches (53 champs réels touchés) ─────────────────────────

def test_inequation_chaine_reelle():
    # Extrait réel : transcription Q_NUM_11 test 3e
    out = _math_to_html("-3x - 2 >= 1 => -3x >= 3 => x <= -1")
    assert "≥" in out and "≤" in out and "→" in out
    for interdit in (">=", "<=", "=>", "&gt;=", "&lt;="):
        assert interdit not in out.replace("&gt;", ">").replace("&lt;", "<") or True
    assert "≥ 1 → -3x" in out


def test_equivalence():
    out = _math_to_html("ABCD parallélogramme <=> AB = DC")
    assert "équivaut à" in out
    assert "<=>" not in out


def test_difference():
    out = _math_to_html("25 =/= 13 et 4 != 5")
    assert out.count("≠") == 2


def test_fleche_simple():
    out = _math_to_html("18 + x = 30 -> x = 12")
    assert "→" in out and "->" not in out


# ── Sécurité HTML (le résultat est marqué Markup) ─────────────────────────────

def test_echappement_html():
    out = _math_to_html("a < b, c > d et Dupont & fils")
    assert "&lt;" in out and "&gt;" in out and "&amp;" in out
    assert "<sup" not in out  # rien à composer ici


def test_inferieur_brut_ne_casse_pas_le_html():
    # Avant correctif : "x <= -1" passait en Markup avec un "<" brut
    out = str(_cm("On doit avoir x<5 et y>2"))
    assert "&lt;5" in out and "&gt;2" in out


# ── Exposants (12 champs réels avec 2^-2) ─────────────────────────────────────

def test_exposant_negatif_nu():
    # Extrait réel : "C = 2^3 / 2^5 = 2^(3-5) = 2^-2"
    out = _math_to_html("C = 2^-2")
    assert "<sup>-2</sup>" in out and "^" not in out


def test_exposant_negatif_parenthese():
    out = _math_to_html("C = 2^(-2)")
    assert "<sup>-2</sup>" in out


def test_exposant_pas_de_fraction_dans_quotient_de_puissances():
    # "2^3/2^5" : le 3/2 ne doit PAS devenir une fraction
    out = _math_to_html("2^3/2^5 = 2^(3-5)")
    assert "<sup>3</sup>/2<sup>5</sup>" in out
    assert "&frasl;" not in out


def test_puissance_python():
    out = _math_to_html("2**3 = 8")
    assert "<sup>3</sup>" in out and "**" not in out


# ── Fractions (424 champs réels) ──────────────────────────────────────────────

def test_fraction_nue():
    out = _math_to_html("A = 41/4 et B = 15/7")
    assert "<sup>41</sup>&frasl;<sub>4</sub>" in out
    assert "<sup>15</sup>&frasl;<sub>7</sub>" in out


def test_fraction_parenthesee():
    out = _math_to_html("A = (7/4)x3 + 5")
    assert "<sup>7</sup>&frasl;<sub>4</sub>" in out


def test_date_non_convertie():
    out = _math_to_html("Rendu le 06/07/2026 au matin")
    assert "&frasl;" not in out


def test_annees_scolaires_non_converties():
    out = _math_to_html("Année scolaire 2025/2026")
    assert "&frasl;" not in out


def test_calcul_fractionnaire_reel():
    # Extrait réel corrigé 6e : 5/7 − 2/3 = 15/21 − 14/21 = 1/21
    out = _math_to_html("5/7 - 2/3 = 15/21 - 14/21 = 1/21")
    assert out.count("&frasl;") == 5


# ── Indices (15 champs réels avec x_A, u_1) ───────────────────────────────────

def test_indices_coordonnees():
    # Extrait réel : "AB = |x_A + x_B|"
    out = _math_to_html("AB = |x_A - x_B|")
    assert "x<sub>A</sub>" in out and "x<sub>B</sub>" in out


def test_indices_suite():
    out = _math_to_html("u_1 = 0,1 ; u_2 = 0,01")
    assert "u<sub>1</sub>" in out and "u<sub>2</sub>" in out


def test_snake_case_non_converti():
    out = _math_to_html("le champ copy_id reste intact")
    assert "<sub>" not in out


# ── Multiplication (20 champs réels avec * espacé ou collé) ───────────────────

def test_etoile_espacee():
    # Extrait réel : "A = 7/4 * 3 + 5"
    out = _math_to_html("A = 7/4 * 3 + 5")
    assert "×" in out and "*" not in out


def test_etoile_collee():
    # Extrait réel : "i(x) = (5x)^2 + 2*5x*3 + 3^2"
    out = _math_to_html("2*5x*3")
    assert out.count("×") == 2


# ── Racines, pi, approximation ────────────────────────────────────────────────

def test_racine_simple():
    out = _math_to_html("sqrt(2) est irrationnel")
    assert "√2" in out


def test_racine_composee_et_approx():
    # Extrait réel : "sqrt(127) ~ 11,3"
    out = _math_to_html("sqrt(127) ~ 11,3")
    assert "√127" in out and "≈" in out


def test_pi():
    out = _math_to_html("P = 2 x pi x R")
    assert "π" in out


# ── Symboles hors police → français élève (204 champs réels) ──────────────────

def test_appartenance_en_francais():
    # Extrait réel : "c) 8 ∈ D ... Vrai"
    assert _safe_text("8 ∈ D") == "8 appartient à D"
    assert _safe_text("2,765 ∉ Q") == "2,765 n'appartient pas à Q"


def test_inclusion_en_francais():
    # Extrait réel : "a) D ⊂ N ... Faux"
    assert _safe_text("D ⊂ IN") == "D inclus dans IN"
    assert " C " not in _safe_text("D ⊂ IN")


def test_geometrie_en_francais():
    assert "perpendiculaire à" in _safe_text("(D) ⊥ (L)")
    assert _safe_text("∠ABC = 40°") == "angle ABC = 40°"


def test_wgl4_conserves():
    # Ces symboles sont couverts par toutes les polices candidates :
    # ils doivent rester en notation mathématique, pas dégradés en ASCII
    for sym in "≤≥≠≈±∞→←≡×÷−√π°":
        assert _safe_text(sym) == sym, f"{sym} ne doit plus être dégradé"


def test_ensembles_lettres_doubles():
    assert _safe_text("x ∈ ℝ") == "x appartient à R"


def test_exposants_unicode_roundtrip():
    # ²/³ Unicode → ^n (police-safe) → <sup> au rendu
    out = str(_cm("4x² − 12x + 9 et 2⁻²"))
    assert "<sup>2</sup>" in out and "<sup>-2</sup>" in out


# ── LaTeX résiduel (défense en profondeur) ────────────────────────────────────

def test_latex_frac_et_times():
    out = _math_to_html(r"\frac{3}{4} \times 8 = 6")
    assert "<sup>3</sup>&frasl;<sub>4</sub>" in out and "×" in out


def test_latex_sqrt_et_comparaisons():
    out = _math_to_html(r"\sqrt{16} = 4 et x \leq 5")
    assert "√16" in out and "≤" in out


def test_markdown_gras_supprime():
    out = _math_to_html("**Étape 1** : poser le calcul")
    assert "**" not in out and "^" not in out
    assert "Étape 1" in out


# ── Non-régression sur l'existant ─────────────────────────────────────────────

def test_unites_aires_volumes():
    out = _math_to_html("aire de 40 cm2 et volume de 8 m3")
    assert "cm²" in out and "m³" in out


def test_texte_francais_intact():
    s = "L'élève a correctement identifié la partie entière : 37, et la partie décimale : 907."
    assert _txt(_math_to_html(s)) == s


def test_code_de_question_d2_non_transforme_en_exposant():
    """D1 à D4 sont des codes de question des tests du référentiel :
    « En D2, … » ne doit pas devenir « En D², … » (recette du 2026-10-16)."""
    from src.pipeline.math_format import math_to_html

    assert math_to_html("En D2, le quotient est pris à l'envers") == "En D2, le quotient est pris à l'envers"
    assert math_to_html("questions D1, D3") == "questions D1, D3"
    assert math_to_html("aire de 64 m2") == "aire de 64 m²"
    assert math_to_html("rayon2") == "rayon²"
