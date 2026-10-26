import json
import logging
import re
from pathlib import Path
from typing import Any

from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.models.domain import (
    ClaudeResponse,
    ConfirmationRequest,
    ConfirmationSubject,
    ContenuAcquis,
    ContenuSection,
    CopyGrade,
    DemandePlan,
    DiagnosticResult,
    PageTranscription,
    Rubric,
    RubricItem,
    SectionPlanDemande,
    SortieDiagnosticContraint,
    TranscriptionResult,
    VerificationRequest,
    VerificationSubject,
)

logger = logging.getLogger(__name__)

_MAX_PAGES_PER_BATCH = 3   # 3 pages par appel → 3× moins d'appels facturés
_TOKENS_PER_BATCH = 4096  # 4096 nécessaire pour 3 pages de copie math sans troncature

#: Modèles qui **refusent** les paramètres d'échantillonnage.
#:
#: À partir d'Opus 4.7, `temperature`, `top_p` et `top_k` ne sont plus acceptés :
#: les envoyer rend un 400 `invalid_request_error`, pas un avertissement. Le
#: dépôt appelle `messages.create(..., temperature=0)` en onze endroits, hérités
#: d'une époque où le déterminisme se demandait comme ça — il se demande
#: désormais par le prompt et par `effort`.
#:
#: Le filtrage se fait ici, sur le nom du modèle, plutôt qu'en retirant
#: `temperature` de chaque appel : le même client sert Sonnet 4.6, qui l'accepte
#: encore, et un simple changement de `CLAUDE_MODEL_HEAVY` dans `.env` suffirait
#: à faire échouer un appel resté correct par ailleurs.
_PARAMETRES_ECHANTILLONNAGE = ("temperature", "top_p", "top_k")
_PREFIXES_SANS_ECHANTILLONNAGE = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)

_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# ── Tool schemas (tool_use = JSON garanti correctement échappé par l'API) ─────

_TRANSCRIPTION_TOOL: dict[str, Any] = {
    "name": "save_transcription",
    "description": "Sauvegarde la transcription structurée de la copie manuscrite.",
    "input_schema": {
        "type": "object",
        "properties": {
            "copy_id": {"type": "string"},
            "global_quality": {"type": "string", "enum": ["good", "medium", "poor"]},
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page_number": {"type": "integer"},
                        "content": {
                            "type": "string",
                            "description": "Tout le texte manuscrit de la page, transcrit mot pour mot.",
                        },
                        "formulas": {
                            "type": "array",
                            "description": "Liste de chaînes de caractères — chaque formule est une STRING simple, ex: 'x^2 + 2x + 1 = 0'. Ne pas utiliser d'objets.",
                            "items": {"type": "string"},
                        },
                        "diagrams": {
                            "type": "array",
                            "description": "Liste de chaînes de caractères décrivant chaque schéma visible. Ne pas utiliser d'objets.",
                            "items": {"type": "string"},
                        },
                        "uncertainties": {
                            "type": "array",
                            "description": "Liste de chaînes de caractères signalant les zones illisibles ou ambiguës, ex: 'Ligne 3 illisible'. Ne pas utiliser d'objets.",
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number"},
                    },
                    "required": ["page_number", "content", "formulas", "diagrams",
                                 "uncertainties", "confidence"],
                },
            },
        },
        "required": ["copy_id", "global_quality", "pages"],
    },
}

_GRADING_TOOL: dict[str, Any] = {
    "name": "save_grading",
    "description": "Sauvegarde les résultats de correction de la copie.",
    "input_schema": {
        "type": "object",
        "properties": {
            "copy_id": {"type": "string"},
            "total_score": {"type": "number"},
            "total_possible": {"type": "number"},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rubric_item_id": {"type": "string"},
                        # Rempli AVANT la note : le modèle raisonnait jusque-là
                        # dans `comment` et changeait d'avis en cours de phrase,
                        # après avoir déjà fixé `points_obtenus` (« 1,5 pt sur 2 :
                        # … donc le second point est acquis », recette du
                        # 2026-10-17). Non conservé (ignoré par QuestionGrade).
                        "analyse": {
                            "type": "string",
                            "description": (
                                "Brouillon rédigé AVANT de noter, pour les items notés critère par "
                                "critère (score_step < max_score) : chaque critère du barème du "
                                "corrigé, acquis ou non, au vu de la transcription. Deux phrases au "
                                "plus. « — » pour un item tout-ou-rien (partie A, QCM) ou une "
                                "absence de réponse. Non montré à l'enseignant."
                            ),
                        },
                        "score": {"type": "number", "minimum": 0},
                        "confidence": {"type": "number"},
                        "comment": {"type": "string"},
                        "observed_answer": {"type": "string"},
                        "requires_review": {"type": "boolean"},
                        "points_obtenus": {
                            "type": ["number", "null"],
                            "description": "Seulement si le RubricItem porte points_corrige : points du corrigé obtenus (multiple de 0.5).",
                        },
                    },
                    "required": ["rubric_item_id", "analyse", "score", "confidence", "comment",
                                 "observed_answer", "requires_review"],
                },
            },
        },
        "required": ["copy_id", "total_score", "total_possible", "questions"],
    },
}

_TEXTES = {"type": "array", "items": {"type": "string"}}

#: Contraintes que le mode strict n'accepte pas (documentation Anthropic,
#: « JSON Schema limitations ») — revalidées par Pydantic côté client.
_HORS_STRICT = ("minItems", "maxItems", "minimum", "maximum", "minLength", "maxLength")


def _outil_strict(outil: dict[str, Any]) -> dict[str, Any]:
    """Version `strict: true` d'un outil : la sortie suit le schéma à coup
    sûr (essai réel du 2026-10-26 : sans lui, Opus rendait parfois
    `causes: [{}]`). Le mode strict veut `additionalProperties: false` et
    toutes les propriétés requises (une propriété facultative y est
    nullable), et refuse les bornes numériques et de longueur : elles sont
    retirées ici, Pydantic les vérifie, et un refus est renvoyé au modèle."""
    def convertir(noeud: Any) -> Any:
        if isinstance(noeud, list):
            return [convertir(n) for n in noeud]
        if not isinstance(noeud, dict):
            return noeud
        resultat = {k: convertir(v) for k, v in noeud.items() if k not in _HORS_STRICT}
        if resultat.get("type") == "object" and "properties" in resultat:
            resultat["additionalProperties"] = False
            resultat["required"] = list(resultat["properties"])
        return resultat

    return {**outil, "input_schema": convertir(outil["input_schema"]), "strict": True}


#: Outil de rédaction d'une section du plan de remédiation — mêmes champs que
#: `ContenuSection`. Envoyé en mode strict (`_outil_strict`) : les bornes
#: (5 exercices, listes non vides) sont vérifiées par Pydantic.
_OUTIL_SECTION_PLAN: dict[str, Any] = _outil_strict({
    "name": "rediger_section",
    "description": "Enregistre le contenu rédigé d'une section du plan de remédiation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "titre_tableau": {"type": ["string", "null"]},
            "titre_court": {"type": "string"},
            "ecrits": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "reponse_eleve": {"type": "string"},
                        "reponse_attendue": {"type": "string"},
                        "reussie": {"type": "boolean"},
                    },
                    "required": ["question", "reponse_eleve", "reponse_attendue"],
                },
            },
            "ce_qui_ne_va_pas": {"type": "string"},
            "causes": {**_TEXTES, "minItems": 1},
            "a_retenir": {**_TEXTES, "minItems": 1},
            "methode_titre": {"type": "string"},
            "methode": _TEXTES,
            "consigne_exercices": {"type": ["string", "null"]},
            "exercices": {
                "type": "array", "minItems": 5, "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "enonce": {"type": "string"},
                        "niveau": {"type": "integer", "enum": [1, 2, 3]},
                        "reponse": {"type": "string"},
                    },
                    "required": ["enonce", "niveau", "reponse"],
                },
            },
        },
        "required": ["titre", "titre_court", "ecrits", "ce_qui_ne_va_pas", "causes",
                     "a_retenir", "methode_titre", "methode", "exercices"],
    },
})

_OUTIL_ACQUIS_PLAN: dict[str, Any] = _outil_strict({
    "name": "rediger_acquis",
    "description": "Enregistre l'encadré « Ce que tu sais déjà faire ».",
    "input_schema": {
        "type": "object",
        "properties": {"acquis": _TEXTES},
        "required": ["acquis"],
    },
})


def _diagnostic_contraint_tool(
    codes_questions: list[str],
    codes_competences: list[str],
    codes_types: list[str],
) -> dict[str, Any]:
    """Outil du diagnostic contraint — les codes admis sont des `enum` du schéma.

    C'est la première des trois barrières demandées par le module 4 : un code
    absent du référentiel devient très difficile à produire, plutôt que d'être
    rattrapé après coup. Les deux autres restent nécessaires et sont ailleurs :
    la validation par question (`referentiel/diagnostic.py`) et la redemande.

    Pourquoi une validation reste nécessaire malgré l'`enum` : le schéma ne peut
    porter qu'**une** liste de compétences pour tout le tableau, alors que chaque
    question a la sienne (sa compétence et ses prérequis). L'`enum` interdit donc
    un code hors référentiel, pas un code référentiel attribué à la mauvaise
    question. Et les autres fournisseurs ne contraignent pas tous aussi fermement.
    """
    return {
        "name": "enregistrer_problemes",
        "description": (
            "Enregistre les problèmes relevés sur la copie. Un problème par "
            "question ratée au plus. Aucune prose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "problemes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code_question": {
                                "type": "string",
                                "enum": codes_questions,
                                "description": "La question analysée.",
                            },
                            "code_competence": {
                                "type": "string",
                                "enum": codes_competences,
                                "description": (
                                    "Compétence de la question, ou l'un de ses "
                                    "prérequis pour un PRQ. Voir "
                                    "`codes_competence_admis` de cette question."
                                ),
                            },
                            "code_type_erreur": {
                                "type": "string",
                                "enum": codes_types,
                            },
                            "citation": {
                                "type": "string",
                                "description": (
                                    "Ce qui est écrit sur la copie, au plus près. "
                                    "« (aucune réponse) » si la zone est vierge."
                                ),
                            },
                        },
                        "required": [
                            "code_question",
                            "code_competence",
                            "code_type_erreur",
                            "citation",
                        ],
                    },
                }
            },
            "required": ["problemes"],
        },
    }


_QUESTIONS_EXTRACTION_TOOL: dict[str, Any] = {
    "name": "save_questions",
    "description": "Sauvegarde la liste des questions identifiées dans la transcription.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "Liste ordonnée de toutes les questions et sous-questions.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Identifiant court et cohérent, ex : Q1, Q2a, Q2b, Q3.",
                        },
                        "label": {
                            "type": "string",
                            "description": "Libellé court de la question, ex : 'Calcul de volume'.",
                        },
                    },
                    "required": ["id", "label"],
                },
            },
        },
        "required": ["questions"],
    },
}

_RUBRIC_EXTRACTION_TOOL: dict[str, Any] = {
    "name": "save_rubric",
    "description": "Extrait les items du barème depuis le document fourni.",
    "input_schema": {
        "type": "object",
        "properties": {
            "total_points": {
                "type": "integer",
                "description": "Nombre total de points du barème.",
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Identifiant de la question, ex : Q1, Q2a, Q2b.",
                        },
                        "label": {
                            "type": "string",
                            "description": "Libellé ou description de la question.",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "ID de la question parente si sous-question, sinon null.",
                        },
                    },
                    "required": ["id", "label"],
                },
            },
        },
        "required": ["total_points", "items"],
    },
}


class _ExtractedRubric(BaseModel):
    total_points: float = 0.0
    items: list[dict] = []


# ── Fallback JSON repair (utilisé uniquement pour diagnose) ───────────────────

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_CLOSE_MAP: dict[str, str] = {"[": "]", "{": "}"}


def _close_json(text: str) -> str:
    """Répare un JSON tronqué : ferme les strings ouvertes puis les brackets."""
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
    # Si on est en plein milieu d'une string (troncature), la fermer d'abord
    suffix = ('"' if in_string else "") + "".join(_CLOSE_MAP[c] for c in reversed(stack))
    return text + suffix


def _is_retryable(exc: BaseException) -> bool:
    import anthropic as _anthropic
    if isinstance(exc, _anthropic.APIStatusError):
        return exc.status_code in (429, 529)
    return isinstance(exc, (_anthropic.APIConnectionError, _anthropic.APITimeoutError))


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)


class ClaudeClient:
    def __init__(
        self, *, modele_heavy: str | None = None, modele_opus: str | None = None
    ) -> None:
        import anthropic

        # Modèles par défaut de CE client. `None` ⇒ valeurs `.env` (`settings`).
        # Le pipeline les surcharge selon Paramètres → Modèles IA (variante
        # Sonnet / Opus, src/core/preferences_modeles.py). Les méthodes
        # `transcribe`/`grade`/`diagnose` acceptent en plus un `model=` ponctuel
        # qui prime sur ces défauts.
        self._modele_heavy = modele_heavy or settings.claude_model_heavy
        self._modele_opus = modele_opus or settings.claude_model_opus

        # `anthropic_api_key` est facultative à l'import de la configuration (voir
        # src/core/config.py) pour que les chemins sans IA — migrations Django,
        # lecture des Sheets, affichage d'une liste d'élèves — n'exigent pas de
        # clé. L'exigence est donc rétablie ici, au seul endroit où elle sert.
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY est absente de l'environnement. Claude est le "
                "filet de secours de toutes les étapes du pipeline et le seul "
                "provider de l'extraction de barème : la correction ne peut pas "
                "démarrer sans. Renseigner la clé dans .env."
            )
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._transcription_prompt = self._load_prompt("transcription_prompt.md")
        self._grading_prompt = self._load_prompt("grading_prompt.md")
        self._diagnostic_prompt = self._load_prompt("diagnostic_prompt.md")
        self._diagnostic_contraint_prompt = self._load_prompt(
            "diagnostic_contraint_prompt.md"
        )
        self._diagnostic_plancher_prompt = self._load_prompt(
            "diagnostic_plancher_prompt.md"
        )
        self._plan_remediation_prompt = self._load_prompt("plan_remediation_prompt.md")
        self._plan_acquis_prompt = self._load_prompt("plan_acquis_prompt.md")
        self._confirmation_subject_prompt = self._load_prompt("confirmation_subject_prompt.md")
        self._verification_subject_prompt = self._load_prompt("verification_subject_prompt.md")
        self._retention_subject_prompt = self._load_prompt("retention_subject_prompt.md")

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / filename
        return prompt_path.read_text(encoding="utf-8")

    def _creer_message(self, *, model: str, stream: bool = False, **kwargs: Any) -> Any:
        """Appelle l'API en retirant ce que le modèle visé n'accepte plus.

        Un seul passage obligé vers `messages.create`, pour que le filtrage des
        paramètres d'échantillonnage (voir `_PREFIXES_SANS_ECHANTILLONNAGE`) ne
        dépende pas de la vigilance de chaque appelant. Le retrait est
        journalisé : un `temperature=0` qui disparaît en silence donnerait
        l'illusion d'un déterminisme qu'on n'a plus.

        `stream=True` : passe par `messages.stream(...)` et rend le message
        final assemblé (même forme qu'un appel non streamé — `.content`,
        `.stop_reason`, etc.) — nécessaire au-delà d'un certain `max_tokens`,
        le SDK Anthropic refuse un appel non streamé au-delà (« Streaming is
        required for operations that may take longer than 10 minutes »)."""
        if model.startswith(_PREFIXES_SANS_ECHANTILLONNAGE):
            retires = [p for p in _PARAMETRES_ECHANTILLONNAGE if p in kwargs]
            for parametre in retires:
                kwargs.pop(parametre)
            if retires:
                logger.debug(
                    "%s n'accepte plus %s — paramètre(s) retiré(s) de l'appel.",
                    model, ", ".join(retires),
                )
        if stream:
            with self.client.messages.stream(model=model, **kwargs) as flux:
                return flux.get_final_message()
        return self.client.messages.create(model=model, **kwargs)

    @staticmethod
    def _texte_reponse(response: Any) -> str:
        """Texte du premier bloc `text` de la réponse.

        `content[0]` n'est pas toujours ce bloc : certains modèles (ex. la
        famille Sonnet 5) préfixent la réponse d'un `ThinkingBlock`, qui n'a
        pas d'attribut `.text`.
        """
        for bloc in response.content:
            if getattr(bloc, "type", None) == "text":
                return bloc.text.strip()
        raise ValueError(f"Aucun bloc texte dans la réponse (types : {[getattr(b, 'type', '?') for b in response.content]})")

    # ── Transcription ──────────────────────────────────────────────────────────

    def transcribe(
        self, copy_id: str, image_paths: list[Path], model: str | None = None
    ) -> ClaudeResponse:
        modele = model or self._modele_heavy
        logger.info("[%s] Claude transcription — modèle : %s | pages : %d",
                    copy_id, modele, len(image_paths))
        if len(image_paths) <= _MAX_PAGES_PER_BATCH:
            return self._transcribe_batch(copy_id, image_paths, page_offset=0, model=modele)
        return self._transcribe_batched(copy_id, image_paths, model=modele)

    def _transcribe_batched(
        self, copy_id: str, image_paths: list[Path], model: str | None = None
    ) -> ClaudeResponse:
        modele = model or self._modele_heavy
        batches = [
            (start, image_paths[start : start + _MAX_PAGES_PER_BATCH])
            for start in range(0, len(image_paths), _MAX_PAGES_PER_BATCH)
        ]

        batch_results: list[tuple[int, ClaudeResponse]] = []
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            future_to_offset = {
                pool.submit(self._transcribe_batch, copy_id, batch, offset, modele): offset
                for offset, batch in batches
            }
            for fut in as_completed(future_to_offset):
                offset = future_to_offset[fut]
                try:
                    resp = fut.result()
                except Exception as exc:
                    logger.error("Claude batch (offset=%d, copy_id=%s) exception : %s", offset, copy_id, exc)
                    return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
                if not resp.success or resp.data is None:
                    return resp
                batch_results.append((offset, resp))

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
            raw_response=f"[claude batched parallel {len(all_pages)} pages]",
            error=None,
        )

    @_retry
    def _transcribe_batch(
        self, copy_id: str, image_paths: list[Path], page_offset: int = 0,
        model: str | None = None,
    ) -> ClaudeResponse:
        page_hint = (
            f"\nCes images sont les pages {page_offset + 1} à {page_offset + len(image_paths)}."
            f" Utilise page_number à partir de {page_offset + 1}."
            if page_offset > 0 else ""
        )

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._transcription_prompt,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"copy_id : {copy_id}{page_hint}",
            },
            *[
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": self._media_type(path),
                        "data": self._encode_image(path),
                    },
                }
                for path in image_paths
            ],
        ]

        response = self._creer_message(
            model=model or self._modele_heavy,
            max_tokens=_TOKENS_PER_BATCH,
            temperature=0,
            tools=[_TRANSCRIPTION_TOOL],
            tool_choice={"type": "tool", "name": "save_transcription"},
            messages=[{"role": "user", "content": content}],
        )

        return self._extract_tool_result(response, TranscriptionResult)

    # ── Correction ────────────────────────────────────────────────────────────

    @_retry
    def grade(
        self,
        transcription: TranscriptionResult,
        rubric: Rubric,
        subject_text: str,
        expert_instructions: str = "",
        official_answers: str = "",
        temperature: float = 0,
        model: str | None = None,
    ) -> ClaudeResponse:
        modele = model or self._modele_heavy
        logger.info("[%s] Claude correction — modèle : %s",
                    transcription.copy_id, modele)
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

        prompt = (
            f"{self._grading_prompt}{auto_block}{official_block}{expert_block}"
            f"\n\nÉNONCÉ:\n{subject_text}"
            f"\n\nBARÈME:\n{rubric.model_dump_json(indent=2)}"
            f"\n\nTRANSCRIPTION:\n{transcription.model_dump_json(indent=2)}"
        )

        # 16000 : le champ `analyse` (un brouillon par question) double à peu
        # près la sortie — 8192 ne tenait plus sur un barème de 46 items.
        response = self._creer_message(
            model=modele,
            max_tokens=16000,
            temperature=temperature,
            tools=[_GRADING_TOOL],
            tool_choice={"type": "tool", "name": "save_grading"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ],
        )

        result = self._extract_tool_result(response, CopyGrade)
        if result.success and result.data is not None and expert_instructions.strip():
            result.data.expert_instructions_used = True
        return result

    # ── Diagnostic ────────────────────────────────────────────────────────────

    @_retry
    def diagnose(
        self, grades: CopyGrade, curriculum_context: str = "", model: str | None = None
    ) -> ClaudeResponse:
        modele_diag = model or self._modele_opus
        logger.info("[%s] Claude diagnostic — modèle : %s",
                    grades.copy_id, modele_diag)
        base_prompt = self._diagnostic_prompt.replace(
            "{{CURRICULUM_CONTEXT}}", curriculum_context or ""
        )

        # Envoie toutes les questions : questions réussies pour les points forts et la détection
        # d'inattention, questions échouées avec le détail complet pour l'analyse des erreurs.
        import json as _json
        all_question_details = []
        for q in grades.questions:
            effective = (
                q.teacher_score
                if q.teacher_score is not None and q.teacher_decision.value == "refused"
                else q.score
            )
            if effective < 1:
                # Échec (0) ou réussite partielle (taux < 1, ex. démarche
                # absente) : le détail est transmis pour que le diagnostic
                # puisse nommer ce qui a manqué.
                all_question_details.append({
                    "question_id": q.rubric_item_id,
                    "score": round(effective, 2),
                    "correct_answer": q.correct_answer or "—",
                    "observed_answer": q.observed_answer,
                    "comment_ia": q.comment,
                })
            else:
                # Score réel (0.5, 0.75, 1.0…) pour que le modèle distingue
                # réussite partielle de réussite complète — évite les hallucinations.
                all_question_details.append({
                    "question_id": q.rubric_item_id,
                    "score": round(effective, 2),
                })

        all_block = _json.dumps(all_question_details, ensure_ascii=False, indent=2)

        prompt = (
            f"{base_prompt}"
            f"\n\n## Données de la copie\n```json\n{all_block}\n```"
            f"\n\nSCORE FINAL : {grades.final_score or grades.total_score} / {grades.total_possible}"
            f"  (copy_id : {grades.copy_id})"
            "\n\nCommence directement par { et termine par }. Aucune balise Markdown. Aucun texte avant ou après."
        )

        def _call_diagnose(model: str) -> object:
            # 64000 plutôt que 16384 : `claude_model_opus` pointe en pratique
            # vers une famille de modèles qui préfixe sa réponse d'un bloc
            # `thinking` non affiché ici (voir `_texte_reponse`) — sur une
            # copie où beaucoup de questions échouent (donc un diagnostic
            # long à produire), le budget peut être épuisé par la pensée
            # interne avant qu'aucun texte ne soit émis (`stop_reason=
            # max_tokens`, `_texte_reponse` lève `ValueError`). Constaté en
            # conditions réelles même à 32000 sur une copie à 45/45 questions
            # échouées (le pire cas du référentiel) — 64000 réduit le risque
            # sans l'éliminer complètement ; le fallback GPT-5 ci-dessous
            # (lui aussi élargi, `openai_client.py`) reste le filet de
            # sécurité si ça arrive malgré tout.
            # `stream=True` : à ce niveau de `max_tokens`, le SDK Anthropic
            # refuse un appel non streamé (« Streaming is required for
            # operations that may take longer than 10 minutes »).
            return self._creer_message(
                model=model,
                stream=True,
                max_tokens=64000,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    },
                ],
            )

        import anthropic as _anthropic
        try:
            response = _call_diagnose(modele_diag)
        except _anthropic.BadRequestError as refus:
            # 400 ne veut pas toujours dire « modèle invalide » : un crédit
            # épuisé répond aussi 400 — le motif réel est journalisé.
            logger.warning(
                "[%s] diagnostic '%s' refusé (400 : %s) — fallback diagnostic → %s",
                grades.copy_id, modele_diag, refus, settings.claude_model_heavy,
            )
            try:
                response = _call_diagnose(settings.claude_model_heavy)
            except Exception as exc2:
                logger.error("[%s] Diagnostic fallback heavy échoué : %s", grades.copy_id, exc2)
                return ClaudeResponse(success=False, data=None, confidence=0.0,
                                      raw_response="", error=str(exc2))
        except Exception as exc:
            logger.error("[%s] Diagnostic — erreur inattendue : %s", grades.copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(exc))

        stop = getattr(response, "stop_reason", "?")
        if stop == "max_tokens":
            logger.warning(
                "[%s] Diagnostic tronqué (stop_reason=max_tokens) — réponse incomplète, tentative de réparation JSON",
                grades.copy_id,
            )
        try:
            raw = self._texte_reponse(response)
        except ValueError as exc:
            # Le budget de tokens a pu être entièrement consommé par le bloc
            # `thinking` d'Opus, sans qu'aucun texte ne soit produit (surtout
            # en combinaison avec stop_reason=max_tokens ci-dessus). L'appelant
            # (`_run_phase_b`) traite un diagnostic en échec comme non bloquant
            # et retente via le fallback GPT-5 : il ne faut donc pas laisser
            # cette erreur remonter et interrompre toute la Phase B.
            logger.error("[%s] Diagnostic — %s", grades.copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(exc))
        return self._parse_response(raw, DiagnosticResult)

    # ── Diagnostic contraint (module 4) ───────────────────────────────────────

    @_retry
    def diagnose_constrained(
        self,
        *,
        copy_id: str,
        niveau_test: str,
        questions: list[dict[str, Any]],
        codes_competences: list[str],
        codes_types: list[str],
        corrections: str = "",
    ) -> ClaudeResponse:
        """Diagnostic structuré d'une copie — aucune prose, que des codes.

        `questions` est construit par `referentiel/diagnostic.py` : une entrée par
        question à diagnostiquer, avec ses signatures d'erreur et les codes de
        compétence admis pour elle. Ce client ne connaît pas le référentiel et ne
        le consulte pas — il ne sait qu'appeler le modèle sous contrainte.

        `corrections` porte les motifs de rejet d'une première tentative. C'est la
        redemande exigée par le module 4 : on ne réécrit pas la sortie du modèle à
        sa place, on lui dit ce qui n'allait pas et on redemande.

        Les QCM ne passent jamais ici : leur diagnostic est mécanique
        (`option_qcm`) et aucun appel de modèle ne doit avoir lieu pour eux.
        """
        import json as _json

        logger.info(
            "[%s] Diagnostic contraint — modèle : %s | questions : %d%s",
            copy_id,
            settings.claude_model_opus,
            len(questions),
            " (redemande)" if corrections else "",
        )

        codes_questions = [q["code_question"] for q in questions]
        outil = _diagnostic_contraint_tool(
            codes_questions, codes_competences, codes_types
        )

        bloc_corrections = ""
        if corrections:
            bloc_corrections = (
                "\n\n## Sortie précédente refusée\n"
                "Ta réponse précédente comportait les anomalies suivantes. "
                "Reprends l'analyse complète en les corrigeant — ne rends pas "
                "seulement les lignes fautives.\n"
                f"{corrections}"
            )

        prompt = (
            f"{self._diagnostic_contraint_prompt}"
            f"\n\n## Copie analysée\n"
            f"Test d'entrée en {niveau_test} (copie {copy_id}).\n"
            f"\n## Questions à diagnostiquer\n"
            f"```json\n{_json.dumps(questions, ensure_ascii=False, indent=2)}\n```"
            f"{bloc_corrections}"
        )

        def _appeler(model: str) -> Any:
            return self._creer_message(
                model=model,
                max_tokens=8192,
                temperature=0,
                tools=[outil],
                tool_choice={"type": "tool", "name": "enregistrer_problemes"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                ],
            )

        import anthropic as _anthropic

        try:
            response = _appeler(settings.claude_model_opus)
        except _anthropic.BadRequestError as refus:
            # Même repli que `diagnose()` : un identifiant de modèle invalide ne
            # doit pas priver la copie de son diagnostic.
            logger.warning(
                "[%s] claude_model_opus '%s' refusé (400 : %s) — repli sur %s",
                copy_id, settings.claude_model_opus, refus, settings.claude_model_heavy,
            )
            try:
                response = _appeler(settings.claude_model_heavy)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] Diagnostic contraint échoué : %s", copy_id, exc)
                return ClaudeResponse(success=False, data=None, confidence=0.0,
                                      raw_response="", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Diagnostic contraint — erreur : %s", copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(exc))

        return self._extract_tool_result(response, SortieDiagnosticContraint)

    @_retry
    def diagnose_unanchored(
        self,
        *,
        copy_id: str,
        niveau_test: str,
        productions: list[dict[str, Any]],
        catalogue: list[dict[str, Any]],
        codes_types: list[str],
        corrections: str = "",
        evaluation: str = "Évaluation d'entrée",
    ) -> ClaudeResponse:
        """Diagnostic sans ancrage de question — la mesure « plancher ».

        Le modèle ne reçoit **aucune signature d'erreur** : la production de
        l'élève, le catalogue des compétences déjà enseignées à ce niveau, les
        sept types. C'est la tâche qu'a faite l'humain qui a tagué le corpus de
        référence, donc la seule comparaison loyale possible tant qu'aucune copie
        du nouveau format n'existe — et c'est un plancher, le mode ancré étant
        mieux armé.

        ⚠ Ce qui entre ici doit être la production **brute** de l'élève. Y verser
        la justification d'un tagage reviendrait à donner la réponse avec la
        question : voir l'avertissement en tête de `referentiel/diagnostic.py`.
        """
        import json as _json

        logger.info(
            "[%s] Mesure plancher — modèle : %s | productions : %d | catalogue : %d",
            copy_id, settings.claude_model_opus, len(productions), len(catalogue),
        )

        outil = _diagnostic_contraint_tool(
            [p["repere"] for p in productions],
            [c["code"] for c in catalogue],
            codes_types,
        )

        bloc_corrections = ""
        if corrections:
            bloc_corrections = (
                "\n\n## Sortie précédente refusée\n"
                "Reprends l'analyse complète en corrigeant ceci :\n"
                f"{corrections}"
            )

        prompt = (
            f"{self._diagnostic_plancher_prompt}"
            f"\n\n## Copie analysée\n"
            f"{evaluation} en {niveau_test} (copie {copy_id}).\n"
            f"\n## Compétences du référentiel déjà enseignées à ce niveau\n"
            f"```json\n{_json.dumps(catalogue, ensure_ascii=False, indent=2)}\n```"
            f"\n\n## Ce que l'élève a écrit\n"
            f"```json\n{_json.dumps(productions, ensure_ascii=False, indent=2)}\n```"
            f"{bloc_corrections}"
        )

        try:
            response = self._creer_message(
                model=settings.claude_model_opus,
                max_tokens=8192,
                temperature=0,
                tools=[outil],
                tool_choice={"type": "tool", "name": "enregistrer_problemes"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Mesure plancher — erreur : %s", copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0,
                                  raw_response="", error=str(exc))

        return self._extract_tool_result(response, SortieDiagnosticContraint)

    # ── Sujet de confirmation (T1, module 5) ──────────────────────────────────

    @_retry
    def generate_confirmation_subject(self, request: ConfirmationRequest) -> ClaudeResponse:
        """Génère 2 questions par hypothèse — départage, ne remédie pas."""
        logger.info("[%s] Claude confirmation T1 — modèle : %s | hypothèses : %d",
                    request.copy_id, settings.claude_model_heavy, len(request.hypotheses))
        if not request.hypotheses:
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response="",
                error="Aucune hypothèse à confirmer — pas de sujet T1 à générer.",
            )

        prompt = (
            f"{self._confirmation_subject_prompt}"
            f"\n\n---\n\nHYPOTHÈSES ({len(request.hypotheses)}):\n"
            f"{request.model_dump_json(indent=2)}"
        )

        # `stream=True` + `max_tokens` large : même raison que `_call_diagnose`.
        # `claude_model_heavy` pointe vers une famille (Sonnet 5) qui préfixe sa
        # réponse d'un bloc `thinking` non affiché, et l'échantillonnage
        # (`temperature`) lui est retiré par `_creer_message`. Avec 8192, sur
        # une dizaine d'hypothèses, la pensée interne épuisait tout le budget
        # avant qu'aucun texte JSON ne soit émis (`stop_reason=max_tokens`,
        # `_texte_reponse` lève `ValueError`) — le sujet T1 n'était jamais
        # généré. Constaté en conditions réelles (copie-b8e7f8db4f78, 2026-09-09).
        response = self._creer_message(
            model=settings.claude_model_heavy,
            stream=True,
            max_tokens=64000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt + "\n\nIMPORTANT: Réponds UNIQUEMENT avec un"
                            " objet JSON valide commençant par { et finissant par }."
                            " Aucun texte avant ou après.",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                },
            ],
        )

        if getattr(response, "stop_reason", None) == "max_tokens":
            logger.warning(
                "[%s] Sujet T1 tronqué (stop_reason=max_tokens) — tentative de réparation JSON.",
                request.copy_id,
            )
        try:
            raw = self._texte_reponse(response)
        except ValueError as exc:
            # Budget encore épuisé par le `thinking` : échec propre plutôt que
            # remontée d'exception — l'appelant (`taches._generer_sujet_confirmation`)
            # est best-effort.
            logger.warning("[%s] Sujet T1 non généré — %s", request.copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
        return self._parse_response(raw, ConfirmationSubject)

    # ── Sujet de vérification / rétention (T3, T4, T5, module 5 étendu) ───────

    def _verification_prompt_pour(self, type_evaluation: str) -> str:
        """T3 vérifie une remédiation, T4/T5 vérifient une rétention — deux
        intentions différentes, un seul prompt partagé entre T4 et T5 : le
        délai (45 jours ou 3 mois) ne change pas le contenu du sujet."""
        if type_evaluation == "T3":
            return self._verification_subject_prompt
        return self._retention_subject_prompt

    @_retry
    def generate_verification_subject(self, request: VerificationRequest) -> ClaudeResponse:
        """Génère le sujet T3 (vérification) ou T4/T5 (rétention) : la cause du
        problème est déjà connue, on vérifie seulement si la maîtrise est là."""
        logger.info(
            "[%s] Claude %s — modèle : %s | problèmes : %d",
            request.copy_id, request.type_evaluation, settings.claude_model_heavy,
            len(request.items),
        )
        if not request.items:
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response="",
                error=f"Aucun problème à vérifier — pas de sujet {request.type_evaluation} à générer.",
            )

        prompt = (
            f"{self._verification_prompt_pour(request.type_evaluation)}"
            f"\n\n---\n\nPROBLÈMES ({len(request.items)}):\n"
            f"{request.model_dump_json(indent=2)}"
        )

        # `stream=True` + `max_tokens` large : voir `generate_confirmation_subject`
        # et `_call_diagnose` — le `thinking` de Sonnet 5 épuise sinon le budget
        # avant tout texte JSON, et le sujet n'est jamais produit.
        response = self._creer_message(
            model=settings.claude_model_heavy,
            stream=True,
            max_tokens=64000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt + "\n\nIMPORTANT: Réponds UNIQUEMENT avec un"
                            " objet JSON valide commençant par { et finissant par }."
                            " Aucun texte avant ou après.",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                },
            ],
        )

        if getattr(response, "stop_reason", None) == "max_tokens":
            logger.warning(
                "[%s] Sujet %s tronqué (stop_reason=max_tokens) — tentative de réparation JSON.",
                request.copy_id, request.type_evaluation,
            )
        try:
            raw = self._texte_reponse(response)
        except ValueError as exc:
            logger.warning("[%s] Sujet %s non généré — %s", request.copy_id, request.type_evaluation, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
        return self._parse_response(raw, VerificationSubject)

    # ── Plan de remédiation (cahier élève) ────────────────────────────────────

    def _appel_outil(self, *, copy_id: str, etape: str, prompt_fixe: str, prompt_variable: str,
                     outil: dict[str, Any], max_tokens: int, modele: str | None = None) -> Any:
        """Appel à sortie par outil, Opus puis repli Sonnet sur 400 (même
        repli que `diagnose_constrained`). La partie fixe du prompt (consignes
        + exemples) est mise en cache : elle est identique pour toutes les
        sections d'un plan, appelées en parallèle.

        L'outil n'est pas forcé (`tool_choice` auto) : un choix forcé interdit
        la réflexion préalable, et c'est elle qui fait vérifier au modèle ses
        calculs avant d'écrire les exercices (essai réel du 2026-10-26 :
        réponses incohérentes et exercices hors sujet sans elle). Le prompt
        demande l'appel ; une réponse sans bloc `tool_use` est un échec, que
        l'appelant redemande.

        `modele` : impose le modèle (dernière tentative d'une section, sur le
        modèle de repli), sans repli supplémentaire."""
        import anthropic as _anthropic

        def _appeler(model: str) -> Any:
            return self._creer_message(
                model=model,
                stream=True,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": "high"},
                tools=[outil],
                tool_choice={"type": "auto"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_fixe, "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": prompt_variable},
                    ],
                }],
            )

        if modele:
            return _appeler(modele)
        try:
            return _appeler(self._modele_opus)
        except _anthropic.BadRequestError as refus:
            logger.warning("[%s] %s : modèle '%s' refusé (400 : %s) — repli sur %s",
                           copy_id, etape, self._modele_opus, refus, self._modele_heavy)
            return _appeler(self._modele_heavy)

    @property
    def modele_repli(self) -> str:
        return self._modele_heavy

    @_retry
    def generate_plan_section(self, demande: "DemandePlan", section: "SectionPlanDemande",
                              refus: str = "", modele: str | None = None) -> ClaudeResponse:
        """Rédige une section du plan de remédiation. Le squelette (compétence,
        durée, questions, prérequis) est fixé par l'appelant ; le modèle n'écrit
        que le contenu (`ContenuSection`).

        `refus` : motif du rejet de la tentative précédente, rendu au modèle
        pour qu'il le corrige plutôt que de retenter à l'aveugle."""
        import json as _json

        logger.info("[%s] Plan — section %d (%s), modèle : %s",
                    demande.copy_id, section.ordre, section.code_competence, modele or self._modele_opus)
        contexte = {
            "eleve": {"prenom": demande.prenom, "classe": demande.classe},
            "test": demande.test_libelle,
            "section": section.model_dump(exclude={"duree_h"}),
        }
        prompt_variable = (
            "## Section à rédiger\n"
            "`questions` : les questions de la copie rattachées à cette compétence, "
            "telles que la correction les a relevées (`citation` : ce que le "
            "diagnostic a lu sur la copie). `types_erreur` : le diagnostic retenu, "
            "à expliquer dans `causes`. `libelles_prerequis` : compétences "
            "travaillées dans les sections précédentes.\n"
            f"```json\n{_json.dumps(contexte, ensure_ascii=False, indent=2)}\n```"
        )
        if refus:
            prompt_variable += (
                "\n\n## Ta réponse précédente a été refusée\n"
                f"{refus}\n"
                "Rédige à nouveau la section entière en corrigeant ce point, et "
                "rends-la en appelant l'outil `rediger_section` : tous les champs "
                "obligatoires remplis (listes non vides, exactement cinq exercices)."
            )
        try:
            response = self._appel_outil(
                copy_id=demande.copy_id, etape=f"plan section {section.ordre}",
                prompt_fixe=self._plan_remediation_prompt, prompt_variable=prompt_variable,
                outil=_OUTIL_SECTION_PLAN, max_tokens=32000, modele=modele,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_retryable(exc):
                raise  # surcharge, quota : relancé par @_retry
            logger.error("[%s] Plan — section %d : %s", demande.copy_id, section.ordre, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
        return self._extract_tool_result(response, ContenuSection)

    @_retry
    def generate_plan_acquis(self, demande: "DemandePlan") -> ClaudeResponse:
        """Rédige « Ce que tu sais déjà faire » à partir des questions réussies."""
        import json as _json

        questions = [q.model_dump(include={"code", "intitule", "reponse_eleve", "reponse_attendue"})
                     for q in demande.questions_reussies]
        prompt_variable = (
            f"## Élève\n{demande.prenom}, {demande.classe} — {demande.test_libelle}.\n\n"
            f"## Questions réussies\n```json\n{_json.dumps(questions, ensure_ascii=False, indent=2)}\n```"
        )
        try:
            response = self._appel_outil(
                copy_id=demande.copy_id, etape="plan acquis",
                prompt_fixe=self._plan_acquis_prompt, prompt_variable=prompt_variable,
                outil=_OUTIL_ACQUIS_PLAN, max_tokens=8000,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_retryable(exc):
                raise  # surcharge, quota : relancé par @_retry
            logger.error("[%s] Plan — acquis : %s", demande.copy_id, exc)
            return ClaudeResponse(success=False, data=None, confidence=0.0, raw_response="", error=str(exc))
        return self._extract_tool_result(response, ContenuAcquis)

    # ── Nom de l'élève depuis la première page ────────────────────────────────

    def extract_student_name(self, first_page: Path) -> str:
        """
        Lit la première page de la copie et retourne le nom complet de l'élève.
        Cherche les champs NOM / PRENOM / NOM ET PRENOM / NAME typiques d'une
        feuille d'examen. Retourne une chaîne vide si rien n'est trouvé.
        Fallback : appelé quand le client de transcription actif (Gemini par
        défaut) n'a pas trouvé de nom ou a échoué.
        """
        logger.info("Claude extraction nom — modèle : %s | page : %s",
                    settings.claude_model_light, first_page.name)
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Regarde cette image de copie d'élève. "
                    "Trouve le nom et le prénom de l'élève (champs NOM, PRENOM, "
                    "NOM ET PRENOM, ou équivalent). "
                    "Retourne UNIQUEMENT le nom complet sous la forme 'Prénom NOM', "
                    "sans aucun autre texte ni ponctuation. "
                    "Si tu ne trouves pas de nom, retourne exactement la chaîne vide."
                ),
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._media_type(first_page),
                    "data": self._encode_image(first_page),
                },
            },
        ]
        try:
            response = self._creer_message(
                model=settings.claude_model_light,
                max_tokens=64,
                temperature=0,
                messages=[{"role": "user", "content": content}],
            )
            name = self._texte_reponse(response)
            # Rejet si la réponse ressemble à un texte d'échec plutôt qu'un nom
            if len(name) > 80 or "\n" in name:
                return ""
            return name
        except Exception as e:
            logger.warning("extract_student_name échoué : %s", e)
            return ""

    # ── Extraction des questions depuis la transcription ──────────────────────

    @_retry
    def extract_questions_from_transcription(
        self, transcription: TranscriptionResult
    ) -> Rubric:
        """
        Extrait la liste stable des questions depuis la transcription pour créer
        un barème virtuel utilisé quand aucun barème n'est fourni.

        Sépare l'identification des questions du jugement de correction :
        cette passe produit une liste déterministe (tool_use, temperature implicitement
        faible) qui sera passée comme rubric fixe à l'étape de grading.

        Retourne un Rubric vide si aucune question n'est identifiable.
        """
        logger.info(
            "[%s] Extraction des questions depuis la transcription (modèle : %s)…",
            transcription.copy_id, settings.claude_model_heavy,
        )
        content_parts = [
            f"Page {p.page_number} :\n{p.content}"
            for p in transcription.pages
            if p.content.strip() and p.content.strip() != "[ILLISIBLE]"
        ]
        if not content_parts:
            logger.warning(
                "[%s] Transcription vide — impossible d'extraire les questions.",
                transcription.copy_id,
            )
            return Rubric(subject="mathematics", total_points=0, items=[])

        prompt = (
            "Analyse cette transcription de copie d'élève de mathématiques.\n"
            "Identifie TOUTES les questions et sous-questions visibles "
            "(cherche les numéros d'exercices, lettres de sous-questions, etc.).\n"
            "Génère des identifiants courts et cohérents : Q1, Q2a, Q2b, Q3, etc.\n"
            "Ne note pas les réponses — liste uniquement les questions.\n\n"
            "TRANSCRIPTION :\n" + "\n\n".join(content_parts)
        )

        response = self._creer_message(
            model=settings.claude_model_heavy,
            max_tokens=1024,
            temperature=0,
            tools=[_QUESTIONS_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "save_questions"},
            messages=[{"role": "user", "content": prompt}],
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None or not isinstance(tool_block.input, dict):
            logger.warning(
                "[%s] Extraction des questions : aucun bloc tool_use reçu.",
                transcription.copy_id,
            )
            return Rubric(subject="mathematics", total_points=0, items=[])

        raw_questions = tool_block.input.get("questions", [])
        items = [
            RubricItem(
                id=q.get("id", f"Q{i + 1}"),
                label=q.get("label", ""),
            )
            for i, q in enumerate(raw_questions)
            if isinstance(q, dict) and q.get("id")
        ]

        logger.warning(
            "[%s] Barème virtuel extrait : %d question(s) — %s",
            transcription.copy_id,
            len(items),
            ", ".join(item.id for item in items[:10]) + ("…" if len(items) > 10 else ""),
        )
        return Rubric(subject="mathematics", total_points=len(items), items=items)

    # ── Énoncé ────────────────────────────────────────────────────────────────

    def extract_subject(self, file_path: Path) -> str:
        images = (
            self._pdf_to_images(file_path)
            if file_path.suffix.lower() == ".pdf"
            else [file_path]
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Transcris intégralement le texte de cet énoncé. "
                    "Retourne uniquement le texte brut, sans JSON, sans commentaire."
                ),
            },
            *[
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": self._media_type(img),
                        "data": self._encode_image(img),
                    },
                }
                for img in images
            ],
        ]
        response = self._creer_message(
            model=settings.claude_model_light,
            max_tokens=2048,
            temperature=0,
            messages=[{"role": "user", "content": content}],
        )
        return self._texte_reponse(response)

    # ── Extraction barème depuis PDF/image ────────────────────────────────────

    @_retry
    def extract_rubric(self, file_path: Path) -> ClaudeResponse:
        """Extrait un barème structuré depuis un PDF ou une image via tool_use."""
        images = (
            self._pdf_to_images(file_path)
            if file_path.suffix.lower() == ".pdf"
            else [file_path]
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Extrais tous les items de ce barème. "
                    "Pour chaque question ou sous-question, donne son identifiant "
                    "(Q1, Q2a, Q2b, etc.) et son libellé. "
                    "Si le document indique un nombre de points par question, "
                    "utilise-le pour calculer total_points."
                ),
            },
            *[
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": self._media_type(img),
                        "data": self._encode_image(img),
                    },
                }
                for img in images
            ],
        ]

        response = self._creer_message(
            model=settings.claude_model_heavy,
            max_tokens=2048,
            temperature=0,
            tools=[_RUBRIC_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "save_rubric"},
            messages=[{"role": "user", "content": content}],
        )

        raw_resp = self._extract_tool_result(response, _ExtractedRubric)
        if not raw_resp.success or raw_resp.data is None:
            return raw_resp

        extracted: _ExtractedRubric = raw_resp.data
        items = [
            RubricItem(
                id=item.get("id", f"Q{i+1}"),
                label=item.get("label", ""),
                parent_id=item.get("parent_id") or None,
            )
            for i, item in enumerate(extracted.items)
        ]
        total = extracted.total_points or len(items)
        rubric = Rubric(subject="mathematics", total_points=total, items=items)
        return ClaudeResponse(
            success=True,
            data=rubric,
            confidence=raw_resp.confidence,
            raw_response=raw_resp.raw_response,
            error=None,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _media_type(self, path: Path) -> str:
        return _MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")

    def _encode_image(self, path: Path) -> str:
        import base64
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    def _pdf_to_images(self, pdf_path: Path) -> list[Path]:
        import fitz
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp())
        doc = fitz.open(pdf_path)
        images: list[Path] = []
        for i in range(len(doc)):
            pix = doc.load_page(i).get_pixmap(dpi=150)  # 150 DPI : équilibre qualité/tokens
            img_path = tmp_dir / f"subject_page_{i+1}.jpg"
            pix.save(str(img_path))
            images.append(img_path)
        doc.close()
        return images

    # ── Normalisation des tableaux de strings ─────────────────────────────────

    @staticmethod
    def _item_to_str(item: Any) -> str:
        """Convertit un élément (string ou dict) en string propre.

        Claude retourne parfois des objets {"expression": "...", "interpretation": "..."}
        ou {"zone": "...", "note": "..."} là où le schéma attend une simple string.
        """
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            # Formule : préférer 'expression', sinon 'formula', sinon première valeur
            for key in ("expression", "formula", "formule"):
                if key in item:
                    val = str(item[key])
                    note = item.get("interpretation") or item.get("annotation")
                    return f"{val} ({note})" if note else val
            # Incertitude : préférer 'zone' + 'note'
            for key in ("zone", "area", "location"):
                if key in item:
                    zone = str(item[key])
                    note = item.get("note") or item.get("description") or item.get("issue")
                    return f"{zone} : {note}" if note else zone
            # Schéma : préférer 'description'
            for key in ("description", "desc", "content"):
                if key in item:
                    return str(item[key])
            # Fallback : première valeur non-vide
            for v in item.values():
                if v:
                    return str(v)
        return str(item)

    @classmethod
    def _normalize_transcription(cls, data: Any) -> dict:
        """Normalise le dict issu du tool_use avant validation Pydantic.

        Gère les cas dégénérés :
        - data est une string (JSON partiel non parsé par le SDK)
        - pages[i] est une string au lieu d'un dict
        - formulas/uncertainties[j] est un dict au lieu d'une string
        """
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return {"copy_id": "unknown", "global_quality": "poor", "pages": []}

        if not isinstance(data, dict):
            return {"copy_id": "unknown", "global_quality": "poor", "pages": []}

        raw_pages = data.get("pages", [])
        if not isinstance(raw_pages, list):
            raw_pages = []

        normalized: list[dict] = []
        for i, page in enumerate(raw_pages):
            if isinstance(page, str):
                # Claude a renvoyé la page comme texte brut
                normalized.append({
                    "page_number": i + 1,
                    "content": page,
                    "formulas": [],
                    "diagrams": [],
                    "uncertainties": [],
                    "confidence": 0.5,
                })
            elif isinstance(page, dict):
                # Garantit que content est toujours une chaîne
                if not isinstance(page.get("content"), str):
                    page["content"] = str(page.get("content") or "")
                for field in ("formulas", "diagrams", "uncertainties"):
                    val = page.get(field, [])
                    if not isinstance(val, list):
                        val = [val] if val else []
                    page[field] = [cls._item_to_str(x) for x in val if x is not None]
                normalized.append(page)

        data["pages"] = normalized
        return data

    # ── Extraction tool_use ───────────────────────────────────────────────────

    @staticmethod
    def _normaliser_problemes(data: dict) -> dict:
        """Remet `problemes` en liste quand le modèle l'a emballé autrement.

        Deux formes constatées sur Sonnet 5 (2026-08-01), les deux
        intermittentes et les deux fatales telles quelles :

        1. `{"problemes": {…}}` — un objet seul là où une liste est attendue,
           quand il n'y a qu'un problème à déclarer ;
        2. `{"problemes": "{\\"problemes\\": [{…}]}"}` — **tout le JSON réemballé
           dans une chaîne**, à l'intérieur du champ qu'il était censé remplir.

        Pydantic refuse, `_extract_tool_result` rend un échec, et **la copie
        entière est perdue**. Deux des cinq copies du corpus rendaient ainsi zéro
        problème — ce qui se lit comme « aucune lacune détectée », pas comme une
        panne de format. C'est le pire des symptômes : un échec qui a l'air d'un
        résultat.

        ⚠ Ce n'est pas une entorse à la règle « une sortie refusée n'est jamais
        réparée à sa place » (module 4). Cette règle porte sur le **contenu** :
        on n'invente pas un code, on ne déplace pas une compétence. Ici on
        déballe, sans rien ajouter ni modifier. Les codes obtenus restent soumis
        inchangés à la validation par question, seule juge de leur admissibilité.
        """
        problemes = data.get("problemes")

        if isinstance(problemes, str):
            try:
                decode = json.loads(problemes)
            except json.JSONDecodeError:
                return data
            logger.warning("`problemes` rendu comme chaîne JSON — déballé tel quel.")
            # Le modèle réemballe parfois l'objet complet, clé comprise.
            if isinstance(decode, dict) and "problemes" in decode:
                decode = decode["problemes"]
            problemes = decode
            data = dict(data)
            data["problemes"] = problemes

        if isinstance(problemes, dict):
            logger.warning(
                "`problemes` rendu comme objet seul plutôt que liste — enveloppé "
                "sans modification de son contenu."
            )
            data = dict(data)
            data["problemes"] = [problemes]

        return data

    @staticmethod
    def _normaliser_listes_texte(data: dict) -> dict:
        """Listes de textes du plan (`causes`, `a_retenir`, `methode`,
        `acquis`) : Opus 5 y glisse parfois un objet vide `{}` (essai réel du
        2026-10-26, section entière rejetée deux fois de suite). Un élément
        vide est retiré, un objet à valeur texte unique ramené à ce texte ; si
        la liste se vide, la validation échoue et la section est redemandée."""
        for champ in ("causes", "a_retenir", "methode", "acquis"):
            valeurs = data.get(champ)
            if not isinstance(valeurs, list):
                continue
            propres = []
            for v in valeurs:
                if isinstance(v, dict):
                    textes = [x for x in v.values() if isinstance(x, str) and x.strip()]
                    v = textes[0] if len(textes) == 1 else None
                if isinstance(v, str) and v.strip():
                    propres.append(v)
            if len(propres) != len(valeurs):
                logger.warning("Plan : %d élément(s) non textuel(s) retiré(s) de « %s »",
                               len(valeurs) - len(propres), champ)
            data[champ] = propres
        return data

    def _extract_tool_result(self, response: Any, model_cls: type) -> ClaudeResponse:
        """Extrait le résultat d'un appel tool_use — JSON garanti correctement formé."""
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )

        if tool_block is None:
            stop = getattr(response, "stop_reason", "?")
            logger.error(
                "Aucun bloc tool_use (stop_reason=%s, model=%s, blocs=%s)",
                stop, model_cls.__name__, [b.type for b in response.content],
            )
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response=str(response.content),
                error=f"Réponse tronquée avant l'appel outil (stop_reason={stop}).",
            )

        # ── Normalise tool_block.input en dict Python ──────────────────────────
        raw = tool_block.input
        raw_repr = repr(raw)[:400]
        logger.debug("tool_block.input type=%s val=%.400s", type(raw).__name__, raw_repr)

        try:
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError as je:
                    # JSON partiel — tente une réparation basique
                    repaired = _TRAILING_COMMA.sub(r"\1", raw)
                    repaired = _close_json(repaired)
                    try:
                        raw = json.loads(repaired)
                    except json.JSONDecodeError:
                        logger.error("Input outil tronqué irréparable : %s — %.200s", je, raw)
                        return ClaudeResponse(
                            success=False, data=None, confidence=0.0,
                            raw_response=raw,
                            error=f"Input outil JSON invalide : {je}",
                        )

            # Convertit en dict Python quelle que soit la source
            if isinstance(raw, dict):
                data: dict = dict(raw)
            else:
                # Fallback : sérialise/désérialise pour obtenir un dict propre
                try:
                    data = json.loads(json.dumps(raw, default=str))
                    if not isinstance(data, dict):
                        data = {}
                except Exception:
                    data = {}
                logger.warning(
                    "tool_block.input inattendu (type=%s) — converti en dict: %s",
                    type(raw).__name__, str(data)[:200],
                )

            if model_cls is TranscriptionResult:
                data = self._normalize_transcription(data)
            elif model_cls is SortieDiagnosticContraint:
                data = self._normaliser_problemes(data)
            elif model_cls in (ContenuSection, ContenuAcquis):
                data = self._normaliser_listes_texte(data)

            validated = model_cls(**data)
            return ClaudeResponse(
                success=True,
                data=validated,
                confidence=self._estimate_confidence(validated),
                raw_response=str(raw)[:2000],
                error=None,
            )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(
                "Erreur dans _extract_tool_result (%s) :\n%s\ntool_block.input type=%s val=%.400s",
                model_cls.__name__, tb, type(raw).__name__, raw_repr,
            )
            return ClaudeResponse(
                success=False, data=None, confidence=0.0,
                raw_response=raw_repr,
                error=f"{e} [input_type={type(raw).__name__}]",
            )

    def _parse_response(self, raw_text: str, model_cls: type) -> ClaudeResponse:
        """Parse JSON brut — utilisé uniquement pour diagnose (pas de tool_use)."""
        text = raw_text.strip()

        match = _JSON_FENCE.search(text)
        if match:
            text = match.group(1).strip()
        else:
            open_fence = re.search(r"```(?:json)?\s*([\s\S]+)$", text, re.IGNORECASE)
            if open_fence:
                text = open_fence.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

        text = _TRAILING_COMMA.sub(r"\1", text)

        derniere_erreur: Exception | None = None
        for candidate in (text, _close_json(text)):
            candidate = _TRAILING_COMMA.sub(r"\1", candidate)
            try:
                data = json.loads(candidate)
                # Défauts pour DiagnosticResult partiellement tronqué
                if model_cls.__name__ == "DiagnosticResult":
                    data.setdefault("academic_profile", "")
                    data.setdefault("strengths", [])
                    data.setdefault("weaknesses", [])
                    data.setdefault("skills", [])
                    data.setdefault("remediation_plan", [])
                    data.setdefault("root_causes", [])
                validated = model_cls(**data)
                return ClaudeResponse(
                    success=True,
                    data=validated,
                    confidence=self._estimate_confidence(validated),
                    raw_response=raw_text,
                    error=None,
                )
            except Exception as exc:  # noqa: BLE001 — capturée pour être loggée, pas silencieusement perdue
                derniere_erreur = exc
                continue

        # La raison réelle (JSON malformé vs modèle Pydantic invalide, et le
        # message précis) était jusqu'ici jetée — seul un extrait de 300
        # caractères du texte brut survivait, sans dire pourquoi le parsing
        # avait échoué. Elle est maintenant loggée en entier (DEBUG, peut
        # être volumineux) pour permettre un post-mortem.
        logger.error(
            "JSON irréparable (%s) — %s : %s. Début : %.300s",
            model_cls.__name__,
            type(derniere_erreur).__name__ if derniere_erreur else "?",
            derniere_erreur,
            raw_text,
        )
        logger.debug("[%s] Texte brut complet de la réponse échouée :\n%s", model_cls.__name__, raw_text)
        return ClaudeResponse(
            success=False,
            data=None,
            confidence=0.0,
            raw_response=raw_text,
            error=f"JSON invalide ({type(derniere_erreur).__name__ if derniere_erreur else '?'}) : {derniere_erreur}",
        )

    def _estimate_confidence(self, result: Any) -> float:
        if hasattr(result, "global_quality"):
            return {"good": 0.9, "medium": 0.7, "poor": 0.5}.get(result.global_quality, 0.5)
        if hasattr(result, "questions"):
            confidences = [q.confidence for q in result.questions if hasattr(q, "confidence")]
            return sum(confidences) / len(confidences) if confidences else 0.5
        return 0.8
