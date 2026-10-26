"""
DeepSeekClient — correction et diagnostic via API DeepSeek.

Répartition des modèles :
  grade()    → DeepSeek V3 (deepseek-chat)     : $0.27/$1.10 par MTok
               Meilleur score MATH-500 benchmark toutes catégories confondues (~90%)
  diagnose() → DeepSeek R1 (deepseek-reasoner) : $0.55/$2.19 par MTok
               Modèle de raisonnement chain-of-thought — idéal pour l'analyse de fond

L'API DeepSeek est compatible OpenAI — utilise le SDK openai avec base_url personnalisée.
Contraintes R1 : pas de system message, pas de temperature, pas de response_format.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

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

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")

# Schéma JSON attendu pour la correction — inclus dans le prompt (V3 supporte json_object)
_GRADING_SCHEMA = """
{
  "copy_id": "<string>",
  "total_score": <nombre décimal, ex: 12.5>,
  "total_possible": <nombre décimal, ex: 20.0>,
  "questions": [
    {
      "rubric_item_id": "<string — DOIT être l'id EXACT du RubricItem dans le barème, ex: Q_NUM_04, Q_GEO_01>",
      "score": <0 si incorrect, ou valeur exacte de max_score si correct (items à barème détaillé : recalculé par le système depuis points_obtenus)>,
      "points_obtenus": <UNIQUEMENT si le RubricItem porte points_corrige : points DU CORRIGÉ obtenus, critère par critère (ex. 1 sur 2, 2.5 sur 3), multiple de 0.5 ; sinon null>,
      "confidence": <float 0.0-1.0>,
      "comment": "<1 phrase bienveillante pour l'enseignant>",
      "observed_answer": "<ce que l'élève a écrit, résumé en 1 ligne — '—' si absent/illisible>",
      "requires_review": <true|false>
    }
  ]
}
"""

# Schéma JSON attendu pour le diagnostic (utilisé dans le prompt R1)
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


# ── Utilitaires JSON ──────────────────────────────────────────────────────────

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
                success=True, data=validated, confidence=0.88,
                raw_response=raw[:2000], error=None,
            )
        except (json.JSONDecodeError, Exception):
            continue

    logger.error("DeepSeek — JSON irréparable (%s). Début : %.300s", model_cls.__name__, raw)
    return ClaudeResponse(
        success=False, data=None, confidence=0.0,
        raw_response=raw[:500],
        error=f"JSON invalide retourné par DeepSeek. Début : {raw[:200]}",
    )


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8")


# ── Retry — compatible avec openai.APIStatusError ────────────────────────────

def _is_retryable_openai(exc: BaseException) -> bool:
    try:
        from openai import APIStatusError, APIConnectionError, APITimeoutError
        if isinstance(exc, APITimeoutError):
            return False  # timeout R1 = modèle trop lent → fallback immédiat, pas de retry
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

class DeepSeekClient:
    """
    Correction (DeepSeek V3) + Diagnostic (DeepSeek R1).

    V3 = modèle standard : meilleur raisonnement mathématique au meilleur coût.
    R1 = modèle de raisonnement : chain-of-thought explicite pour diagnostic profond.
    """

    def __init__(self) -> None:
        if not settings.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY manquante. Ajoutez-la dans .env pour utiliser DeepSeek."
            )
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
            timeout=90.0,   # 90s max — évite le blocage de l'UI sur R1 chain-of-thought
        )
        self._grading_prompt = _load_prompt("grading_prompt.md")
        self._diagnostic_prompt = _load_prompt("diagnostic_prompt.md")
        logger.info(
            "DeepSeekClient initialisé (grading=%s, diagnostic=%s)",
            settings.deepseek_model_v3, settings.deepseek_model_r1,
        )

    # ── Correction (V3) ───────────────────────────────────────────────────────

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
        """Correction selon barème via DeepSeek V3 — json_object forcé."""
        logger.info("[%s] DeepSeek correction — modèle : %s",
                    transcription.copy_id, settings.deepseek_model_v3)
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
                model=settings.deepseek_model_v3,
                messages=[{"role": "user", "content": user_content}],
                response_format={"type": "json_object"},
                max_tokens=8192,
                temperature=temperature,
            )
            raw = response.choices[0].message.content or ""
            result = _parse_json_response(raw, CopyGrade)
            if result.success and result.data is not None and expert_instructions.strip():
                result.data.expert_instructions_used = True
            if result.success and result.data is not None:
                logger.warning(
                    "DeepSeek V3 grading OK — tokens: %d in / %d out",
                    response.usage.prompt_tokens, response.usage.completion_tokens,
                )
                for q in result.data.questions:
                    logger.warning(
                        "  %s → score=%g conf=%.0f%% | observed='%s' | comment='%s'",
                        q.rubric_item_id, q.score, q.confidence * 100,
                        q.observed_answer[:80], q.comment[:80],
                    )
            return result
        except Exception as e:
            logger.error("DeepSeek V3 grade erreur : %s", e)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(e))

    # ── Diagnostic (R1) ───────────────────────────────────────────────────────

    @_retry
    def diagnose(self, grades: CopyGrade, curriculum_context: str = "") -> ClaudeResponse:
        """
        Diagnostic pédagogique via DeepSeek R1 (modèle de raisonnement).

        R1 produit une chaîne de pensée interne avant de répondre — idéal pour
        identifier les causes cachées derrière les erreurs de surface.
        Contraintes R1 : pas de system message, pas de temperature, pas de response_format.
        """
        logger.info("[%s] DeepSeek diagnostic — modèle : %s",
                    grades.copy_id, settings.deepseek_model_r1)
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
                model=settings.deepseek_model_r1,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=4096,  # 4096 suffit pour le JSON diagnostic ; réduit le temps R1
                # R1 : pas de temperature, pas de response_format, pas de system
            )
            raw = response.choices[0].message.content or ""

            # Logguer les tokens de raisonnement (chaîne de pensée interne)
            usage = response.usage
            reasoning_tokens = getattr(
                getattr(usage, "completion_tokens_details", None),
                "reasoning_tokens", "N/A"
            )
            logger.info(
                "DeepSeek R1 diagnostic OK — tokens: %d in / %d out (reasoning: %s)",
                usage.prompt_tokens, usage.completion_tokens, reasoning_tokens,
            )
            return _parse_json_response(raw, DiagnosticResult)
        except Exception as e:
            logger.error("DeepSeek R1 diagnose erreur : %s", e)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(e))
