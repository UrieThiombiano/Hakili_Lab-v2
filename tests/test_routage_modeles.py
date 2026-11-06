"""Routage des fournisseurs IA piloté par `preferences_modeles` (D-CEO-44) :
sélection du client par étape du pipeline + parsing JSON du client Gemini
étendu (`grade` / `diagnose`).
"""
from __future__ import annotations

import pytest

from src.api.gemini_client import _parse_structured
from src.core import preferences_modeles as pm
from src.models.domain import CopyGrade, DiagnosticResult, Rubric
from src.pipeline import pipeline


# ── Parsing structuré Gemini ────────────────────────────────────────────────

def test_parse_structured_correction_valide():
    brut = (
        '{"copy_id": "C1", "total_score": 1, "total_possible": 2, '
        '"questions": [{"rubric_item_id": "Q1", "score": 1, "confidence": 0.9, '
        '"comment": "ok", "observed_answer": "x=2", "requires_review": false}]}'
    )
    r = _parse_structured(brut, CopyGrade)
    assert r.success and isinstance(r.data, CopyGrade)
    assert r.data.total_possible == 2


def test_parse_structured_repare_un_json_tronque():
    brut = '{"copy_id": "C1", "strengths": ["algèbre"], "weaknesses": ["fractions"'
    r = _parse_structured(brut, DiagnosticResult)
    assert r.success and isinstance(r.data, DiagnosticResult)


def test_parse_structured_echec_renvoie_success_false():
    r = _parse_structured("pas du tout du json", CopyGrade)
    assert r.success is False
    assert r.data is None


# ── Sélection du client par étape ───────────────────────────────────────────

@pytest.fixture
def _prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("PREFERENCES_MODELES_PATH", str(tmp_path / "prefs.json"))
    pm._reinitialiser_cache()
    yield pm
    pm._reinitialiser_cache()


def test_grading_client_suit_la_preference_gemini(_prefs, monkeypatch):
    _prefs.enregistrer({
        **_prefs.defauts(),
        "correction": {"fournisseur": "gemini", "variante_claude": "sonnet"},
    })
    marqueur = object()
    monkeypatch.setattr("src.api.gemini_client.GeminiTranscriptionClient", lambda: marqueur)
    assert pipeline._make_grading_client() is marqueur


def test_diagnostic_client_claude_opus_passe_le_modele(_prefs, monkeypatch):
    _prefs.enregistrer({
        **_prefs.defauts(),
        "analyse": {"fournisseur": "claude", "variante_claude": "opus"},
    })
    recu = {}
    monkeypatch.setattr(
        pipeline, "ClaudeClient",
        lambda **kw: recu.update(kw) or "client-claude",
    )
    assert pipeline._make_diagnostic_client() == "client-claude"
    from src.core.config import settings
    assert recu == {"modele_opus": settings.claude_model_opus}


def test_transcription_client_openai(_prefs, monkeypatch):
    _prefs.enregistrer({
        **_prefs.defauts(),
        "transcription": {"fournisseur": "openai", "variante_claude": "sonnet"},
    })
    monkeypatch.setattr(pipeline, "OpenAIClient", lambda: "client-openai")
    assert pipeline._make_transcription_client() == "client-openai"


# ── Le choix de Paramètres est strict (2026-11-06) ──────────────────────────
# Une transcription Gemini en échec (crédits épuisés) basculait en silence sur
# GPT-5, et l'enseignant voyait l'erreur d'OpenAI au lieu de celle de Gemini.

def test_fournisseur_sans_cle_arrete_au_lieu_de_basculer(_prefs, monkeypatch):
    monkeypatch.setattr(pipeline.preferences_modeles, "cle_presente", lambda f: f != "gemini")
    monkeypatch.setattr(
        pipeline.preferences_modeles, "resoudre",
        lambda tache: pm.ResolutionModele(fournisseur="gemini", modele=None),
    )
    with pytest.raises(RuntimeError, match="Gemini"):
        pipeline._make_transcription_client()


def test_echec_transcription_sans_repli_gpt5(_prefs, monkeypatch, tmp_path):
    from types import SimpleNamespace

    class ClientEnPanne:
        def transcribe(self, copy_id, pages):
            return SimpleNamespace(success=False, data=None, error="402 credits are depleted")

    appels_openai = []
    monkeypatch.setattr(pipeline, "_make_transcription_client", lambda: ClientEnPanne())
    monkeypatch.setattr(pipeline, "OpenAIClient", lambda *a, **k: appels_openai.append(1))
    monkeypatch.setattr(pipeline, "_verifier_eleve", lambda **k: {"classe": "3e"})
    monkeypatch.setattr(
        pipeline, "ingest_images",
        lambda paths, copy_id, out: SimpleNamespace(pages=[object()]),
    )
    img = tmp_path / "p1.png"
    img.write_bytes(b"x")

    r = pipeline.run_transcription(
        file_paths=[img], copy_id="C1", student_name="Feryel Sanou",
        identifiant_hakili="H1", runs_dir=tmp_path,
        rubric=Rubric(subject="mathematics", total_points=0, items=[]),
    )

    assert appels_openai == []
    assert any("402 credits are depleted" in e for e in r.errors)
