"""
Pipeline Hakili Lab — Correction assistée par IA.

Flux en deux phases :
  Phase A : ingestion → transcription → (relecture enseignant) → correction IA
            → (arrêt : validation enseignant)
  Phase B : RAG → diagnostic → plan de remédiation → export PDF + JSON

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
  plan de remédiation — voir claude_client.py).

  Deux PDF par copie : le rapport de correction, et — sous 19/20 — le plan de
  remédiation (cahier élève, exercices et réponses compris). Le squelette du
  plan (compétences, ordre, durées) vient du diagnostic contraint et du
  référentiel : l'application le calcule et le passe à `run_phase_b`
  (`demande_plan`) ; ce module n'en rédige que le contenu.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable


from src.api.claude_client import ClaudeClient
from src.api.openai_client import OpenAIClient
from src.core import preferences_modeles
from src.core.config import settings
from src.knowledge.curriculum_retriever import CurriculumRetriever
from src.models.domain import (
    CompetencyGap,
    CopyGrade,
    ContenuSection,
    DemandePlan,
    DiagnosticResult,
    IngestionResult,
    PlanRemediation,
    Rubric,
    TeacherDecision,
    TranscriptionResult,
)
from src.pipeline.ancrage_incertitudes import ancrer_incertitudes
from src.pipeline.ingestion import ingest_images, ingest_pdf
from src.pipeline.orchestrator import (
    ValidationIssue,
    consolider_corrections,
    validate_diagnostic,
    validate_grading,
    validate_transcription,
)
from src.pipeline.pdf_plan_remediation import generate_plan_remediation_pdf
from src.pipeline.pdf_report_html import generate_copy_report
from src.pipeline.plan_remediation import PlanIncomplet, generer_plan, plan_requis

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


# ── Rien n'est écrit en base pendant l'analyse ───────────────────────────────
# Le pipeline produit dans son espace de travail (`runs_dir/<copy_id>/`) : la
# note, la classe, le rapport et le plan restent dans `PipelineResult`. Ils ne
# sont conservés que si l'enseignant sauvegarde l'analyse — décision de
# l'utilisateur du 2026-10-26, qui remplace les cinq points d'injection
# best-effort de D-CEO-19.


# Placeholder si le Sheet élèves n'a pas de classe renseignée pour l'élève
# choisi. Remplacé par la classe lue sur l'en-tête transcrit quand elle est
# fiable (`_apply_extracted_classe`). Ne jamais y substituer une valeur devinée :
# "Non renseignée" est honnête, une classe fausse ne l'est pas.
_CLASSE_PLACEHOLDER = "Non renseignée"


def _verifier_eleve(*, copy_id: str, identifiant_hakili: str) -> dict:
    """Vérifie que l'élève choisi existe dans les Google Sheets et rend sa
    fiche. Bloquant : appelé avant tout appel IA payant (D-CEO-20) — un élève
    introuvable ou un Sheet injoignable arrête le pipeline."""
    if not identifiant_hakili:
        raise ValueError("Aucun élève sélectionné — impossible de traiter cette copie.")

    from src.integrations.google_sheets import GoogleSheetsError, get_eleve_by_identifiant

    try:
        eleve = get_eleve_by_identifiant(identifiant_hakili)
    except GoogleSheetsError as exc:
        logger.warning("[%s] Vérification élève impossible (Google Sheets injoignable) : %s", copy_id, exc)
        raise RuntimeError(f"Impossible de vérifier l'élève auprès des Google Sheets : {exc}") from exc

    if eleve is None:
        logger.warning(
            "[%s] Identifiant élève '%s' introuvable dans les Google Sheets — traitement bloqué, "
            "aucun appel IA effectué.", copy_id, identifiant_hakili,
        )
        raise ValueError(
            f"Élève introuvable (identifiant '{identifiant_hakili}') dans les Google "
            f"Sheets — vérifiez la sélection. Aucun traitement effectué."
        )
    return eleve


def _score_on_20(total: float, denom: float) -> float | None:
    """Même formule que CopyGrade.compute_final_score() (arrondi au 0.25 le
    plus proche) — dupliquée ici volontairement pour ne pas muter grade.final_score
    avant que la validation enseignant n'ait réellement eu lieu."""
    if denom <= 0:
        return None
    return round(round(total / denom * 20 * 4) / 4, 2)


def _apply_extracted_classe(*, copy_id: str, transcription, bareme_id: str) -> str | None:
    """Classe réelle lue sur l'en-tête transcrit, si — et seulement si — le
    résultat est fiable (voir classe_normalizer.resolve_classe : ne jamais
    deviner). `None` sinon : la classe du Sheet est gardée."""
    from src.core.classe_normalizer import (
        extract_raw_classe_header,
        niveaux_to_canonical_list,
        normalize_classe,
        resolve_classe,
    )

    if not transcription or not transcription.pages:
        return None

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
            "[%s] Classe non déterminée (%s) — brut='%s', extrait=%s, "
            "niveaux déclarés=%s. Classe du Sheet conservée.",
            copy_id, reason, raw, extracted, niveaux_declares,
        )
        return None
    return classe


# ── Résultat du pipeline ──────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    copy_id: str
    student_name: str
    ingestion: IngestionResult
    transcription: TranscriptionResult | None = None
    grade: CopyGrade | None = None
    diagnostic: DiagnosticResult | None = None
    plan_remediation: PlanRemediation | None = None
    #: Motif d'absence de plan alors qu'il en fallait un (note < 19) — vide sinon.
    plan_erreur: str = ""
    #: Squelette du plan, gardé pour pouvoir reprendre un plan incomplet
    #: (`reprendre_plan`) sans refaire l'analyse.
    demande_plan: DemandePlan | None = None
    #: Plan incomplet : sections déjà rédigées (par numéro d'ordre) et acquis.
    plan_sections_redigees: dict[int, ContenuSection] = field(default_factory=dict)
    plan_acquis_rediges: list[str] = field(default_factory=list)
    #: Classe de l'élève pour cette copie : celle du Sheet, remplacée par
    #: l'en-tête transcrit quand il est fiable. Écrite en base à la sauvegarde.
    classe: str = ""
    pdf_path: Path | None = None
    #: PDF du plan de remédiation (`plan_remediation.pdf`), None sans plan.
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
    # Tout premier appel : l'élève sélectionné existe-t-il dans les Google
    # Sheets ? Vérifié AVANT tout appel IA payant (construction des clients
    # ci-dessous incluse). Bloque (exception) si l'élève est introuvable.
    eleve = _verifier_eleve(copy_id=copy_id, identifiant_hakili=identifiant_hakili)
    classe_sheet = (eleve.get("classe") or "").strip() or _CLASSE_PLACEHOLDER

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
        classe=classe_sheet,
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

    # Classe réelle lue sur l'en-tête transcrit, quand elle est fiable.
    result.classe = (
        _apply_extracted_classe(copy_id=copy_id, transcription=result.transcription, bareme_id=bareme_id)
        or result.classe
    )

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
    demande_plan: DemandePlan | None = None,
) -> PipelineResult:
    """
    Phase B : ancrage programme + diagnostic + plan de remédiation + export PDF + JSON.
    Reçoit le PipelineResult de la Phase A après validation enseignant.
    result.grade doit avoir compute_final_score() déjà appelé.

    `ancrage` : fonction qui, pour une liste de codes de questions échouées, rend
    (contexte_texte, lacunes). Passée par l'appelant plutôt qu'importée ici, parce
    que sa source — le référentiel — vit dans l'application, et que ce
    module doit rester indépendant de tout framework. Sans elle, on retombe sur
    l'ancrage historique par `chunk_ids`, qui ne couvre que les tests d'avant le
    référentiel v2.

    `demande_plan` : squelette du plan de remédiation, calculé par l'application
    depuis le diagnostic contraint et le référentiel, pour même raison. Sans
    lui (mode libre, test hors référentiel), pas de plan ; une note ≥ 19/20
    n'en a pas non plus.
    """
    if result.grade is None:
        result.errors.append("Phase B impossible : aucune correction disponible.")
        return result

    # Calcul du score final si pas encore fait
    if result.grade.final_score is None:
        result.grade.compute_final_score()

    sentinel = result
    try:
        return _run_phase_b(result=result, on_progress=on_progress, ancrage=ancrage, demande_plan=demande_plan)
    except Exception as exc:
        logger.exception("[%s] Erreur Phase B : %s", result.copy_id, exc)
        sentinel.errors.append(f"Erreur Phase B : {exc}")
        return sentinel


def _run_phase_b(
    *,
    result: PipelineResult,
    on_progress: Callable[[str, int], None] | None,
    ancrage: Callable[[list[str]], tuple[str, list[dict]]] | None = None,
    demande_plan: DemandePlan | None = None,
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

    claude_client      = ClaudeClient()
    diagnostic_client  = _make_diagnostic_client()

    result.model_routing.update({
        "Diagnostic": _client_label(diagnostic_client, "diagnostic"),
    })

    # Score parfait (20/20 après validation enseignant) : rien à diagnostiquer.
    is_perfect = (grade.final_score_on_20 or 0) >= 20.0

    if not is_perfect:
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

    # 6. Plan de remédiation — sous 19/20 seulement. Non bloquant : sans plan,
    # le rapport de correction reste produit, et le motif est conservé pour
    # être montré à l'enseignant.
    if plan_requis(grade.final_score_on_20):
        result.demande_plan = demande_plan
        if demande_plan is None:
            result.plan_erreur = "Pas de plan : le diagnostic de la copie n'a pas pu être établi."
        elif not demande_plan.sections:
            result.plan_erreur = "Pas de plan : le diagnostic n'a relevé aucune compétence à reprendre."
        else:
            _progress("plan", 80)
            _rediger_plan(result, claude_client)
        if result.plan_erreur:
            logger.warning("[%s] %s", copy_id, result.plan_erreur)

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
        "plan_remediation": result.plan_remediation.model_dump() if result.plan_remediation else None,
        "plan_erreur": result.plan_erreur,
        "errors": list(result.errors or []),
        "validation_issues": [asdict(i) for i in (result.validation_issues or [])],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.json_path = json_path

    # 8. Génération PDF (rapport + plan de remédiation en parallèle)
    pdf_path = json_dir / "rapport_correction.pdf"
    remediation_pdf_path = json_dir / "plan_remediation.pdf"
    has_remediation = result.plan_remediation is not None

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
            generate_plan_remediation_pdf(remediation_pdf_path, result.plan_remediation)

    with ThreadPoolExecutor(max_workers=2) as pool:
        rapport = pool.submit(_gen_report)
        plan_pdf = pool.submit(_gen_remediation)
        rapport.result()
        try:
            plan_pdf.result()
        except Exception as exc:  # noqa: BLE001 — Chromium absent, etc. : le rapport reste
            logger.exception("[%s] PDF du plan de remédiation non produit : %s", copy_id, exc)
            result.plan_erreur = f"PDF du plan de remédiation non produit — {exc}"
            has_remediation = False

    # Les deux PDF restent dans l'espace de travail de la copie : conservés
    # en base seulement si l'enseignant sauvegarde l'analyse.
    result.pdf_path = pdf_path
    if has_remediation:
        result.remediation_pdf_path = remediation_pdf_path

    n_sections = len(result.plan_remediation.competences) if has_remediation else 0
    logger.warning(
        "[%s] ✓ Phase B terminée — note finale : %g/%g (%.1f/20) | plan : %d compétence(s)",
        copy_id,
        grade.final_score or 0, grade.total_possible,
        grade.final_score_on_20 or 0,
        n_sections,
    )
    return result


# ── Plan de remédiation : rédaction et reprise ────────────────────────────────


def _rediger_plan(result: PipelineResult, claude_client) -> None:
    """Rédige le plan (ou ses sections manquantes) et met `result` à jour.
    Un plan incomplet garde ses sections écrites pour `reprendre_plan`."""
    try:
        result.plan_remediation = generer_plan(
            result.demande_plan, claude_client,
            deja=result.plan_sections_redigees, acquis_deja=result.plan_acquis_rediges,
        )
    except PlanIncomplet as exc:
        result.plan_remediation = None
        result.plan_sections_redigees = exc.contenus
        result.plan_acquis_rediges = exc.acquis
        result.plan_erreur = f"Plan de remédiation non produit — {exc}"
        return
    result.plan_sections_redigees = {}
    result.plan_acquis_rediges = []
    result.plan_erreur = ""


def reprendre_plan(result: PipelineResult, claude_client=None) -> PipelineResult:
    """Termine un plan resté incomplet à la fin de l'analyse : seules les
    sections manquantes sont rédigées, les autres sont reprises telles
    quelles ; puis le PDF est produit. Rien d'autre de l'analyse n'est refait."""
    if result.demande_plan is None or not result.demande_plan.sections:
        raise ValueError("Aucun plan à reprendre pour cette copie.")
    if result.plan_remediation is not None and result.remediation_pdf_path:
        return result

    if result.plan_remediation is None:
        _rediger_plan(result, claude_client or ClaudeClient())
        if result.plan_remediation is None:
            return result

    dossier = result.json_path.parent if result.json_path else Path(result.runs_dir or settings.runs_dir) / result.copy_id
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "plan_remediation.pdf"
    try:
        generate_plan_remediation_pdf(chemin, result.plan_remediation)
    except Exception as exc:  # noqa: BLE001 — le plan rédigé reste dans le résultat
        logger.exception("[%s] PDF du plan de remédiation non produit : %s", result.copy_id, exc)
        result.plan_erreur = f"PDF du plan de remédiation non produit — {exc}"
        return result
    result.remediation_pdf_path = chemin
    result.plan_erreur = ""
    logger.warning("[%s] ✓ Plan de remédiation repris : %d compétence(s)",
                   result.copy_id, len(result.plan_remediation.competences))
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
