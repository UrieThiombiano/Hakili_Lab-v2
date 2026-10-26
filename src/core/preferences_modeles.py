"""Choix des fournisseurs IA par tâche — magasin de préférences.

Le routage multi-provider (D-CEO-03) était figé dans `.env` (`VISION_PROVIDER`,
`GRADING_PROVIDER`, `DIAGNOSTIC_PROVIDER`). Ce module expose une configuration
**globale** (une seule pour toute la plateforme), persistée dans
`data/preferences_modeles.json`, qui **prime sur `.env`** — ce dernier ne sert
plus que de valeur de repli quand le fichier est absent ou incomplet
(D-CEO-44).

Trois familles de tâches :
- ``transcription`` — lecture des copies (étape `vision_provider` du pipeline)
- ``correction``    — notation selon barème (`grading_provider`)
- ``analyse``       — diagnostic + génération des rapports (`diagnostic_provider`)

Ce module ne connaît ni FastAPI ni SQLAlchemy : le pipeline (`src/pipeline/`)
comme le backend l'importent tel quel.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.core.config import settings

logger = logging.getLogger(__name__)

# ── Vocabulaire ──────────────────────────────────────────────────────────────

TACHES: tuple[str, ...] = ("transcription", "correction", "analyse")

#: Fournisseurs sélectionnables par tâche — liste **fermée**. Un fournisseur
#: hors de cette liste est une erreur (422 côté API), jamais une variante.
FOURNISSEURS_AUTORISES: dict[str, tuple[str, ...]] = {
    "transcription": ("claude", "gemini", "openai"),
    "correction": ("deepseek", "claude", "gemini"),
    "analyse": ("gemini", "claude", "openai", "deepseek"),
}

VARIANTES_CLAUDE: tuple[str, ...] = ("sonnet", "opus")

#: Repli quand `.env` ne désigne pas un fournisseur autorisé pour la tâche
#: (ex. `VISION_PROVIDER=mistral`, retiré de l'offre).
_REPLI: dict[str, str] = {
    "transcription": "gemini",
    "correction": "deepseek",
    "analyse": "claude",
}

#: Libellés d'affichage (l'UI peut les surcharger, gardés ici pour le catalogue API).
LIBELLES_FOURNISSEUR: dict[str, str] = {
    "claude": "Claude (Anthropic)",
    "gemini": "Gemini (Google)",
    "openai": "ChatGPT (OpenAI)",
    "deepseek": "DeepSeek",
}

LIBELLES_TACHE: dict[str, str] = {
    "transcription": "Transcription (lecture des copies)",
    "correction": "Correction",
    "analyse": "Analyse et génération des rapports",
}


@dataclass(frozen=True)
class ResolutionModele:
    """Résultat de `resoudre()` : quel client instancier et, pour Claude, quel modèle."""

    fournisseur: str
    modele: str | None  # renseigné uniquement pour Claude (sinon le client lit son `.env`)


# ── Emplacement du fichier + cache ───────────────────────────────────────────

def _chemin() -> Path:
    """`<racine>/data/preferences_modeles.json`. Surchargable par la variable
    d'environnement ``PREFERENCES_MODELES_PATH`` (tests, déploiements)."""
    surcharge = os.environ.get("PREFERENCES_MODELES_PATH")
    if surcharge:
        return Path(surcharge)
    return Path(__file__).resolve().parents[2] / "data" / "preferences_modeles.json"


_cache: dict | None = None
_cache_mtime: float | None = None


def _reinitialiser_cache() -> None:
    """Vide le cache mémoire — utile aux tests et après `enregistrer()`."""
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None


# ── Défauts (issus de `.env` via `settings`) ─────────────────────────────────

def _defaut_fournisseur(tache: str) -> str:
    brut = {
        "transcription": settings.vision_provider,
        "correction": settings.grading_provider,
        "analyse": settings.diagnostic_provider,
    }[tache].strip().lower()
    return brut if brut in FOURNISSEURS_AUTORISES[tache] else _REPLI[tache]


def _defaut_variante(tache: str) -> str:
    # L'analyse tournait sur `claude_model_opus` (raisonnement approfondi) ;
    # transcription et correction sur `claude_model_heavy` (Sonnet).
    return "opus" if tache == "analyse" else "sonnet"


def _defaut_tache(tache: str) -> dict[str, str]:
    return {
        "fournisseur": _defaut_fournisseur(tache),
        "variante_claude": _defaut_variante(tache),
    }


def defauts() -> dict[str, dict[str, str]]:
    return {tache: _defaut_tache(tache) for tache in TACHES}


# ── Validation ───────────────────────────────────────────────────────────────

def _valider_entree(tache: str, entree: dict) -> dict[str, str]:
    if tache not in TACHES:
        raise ValueError(f"Tâche inconnue : « {tache} ». Attendu : {', '.join(TACHES)}.")
    fournisseur = str(entree.get("fournisseur", "")).strip().lower()
    if fournisseur not in FOURNISSEURS_AUTORISES[tache]:
        raise ValueError(
            f"Fournisseur « {fournisseur or '?'} » non autorisé pour la tâche "
            f"« {tache} ». Autorisés : {', '.join(FOURNISSEURS_AUTORISES[tache])}."
        )
    variante = str(entree.get("variante_claude", "sonnet")).strip().lower()
    if variante not in VARIANTES_CLAUDE:
        raise ValueError(
            f"Variante Claude « {variante} » inconnue. Attendu : {', '.join(VARIANTES_CLAUDE)}."
        )
    return {"fournisseur": fournisseur, "variante_claude": variante}


def valider(prefs: dict) -> dict[str, dict[str, str]]:
    """Normalise et valide un jeu de préférences complet. Lève ``ValueError``."""
    return {tache: _valider_entree(tache, prefs.get(tache, {})) for tache in TACHES}


# ── Lecture / écriture ───────────────────────────────────────────────────────

def charger() -> dict[str, dict[str, str]]:
    """Préférences effectives : fichier fusionné avec les défauts `.env`.

    Rechargement à chaud : le cache est invalidé dès que le `mtime` du fichier
    change (pas besoin de redémarrer le backend après un enregistrement).
    """
    global _cache, _cache_mtime

    chemin = _chemin()
    try:
        mtime = chemin.stat().st_mtime
    except OSError:
        mtime = None

    if _cache is not None and _cache_mtime == mtime:
        return _cache

    resultat = defauts()
    if mtime is not None:
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
            for tache in TACHES:
                if isinstance(brut.get(tache), dict):
                    try:
                        resultat[tache] = _valider_entree(tache, brut[tache])
                    except ValueError as exc:
                        logger.warning(
                            "preferences_modeles : entrée « %s » ignorée (%s) — défaut conservé.",
                            tache, exc,
                        )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "preferences_modeles : lecture de %s impossible (%s) — défauts `.env`.",
                chemin, exc,
            )

    _cache = resultat
    _cache_mtime = mtime
    return resultat


def enregistrer(prefs: dict) -> dict[str, dict[str, str]]:
    """Valide puis écrit le fichier (écriture atomique). Renvoie l'état persisté."""
    valides = valider(prefs)
    chemin = _chemin()
    chemin.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".prefs-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(valides, f, ensure_ascii=False, indent=2)
        os.replace(tmp, chemin)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise

    _reinitialiser_cache()
    logger.info("preferences_modeles enregistrées : %s", valides)
    return valides


# ── Résolution (consommée par le pipeline et le backend) ─────────────────────

def resoudre(tache: str) -> ResolutionModele:
    """Fournisseur retenu pour la tâche + modèle Claude si applicable."""
    if tache not in TACHES:
        raise ValueError(f"Tâche inconnue : « {tache} ».")
    entree = charger()[tache]
    fournisseur = entree["fournisseur"]
    modele: str | None = None
    if fournisseur == "claude":
        modele = (
            settings.claude_model_opus
            if entree["variante_claude"] == "opus"
            else settings.claude_model_heavy
        )
    return ResolutionModele(fournisseur=fournisseur, modele=modele)


# ── Disponibilité des clés API (pour griser l'UI) ────────────────────────────

def _cle_presente(fournisseur: str) -> bool:
    return bool({
        "claude": settings.anthropic_api_key,
        "gemini": settings.google_api_key,
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
    }.get(fournisseur, ""))


def cle_presente(fournisseur: str) -> bool:
    """Expose `_cle_presente` — le routeur l'utilise pour refuser un fournisseur
    sans clé configurée."""
    return _cle_presente(fournisseur)


def catalogue() -> dict:
    """Décrit l'offre pour l'écran Paramètres : fournisseurs par tâche, présence
    de clé API, libellés, et l'état courant."""
    return {
        "taches": [
            {
                "cle": tache,
                "libelle": LIBELLES_TACHE[tache],
                "fournisseurs": [
                    {
                        "cle": f,
                        "libelle": LIBELLES_FOURNISSEUR.get(f, f),
                        "cle_presente": _cle_presente(f),
                    }
                    for f in FOURNISSEURS_AUTORISES[tache]
                ],
            }
            for tache in TACHES
        ],
        "variantes_claude": list(VARIANTES_CLAUDE),
        "preferences": charger(),
    }
