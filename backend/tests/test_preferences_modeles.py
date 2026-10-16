"""Magasin de préférences de modèles IA (`src/core/preferences_modeles.py`,
D-CEO-44) : défauts `.env`, aller-retour de persistance, validation, résolution.
"""
from __future__ import annotations

import json

import pytest

from src.core import preferences_modeles as pm
from src.core.config import settings


@pytest.fixture(autouse=True)
def _fichier_temporaire(tmp_path, monkeypatch):
    """Isole chaque test : fichier de prefs dédié + cache vidé avant/après."""
    monkeypatch.setenv("PREFERENCES_MODELES_PATH", str(tmp_path / "prefs.json"))
    pm._reinitialiser_cache()
    yield
    pm._reinitialiser_cache()


def test_charger_sans_fichier_rend_les_defauts_env():
    prefs = pm.charger()
    assert set(prefs) == set(pm.TACHES)
    # `.env` de test : VISION_PROVIDER=gemini, DIAGNOSTIC_PROVIDER=claude ; le
    # correcteur suit GRADING_PROVIDER (claude en production depuis le 2026-10-16).
    from src.core.config import settings

    assert prefs["transcription"]["fournisseur"] == "gemini"
    assert prefs["correction"]["fournisseur"] == settings.grading_provider
    assert prefs["analyse"]["fournisseur"] == "claude"
    assert prefs["analyse"]["variante_claude"] == "opus"


def test_enregistrer_puis_charger_reflete_le_changement():
    pm.enregistrer({
        "transcription": {"fournisseur": "claude", "variante_claude": "opus"},
        "correction": {"fournisseur": "claude", "variante_claude": "sonnet"},
        "analyse": {"fournisseur": "deepseek", "variante_claude": "sonnet"},
    })
    prefs = pm.charger()
    assert prefs["transcription"] == {"fournisseur": "claude", "variante_claude": "opus"}
    assert prefs["analyse"]["fournisseur"] == "deepseek"


def test_enregistrer_ecrit_un_json_valide(tmp_path):
    pm.enregistrer(pm.defauts())
    contenu = json.loads((tmp_path / "prefs.json").read_text(encoding="utf-8"))
    assert set(contenu) == set(pm.TACHES)


@pytest.mark.parametrize(
    "tache,fournisseur",
    [
        ("correction", "openai"),   # non autorisé pour la correction
        ("transcription", "deepseek"),
        ("analyse", "mistral"),
    ],
)
def test_valider_rejette_un_fournisseur_hors_liste(tache, fournisseur):
    demande = pm.defauts()
    demande[tache] = {"fournisseur": fournisseur, "variante_claude": "sonnet"}
    with pytest.raises(ValueError):
        pm.valider(demande)


def test_valider_rejette_une_variante_inconnue():
    demande = pm.defauts()
    demande["analyse"] = {"fournisseur": "claude", "variante_claude": "haiku"}
    with pytest.raises(ValueError):
        pm.valider(demande)


def test_resoudre_claude_choisit_le_modele_selon_la_variante():
    pm.enregistrer({
        **pm.defauts(),
        "analyse": {"fournisseur": "claude", "variante_claude": "opus"},
        "correction": {"fournisseur": "claude", "variante_claude": "sonnet"},
    })
    assert pm.resoudre("analyse").modele == settings.claude_model_opus
    assert pm.resoudre("correction").modele == settings.claude_model_heavy


def test_resoudre_non_claude_ne_fixe_pas_de_modele():
    pm.enregistrer({**pm.defauts(), "transcription": {"fournisseur": "gemini", "variante_claude": "sonnet"}})
    r = pm.resoudre("transcription")
    assert r.fournisseur == "gemini"
    assert r.modele is None


def test_cle_presente_reflete_la_config(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "google_api_key", "cle-test")
    assert pm.cle_presente("openai") is False
    assert pm.cle_presente("gemini") is True


def test_catalogue_liste_les_trois_taches_et_les_fournisseurs():
    cat = pm.catalogue()
    assert [t["cle"] for t in cat["taches"]] == list(pm.TACHES)
    correction = next(t for t in cat["taches"] if t["cle"] == "correction")
    assert {f["cle"] for f in correction["fournisseurs"]} == set(pm.FOURNISSEURS_AUTORISES["correction"])


def test_fichier_corrompu_retombe_sur_les_defauts(tmp_path):
    (tmp_path / "prefs.json").write_text("{ pas du json", encoding="utf-8")
    pm._reinitialiser_cache()
    assert pm.charger()["transcription"]["fournisseur"] == "gemini"
