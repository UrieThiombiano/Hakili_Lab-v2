"""
Pipeline Hakili Lab — Correction assistée par IA.

Flux en deux phases :
  Phase A : ingestion → transcription → (relecture enseignant) → correction IA
            → (arrêt : validation enseignant)
  Phase B : RAG → diagnostic → export PDF + JSON (pas de sujet de remédiation
            généré ici — voir la note plus bas)

  Mode Copie Unique (interactif, avec relecture transcription) :
    run_transcription() → écran de relecture (l'enseignant corrige la
    transcription) → run_grading() → tableau de validation → run_phase_b().

  Mode Batch (pas de relecture transcription, trop coûteux en temps sur un
  lot de copies) :
    run_phase_a() [= run_transcription() + run_grading() enchaînés]
    → tableau de validation → run_phase_b().

Routage multi-providers (Paramètres → Modèles IA, `data/preferences_modeles.json`,
prime sur .env — D-CEO-44) :
  Transcription  → tâche "transcription" : "claude" | "gemini" | "openai"
  Correction     → tâche "correction"    : "deepseek" | "claude" | "gemini"
  Diagnostic     → tâche "analyse"        : "gemini" | "claude" | "openai" | "deepseek"

  Fallback automatique sur GPT-5 (OpenAI) si le provider principal de l'étape
  échoue — transcription, nom élève, correction, diagnostic.
  Claude n'est plus utilisé comme fallback : il reste seul utilisé là où il
  n'y a pas d'alternative (extraction sujet/barème uploadé, barème virtuel,
  enrichissement 20/20 — voir claude_client.py).

  Aucun sujet de remédiation IA n'est plus généré par le pipeline (D-CEO-33) :
  à T0, seules des hypothèses de lacunes sont produites (diagnostic
  ci-dessous), et c'est le sujet de confirmation T1 (module 5,
  `generate_confirmation_subject`) qui prend le relais — jamais un sujet
  d'exercices de remédiation généré à l'aveugle avant confirmation. Le plan de
  remédiation chiffré (module 6, `suivi/plan.py`) est généré à la demande,
  après confirmation, hors de ce pipeline.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from tenacity import retry, stop_after_attempt, wait_fixed

from src.api.claude_client import ClaudeClient
from src.api.openai_client import OpenAIClient
from src.core import preferences_modeles
from src.core.config import settings
from src.knowledge.curriculum_retriever import CurriculumRetriever
from src.models.domain import (
    CompetencyGap,
    CopyGrade,
    DiagnosticResult,
    IngestionResult,
    Rubric,
    RemediationSubject,
    TeacherDecision,
    TranscriptionResult,
)
from src.pipeline.ancrage_incertitudes import ancrer_incertitudes
from src.pipeline.depot import depot
from src.pipeline.ingestion import ingest_images, ingest_pdf
from src.pipeline.orchestrator import (
    ValidationIssue,
    consolider_corrections,
    validate_diagnostic,
    validate_grading,
    validate_transcription,
)
from src.pipeline.pdf_remediation_html import generate_remediation_pdf
from src.pipeline.pdf_report_html import generate_copy_report

# Singleton RAG — chargé une seule fois pour toute la session
_retriever: CurriculumRetriever | None = None


def _get_retriever() -> CurriculumRetriever:
    global _retriever
    if _retriever is None:
        _retriever = CurriculumRetriever()
    return _retriever


logger = logging.getLogger(__name__)


# ── Factories de clients ───────────────────────────────────────────────────────

# Le fournisseur de chaque étape vient de Paramètres → Modèles IA
# (`data/preferences_modeles.json`, D-CEO-44), avec repli sur les valeurs `.env`.
# Le repli client reste Claude partout : c'est le seul provider sans trou de
# couverture (transcription, correction, diagnostic).

def _make_transcription_client():
    r = preferences_modeles.resoudre("transcription")
    if r.fournisseur == "gemini" and settings.google_api_key:
        from src.api.gemini_client import GeminiTranscriptionClient
        return GeminiTranscriptionClient()
    if r.fournisseur == "openai" and settings.openai_api_key:
        return OpenAIClient()
    return ClaudeClient(modele_heavy=r.modele)


def _make_grading_client():
    r = preferences_modeles.resoudre("correction")
    if r.fournisseur == "deepseek" and settings.deepseek_api_key:
        from src.api.deepseek_client import DeepSeekClient
        return DeepSeekClient()
    if r.fournisseur == "gemini" and settings.google_api_key:
        from src.api.gemini_client import GeminiTranscriptionClient
        return GeminiTranscriptionClient()
    return ClaudeClient(modele_heavy=r.modele)


def _make_diagnostic_client():
    r = preferences_modeles.resoudre("analyse")
    if r.fournisseur == "deepseek" and settings.deepseek_api_key:
        from src.api.deepseek_client import DeepSeekClient
        return DeepSeekClient()
    if r.fournisseur == "gemini" and settings.google_api_key:
        from src.api.gemini_client import GeminiTranscriptionClient
        return GeminiTranscriptionClient()
    if r.fournisseur == "openai" and settings.openai_api_key:
        return OpenAIClient()
    return ClaudeClient(modele_opus=r.modele)


def _fallback_openai_client() -> OpenAIClient | None:
    """Instancie le client GPT-5 de secours — None (et log) si OPENAI_API_KEY absente."""
    try:
        return OpenAIClient()
    except ValueError as e:
        logger.error("Fallback GPT-5 indisponible : %s", e)
        return None


def _client_label(client, step: str = "") -> str:
    cls = type(client).__name__
    if cls == "GeminiTranscriptionClient":
        return f"Gemini · {getattr(client, '_model', settings.gemini_model)}"
    if cls == "MistralTranscriptionClient":
        return f"Mistral · {settings.mistral_vision_model}"
    if cls == "DeepSeekClient":
        if step == "diagnostic":
            return f"DeepSeek R1 · {settings.deepseek_model_r1}"
        return f"DeepSeek V3 · {settings.deepseek_model_v3}"
    if cls == "MistralRemediationClient":
        return f"Mistral Small · {settings.mistral_model}"
    if cls == "OpenAIClient":
        return f"GPT-5 · {settings.openai_model}"
    if step == "diagnostic":
        return f"Claude · {getattr(client, '_modele_opus', settings.claude_model_opus)}"
    return f"Claude · {getattr(client, '_modele_heavy', settings.claude_model_heavy)}"


# ── Persistance base de données (best-effort — ne bloque jamais le pipeline) ──
# Le pipeline ne connaît pas la base : il écrit dans le dépôt courant
# (`src/pipeline/depot.py`), que l'application installe au démarrage. Sans base
# configurée — portail de consultation, essais hors ligne — le dépôt neutre ne
# fait rien et la correction se déroule quand même.
#
# Retry léger : une base serverless (ex. Neon) peut refuser la toute première
# connexion après une période d'inactivité ("cold start") puis fonctionner
# normalement l'instant d'après — observé en pratique (rapport perdu alors
# que la remédiation, écrite juste après dans une connexion neuve, réussit).
_retry_db = retry(stop=stop_after_attempt(2), wait=wait_fixed(1.5), reraise=True)


# Placeholder de repli si le Sheet élèves n'a pas de classe renseignée pour
# l'élève choisi (voir _db_persist_scan). Écrasé par le point 5 une fois
# l'en-tête transcrit et résolu via classe_normalizer.resolve_classe(). Ne
# jamais y substituer une valeur devinée : "Non renseignée" est honnête, une
# classe fausse ne l'est pas.
_CLASSE_PLACEHOLDER = "Non renseignée"


def _db_persist_scan(*, copy_id: str, file_paths: list[Path], identifiant_hakili: str) -> None:
    """Point d'injection 1 : vérifie que l'élève choisi existe dans les
    Google Sheets, puis crée la Copie + le document 'scan' en base.

    IMPORTANT — contrairement au reste de cette fonction (et au reste des
    points d'injection), la vérification d'existence de l'élève N'EST PAS
    best-effort : si identifiant_hakili est vide ou introuvable dans les
    Sheets, on lève une exception qui remonte et arrête le pipeline avant
    tout appel IA payant (voir l'appel en tout premier dans _run_transcription,
    avant la construction des clients). Une fois l'élève confirmé,
    l'écriture en base elle-même reste best-effort — une erreur réseau/DB ne
    bloque jamais le pipeline, comme les autres points d'injection.
    """
    if not identifiant_hakili:
        raise ValueError("Aucun élève sélectionné — impossible de traiter cette copie.")

    from src.integrations.google_sheets import GoogleSheetsError, get_eleve_by_identifiant

    try:
        eleve = get_eleve_by_identifiant(identifiant_hakili)
    except GoogleSheetsError as exc:
        logger.warning(
            "[%s] [DB WARNING] Vérification élève impossible (Google Sheets injoignable) : %s",
            copy_id, exc,
        )
        raise RuntimeError(
            f"Impossible de vérifier l'élève auprès des Google Sheets : {exc}"
        ) from exc

    if eleve is None:
        logger.warning(
            "[%s] [DB WARNING] Identifiant élève '%s' introuvable dans les Google Sheets "
            "— traitement bloqué, aucun appel IA effectué.",
            copy_id, identifiant_hakili,
        )
        raise ValueError(
            f"Élève introuvable (identifiant '{identifiant_hakili}') dans les Google "
            f"Sheets — vérifiez la sélection. Aucun traitement effectué."
        )

    if not file_paths:
        return

    # Classe initiale : celle déclarée pour l'élève dans le Sheet (info
    # réelle disponible dès la sélection — voir décision documentée dans le
    # rapport de chantier). Écrasée au point 5 si l'extraction depuis
    # l'en-tête transcrit donne un résultat fiable et différent (garde-fou
    # anti-erreur de saisie/anti-décalage administratif — voir
    # _apply_extracted_classe). Repli sur le placeholder si le Sheet n'a pas
    # de classe renseignée pour cet élève.
    classe_initiale = (eleve.get("classe") or "").strip() or _CLASSE_PLACEHOLDER

    try:
        scan_bytes = file_paths[0].read_bytes()

        @_retry_db
        def _write() -> None:
            depot().creer_copie(
                copy_id=copy_id,
                identifiant_hakili=identifiant_hakili,
                classe=classe_initiale,
                annee_scolaire=str(datetime.now().year),
            )
            depot().ajouter_document(
                copy_id=copy_id, type_document="scan", contenu=scan_bytes
            )

        _write()
        logger.warning(
            "[%s] [DB OK] Copie créée pour identifiant_hakili=%s (classe initiale=%s)",
            copy_id, identifiant_hakili, classe_initiale,
        )
    except Exception as e:
        logger.warning("[%s] [DB WARNING] Erreur écriture base (scan) : %s", copy_id, e)


def _db_add_document(copy_id: str, doc_type: str, path: Path | None) -> None:
    """Points d'injection 2 (rapport) et 3 (remédiation) : ajoute un document
    généré à la copie existante. Best-effort — n'échoue jamais le pipeline
    (ex. si la copie n'a pas pu être créée au point 1, l'insertion échoue
    proprement sur la contrainte de clé étrangère et est journalisée)."""
    if not path or not path.exists():
        return
    try:
        doc_bytes = path.read_bytes()

        @_retry_db
        def _write() -> None:
            depot().ajouter_document(
                copy_id=copy_id, type_document=doc_type, contenu=doc_bytes
            )

        _write()
        logger.warning("[%s] [DB OK] Document '%s' ajouté", copy_id, doc_type)
    except Exception as e:
        logger.warning("[%s] [DB WARNING] Erreur ajout document '%s' : %s", copy_id, doc_type, e)


def _score_on_20(total: float, denom: float) -> float | None:
    """Même formule que CopyGrade.compute_final_score() (arrondi au 0.25 le
    plus proche) — dupliquée ici volontairement pour ne pas muter grade.final_score
    avant que la validation enseignant n'ait réellement eu lieu."""
    if denom <= 0:
        return None
    return round(round(total / denom * 20 * 4) / 4, 2)


def _db_update_notes(copy_id: str, notes_finales: float | None) -> None:
    """Point d'injection 4 : écrit/écrase COPIE.notes_finales (déjà sur 20,
    aucune conversion à faire — voir CopyGrade.final_score_on_20).

    Appelé deux fois par exécution :
    - en fin de run_grading(), avec la note IA provisoire (avant validation
      enseignant) ;
    - en Phase B, avec la note validée — écrase toujours la valeur précédente,
      donc la dernière écriture est toujours la plus fiable.

    Si aucune note fiable n'est disponible (barème vide → denom=0), on
    n'écrit rien plutôt que d'inventer une valeur. Best-effort : n'échoue
    jamais le pipeline.
    """
    if notes_finales is None:
        return
    try:
        @_retry_db
        def _write() -> None:
            depot().maj_notes(copy_id=copy_id, notes_finales=notes_finales)

        _write()
        logger.warning("[%s] [DB OK] Note finale enregistrée : %.2f/20", copy_id, notes_finales)
    except Exception as e:
        logger.warning("[%s] [DB WARNING] Erreur écriture note : %s", copy_id, e)


def _db_update_classe(copy_id: str, classe: str) -> None:
    """Point d'injection 5 : écrase le placeholder posé au point 1 avec la
    classe réellement extraite de l'en-tête transcrit. Best-effort — n'échoue
    jamais le pipeline."""
    try:
        @_retry_db
        def _write() -> None:
            depot().maj_classe(copy_id=copy_id, classe=classe)

        _write()
        logger.warning("[%s] [DB OK] Classe enregistrée : %s", copy_id, classe)
    except Exception as e:
        logger.warning("[%s] [DB WARNING] Erreur écriture classe : %s", copy_id, e)


def _apply_extracted_classe(*, copy_id: str, transcription, bareme_id: str) -> None:
    """Résout la classe réelle à partir de l'en-tête transcrit et l'écrit en
    base si — et seulement si — le résultat est fiable (voir
    classe_normalizer.resolve_classe : ne jamais deviner). En cas d'échec,
    le placeholder "Non renseignée" posé au point 1 reste en base."""
    from src.core.classe_normalizer import (
        extract_raw_classe_header,
        niveaux_to_canonical_list,
        normalize_classe,
        resolve_classe,
    )

    if not transcription or not transcription.pages:
        return

    raw = extract_raw_classe_header(transcription.pages[0].content)
    extracted = normalize_classe(raw) if raw else None

    niveaux_declares: list[str] = []
    if bareme_id:
        try:
            from src.knowledge.test_registry import get_registry
            test = get_registry().get_test(bareme_id)
            if test and test.niveaux:
                niveaux_declares = niveaux_to_canonical_list(test.niveaux)
        except Exception:
            pass

    classe, reason = resolve_classe(extracted=extracted, niveaux_declares=niveaux_declares)

    if classe is None:
        logger.warning(
            "[%s] [DB WARNING] Classe non déterminée (%s) — brut='%s', extrait=%s, "
            "niveaux déclarés=%s. Copie laissée en '%s'.",
            copy_id, reason, raw, extracted, niveaux_declares, _CLASSE_PLACEHOLDER,
        )
        return

    _db_update_classe(copy_id, classe)


# ── Résultat du pipeline ──────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    copy_id: str
    student_name: str
    ingestion: IngestionResult
    transcription: TranscriptionResult | None = None
    grade: CopyGrade | None = None
    diagnostic: DiagnosticResult | None = None
    remediation_subject: RemediationSubject | None = None
    pdf_path: Path | None = None
    remediation_pdf_path: Path | None = None
    json_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    model_routing: dict[str, str] = field(default_factory=dict)
    # rubric conservé pour la Phase B
    rubric: Rubric | None = None
    subject_text: str = ""
    bareme_id: str = ""
    runs_dir: str = ""
    # conservés entre run_transcription() et run_grading()
    expert_instructions: str = ""
    official_answers: str = ""

    @property
    def success(self) -> bool:
        return self.grade is not None and not self.errors

    @property
    def transcription_ready(self) -> bool:
        return self.transcription is not None

    @property
    def phase_a_complete(self) -> bool:
        return self.grade is not None

    @property
    def phase_b_complete(self) -> bool:
        return self.pdf_path is not None


# ── Phase A — ingestion → transcription → (relecture enseignant) → correction IA ─

def run_transcription(
    *,
    copy_id: str,
    identifiant_hakili: str,
    student_name: str = "",
    file_paths: list[Path],
    rubric: Rubric,
    rubric_file_path: Path | None = None,
    subject_text: str = "",
    subject_file_path: Path | None = None,
    expert_instructions: str = "",
    bareme_id: str = "",
    official_answers: str = "",
    runs_dir: Path | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> PipelineResult:
    """
    Étape 1 de la Phase A : ingestion → transcription. S'arrête avant la
    correction — l'enseignant relit/corrige la transcription (écran de
    relecture) avant qu'elle soit envoyée au modèle de correction via
    run_grading().

    identifiant_hakili : élève choisi explicitement par l'enseignant avant
    le lancement (liste alimentée par les Google Sheets — voir
    src.integrations.google_sheets). Vérifié dès le tout début de
    _run_transcription, avant tout appel IA : si l'élève n'existe pas dans
    les Sheets, le traitement est bloqué et remonte dans errors ci-dessous.
    """
    sentinel = PipelineResult(
        copy_id=copy_id,
        student_name=student_name,
        ingestion=None,  # type: ignore[arg-type]
    )
    try:
        return _run_transcription(
            copy_id=copy_id,
            identifiant_hakili=identifiant_hakili,
            student_name=student_name,
            file_paths=file_paths,
            rubric=rubric,
            rubric_file_path=rubric_file_path,
            subject_text=subject_text,
            subject_file_path=subject_file_path,
            expert_instructions=expert_instructions,
            bareme_id=bareme_id,
            official_answers=official_answers,
            runs_dir=runs_dir,
            on_progress=on_progress,
        )
    except Exception as exc:
        logger.exception("[%s] Erreur transcription : %s", copy_id, exc)
        sentinel.errors.append(f"Erreur transcription : {exc}")
        return sentinel


def _run_transcription(
    *,
    copy_id: str,
    identifiant_hakili: str,
    student_name: str,
    file_paths: list[Path],
    rubric: Rubric,
    rubric_file_path: Path | None,
    subject_text: str,
    subject_file_path: Path | None,
    expert_instructions: str,
    bareme_id: str,
    official_answers: str,
    runs_dir: Path | None,
    on_progress: Callable[[str, int], None] | None,
) -> PipelineResult:
    # Point d'injection 1, tout premier appel de la fonction : vérifie que
    # l'élève sélectionné existe dans les Google Sheets AVANT tout appel IA
    # payant (construction des clients ci-dessous incluse), et crée la Copie
    # + le document scan si oui. Bloque (exception) si l'élève est introuvable.
    _db_persist_scan(copy_id=copy_id, file_paths=file_paths, identifiant_hakili=identifiant_hakili)

    def _progress(step: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(step, pct)
            except Exception:
                pass

    out = Path(runs_dir or settings.runs_dir)
    claude_client = ClaudeClient()
    transcription_client = _make_transcription_client()

    logger.warning(
        "[%s] Transcription — provider=%s", copy_id, type(transcription_client).__name__,
    )

    # Extraction parallèle énoncé + barème si nécessaire
    need_subject = not subject_text.strip() and subject_file_path is not None
    need_rubric  = not rubric.items and rubric_file_path is not None

    if need_subject and need_rubric:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_s = pool.submit(claude_client.extract_subject, subject_file_path)
            fut_r = pool.submit(claude_client.extract_rubric, rubric_file_path)
            subject_text = fut_s.result()
            rubric_resp  = fut_r.result()
        if rubric_resp.success and rubric_resp.data is not None:
            rubric = rubric_resp.data
    elif need_subject:
        subject_text = claude_client.extract_subject(subject_file_path)
    elif need_rubric:
        rubric_resp = claude_client.extract_rubric(rubric_file_path)
        if rubric_resp.success and rubric_resp.data is not None:
            rubric = rubric_resp.data

    # 1. Ingestion
    _progress("ingestion", 5)
    if len(file_paths) == 1 and file_paths[0].suffix.lower() == ".pdf":
        ingestion = ingest_pdf(file_paths[0], copy_id, out)
    else:
        ingestion = ingest_images(file_paths, copy_id, out)

    # Extraction nom élève si placeholder
    _name_is_placeholder = (
        not student_name.strip()
        or student_name.strip().replace(" ", "").isdigit()
        or len(student_name.strip()) <= 2
    )
    if _name_is_placeholder and ingestion.pages:
        extracted = ""
        if hasattr(transcription_client, "extract_student_name"):
            try:
                extracted = transcription_client.extract_student_name(ingestion.pages[0])
            except Exception as exc:
                logger.warning(
                    "[%s] extract_student_name (%s) échoué : %s",
                    copy_id, type(transcription_client).__name__, exc,
                )
        if not extracted and type(transcription_client).__name__ != "OpenAIClient":
            fallback = _fallback_openai_client()
            if fallback is not None:
                extracted = fallback.extract_student_name(ingestion.pages[0])
        if extracted:
            student_name = extracted

    result = PipelineResult(
        copy_id=copy_id,
        student_name=student_name,
        ingestion=ingestion,
        rubric=rubric,
        subject_text=subject_text,
        bareme_id=bareme_id,
        expert_instructions=expert_instructions,
        official_answers=official_answers,
        runs_dir=str(out),
    )
    result.model_routing = {
        "Transcription": _client_label(transcription_client, "transcription"),
        "Extraction (barème/énoncé)": f"Claude · {settings.claude_model_heavy}",
    }

    # 2. Transcription
    _progress("transcription", 30)
    trans_resp = transcription_client.transcribe(copy_id, ingestion.pages)
    if not trans_resp.success or trans_resp.data is None:
        if type(transcription_client).__name__ != "OpenAIClient":
            fallback = _fallback_openai_client()
            if fallback is not None:
                logger.warning("[%s] Fallback transcription → GPT-5", copy_id)
                trans_resp = fallback.transcribe(copy_id, ingestion.pages)
                result.model_routing["Transcription"] += " → GPT-5 (fallback)"
    if not trans_resp.success or trans_resp.data is None:
        result.errors.append(f"Transcription échouée : {trans_resp.error}")
        return result

    vt = validate_transcription(trans_resp.data)
    result.validation_issues.extend(vt.issues)
    if not vt.valid:
        result.errors.append(f"Transcription invalide : {vt.summary}")
        return result
    # Les doutes listés par le modèle sans `⟦…⟧` dans le texte deviennent des
    # zones surlignées, corrigeables au double-clic en relecture.
    result.transcription = ancrer_incertitudes(vt.data)

    # Point d'injection 5 — classe réelle extraite de l'en-tête transcrit
    # (écrase le placeholder posé au point 1).
    _apply_extracted_classe(copy_id=copy_id, transcription=result.transcription, bareme_id=bareme_id)

    _progress("awaiting_transcription_review", 45)
    logger.warning(
        "[%s] ✓ Transcription terminée — %d page(s) — en attente de relecture enseignant",
        copy_id, len(result.transcription.pages),
    )
    return result


def run_grading(
    *,
    result: PipelineResult,
    on_progress: Callable[[str, int], None] | None = None,
) -> PipelineResult:
    """
    Étape 2 de la Phase A : correction IA à partir de la transcription
    validée par l'enseignant. Reçoit le PipelineResult produit par
    run_transcription() — transcription.pages[i].content a pu être réécrit
    par l'enseignant dans l'écran de relecture.
    """
    if result.transcription is None:
        result.errors.append("Correction impossible : aucune transcription disponible.")
        return result
    sentinel = result
    try:
        return _run_grading(result=result, on_progress=on_progress)
    except Exception as exc:
        logger.exception("[%s] Erreur correction : %s", result.copy_id, exc)
        sentinel.errors.append(f"Erreur correction : {exc}")
        return sentinel


def _run_grading(
    *,
    result: PipelineResult,
    on_progress: Callable[[str, int], None] | None,
) -> PipelineResult:

    def _progress(step: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(step, pct)
            except Exception:
                pass

    copy_id = result.copy_id
    rubric  = result.rubric or Rubric(subject="mathematics", total_points=0, items=[])

    claude_client   = ClaudeClient()
    grading_client  = _make_grading_client()
    result.model_routing["Correction (proposition IA)"] = _client_label(grading_client, "grading")

    # Barème virtuel si aucun barème fourni
    if not rubric.items:
        rubric = claude_client.extract_questions_from_transcription(result.transcription)
        result.rubric = rubric

    # 3. Correction IA (proposition)
    _progress("correction", 55)
    # Sans barème (mode personnalisé ou extraction échouée), seul Claude peut auto-résoudre
    # les questions — DeepSeek/Mistral ne font pas de self-solving sur rubric vide.
    _grading = claude_client if not rubric.items else grading_client
    if _grading is not grading_client:
        logger.warning("[%s] Aucun barème disponible — correction déléguée à Claude (auto-résolution)", copy_id)
        result.model_routing["Correction (proposition IA)"] = f"Claude · {settings.claude_model_heavy} (auto)"

    grading_kwargs = dict(
        transcription=result.transcription,
        rubric=rubric,
        subject_text=result.subject_text,
        expert_instructions=result.expert_instructions,
        official_answers=result.official_answers,
        temperature=0,
    )
    repli_utilise: list[bool] = []

    def _corriger_une_fois():
        """Une correction complète (repli GPT-5 compris), validée."""
        grade_resp = _grading.grade(**grading_kwargs)
        if not grade_resp.success or grade_resp.data is None:
            if type(_grading).__name__ != "OpenAIClient":
                fallback = _fallback_openai_client()
                if fallback is not None:
                    logger.warning("[%s] Fallback correction → GPT-5", copy_id)
                    grade_resp = fallback.grade(**grading_kwargs)
                    repli_utilise.append(True)
        if not grade_resp.success or grade_resp.data is None:
            return None, f"Correction échouée : {grade_resp.error}", []
        grade = grade_resp.data
        grade.copy_id = copy_id
        vg = validate_grading(grade, rubric_provided=bool(rubric.items), rubric=rubric)
        if not vg.valid:
            return None, f"Correction invalide : {vg.summary}", vg.issues
        return vg.data, "", vg.issues

    # Barème détaillé (tests du référentiel) : plusieurs corrections
    # indépendantes, consolidées par médiane — voir consolider_corrections.
    bareme_detaille = any(item.points_corrige for item in rubric.items)
    nb_passages = max(1, settings.nb_corrections_ia) if bareme_detaille else 1
    with ThreadPoolExecutor(max_workers=nb_passages) as pool:
        passages = list(pool.map(lambda _i: _corriger_une_fois(), range(nb_passages)))
    if repli_utilise:
        result.model_routing["Correction (proposition IA)"] += " → GPT-5 (fallback)"

    reussis = [p for p in passages if p[0] is not None]
    if not reussis:
        _, erreur, issues = passages[0]
        result.validation_issues.extend(issues)
        result.errors.append(erreur)
        return result

    result.validation_issues.extend(reussis[0][2])
    if len(reussis) > 1:
        result.model_routing["Correction (proposition IA)"] += f" · {len(reussis)} passages, médiane"
    result.grade = consolider_corrections([p[0] for p in reussis], rubric)

    # Injecter les bonnes réponses officielles du corrigé dans chaque question
    if result.bareme_id:
        from src.knowledge.answer_loader import get_answer_loader
        answer_map = get_answer_loader().get_answer_map(result.bareme_id)
        if answer_map:
            for q in result.grade.questions:
                if not q.correct_answer and q.rubric_item_id in answer_map:
                    q.correct_answer = answer_map[q.rubric_item_id]

    _progress("awaiting_validation", 60)
    _score_20 = _score_on_20(result.grade.total_score, result.grade.total_possible)
    logger.warning(
        "[%s] ✓ Correction terminée — %d questions, score IA : %g/%g pts → %s/20 — en attente de validation enseignant",
        copy_id, len(result.grade.questions),
        result.grade.total_score, result.grade.total_possible, _score_20,
    )
    # Point d'injection 4a — note IA provisoire (avant validation enseignant,
    # sera écrasée par la note validée au point 4b en Phase B).
    _db_update_notes(copy_id, _score_20)
    return result


def run_phase_a(
    *,
    copy_id: str,
    identifiant_hakili: str,
    student_name: str = "",
    file_paths: list[Path],
    rubric: Rubric,
    rubric_file_path: Path | None = None,
    subject_text: str = "",
    subject_file_path: Path | None = None,
    expert_instructions: str = "",
    bareme_id: str = "",
    official_answers: str = "",
    runs_dir: Path | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> PipelineResult:
    """
    Phase A complète : transcription → correction IA, sans arrêt intermédiaire.
    Utilisé par le mode Batch, qui ne propose pas d'écran de relecture de la
    transcription (trop coûteux en temps enseignant sur un lot de copies).
    Le mode Copie Unique appelle run_transcription() puis run_grading()
    séparément, avec l'écran de relecture enseignant entre les deux.
    """
    result = run_transcription(
        copy_id=copy_id,
        identifiant_hakili=identifiant_hakili,
        student_name=student_name,
        file_paths=file_paths,
        rubric=rubric,
        rubric_file_path=rubric_file_path,
        subject_text=subject_text,
        subject_file_path=subject_file_path,
        expert_instructions=expert_instructions,
        bareme_id=bareme_id,
        official_answers=official_answers,
        runs_dir=runs_dir,
        on_progress=on_progress,
    )
    if result.errors or result.transcription is None:
        return result
    return run_grading(result=result, on_progress=on_progress)


# ── Phase B — RAG → diagnostic → remédiation → export ─────────────────────────

def run_phase_b(
    *,
    result: PipelineResult,
    on_progress: Callable[[str, int], None] | None = None,
    ancrage: Callable[[list[str]], tuple[str, list[dict]]] | None = None,
) -> PipelineResult:
    """
    Phase B : ancrage programme + diagnostic + remédiation + export PDF + JSON.
    Reçoit le PipelineResult de la Phase A après validation enseignant.
    result.grade doit avoir compute_final_score() déjà appelé.

    `ancrage` : fonction qui, pour une liste de codes de questions échouées, rend
    (contexte_texte, lacunes). Passée par l'appelant plutôt qu'importée ici, parce
    que sa source — le référentiel — vit dans une application Django, et que ce
    module doit rester indépendant de tout framework. Sans elle, on retombe sur
    l'ancrage historique par `chunk_ids`, qui ne couvre que les tests d'avant le
    référentiel v2.
    """
    if result.grade is None:
        result.errors.append("Phase B impossible : aucune correction disponible.")
        return result

    # Calcul du score final si pas encore fait
    if result.grade.final_score is None:
        result.grade.compute_final_score()

    sentinel = result
    try:
        return _run_phase_b(result=result, on_progress=on_progress, ancrage=ancrage)
    except Exception as exc:
        logger.exception("[%s] Erreur Phase B : %s", result.copy_id, exc)
        sentinel.errors.append(f"Erreur Phase B : {exc}")
        return sentinel


def _run_phase_b(
    *,
    result: PipelineResult,
    on_progress: Callable[[str, int], None] | None,
    ancrage: Callable[[list[str]], tuple[str, list[dict]]] | None = None,
) -> PipelineResult:

    def _progress(step: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(step, pct)
            except Exception:
                pass

    copy_id    = result.copy_id
    grade      = result.grade
    rubric     = result.rubric
    bareme_id  = result.bareme_id
    out        = Path(result.runs_dir or settings.runs_dir)

    # Point d'injection 4b — note validée (écrase la note IA provisoire du point 4a).
    # final_score_on_20 est garanti non-None ici : run_phase_b() l'a calculé
    # si besoin avant d'appeler _run_phase_b().
    _db_update_notes(copy_id, grade.final_score_on_20)

    claude_client      = ClaudeClient()
    diagnostic_client  = _make_diagnostic_client()

    result.model_routing.update({
        "Diagnostic": _client_label(diagnostic_client, "diagnostic"),
    })

    # Détection score parfait (20/20 après validation enseignant)
    is_perfect = (grade.final_score_on_20 or 0) >= 20.0

    if is_perfect:
        # Score parfait → exercices d'enrichissement niveau 2nde/1ère, pas de remédiation
        logger.warning("[%s] Score parfait 20/20 — génération d'exercices d'enrichissement", copy_id)
        _progress("enrichment", 75)
        enrich_resp = claude_client.generate_enrichment_subject(grade, rubric)
        if enrich_resp.success and enrich_resp.data is not None:
            result.remediation_subject = enrich_resp.data
        else:
            logger.warning("[%s] Enrichissement échoué (non bloquant) : %s", copy_id, enrich_resp.error)
    else:
        # Le diagnostic raisonne en taux de réussite (0 = échouée, 1 = complète) :
        # avec les barèmes détaillés, une question vaut 0,333 ou 0,667 point
        # sur 20 et une réussite partielle n'est ni 0 ni 1.
        grade_diag = _grade_en_taux(grade, rubric)

        # Questions non réussies entièrement après validation enseignant : les
        # réponses partielles (démarche absente, conclusion manquante) sont des
        # lacunes à ancrer au même titre que les échecs.
        failed_ids = [
            q.rubric_item_id for q in grade_diag.questions
            if _effective_score(q) < 1
        ]

        # 4. Ancrage sur le programme officiel
        _progress("rag", 65)
        curriculum_context = ""
        competency_gaps: list[CompetencyGap] = []

        if failed_ids:
            # `ancrage` est fourni par l'appelant quand le référentiel est
            # disponible (voir referentiel/contexte.py). Ce module ne l'importe
            # pas lui-même : `src/` ne doit dépendre ni de Django ni d'aucun
            # framework — c'est ce qui lui permet de servir les deux interfaces
            # pendant la migration.
            if ancrage is not None:
                curriculum_context, raw_gaps = ancrage(failed_ids)
                competency_gaps = [CompetencyGap(**g) for g in raw_gaps]
                source = "référentiel"
            elif bareme_id:
                # Chemin historique : les anciens barèmes portent des `chunk_ids`
                # vers les leçons du curriculum. Les barèmes générés depuis le
                # classeur n'en ont pas — sans `ancrage`, le diagnostic tournerait
                # sans aucun contexte programme.
                retriever = _get_retriever()
                curriculum_context = retriever.get_diagnostic_context(failed_ids, bareme_id)
                raw_gaps = retriever.get_competency_gaps(failed_ids, bareme_id)
                competency_gaps = [CompetencyGap(**g) for g in raw_gaps]
                source = "curriculum (chunk_ids)"
            else:
                source = "aucun"

            if not curriculum_context:
                logger.warning(
                    "[%s] Diagnostic SANS ancrage programme (source: %s, barème: %s) — "
                    "les lacunes ne seront pas rattachées à une compétence.",
                    copy_id, source, bareme_id or "aucun",
                )
            else:
                logger.info(
                    "[%s] Ancrage %s — %d lacunes pour %d questions échouées.",
                    copy_id, source, len(competency_gaps), len(failed_ids),
                )

        # 5. Diagnostic
        _progress("diagnostic", 75)
        diag_resp = diagnostic_client.diagnose(grade_diag, curriculum_context=curriculum_context)
        if not diag_resp.success or diag_resp.data is None:
            if type(diagnostic_client).__name__ != "OpenAIClient":
                fallback = _fallback_openai_client()
                if fallback is not None:
                    logger.warning("[%s] Fallback diagnostic → GPT-5", copy_id)
                    diag_resp = fallback.diagnose(grade_diag, curriculum_context=curriculum_context)
        if diag_resp.success and diag_resp.data is not None:
            diag_resp.data.competency_gaps = competency_gaps
            vd = validate_diagnostic(diag_resp.data, grade_diag)
            result.validation_issues.extend(vd.issues)
            result.diagnostic = vd.data
        else:
            logger.warning("[%s] Diagnostic échoué (non bloquant) : %s", copy_id, diag_resp.error)

        # Pas de sujet de remédiation généré ici : à T0, seules des hypothèses
        # de lacunes sont produites (diagnostic ci-dessus). C'est le test de
        # confirmation T1 (module 5) qui départage hypothèse confirmée / écartée
        # avant qu'un plan de remédiation ait un sens — voir docs/cycle_de_suivi.md.

    # 7. Export JSON
    _progress("export", 94)
    json_dir = out / copy_id
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / "result.json"
    payload = {
        "copy_id": copy_id,
        "student_name": result.student_name,
        "final_score": grade.final_score,
        "final_score_on_20": grade.final_score_on_20,
        "total_possible": grade.total_possible,
        "transcription": result.transcription.model_dump() if result.transcription else None,
        "grade": grade.model_dump(),
        "diagnostic": result.diagnostic.model_dump() if result.diagnostic else None,
        "remediation_subject": result.remediation_subject.model_dump() if result.remediation_subject else None,
        "errors": list(result.errors or []),
        "validation_issues": [asdict(i) for i in (result.validation_issues or [])],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.json_path = json_path

    # 8. Génération PDF (rapport + remédiation/enrichissement en parallèle)
    pdf_path = json_dir / "rapport_correction.pdf"
    _is_enrich = getattr(result.remediation_subject, "is_enrichment", False)
    remediation_pdf_path = json_dir / (
        "sujet_enrichissement.pdf" if _is_enrich else "sujet_remediation.pdf"
    )
    has_remediation = bool(result.remediation_subject and result.remediation_subject.exercises)

    def _gen_report() -> None:
        generate_copy_report(
            output_path=pdf_path,
            copy_id=copy_id,
            student_name=result.student_name,
            grade=grade,
            diagnostic=result.diagnostic,
            rubric=rubric,
        )

    def _gen_remediation() -> None:
        if has_remediation:
            generate_remediation_pdf(
                output_path=remediation_pdf_path,
                copy_id=copy_id,
                student_name=result.student_name,
                remediation_subject=result.remediation_subject,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(_gen_report).result()
        pool.submit(_gen_remediation).result()

    result.pdf_path = pdf_path
    # Point d'injection 2 — rapport généré : document "rapport" (best-effort)
    _db_add_document(copy_id, "rapport", pdf_path)

    if has_remediation:
        result.remediation_pdf_path = remediation_pdf_path
        # Point d'injection 3 — remédiation générée : document "remediation" (best-effort)
        _db_add_document(copy_id, "remediation", remediation_pdf_path)

    n_exercises = len(result.remediation_subject.exercises) if result.remediation_subject else 0
    logger.warning(
        "[%s] ✓ Phase B terminée — note finale : %g/%g (%.1f/20) | %d exercices remédiation",
        copy_id,
        grade.final_score or 0, grade.total_possible,
        grade.final_score_on_20 or 0,
        n_exercises,
    )
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade_en_taux(grade, rubric):
    """Copie de la correction où chaque score devient un taux de réussite
    (score effectif / maximum de la question, arrondi au centième) — l'échelle
    attendue par les consignes de diagnostic. Sans barème, inchangée."""
    from src.models.domain import TeacherDecision

    maxima = {item.id: item.max_score for item in (rubric.items if rubric else [])}
    if not maxima:
        return grade
    questions = []
    for q in grade.questions:
        maximum = maxima.get(q.rubric_item_id)
        if not maximum:
            questions.append(q)
            continue
        taux = round(min(max(_effective_score(q) / maximum, 0.0), 1.0), 2)
        questions.append(q.model_copy(update={
            "score": taux,
            "teacher_score": taux if q.teacher_decision == TeacherDecision.refused and q.teacher_score is not None else q.teacher_score,
        }))
    return grade.model_copy(update={"questions": questions})


def _effective_score(q) -> float:
    """Score effectif d'une question : décision enseignant si disponible, sinon IA."""
    from src.models.domain import TeacherDecision
    if q.teacher_decision == TeacherDecision.refused and q.teacher_score is not None:
        return q.teacher_score
    return q.score


# ── Wrapper de compatibilité (mode batch / tests) ─────────────────────────────

def run_single_copy(
    *,
    copy_id: str,
    identifiant_hakili: str,
    student_name: str = "",
    file_paths: list[Path],
    rubric: Rubric,
    rubric_file_path: Path | None = None,
    subject_text: str = "",
    subject_file_path: Path | None = None,
    expert_instructions: str = "",
    bareme_id: str = "",
    official_answers: str = "",
    runs_dir: Path | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> PipelineResult:
    """
    Wrapper pour le mode batch : enchaîne Phase A (sans relecture transcription)
    + validation automatique (tout accepté) + Phase B.
    En mode interactif (traitement unique), utiliser run_transcription() → écran de
    relecture → run_grading() → tableau de validation → run_phase_b() séparément.
    """
    result = run_phase_a(
        copy_id=copy_id,
        identifiant_hakili=identifiant_hakili,
        student_name=student_name,
        file_paths=file_paths,
        rubric=rubric,
        rubric_file_path=rubric_file_path,
        subject_text=subject_text,
        subject_file_path=subject_file_path,
        expert_instructions=expert_instructions,
        bareme_id=bareme_id,
        official_answers=official_answers,
        runs_dir=runs_dir,
        on_progress=on_progress,
    )
    if not result.success or result.grade is None:
        return result

    # Validation automatique : tout accepté
    for q in result.grade.questions:
        q.teacher_decision = TeacherDecision.accepted
    result.grade.compute_final_score()

    return run_phase_b(result=result, on_progress=on_progress)
