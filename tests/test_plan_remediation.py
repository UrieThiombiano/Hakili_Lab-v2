"""Plan de remédiation (cahier élève) — modèle, gabarit et rendu PDF.

La référence est l'exemplaire validé NIKIEMA K. Amale (24 octobre 2026),
extrait en données dans tests/fixtures/plan_remediation_nikiema.json. Imprimé
par Chromium, le gabarit le reproduit au pixel près (39 pages) : tout écart de
structure ou de libellé se juge d'abord contre lui.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.domain import PlanRemediation
from src.pipeline.pdf_plan_remediation import _duree, _emphase, render_plan_html

_FIXTURE = Path(__file__).parent / "fixtures" / "plan_remediation_nikiema.json"


def _donnees() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def plan() -> PlanRemediation:
    return PlanRemediation.model_validate(_donnees())


def test_calendrier_identique_a_l_exemplaire(plan):
    assert (plan.total_h, plan.nb_seances, plan.nb_semaines) == (38.0, 26, 13)
    assert plan.seances() == [
        (1, 1), (1, 4), (4, 6), (7, 8), (8, 8), (9, 10), (11, 12), (13, 14), (15, 16),
        (17, 17), (17, 18), (18, 20), (20, 21), (21, 22), (22, 23), (23, 25), (25, 26),
    ]


def test_cinq_exercices_exactement():
    donnees = _donnees()
    donnees["competences"][0]["exercices"].pop()
    with pytest.raises(ValidationError):
        PlanRemediation.model_validate(donnees)


def test_prerequis_doit_preceder_la_section():
    donnees = _donnees()
    donnees["competences"][0]["prerequis"] = [2]
    with pytest.raises(ValidationError, match="section antérieure"):
        PlanRemediation.model_validate(donnees)


def test_duree_affichee():
    assert (_duree(1.0), _duree(1.5), _duree(38.0)) == ("1 h", "1 h 30", "38 h")


def test_html_reprend_les_libelles_de_l_exemplaire(plan):
    html = render_plan_html(plan)
    assert html.count('<section class="comp"') == 17
    assert "<span>séances 1 à 4</span>" in html
    assert "<span>après les sections 3 et 14</span>" in html
    assert "<span>question G8</span>" in html
    assert '<td class="ok" colspan="2">réussie : \\(m = -9\\)</td>' in html
    assert '<a href="#c2">Intervalles, valeur absolue, encadrements</a>' in html
    assert '<p class="small">Pour les exercices 1 à 3 :' in html
    assert "le <em>centre</em> de l&#39;intervalle" in html
    # Formule centrée hors paragraphe, comme dans l'exemplaire.
    assert "</p>\n  \\[AB = \\sqrt{6^2 + (-8)^2} = \\sqrt{100} = 10.\\]<p>" in html


def test_emphase_echappe_et_epargne_les_formules():
    assert str(_emphase("*a* <b> \\(x*y*z\\)")) == "<em>a</em> &lt;b&gt; \\(x*y*z\\)"


def test_contenu_genere_echappe(plan):
    plan.competences[0].causes = ["<script>alert(1)</script>"]
    assert "<script>alert(1)" not in render_plan_html(plan)


def test_pdf_chromium(plan, tmp_path):
    pytest.importorskip("playwright")
    from src.pipeline.pdf_plan_remediation import generate_plan_remediation_pdf

    sortie = tmp_path / "plan_remediation.pdf"
    try:
        erreurs = generate_plan_remediation_pdf(sortie, plan)
    except Exception as e:  # Chromium absent du poste : `playwright install chromium`
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium de Playwright non installé")
        raise
    assert erreurs == 0
    import fitz

    assert fitz.open(sortie).page_count == 39
