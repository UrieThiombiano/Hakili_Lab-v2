"""
OpenAIClient — filet de secours (GPT-5) pour la transcription, le nom élève,
la correction, le diagnostic et la remédiation.

N'est appelé QUE quand le provider principal de l'étape échoue (Gemini/Mistral
pour la transcription, DeepSeek pour la correction, Mistral pour la
remédiation…) — remplace Claude comme fallback partout où un fallback existe.

Claude reste seul utilisé là où il n'y a pas d'alternative (pas de "fallback"
à proprement parler) : extraction sujet/barème uploadé, barème virtuel,
enrichissement 20/20 — voir claude_client.py et docs/decision_register.md D-CEO-03.

Utilise le SDK openai standard (même librairie que DeepSeekClient, mais sans
base_url personnalisée — véritable API OpenAI).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.models.domain import (
    ClaudeResponse,
    CopyGrade,
    DiagnosticResult,
    Rubric,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")

# Schéma JSON attendu pour la correction (identique à DeepSeekClient — même convention)
_GRADING_SCHEMA = """
{
  "copy_id": "<string>",
  "total_score": <nombre décimal, ex: 12.5>,
  "total_possible": <nombre décimal, ex: 20.0>,
  "questions": [
    {
      "rubric_item_id": "<string — DOIT être l'id EXACT du RubricItem dans le barème, ex: Q_NUM_04, Q_GEO_01>",
      "score": <0 si incorrect, ou valeur exacte du champ max_score du RubricItem si correct>,
      "confidence": <float 0.0-1.0>,
      "comment": "<1 phrase bienveillante pour l'enseignant>",
      "observed_answer": "<ce que l'élève a écrit, résumé en 1 ligne — '—' si absent/illisible>",
      "requires_review": <true|false>
    }
  ]
}
"""

# Schéma JSON attendu pour le diagnostic
_DIAGNOSTIC_SCHEMA = """
{
  "copy_id": "<string>",
  "strengths": ["<string>", ...],
  "weaknesses": ["<string>", ...],
  "root_causes": [
    {
      "visible_error": "<string>",
      "hidden_cause": "<string — mécanisme précis défaillant>",
      "linked_questions": ["Q1", "Q3", ...]
    }
  ],
  "skills": [
    {
      "name": "<string>",
      "level": "<mastered|partial|weak|unknown>",
      "evidence": "<string>"
    }
  ],
  "remediation_plan": [
    {
      "priority": <integer, 1 = plus haute priorité>,
      "topic": "<string>",
      "action": "<string>"
    }
  ]
}
"""


# ── Utilitaires JSON (identiques à DeepSeekClient/GeminiTranscriptionClient) ──

def _repair_json(text: str) -> str:
    """Ferme les accolades/crochets non fermés."""
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


def _parse_json_response(raw: str, model_cls: type) -> ClaudeResponse:
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
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

    logger.error("GPT-5 — JSON irréparable (%s). Début : %.300s", model_cls.__name__, raw)
    return ClaudeResponse(
        success=False, data=None, confidence=0.0,
        raw_response=raw[:500],
        error=f"JSON invalide retourné par GPT-5. Début : {raw[:200]}",
    )


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8")


# ── Retry — compatible avec openai.APIStatusError ────────────────────────────

def _is_retryable_openai(exc: BaseException) -> bool:
    try:
        from openai import APIStatusError, APIConnectionError, APITimeoutError
        if isinstance(exc, APITimeoutError):
            return False
        if isinstance(exc, APIStatusError):
            return exc.status_code in (429, 500, 503)
        return isinstance(exc, APIConnectionError)
    except ImportError:
        return False


_retry = retry(
    retry=retry_if_exception(_is_retryable_openai),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)


# ── Client principal ──────────────────────────────────────────────────────────

class OpenAIClient:
    """Filet de secours GPT-5 — transcription, nom élève, correction, diagnostic."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY manquante. Ajoutez-la dans .env pour utiliser le fallback GPT-5."
            )
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=90.0)
        self._transcription_prompt = _load_prompt("transcription_prompt.md")
        self._grading_prompt = _load_prompt("grading_prompt.md")
        self._diagnostic_prompt = _load_prompt("diagnostic_prompt.md")
        logger.info("OpenAIClient initialisé (modèle=%s)", settings.openai_model)

    def _media_type(self, path: Path) -> str:
        return _MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")

    def _encode_image(self, path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    def _image_content(self, path: Path) -> dict[str, Any]:
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{self._media_type(path)};base64,{self._encode_image(path)}"},
        }

    # ── Transcription (fallback) ────────────────────────────────────────────

    @_retry
    def transcribe(self, copy_id: str, image_paths: list[Path]) -> ClaudeResponse:
        logger.info("[%s] GPT-5 transcription (fallback) — modèle : %s | pages : %d",
                    copy_id, settings.openai_model, len(image_paths))
        schema_example = (
            '{\n'
            f'  "copy_id": "{copy_id}",\n'
            '  "global_quality": "good",\n'
            '  "pages": [\n'
            '    {"page_number": 1, "content": "...", "formulas": [], "diagrams": [], "uncertainties": [], "confidence": 0.9}\n'
            '  ]\n}'
        )
        prompt = (
            f"{self._transcription_prompt}\n\ncopy_id : {copy_id}\n\n"
            "Retourne UNIQUEMENT un objet JSON valide sans aucune balise markdown, "
            "avec cette structure exacte (une entrée dans `pages` par image fournie, dans l'ordre) :\n"
            f"{schema_example}"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend(self._image_content(p) for p in image_paths)

        try:
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
                max_completion_tokens=16384,
            )
            raw = response.choices[0].message.content or ""
            logger.info("GPT-5 transcription OK — tokens: %d in / %d out",
                        response.usage.prompt_tokens, response.usage.completion_tokens)
            return _parse_json_response(raw, TranscriptionResult)
        except Exception as e:
            logger.error("GPT-5 transcribe erreur (copy_id=%s) : %s", copy_id, e)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(e))

    # ── Nom de l'élève (fallback) ───────────────────────────────────────────

    def extract_student_name(self, first_page: Path) -> str:
        """Lit la première page et retourne le nom complet de l'élève, ou ''."""
        prompt = (
            "Regarde cette image de copie d'élève. "
            "Trouve le nom et le prénom de l'élève (champs NOM, PRENOM, "
            "NOM ET PRENOM, ou équivalent). "
            "Retourne UNIQUEMENT le nom complet sous la forme 'Prénom NOM', "
            "sans aucun autre texte ni ponctuation. "
            "Si tu ne trouves pas de nom, retourne exactement la chaîne vide."
        )
        try:
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, self._image_content(first_page)],
                }],
                max_completion_tokens=64,
            )
            name = (response.choices[0].message.content or "").strip()
            if len(name) > 80 or "\n" in name:
                return ""
            return name
        except Exception as e:
            logger.warning("GPT-5 extract_student_name échoué : %s", e)
            return ""

    # ── Correction (fallback) ───────────────────────────────────────────────

    @_retry
    def grade(
        self,
        transcription: TranscriptionResult,
        rubric: Rubric,
        subject_text: str,
        expert_instructions: str = "",
        official_answers: str = "",
        temperature: float = 0,
    ) -> ClaudeResponse:
        logger.info("[%s] GPT-5 correction (fallback) — modèle : %s",
                    transcription.copy_id, settings.openai_model)
        expert_block = (
            f"\n\nINSTRUCTIONS EXPERT:\n{expert_instructions}"
            if expert_instructions.strip() else ""
        )
        official_block = (
            f"\n\n{official_answers}"
            if official_answers.strip() else ""
        )
        auto_block = (
            "\n\nINSTRUCTION SPÉCIALE : Aucun barème ni corrigé fourni. "
            "Procède en trois étapes :\n"
            "1. Identifie toutes les questions mathématiques visibles dans la transcription. "
            "Génère les identifiants Q1, Q2a, Q2b, etc.\n"
            "2. Pour chaque question identifiée, RÉSOUS-LA TOI-MÊME pour obtenir la réponse correcte "
            "de référence — tu es mathématicien, utilise tes connaissances.\n"
            "3. Compare la réponse de l'élève (transcription) avec ta solution. "
            "Attribue 1 si l'élève a la bonne réponse, 0 sinon. "
            "Dans le commentaire, indique brièvement ce que l'élève a fait (juste ou faux) et, "
            "si faux, ce que valait la réponse correcte.\n"
            "Fixe total_possible = nombre de questions identifiées.\n"
            "Si aucune question n'est identifiable (transcription vide), retourne une entrée unique : "
            "rubric_item_id='Q1', score=0, confidence=0.1, requires_review=true, "
            "comment='Copie illisible — révision manuelle requise', observed_answer='[ILLISIBLE]', "
            "total_possible=1."
            if not rubric.items else ""
        )

        user_content = (
            f"{self._grading_prompt}{auto_block}{official_block}{expert_block}"
            f"\n\nÉNONCÉ:\n{subject_text}"
            f"\n\nBARÈME:\n{rubric.model_dump_json(indent=2)}"
            f"\n\nTRANSCRIPTION:\n{transcription.model_dump_json(indent=2)}"
            f"\n\nRetourne UNIQUEMENT un objet JSON valide avec cette structure exacte :"
            f"\n{_GRADING_SCHEMA}"
        )

        try:
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": user_content}],
                response_format={"type": "json_object"},
                max_completion_tokens=8192,
            )
            raw = response.choices[0].message.content or ""
            result = _parse_json_response(raw, CopyGrade)
            if result.success and result.data is not None and expert_instructions.strip():
                result.data.expert_instructions_used = True
            if result.success and result.data is not None:
                logger.info("GPT-5 grading OK — tokens: %d in / %d out",
                            response.usage.prompt_tokens, response.usage.completion_tokens)
            return result
        except Exception as e:
            logger.error("GPT-5 grade erreur : %s", e)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(e))

    # ── Diagnostic (fallback) ───────────────────────────────────────────────

    @_retry
    def diagnose(self, grades: CopyGrade, curriculum_context: str = "") -> ClaudeResponse:
        logger.info("[%s] GPT-5 diagnostic (fallback) — modèle : %s",
                    grades.copy_id, settings.openai_model)
        base_prompt = self._diagnostic_prompt.replace(
            "{{CURRICULUM_CONTEXT}}", curriculum_context or ""
        )
        user_content = (
            f"{base_prompt}"
            f"\n\nRÉSULTATS DE CORRECTION:\n{grades.model_dump_json(indent=2)}"
            f"\n\nRetourne UNIQUEMENT un objet JSON valide avec cette structure exacte :"
            f"\n{_DIAGNOSTIC_SCHEMA}"
        )
        try:
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": user_content}],
                response_format={"type": "json_object"},
                # 16384 plutôt que 4096 : sur une copie où beaucoup de
                # questions échouent, le diagnostic complet dépasse
                # facilement l'ancien plafond — constaté en conditions
                # réelles (45/45 échouées, coupé pile à 4096 tokens en
                # sortie), ce fallback n'est censé se déclencher que quand
                # Claude a déjà échoué : ne pas lui infliger la même limite.
                max_completion_tokens=16384,
            )
            raw = response.choices[0].message.content or ""
            logger.info("GPT-5 diagnostic OK — tokens: %d in / %d out",
                        response.usage.prompt_tokens, response.usage.completion_tokens)
            return _parse_json_response(raw, DiagnosticResult)
        except Exception as e:
            logger.error("GPT-5 diagnose erreur : %s", e)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(e))
