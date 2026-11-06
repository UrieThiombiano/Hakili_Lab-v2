"""
Notation des tests diagnostiques selon le barème détaillé des corrigés v1
(batterie allégée du 2026-10-06), et robustesse de la transcription.

Origine : recette du 2026-10-16 sur 29 copies réelles (TESTS_DIAGNOTICS_SIAO).
- Le modèle de correction recevait des consignes binaires (« 0 ou max_score »,
  « résultat correct sans démarche → point accordé ») contraires aux corrigés,
  qui notent la démarche critère par critère : notes gonflées (P2.3 de 6e à
  3/3 pour la seule conclusion, barème : 1/3).
- Aucun garde-fou ne ramenait un score hors barème sur une valeur admise.
- Une coupure réseau Gemini (WinError 10054) n'était pas réessayée, et le
  repli GPT-5 expirait sur les copies de 12 à 14 pages : ~1 copie sur 6 perdue.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.domain import CopyGrade, PageTranscription, QuestionGrade, Rubric, RubricItem, TranscriptionResult


def _q(qid: str, score: float) -> QuestionGrade:
    return QuestionGrade(rubric_item_id=qid, score=score, confidence=0.95, comment="", observed_answer="x", requires_review=False)


def _rubric() -> Rubric:
    # 6e : A sur 1 pt du corrigé (tout ou rien), N8 sur 2 pts, P1.3 sur 3 pts.
    return Rubric(
        subject="mathematics",
        total_points=20,
        items=[
            RubricItem(id="N1", label="", max_score=0.333333, points_corrige=1, score_step=0.333333),
            RubricItem(id="N8", label="", max_score=0.666667, points_corrige=2, score_step=0.166667),
            RubricItem(id="P1.3", label="", max_score=1.0, points_corrige=3, score_step=0.166667),
        ],
    )


def _valider(*questions: QuestionGrade) -> CopyGrade:
    from src.pipeline.orchestrator import validate_grading

    grade = CopyGrade(copy_id="c", total_score=0, total_possible=20, questions=list(questions))
    return validate_grading(grade, rubric_provided=True, rubric=_rubric()).data


# ── Garde-fou : score ramené sur une valeur admise ────────────────────────────

def test_score_au_dessus_du_maximum_plafonne():
    g = _valider(_q("N1", 1.0), _q("N8", 2.0), _q("P1.3", 3.0))
    assert [q.score for q in g.questions] == pytest.approx([0.333333, 0.666667, 1.0], abs=1e-5)


def test_points_partiels_valides_conserves():
    """1 critère sur 2 (N8), 2 sur 3 (P1.3) : déjà sur la grille, inchangés."""
    g = _valider(_q("N8", 0.333333), _q("P1.3", 0.666667))
    assert [q.score for q in g.questions] == pytest.approx([0.333333, 0.666667], abs=1e-5)


def test_bruit_d_arrondi_du_modele_recale_sur_la_valeur_proche():
    g = _valider(_q("N8", 0.3333), _q("P1.3", 0.67))
    assert [q.score for q in g.questions] == pytest.approx([0.333333, 0.666667], abs=1e-5)


def test_valeur_entre_deux_pas_arrondie_vers_le_bas():
    """Jamais un point que le modèle n'a pas donné."""
    g = _valider(_q("N8", 0.25), _q("N1", 0.2))
    assert [q.score for q in g.questions] == pytest.approx([0.166667, 0.0], abs=1e-5)


def test_score_negatif_ramene_a_zero():
    assert _valider(_q("N8", -0.5)).questions[0].score == 0.0


def test_total_recalcule_apres_recalage():
    g = _valider(_q("N1", 1.0), _q("N8", 0.3333))
    assert g.total_score == pytest.approx(0.666666, abs=1e-5)


def test_recalage_signale():
    from src.pipeline.orchestrator import validate_grading

    grade = CopyGrade(copy_id="c", total_score=0, total_possible=20, questions=[_q("N1", 1.0)])
    issues = validate_grading(grade, rubric_provided=True, rubric=_rubric()).issues
    assert any(i.code == "SCORE_HORS_BAREME" and i.auto_fixed for i in issues)


def _qp(qid: str, points: float, score: float = 0.0) -> QuestionGrade:
    q = _q(qid, score)
    q.points_obtenus = points
    return q


def test_points_du_corrige_convertis_par_le_systeme():
    """Le modèle compte les points du corrigé ; son `score` est ignoré."""
    g = _valider(_qp("N8", 1, score=0.166667), _qp("P1.3", 2.5, score=0.9), _qp("N1", 1))
    assert [q.score for q in g.questions] == pytest.approx([0.333333, 0.833333, 0.333333], abs=1e-5)


def test_points_du_corrige_bornes_et_arrondis():
    g = _valider(_qp("N8", 5), _qp("P1.3", -1), _qp("N1", 0.4))
    assert [q.score for q in g.questions] == pytest.approx([0.666667, 0.0, 0.0], abs=1e-5)


def test_bareme_binaire_historique_inchange():
    """Sans score_step (anciens tests, mode libre) : seul le plafond s'applique."""
    from src.pipeline.orchestrator import validate_grading

    rubric = Rubric(subject="mathematics", total_points=2, items=[RubricItem(id="Q1", label="", max_score=1.0)])
    grade = CopyGrade(copy_id="c", total_score=0, total_possible=2, questions=[_q("Q1", 1.0)])
    assert validate_grading(grade, rubric_provided=True, rubric=rubric).data.questions[0].score == 1.0


# ── Le barème socle porte ses points et son pas ───────────────────────────────

@pytest.mark.parametrize("niveau,points_a", [("6eme", 3), ("tleD", 4)])
def test_rubric_socle_porte_points_et_pas(niveau, points_a):
    from src.knowledge.test_registry import get_registry

    items = {i.id: i for i in get_registry().get_test(f"socle_{niveau}").rubric.items}
    n1 = items["N1"]
    assert n1.points_corrige == 1 and n1.score_step == pytest.approx(n1.max_score)
    p13 = items["P1.3"]
    assert p13.points_corrige == 3
    # Demi-point du corrigé : 0,5 / (60 ou 80) × 20.
    assert p13.score_step == pytest.approx(0.5 / points_a, abs=1e-6)


def test_corrige_injecte_porte_les_points_et_le_bareme():
    from src.knowledge.answer_loader import get_answer_loader

    bloc = get_answer_loader().get_official_answers("socle_6eme")
    assert "N10 (2 pts au corrigé) →" in bloc
    assert "Barème : 1 pt pour la division euclidienne" in bloc
    assert "note critère par critère" in bloc


def test_consignes_de_notation_barème_detaille():
    texte = (Path(__file__).parent.parent / "prompts" / "grading_prompt.md").read_text(encoding="utf-8")
    assert "Barème détaillé par critère" in texte
    assert "points_obtenus" in texte and "Ne convertis rien" in texte
    assert "sans tenir compte de la casse" in texte
    # Les règles binaires ne s'appliquent plus qu'aux items sans barème détaillé.
    assert "qu'aux items sans barème détaillé" in texte


# ── Transcription : erreurs passagères réessayées ─────────────────────────────

@pytest.mark.parametrize(
    "erreur",
    [
        ConnectionResetError(10054, "Une connexion existante a dû être fermée par l'hôte distant"),
        OSError("[WinError 10054] Une connexion existante a dû être fermée par l'hôte distant"),
        TimeoutError("Request timed out."),
        RuntimeError("503 UNAVAILABLE. The model is overloaded."),
        RuntimeError("429 RESOURCE_EXHAUSTED"),
    ],
)
def test_gemini_erreurs_passageres_reessayees(erreur):
    from src.api.gemini_client import _is_retryable_gemini

    assert _is_retryable_gemini(erreur)


@pytest.mark.parametrize(
    "erreur",
    [RuntimeError("429 Quota exceeded for GenerateRequestsPerDayPerProjectPerModel"), ValueError("400 INVALID_ARGUMENT")],
)
def test_gemini_erreurs_definitives_non_reessayees(erreur):
    from src.api.gemini_client import _is_retryable_gemini

    assert not _is_retryable_gemini(erreur)


def test_gpt5_transcrit_par_lots_et_renumerote(monkeypatch, tmp_path):
    """14 pages → 5 lots de 3 au plus, pages renumérotées 1..14 dans l'ordre."""
    from src.api import openai_client as oc
    from src.models.domain import ClaudeResponse

    appels: list[tuple[int, int]] = []

    def faux_lot(self, copy_id, image_paths, page_offset):
        appels.append((page_offset, len(image_paths)))
        pages = [
            PageTranscription(page_number=i + 1, content=f"p{page_offset + i + 1}", confidence=0.9)
            for i in range(len(image_paths))
        ]
        return ClaudeResponse(success=True, data=TranscriptionResult(copy_id=copy_id, global_quality="good", pages=pages),
                              confidence=0.9, raw_response="", error=None)

    monkeypatch.setattr(oc.OpenAIClient, "_transcrire_lot", faux_lot)
    client = object.__new__(oc.OpenAIClient)
    images = [tmp_path / f"{i}.png" for i in range(14)]

    rep = client.transcribe("c", images)

    assert rep.success
    assert sorted(appels) == [(0, 3), (3, 3), (6, 3), (9, 3), (12, 2)]
    assert [p.page_number for p in rep.data.pages] == list(range(1, 15))
    assert [p.content for p in rep.data.pages] == [f"p{i}" for i in range(1, 15)]


def test_gpt5_un_lot_en_echec_fait_echouer_la_transcription(monkeypatch, tmp_path):
    from src.api import openai_client as oc
    from src.models.domain import ClaudeResponse

    def faux_lot(self, copy_id, image_paths, page_offset):
        if page_offset == 3:
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error="Request timed out.")
        pages = [PageTranscription(page_number=1, content="", confidence=0.9) for _ in image_paths]
        return ClaudeResponse(success=True, data=TranscriptionResult(copy_id=copy_id, global_quality="good", pages=pages),
                              confidence=0.9, raw_response="", error=None)

    monkeypatch.setattr(oc.OpenAIClient, "_transcrire_lot", faux_lot)
    client = object.__new__(oc.OpenAIClient)
    rep = client.transcribe("c", [tmp_path / f"{i}.png" for i in range(6)])
    assert not rep.success and "timed out" in rep.error


def test_gpt5_lot_reessaye_apres_expiration(monkeypatch, tmp_path):
    from src.api import openai_client as oc

    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG")
    tentatives = {"n": 0}

    class FauxCompletions:
        def create(self, **_):
            tentatives["n"] += 1
            if tentatives["n"] == 1:
                raise TimeoutError("Request timed out.")
            contenu = '{"copy_id": "c", "global_quality": "good", "pages": [{"page_number": 1, "content": "ok", "confidence": 0.9}]}'
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=contenu))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    faux_client = SimpleNamespace(with_options=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=FauxCompletions())))
    client = object.__new__(oc.OpenAIClient)
    client._client = faux_client
    client._transcription_prompt = "consignes"
    monkeypatch.setattr(oc.time, "sleep", lambda _s: None)

    rep = client._transcrire_lot("c", [image], 0)

    assert rep.success and tentatives["n"] == 2


# ── Consolidation de plusieurs corrections IA ─────────────────────────────────

def _grade(*questions: QuestionGrade) -> CopyGrade:
    return CopyGrade(copy_id="c", total_score=sum(q.score for q in questions), total_possible=20, questions=list(questions))


def test_mediane_met_en_minorite_un_passage_hallucine():
    """Recette 2026-10-16 : un passage recopie le corrigé (tout juste), deux
    passages lisent la copie (faux) — la médiane retient la lecture fidèle."""
    from src.pipeline.orchestrator import consolider_corrections

    fideles = [_grade(_q("N8", 0.0), _q("P1.3", 0.333333)) for _ in range(2)]
    hallucine = _grade(_q("N8", 0.666667), _q("P1.3", 1.0))
    g = consolider_corrections([hallucine, *fideles], _rubric())
    assert [q.score for q in g.questions] == [0.0, 0.333333]
    assert g.total_score == pytest.approx(0.333333)


def test_divergence_signalee_a_l_enseignant():
    from src.pipeline.orchestrator import consolider_corrections

    g = consolider_corrections(
        [_grade(_q("N8", 0.0)), _grade(_q("N8", 0.666667)), _grade(_q("N8", 0.666667))], _rubric()
    )
    q = g.questions[0]
    assert q.score == pytest.approx(0.666667)
    assert q.requires_review and q.confidence <= 0.6
    assert "divergentes" in q.comment


def test_ecart_d_un_pas_non_signale():
    from src.pipeline.orchestrator import consolider_corrections

    g = consolider_corrections(
        [_grade(_q("N8", 0.333333)), _grade(_q("N8", 0.5)), _grade(_q("N8", 0.333333))], _rubric()
    )
    assert g.questions[0].score == pytest.approx(0.333333)
    assert not g.questions[0].requires_review


def test_deux_passages_mediane_basse():
    from src.pipeline.orchestrator import consolider_corrections

    g = consolider_corrections([_grade(_q("N8", 0.666667)), _grade(_q("N8", 0.0))], _rubric())
    assert g.questions[0].score == 0.0


def test_un_seul_passage_inchange():
    from src.pipeline.orchestrator import consolider_corrections

    seul = _grade(_q("N8", 0.333333))
    assert consolider_corrections([seul], _rubric()) is seul


# ── Rendu du rapport et diagnostic sur barème détaillé ────────────────────────

def test_rapport_trois_categories_et_points_du_corrige():
    """Une réponse partielle n'est pas rangée parmi les « bonnes réponses », et
    les points s'affichent comme sur le corrigé papier (1 / 2), pas en /20."""
    from src.pipeline.pdf_report_html import _build_context

    grade = _grade(_q("N1", 0.333333), _q("N8", 0.333333), _q("P1.3", 0.0))
    ctx = _build_context("c", grade, None, "Élève", rubric=_rubric())
    assert [q["id"] for q in ctx["good_questions"]] == ["N1"]
    assert [q["id"] for q in ctx["partial_questions"]] == ["N8"]
    assert [q["id"] for q in ctx["bad_questions"]] == ["P1.3"]
    n8 = ctx["partial_questions"][0]
    assert (n8["score_fmt"], n8["max_fmt"]) == ("1", "2")
    assert ctx["POINTS_CORRIGE"] and ctx["TOTAL_CORRIGE"] == "6"


def test_diagnostic_recoit_des_taux_de_reussite():
    from src.pipeline.pipeline import _grade_en_taux

    g = _grade_en_taux(_grade(_q("N1", 0.333333), _q("N8", 0.333333), _q("P1.3", 0.0)), _rubric())
    assert [q.score for q in g.questions] == [1.0, 0.5, 0.0]


def test_faiblesse_sur_reponse_partielle_conservee():
    """Une réponse partielle (taux 0,5) peut porter une faiblesse : seule une
    question entièrement réussie (taux 1) fait retirer la faiblesse."""
    from src.models.domain import DiagnosticResult
    from src.pipeline.orchestrator import validate_diagnostic

    g = _grade(_q("N1", 1.0), _q("N8", 0.5))
    diag = DiagnosticResult(
        copy_id="c", strengths=[], weaknesses=["Résultat juste mais division non posée à la question N8"],
        root_causes=[], remediation_plan=[], skills=[],
    )
    assert validate_diagnostic(diag, g).data.weaknesses == diag.weaknesses


def test_compte_annonce_dans_le_commentaire_fait_foi():
    """Recette 2026-10-16 : « 1/2 : division non montrée… » avec
    points_obtenus = 0.5 (proportion au lieu d'un compte) → 1 point sur 2."""
    q = _qp("N8", 0.5)
    q.comment = "1/2 : division non montrée, conclusion correcte"
    q2 = _qp("P1.3", 0.5)
    q2.comment = "1 pt sur 3 : conclusion seule"
    g = _valider(q, q2)
    assert [x.score for x in g.questions] == pytest.approx([0.333333, 0.333333], abs=1e-5)


def test_commentaire_sans_compte_ou_autre_denominateur_ignore():
    q = _qp("N8", 1)
    q.comment = "Calcul 3/4 de 60 juste"
    assert _valider(q).questions[0].score == pytest.approx(0.333333, abs=1e-5)


def test_points_obtenus_alignes_sur_la_note_retenue():
    """Recette 2026-10-17 (L6) : points_obtenus = 0.5 mais « 0 pt sur 2 » —
    la note retient 0, points_obtenus doit dire la même chose."""
    q = _qp("N8", 0.5)
    q.comment = "0 pt sur 2 : factorisation incomplète"
    g = _valider(q)
    assert g.questions[0].score == 0.0
    assert g.questions[0].points_obtenus == 0.0


def test_outil_de_correction_demande_l_analyse_avant_la_note():
    from src.api.claude_client import _GRADING_TOOL

    item = _GRADING_TOOL["input_schema"]["properties"]["questions"]["items"]
    cles = list(item["properties"])
    assert "analyse" in item["required"]
    assert cles.index("analyse") < cles.index("points_obtenus")
    assert cles.index("analyse") < cles.index("comment")
