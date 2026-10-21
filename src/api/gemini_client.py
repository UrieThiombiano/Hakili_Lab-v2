"""
GeminiTranscriptionClient — transcription via Google Gemini Flash.

Modèle actif : GEMINI_MODEL dans .env (défaut : gemini-1.5-flash-latest)
  - Tier gratuit : 15 RPM, 1 000 000 tokens/jour  → $0 pour une classe entière
  - Tier payant  : ~$0.075 input / $0.30 output par million de tokens

Ce client remplace ClaudeClient.transcribe() quand VISION_PROVIDER=gemini.
Toutes les autres étapes (correction, diagnostic, remédiation) restent sur Claude/DeepSeek/Mistral.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.models.domain import (
    ClaudeResponse,
    CopyGrade,
    DiagnosticResult,
    PageTranscription,
    Rubric,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

_MAX_PAGES_PER_BATCH = 3   # Gemini gère plusieurs pages par appel → moins d'appels
_MAX_OUTPUT_TOKENS = 16384

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


# ── Normalisation JSON (identique à ClaudeClient pour cohérence) ──────────────

def _item_to_str(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("expression", "formula", "formule"):
            if key in item:
                val = str(item[key])
                note = item.get("interpretation") or item.get("annotation")
                return f"{val} ({note})" if note else val
        for key in ("zone", "area", "location"):
            if key in item:
                zone = str(item[key])
                note = item.get("note") or item.get("description") or item.get("issue")
                return f"{zone} : {note}" if note else zone
        for key in ("description", "desc", "content"):
            if key in item:
                return str(item[key])
        for v in item.values():
            if v:
                return str(v)
    return str(item)


def _normalize_transcription(data: Any) -> dict:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {"copy_id": "unknown", "global_quality": "poor", "pages": []}
    if not isinstance(data, dict):
        return {"copy_id": "unknown", "global_quality": "poor", "pages": []}

    if "global_quality" not in data or data["global_quality"] not in ("good", "medium", "poor"):
        data["global_quality"] = "medium"
    data["copy_id"] = str(data["copy_id"]) if "copy_id" in data else "unknown"

    raw_pages = data.get("pages", [])
    if not isinstance(raw_pages, list):
        raw_pages = []

    normalized: list[dict] = []
    for i, page in enumerate(raw_pages):
        if isinstance(page, str):
            normalized.append({
                "page_number": i + 1,
                "content": page,
                "formulas": [],
                "diagrams": [],
                "uncertainties": [],
                "confidence": 0.5,
            })
        elif isinstance(page, dict):
            if not isinstance(page.get("content"), str):
                page["content"] = str(page.get("content") or "")
            for field in ("formulas", "diagrams", "uncertainties"):
                val = page.get(field, [])
                if not isinstance(val, list):
                    val = [val] if val else []
                page[field] = [_item_to_str(x) for x in val if x is not None]
            normalized.append(page)

    data["pages"] = normalized
    return data


def _repair_json(text: str) -> str:
    """Retire les virgules trailing et ferme les accolades/crochets non fermés."""
    stack: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c in ("{", "["):
                stack.append(c)
            elif c in ("}", "]") and stack:
                stack.pop()
        i += 1
    close_map = {"[": "]", "{": "}"}
    return text + "".join(close_map[c] for c in reversed(stack))


# ── Schémas JSON pour correction / diagnostic (repris de deepseek_client.py) ──

_GRADING_SCHEMA = """
{
  "copy_id": "<string>",
  "total_score": <nombre décimal, ex: 12.5>,
  "total_possible": <nombre décimal, ex: 20.0>,
  "questions": [
    {
      "rubric_item_id": "<string — id EXACT du RubricItem du barème>",
      "score": <0 si incorrect, ou valeur exacte de max_score si correct (items à barème détaillé : recalculé par le système depuis points_obtenus)>,
      "points_obtenus": <UNIQUEMENT si le RubricItem porte points_corrige : points DU CORRIGÉ obtenus, critère par critère (ex. 1 sur 2, 2.5 sur 3), multiple de 0.5 ; sinon null>,
      "confidence": <float 0.0-1.0>,
      "comment": "<1 phrase bienveillante pour l'enseignant>",
      "observed_answer": "<ce que l'élève a écrit, résumé en 1 ligne — '—' si absent>",
      "requires_review": <true|false>
    }
  ]
}
"""

_DIAGNOSTIC_SCHEMA = """
{
  "copy_id": "<string>",
  "strengths": ["<string>", ...],
  "weaknesses": ["<string>", ...],
  "root_causes": [
    {"visible_error": "<string>", "hidden_cause": "<string>", "linked_questions": ["Q1", ...]}
  ],
  "skills": [
    {"name": "<string>", "level": "<mastered|partial|weak|unknown>", "evidence": "<string>"}
  ],
  "remediation_plan": [
    {"priority": <integer, 1 = plus haute>, "topic": "<string>", "action": "<string>"}
  ]
}
"""


def _parse_structured(raw: str, model_cls: type) -> ClaudeResponse:
    """Parse tolérant d'une réponse JSON structurée → `ClaudeResponse`.

    Renvoie `success=False` en cas d'échec pour laisser le pipeline basculer
    sur le fallback GPT-5 (`openai_client.py`)."""
    text = (raw or "").strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    text = _TRAILING_COMMA.sub(r"\1", text)

    for candidate in (text, _repair_json(text)):
        candidate = _TRAILING_COMMA.sub(r"\1", candidate)
        try:
            data = json.loads(candidate)
            validated = model_cls(**data)
            return ClaudeResponse(
                success=True, data=validated, confidence=0.85,
                raw_response=raw[:2000], error=None,
            )
        except (json.JSONDecodeError, Exception):
            continue

    logger.error("Gemini — JSON structuré irréparable (%s). Début : %.300s",
                 model_cls.__name__, raw)
    return ClaudeResponse(
        success=False, data=None, confidence=0.0, raw_response=(raw or "")[:500],
        error=f"JSON invalide retourné par Gemini ({model_cls.__name__}).",
    )


# ── Retry 429 ────────────────────────────────────────────────────────────────

# Erreurs passagères observées en recette (2026-10-16, copies SIAO) : une
# coupure réseau en cours d'appel (« WinError 10054 … fermée par l'hôte
# distant ») faisait échouer toute la copie, puis le repli GPT-5 expirait.
_TRANSITOIRES_GEMINI = (
    "429", "resource_exhausted", "quota",
    "500", "502", "503", "504", "unavailable", "internal", "overloaded", "deadline",
    "timed out", "timeout", "10054", "10060", "connection reset", "connection aborted",
    "remote end closed", "server disconnected", "remotedisconnected", "connecterror", "readerror",
)


def _is_retryable_gemini(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__} {exc}".lower()
    # Quota journalier épuisé : inutile de réessayer, aller directement au fallback
    if "perday" in msg:
        return False
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return any(motif in msg for motif in _TRANSITOIRES_GEMINI)


_retry_gemini = retry(
    retry=retry_if_exception(_is_retryable_gemini),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=6, max=60),
    reraise=True,
)


# ── Client principal ──────────────────────────────────────────────────────────

# Ordre de fallback automatique si le modèle configuré est introuvable (404)
_GEMINI_FALLBACKS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.0-flash",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash",
]


class GeminiTranscriptionClient:
    """Gemini Flash — transcription, correction et diagnostic.

    (Nom historique : le client ne faisait que transcrire. Il porte désormais
    aussi `grade()` et `diagnose()`, sélectionnables depuis Paramètres →
    Modèles IA. Alias `GeminiClient` plus bas.)"""

    def __init__(self) -> None:
        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY manquante. Ajoutez-la dans .env pour utiliser Gemini."
            )
        self._client = genai.Client(api_key=settings.google_api_key)
        self._model = self._probe_model(settings.gemini_model)
        self._transcription_prompt = self._load_prompt("transcription_prompt.md")
        self._grading_prompt = self._load_prompt("grading_prompt.md")
        self._diagnostic_prompt = self._load_prompt("diagnostic_prompt.md")
        logger.info("GeminiTranscriptionClient initialisé (modèle=%s)", self._model)

    def _probe_model(self, configured: str) -> str:
        """Vérifie que le modèle est disponible ; essaie les fallbacks sinon."""
        candidates = [configured] + [m for m in _GEMINI_FALLBACKS if m != configured]
        for model in candidates:
            try:
                self._client.models.generate_content(
                    model=model,
                    contents="test",
                    config=types.GenerateContentConfig(max_output_tokens=1),
                )
                if model != configured:
                    logger.warning(
                        "Gemini : modèle '%s' indisponible — fallback automatique → '%s'",
                        configured, model,
                    )
                return model
            except Exception as e:
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    logger.debug("Gemini probe : '%s' introuvable, essai suivant…", model)
                    continue
                # Autre erreur (auth, quota…) → on garde le modèle configuré
                logger.warning("Gemini probe '%s' erreur non-404 : %s — modèle conservé.", model, e)
                return configured
        logger.error(
            "Gemini : aucun modèle disponible parmi %s. Vérifiez votre clé API.",
            candidates,
        )
        return configured

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / filename
        return prompt_path.read_text(encoding="utf-8")

    # ── API publique (même signature que ClaudeClient.transcribe) ─────────────

    def transcribe(self, copy_id: str, image_paths: list[Path]) -> ClaudeResponse:
        try:
            if len(image_paths) <= _MAX_PAGES_PER_BATCH:
                return self._transcribe_batch(copy_id, image_paths, page_offset=0)
            return self._transcribe_batched(copy_id, image_paths)
        except Exception as e:
            # Tenacity a épuisé ses tentatives et re-lève l'exception.
            # On la convertit en ClaudeResponse(success=False) pour déclencher
            # proprement le fallback GPT-5 dans le pipeline.
            logger.error(
                "Gemini transcription abandonnée après retries (copy_id=%s) : %s",
                copy_id, e,
            )
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response="", error=str(e),
            )

    # ── Nom de l'élève depuis la première page ────────────────────────────────

    def extract_student_name(self, first_page: Path) -> str:
        """
        Lit la première page de la copie et retourne le nom complet de l'élève.
        Cherche les champs NOM / PRENOM / NOM ET PRENOM / NAME typiques d'une
        feuille d'examen. Retourne une chaîne vide si rien n'est trouvé ou en
        cas d'erreur — le pipeline retente alors avec Claude.
        """
        prompt = (
            "Regarde cette image de copie d'élève. "
            "Trouve le nom et le prénom de l'élève (champs NOM, PRENOM, "
            "NOM ET PRENOM, ou équivalent). "
            "Retourne UNIQUEMENT le nom complet sous la forme 'Prénom NOM', "
            "sans aucun autre texte ni ponctuation. "
            "Si tu ne trouves pas de nom, retourne exactement la chaîne vide."
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt, Image.open(first_page)],
                config=types.GenerateContentConfig(max_output_tokens=64, temperature=0),
            )
            name = (response.text or "").strip()
            if len(name) > 80 or "\n" in name:
                return ""
            return name
        except Exception as e:
            logger.warning("Gemini extract_student_name échoué : %s", e)
            return ""

    # ── Batching ──────────────────────────────────────────────────────────────

    def _transcribe_batched(self, copy_id: str, image_paths: list[Path]) -> ClaudeResponse:
        batches = [
            (start, image_paths[start : start + _MAX_PAGES_PER_BATCH])
            for start in range(0, len(image_paths), _MAX_PAGES_PER_BATCH)
        ]

        batch_results: list[tuple[int, ClaudeResponse]] = []
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            future_to_offset = {
                pool.submit(self._transcribe_batch, copy_id, batch, offset): offset
                for offset, batch in batches
            }
            for fut in as_completed(future_to_offset):
                offset = future_to_offset[fut]
                try:
                    resp = fut.result()
                except Exception as exc:
                    logger.error("Gemini batch (offset=%d, copy_id=%s) exception : %s", offset, copy_id, exc)
                    return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
                if not resp.success or resp.data is None:
                    return resp
                batch_results.append((offset, resp))

        # Trier par offset pour garantir l'ordre des pages
        batch_results.sort(key=lambda x: x[0])

        all_pages: list[PageTranscription] = []
        qualities: list[str] = []
        for _, resp in batch_results:
            data: TranscriptionResult = resp.data
            all_pages.extend(data.pages)
            qualities.append(data.global_quality)

        global_quality: str = (
            "poor" if "poor" in qualities
            else "medium" if "medium" in qualities
            else "good"
        )
        merged = TranscriptionResult(
            copy_id=copy_id,
            global_quality=global_quality,  # type: ignore[arg-type]
            pages=all_pages,
        )
        avg_conf = sum(p.confidence for p in all_pages) / len(all_pages) if all_pages else 0.5
        return ClaudeResponse(
            success=True,
            data=merged,
            confidence=avg_conf,
            raw_response=f"[gemini batched parallel {len(all_pages)} pages]",
            error=None,
        )

    @_retry_gemini
    def _transcribe_batch(
        self, copy_id: str, image_paths: list[Path], page_offset: int = 0
    ) -> ClaudeResponse:
        first_page = page_offset + 1
        last_page = page_offset + len(image_paths)
        page_hint = (
            f"\nCes images sont les pages {first_page} à {last_page}."
            f" Utilise page_number à partir de {first_page}."
            if page_offset > 0 else ""
        )

        schema_example = (
            '{\n'
            f'  "copy_id": "{copy_id}",\n'
            '  "global_quality": "good",\n'
            '  "pages": [\n'
            f'    {{"page_number": {first_page}, "content": "...", "formulas": [], "diagrams": [], "uncertainties": [], "confidence": 0.9}}'
            + (
                f',\n    {{"page_number": {first_page + 1}, "content": "...", "formulas": [], "diagrams": [], "uncertainties": [], "confidence": 0.9}}'
                if len(image_paths) > 1 else ""
            )
            + '\n  ]\n}'
        )

        prompt = (
            f"{self._transcription_prompt}\n\ncopy_id : {copy_id}{page_hint}\n\n"
            "Retourne UNIQUEMENT un objet JSON valide sans aucune balise markdown, "
            "avec cette structure exacte (une entrée dans `pages` par image fournie) :\n"
            f"{schema_example}\n\n"
            "Rappel : chaque passage douteux est entouré de ⟦…⟧ dans `content`, et chaque "
            "entrée de `uncertainties` suit le format "
            "\"<passage copié depuis content>\" : <raison en français>."
        )

        # Contenu = [texte, image1, image2, ...]
        contents: list[Any] = [prompt]
        for path in image_paths:
            contents.append(Image.open(path))

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    temperature=0.1,
                ),
            )

            raw = response.text.strip()

            # Nettoyer les balises markdown si le modèle les ajoute quand même
            m = _JSON_FENCE.search(raw)
            if m:
                raw = m.group(1).strip()

            # Isoler l'objet JSON
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                raw = raw[start_idx : end_idx + 1]

            raw = _TRAILING_COMMA.sub(r"\1", raw)

            # Tentative parse → réparation si nécessaire
            data_dict: dict | None = None
            for candidate in (raw, _repair_json(raw)):
                candidate = _TRAILING_COMMA.sub(r"\1", candidate)
                try:
                    data_dict = json.loads(candidate)
                    break
                except json.JSONDecodeError:
                    continue

            if data_dict is None:
                logger.error(
                    "Gemini — JSON irréparable (copy_id=%s, offset=%d). Début : %.300s",
                    copy_id, page_offset, raw,
                )
                return ClaudeResponse(
                    success=False, data=None, confidence=0.0,
                    raw_response=raw[:500],
                    error="JSON invalide retourné par Gemini.",
                )

            data_dict = _normalize_transcription(data_dict)
            validated = TranscriptionResult(**data_dict)

            logger.info(
                "Gemini transcription OK (copy_id=%s, pages=%d-%d, qualité=%s)",
                copy_id, page_offset + 1, page_offset + len(image_paths),
                validated.global_quality,
            )
            return ClaudeResponse(
                success=True,
                data=validated,
                confidence=self._estimate_confidence(validated),
                raw_response=raw[:2000],
                error=None,
            )

        except Exception as e:
            if _is_retryable_gemini(e):
                logger.warning(
                    "Gemini erreur passagère (copy_id=%s, offset=%d) — nouvel essai : %s",
                    copy_id, page_offset, e,
                )
                raise  # laisse tenacity gérer le retry
            logger.error(
                "Erreur Gemini (copy_id=%s, offset=%d) : %s", copy_id, page_offset, e
            )
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response="",
                error=str(e),
            )

    def _estimate_confidence(self, result: TranscriptionResult) -> float:
        return {"good": 0.9, "medium": 0.7, "poor": 0.5}.get(result.global_quality, 0.5)

    # ── Correction ────────────────────────────────────────────────────────────

    @_retry_gemini
    def grade(
        self,
        transcription: TranscriptionResult,
        rubric: Rubric,
        subject_text: str,
        expert_instructions: str = "",
        official_answers: str = "",
        temperature: float = 0,
    ) -> ClaudeResponse:
        """Correction selon barème via Gemini — même signature que
        `ClaudeClient.grade` / `DeepSeekClient.grade`."""
        logger.info("[%s] Gemini correction — modèle : %s",
                    transcription.copy_id, self._model)
        expert_block = (
            f"\n\nINSTRUCTIONS EXPERT:\n{expert_instructions}"
            if expert_instructions.strip() else ""
        )
        official_block = f"\n\n{official_answers}" if official_answers.strip() else ""
        auto_block = (
            "\n\nINSTRUCTION SPÉCIALE : Aucun barème ni corrigé fourni. "
            "Identifie les questions (Q1, Q2a…), résous-les toi-même, compare à la "
            "copie, attribue 1 si juste sinon 0, et fixe total_possible = nombre de "
            "questions identifiées. Si la transcription est vide, retourne une entrée "
            "unique rubric_item_id='Q1', score=0, confidence=0.1, requires_review=true, "
            "comment='Copie illisible — révision manuelle requise', "
            "observed_answer='[ILLISIBLE]', total_possible=1."
            if not rubric.items else ""
        )

        prompt = (
            f"{self._grading_prompt}{auto_block}{official_block}{expert_block}"
            f"\n\nÉNONCÉ:\n{subject_text}"
            f"\n\nBARÈME:\n{rubric.model_dump_json(indent=2)}"
            f"\n\nTRANSCRIPTION:\n{transcription.model_dump_json(indent=2)}"
            f"\n\nRetourne UNIQUEMENT un objet JSON valide avec cette structure exacte :"
            f"\n{_GRADING_SCHEMA}"
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    temperature=temperature,
                ),
            )
            result = _parse_structured(response.text or "", CopyGrade)
            if result.success and result.data is not None and expert_instructions.strip():
                result.data.expert_instructions_used = True
            return result
        except Exception as e:
            if _is_retryable_gemini(e):
                raise
            logger.error("Gemini grade erreur (copy_id=%s) : %s", transcription.copy_id, e)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(e))

    # ── Diagnostic ────────────────────────────────────────────────────────────

    @_retry_gemini
    def diagnose(self, grades: CopyGrade, curriculum_context: str = "") -> ClaudeResponse:
        """Diagnostic pédagogique texte libre via Gemini — même signature que
        `ClaudeClient.diagnose` / `DeepSeekClient.diagnose`."""
        logger.info("[%s] Gemini diagnostic — modèle : %s", grades.copy_id, self._model)
        base_prompt = self._diagnostic_prompt.replace(
            "{{CURRICULUM_CONTEXT}}", curriculum_context or ""
        )
        prompt = (
            f"{base_prompt}"
            f"\n\nRÉSULTATS DE CORRECTION:\n{grades.model_dump_json(indent=2)}"
            f"\n\nRetourne UNIQUEMENT un objet JSON valide avec cette structure exacte :"
            f"\n{_DIAGNOSTIC_SCHEMA}"
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    temperature=0.2,
                ),
            )
            return _parse_structured(response.text or "", DiagnosticResult)
        except Exception as e:
            if _is_retryable_gemini(e):
                raise
            logger.error("Gemini diagnose erreur (copy_id=%s) : %s", grades.copy_id, e)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(e))


#: Alias lisible — le client ne se limite plus à la transcription.
GeminiClient = GeminiTranscriptionClient
