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


# ── Génération : du squelette au plan ─────────────────────────────────────────

from src.models.domain import (  # noqa: E402
    ClaudeResponse,
    ContenuAcquis,
    ContenuSection,
    DemandePlan,
    QuestionPlan,
    SectionPlanDemande,
)
from src.pipeline.plan_remediation import PlanIncomplet, generer_plan, plan_requis  # noqa: E402


def _contenu(i: int) -> ContenuSection:
    """Contenu de la section i de l'exemplaire, au format rendu par le modèle."""
    c = _donnees()["competences"][i]
    return ContenuSection.model_validate({k: c[k] for k in ContenuSection.model_fields})


def _demande(n: int = 3) -> DemandePlan:
    sections = [
        SectionPlanDemande(
            ordre=i, code_competence=f"C{i}", libelle_competence=f"Compétence {i}", duree_h=2.0,
            prerequis=[1] if i == 3 else [],
            questions=[QuestionPlan(code=f"Q{i}"), QuestionPlan(code=f"R{i}", reussie=True)],
        )
        for i in range(1, n + 1)
    ]
    return DemandePlan(
        copy_id="c1", eleve_nom="NIKIEMA K. Amale", prenom="Amale", classe="1ère D",
        test_libelle="test diagnostique d'entrée en 1ère D", date="26 octobre 2026",
        sections=sections, questions_reussies=[QuestionPlan(code="R1", reussie=True)],
    )


class _ClientFactice:
    def __init__(self, echecs: dict[int, int] | None = None, acquis_ok: bool = True):
        self.echecs = dict(echecs or {})  # ordre de section → nombre d'échecs avant succès
        self.acquis_ok = acquis_ok
        self.appels: list[int] = []
        self.tentatives: list[tuple[int, str, str | None]] = []  # (section, refus reçu, modèle)

    modele_repli = "modele-de-repli"

    def generate_plan_section(self, demande, section, refus="", modele=None):
        self.appels.append(section.ordre)
        self.tentatives.append((section.ordre, refus, modele))
        if self.echecs.get(section.ordre, 0) > 0:
            self.echecs[section.ordre] -= 1
            return ClaudeResponse(success=False, data=None, confidence=0, raw_response="",
                                  error="1 validation error for ContenuSection\ncauses\n  List should have at least 1 item\n"
                                        "    For further information visit https://errors.pydantic.dev/2.13/v/too_short")
        return ClaudeResponse(success=True, data=_contenu(section.ordre - 1), confidence=1, raw_response="")

    def generate_plan_acquis(self, demande):
        if not self.acquis_ok:
            raise RuntimeError("API indisponible")
        return ClaudeResponse(success=True, data=ContenuAcquis(acquis=["Lire un graphique (R1)."]),
                              confidence=1, raw_response="")


def test_plan_requis_sous_19_seulement():
    assert plan_requis(18.75) and plan_requis(None)
    assert not plan_requis(19.0) and not plan_requis(20.0)


def test_generer_plan_assemble_squelette_et_contenu():
    plan = generer_plan(_demande(), _ClientFactice())
    assert [c.titre for c in plan.competences] == [
        "Racines carrées et radicaux", "Intervalles, valeur absolue et encadrements",
        "Vecteurs : relation de Chasles et alignement",
    ]
    # Durée, prérequis, code : du squelette, jamais du modèle.
    assert [c.duree_h for c in plan.competences] == [2.0, 2.0, 2.0]
    assert plan.competences[2].prerequis == [1]
    assert plan.competences[0].code_competence == "C1"
    # Seules les questions en erreur figurent en tête de section.
    assert plan.competences[0].questions == ["Q1"]
    assert plan.acquis == ["Lire un graphique (R1)."]
    assert "Racines carrées" in render_plan_html(plan)


def test_section_en_echec_redemandee_une_fois():
    client = _ClientFactice(echecs={2: 1})
    plan = generer_plan(_demande(), client)
    assert len(plan.competences) == 3
    assert client.appels.count(2) == 2


def test_motif_du_refus_rendu_au_modele_puis_modele_de_repli():
    client = _ClientFactice(echecs={2: 3})
    plan = generer_plan(_demande(), client)
    assert len(plan.competences) == 3
    tentatives = [(refus, modele) for ordre, refus, modele in client.tentatives if ordre == 2]
    assert tentatives[0] == ("", None)
    # Le motif est rendu, sans le lien de documentation de pydantic.
    assert "List should have at least 1 item" in tentatives[1][0]
    assert "errors.pydantic.dev" not in tentatives[1][0]
    # Trois tentatives sur le modèle principal, la quatrième sur le repli.
    assert [m for _, m in tentatives] == [None, None, None, "modele-de-repli"]


def test_section_en_echec_a_chaque_tentative_pas_de_plan():
    with pytest.raises(PlanIncomplet, match="section 2"):
        generer_plan(_demande(), _ClientFactice(echecs={2: 4}))


def test_objet_vide_dans_une_liste_de_textes_retire():
    """Essai réel du 2026-10-26 : Opus 5 a rendu `causes: [{}]`."""
    from src.api.claude_client import ClaudeClient

    data = {"causes": [{}, "Cause réelle.", {"texte": "Autre cause."}, "  "], "methode": [{"a": "x", "b": "y"}]}
    assert ClaudeClient._normaliser_listes_texte(data) == {
        "causes": ["Cause réelle.", "Autre cause."], "methode": [],
    }


def test_acquis_en_echec_n_empeche_pas_le_plan():
    plan = generer_plan(_demande(), _ClientFactice(acquis_ok=False))
    assert plan.acquis == [] and len(plan.competences) == 3


def test_demande_sans_section_pas_de_plan():
    with pytest.raises(PlanIncomplet):
        generer_plan(_demande(0), _ClientFactice())


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
