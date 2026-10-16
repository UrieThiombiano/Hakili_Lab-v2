"""
Orchestrateur de validation — Hakili Lab
=========================================

Valide et corrige automatiquement les sorties de chaque étape du pipeline
avant de les transmettre à l'étape suivante.

Principes :
  - Aucun appel LLM : 100 % Python, exécution < 1 ms, coût $0.
  - Deux niveaux de problème :
      • "warning"  → problème détecté ET corrigé automatiquement (pipeline continue)
      • "error"    → problème bloquant, pipeline arrêté, message clair à l'enseignant
  - Chaque validateur retourne un ValidationResult[T] avec la donnée
    (éventuellement corrigée) et la liste des problèmes détectés.

Intégration dans le pipeline :
  TRANSCRIPTION → validate_transcription() →
  CORRECTION    → validate_grading()       →
  DIAGNOSTIC    → validate_diagnostic()    →
  REMÉDIATION   → validate_remediation()

Codes d'anomalie (utilisés dans les logs et dans l'UI) :
  NO_PAGES                   Transcription sans aucune page
  ALL_PAGES_EMPTY            Toutes les pages sont vides ou [ILLISIBLE]
  LOW_CONFIDENCE             Confiance moyenne de transcription trop faible
  HIGH_ILLISIBLE_RATIO       Trop de zones illisibles dans la transcription
  NO_QUESTIONS               Correction sans aucune question évaluée
  SCORE_HORS_BAREME          score > max_score ou hors du pas admis → ramené, auto-fixé
  POSSIBLE_COUNT_MISMATCH    total_possible ≠ Σ max_score barème → auto-fixé
  LOW_CONF_REVIEW_FORCED     requires_review forcé sur confiance < 60 % → auto-fixé
  DUPLICATE_QUESTION_IDS     Identifiants de questions en doublon
  SUSPICIOUS_ALL_ZERO        Tous les scores à 0 sans barème fourni
  SUSPICIOUS_ALL_ONE         Tous les scores à 1 sans barème fourni
  SUSPICIOUS_HIGH_ZERO_RATIO ≥ 95 % de scores à 0 sans barème
  SUSPICIOUS_HIGH_ONE_RATIO  ≥ 95 % de scores à 1 sans barème
  STRENGTH_ON_ZERO_SCORE     Force mentionnant une question à score=0 → auto-fixé
  WEAKNESS_ON_ONE_SCORE      Lacune mentionnant une question à score=1 → auto-fixé
  ROOT_CAUSE_INVALID_LINKS   Cause cachée liée à des questions inexistantes → auto-fixé
  EMPTY_REMEDIATION_PLAN     Lacunes présentes mais plan de remédiation vide
  EMPTY_DIAGNOSTIC           Diagnostic sans forces ni lacunes
  NO_EXERCISES               Sujet de remédiation vide
  SERIES_COUNT_MISMATCH      Nombre de séries ≠ nombre de lacunes
  EMPTY_EXERCISE_QUESTIONS   Exercices sans énoncé
  EXERCISE_RENUMBERED        Numérotation non séquentielle → auto-fixée
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from src.models.domain import (
    ConfirmationRequest,
    ConfirmationSubject,
    CopyGrade,
    DiagnosticResult,
    Exercise,
    QuestionGrade,
    RemediationSubject,
    RootCauseError,
    Rubric,
    TranscriptionResult,
    VerificationRequest,
    VerificationSubject,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ══════════════════════════════════════════════════════════════════════════════
# Types de base
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationIssue:
    """
    Un problème détecté lors de la validation d'une étape du pipeline.

    Attributs :
        code        Code machine unique (voir module docstring pour la liste).
        severity    "warning" = corrigé automatiquement, pipeline continue.
                    "error"   = bloquant, pipeline arrêté.
        message     Description lisible, affichable à l'enseignant.
        auto_fixed  True si la donnée a été modifiée automatiquement pour
                    corriger le problème.
    """
    code: str
    severity: Literal["warning", "error"]
    message: str
    auto_fixed: bool = False

    def __str__(self) -> str:
        tag = "AUTO-FIXÉ" if self.auto_fixed else ("⚠ AVERT." if self.severity == "warning" else "✗ ERREUR")
        return f"[{tag}] {self.code} — {self.message}"


@dataclass
class ValidationResult(Generic[T]):
    """
    Résultat d'une validation.

    Attributs :
        data    Donnée validée, potentiellement corrigée automatiquement.
        issues  Liste des problèmes détectés (vide = tout OK).

    Propriétés :
        valid           True si aucune erreur bloquante (warnings acceptés).
        has_warnings    True si au moins un warning.
        has_errors      True si au moins une erreur bloquante.
        summary         Résumé court lisible, ex : "2 avertissement(s) auto-fixé(s)".
        auto_fixes      Liste des seuls problèmes corrigés automatiquement.
    """
    data: T
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.has_errors

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def auto_fixes(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.auto_fixed]

    @property
    def summary(self) -> str:
        if not self.issues:
            return "OK"
        n_err = sum(1 for i in self.issues if i.severity == "error")
        n_fix = sum(1 for i in self.issues if i.auto_fixed)
        n_warn = sum(1 for i in self.issues if i.severity == "warning" and not i.auto_fixed)
        parts = []
        if n_err:
            parts.append(f"{n_err} erreur(s) bloquante(s)")
        if n_fix:
            parts.append(f"{n_fix} correction(s) auto")
        if n_warn:
            parts.append(f"{n_warn} avertissement(s)")
        return " · ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Validateur ① — Transcription
# ══════════════════════════════════════════════════════════════════════════════

def validate_transcription(
    result: TranscriptionResult,
    *,
    min_confidence: float = 0.40,
    max_illisible_ratio: float = 0.60,
) -> ValidationResult[TranscriptionResult]:
    """
    Valide la transcription produite par Gemini ou Claude.

    Erreurs bloquantes :
    - Aucune page dans la transcription.
    - Toutes les pages sont vides ou [ILLISIBLE].

    Avertissements (non bloquants) :
    - Confiance moyenne < min_confidence (défaut 40 %).
    - Plus de max_illisible_ratio pages contiennent [ILLISIBLE] (défaut 60 %).

    Args :
        result              TranscriptionResult issu du client IA.
        min_confidence      Seuil bas de confiance acceptable (0.0–1.0).
        max_illisible_ratio Ratio max de pages illisibles toléré (0.0–1.0).

    Returns :
        ValidationResult[TranscriptionResult]
    """
    issues: list[ValidationIssue] = []

    # ── Erreur : aucune page ───────────────────────────────────────────────────
    if not result.pages:
        issues.append(ValidationIssue(
            code="NO_PAGES",
            severity="error",
            message="La transcription ne contient aucune page — vérifiez le fichier uploadé.",
        ))
        return _done("Transcription", result, issues)

    # ── Erreur : tout illisible ────────────────────────────────────────────────
    non_empty_pages = [
        p for p in result.pages
        if p.content.strip() and p.content.strip() != "[ILLISIBLE]"
    ]
    if not non_empty_pages:
        issues.append(ValidationIssue(
            code="ALL_PAGES_EMPTY",
            severity="error",
            message=(
                "Toutes les pages transcrites sont vides ou [ILLISIBLE]. "
                "Améliorez la qualité du scan (150 DPI recommandé)."
            ),
        ))
        return _done("Transcription", result, issues)

    # ── Avertissement : confiance faible ──────────────────────────────────────
    avg_conf = sum(p.confidence for p in result.pages) / len(result.pages)
    if avg_conf < min_confidence:
        issues.append(ValidationIssue(
            code="LOW_CONFIDENCE",
            severity="warning",
            message=(
                f"Confiance de transcription faible : {avg_conf:.0%} "
                f"(seuil minimum : {min_confidence:.0%}). "
                "Les résultats de correction peuvent être imprécis."
            ),
        ))

    # ── Avertissement : trop d'illisible ──────────────────────────────────────
    illisible_count = sum(1 for p in result.pages if "[ILLISIBLE]" in p.content)
    illisible_ratio = illisible_count / len(result.pages)
    if illisible_ratio > max_illisible_ratio:
        issues.append(ValidationIssue(
            code="HIGH_ILLISIBLE_RATIO",
            severity="warning",
            message=(
                f"{illisible_count}/{len(result.pages)} page(s) contiennent des zones illisibles "
                f"({illisible_ratio:.0%} > seuil {max_illisible_ratio:.0%}). "
                "Vérifiez la luminosité et la netteté du scan."
            ),
        ))

    return _done("Transcription", result, issues)


# ══════════════════════════════════════════════════════════════════════════════
# Validateur ② — Correction
# ══════════════════════════════════════════════════════════════════════════════

# « 1 pt sur 2 : … », « 1,5 pts sur 3 », « 1/2 : … » en tête de commentaire.
_COMPTE_ANNONCE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:pts?\s*)?(?:sur|/)\s*(\d+(?:[.,]\d+)?)(?![\d.,])")


def validate_grading(
    grade: CopyGrade,
    *,
    rubric_provided: bool = False,
    rubric: "Rubric | None" = None,
    low_conf_threshold: float = 0.60,
    suspicious_ratio: float = 0.95,
) -> ValidationResult[CopyGrade]:
    """
    Valide et corrige automatiquement les incohérences dans la correction.

    Normalisations silencieuses (sans warning) :
    - total_score toujours recalculé comme Σ des scores individuels.
    Corrections automatiques (severity="warning", auto_fixed=True) :
    - score ramené dans [0, max_score] et sur un multiple du pas admis (`score_step`).
    - total_possible aligné sur Σ max_score des items du barème (garantit note/20 atteignable à 20).
    - requires_review forcé à True pour toute question avec confidence < seuil.

    Erreurs bloquantes :
    - Aucune question évaluée (total_possible=0).

    Avertissements non bloquants :
    - IDs de questions dupliqués.
    - ≥ suspicious_ratio de scores à 0 sans barème fourni.
    - ≥ suspicious_ratio de scores à 1 sans barème fourni.

    Args :
        grade               CopyGrade issu du client de correction.
        rubric_provided     True si un barème a été fourni par l'enseignant.
        low_conf_threshold  Seuil de confiance sous lequel requires_review est forcé.
        suspicious_ratio    Ratio de scores identiques déclenchant l'alerte (0.0–1.0).

    Returns :
        ValidationResult[CopyGrade]
    """
    issues: list[ValidationIssue] = []
    questions = list(grade.questions)

    # ── Erreur bloquante : aucune question ────────────────────────────────────
    if not questions:
        issues.append(ValidationIssue(
            code="NO_QUESTIONS",
            severity="error",
            message=(
                "La correction ne contient aucune question évaluée. "
                "Fournissez un barème ou un scan de meilleure qualité."
            ),
        ))
        return _done("Correction", grade, issues)

    # ── Correction auto : score hors barème ───────────────────────────────────
    # Le modèle peut renvoyer plus que le maximum de la question, ou une valeur
    # qui n'est pas un multiple du pas admis (barèmes socle : 1/3 de point en
    # partie A, demi-point du corrigé en B/C). Ramené dans [0, max_score] puis
    # sur un multiple du pas : le plus proche si l'écart n'est qu'un arrondi du
    # modèle (0.3333 pour 0.333333), sinon l'inférieur — on n'accorde jamais un
    # point que le modèle n'a pas donné.
    if rubric is not None and rubric.items:
        par_id = {item.id: item for item in rubric.items}
        ajustes: list[str] = []
        recalees: list[QuestionGrade] = []
        for q in questions:
            item = par_id.get(q.rubric_item_id)
            score = q.score
            if item is not None and item.points_corrige and q.points_obtenus is not None:
                # Le modèle compte les points du corrigé ; la conversion est faite ici.
                points = q.points_obtenus
                # Le commentaire annonce le compte (« 1 pt sur 2 : … ») ; s'il
                # contredit points_obtenus, c'est le plus souvent une proportion
                # écrite à la place d'un compte (0.5 pour « 1 sur 2 », recette
                # du 2026-10-16) : le compte explicite du commentaire fait foi.
                annonce = _COMPTE_ANNONCE.match(q.comment or "")
                if annonce and abs(float(annonce.group(2).replace(",", ".")) - item.points_corrige) < 1e-6:
                    points = float(annonce.group(1).replace(",", "."))
                points = min(max(points, 0.0), item.points_corrige)
                score = points / item.points_corrige * item.max_score
            if item is not None:
                score = min(max(score, 0.0), item.max_score)
                if item.score_step:
                    n_pas = max(1, round(item.max_score / item.score_step))
                    k = score / item.max_score * n_pas
                    k = round(k) if abs(k - round(k)) < 0.05 else math.floor(k)
                    score = round(item.max_score * min(k, n_pas) / n_pas, 6)
            if abs(score - q.score) > 1e-4:
                ajustes.append(f"{q.rubric_item_id} {q.score:g}→{score:g}")
            recalees.append(q.model_copy(update={"score": score}) if score != q.score else q)
        if ajustes:
            issues.append(ValidationIssue(
                code="SCORE_HORS_BAREME",
                severity="warning",
                message=f"{len(ajustes)} score(s) ramené(s) sur une valeur admise par le barème : {', '.join(ajustes)}.",
                auto_fixed=True,
            ))
        questions = recalees
        grade = _rebuild_grade(grade, questions=questions)

    # ── Normalisation silencieuse : total_score = somme des scores individuels ──
    # Les scores par question sont la vérité ; on recalcule toujours le total
    # sans émettre de warning (l'IA peut se tromper dans son addition).
    grade = _rebuild_grade(grade, total_score=sum(q.score for q in questions))

    # ── Correction auto : total_possible ─────────────────────────────────────
    # total_possible = total officiel du test (meta.total_possible, ex: 20) — pour l'affichage.
    # rubric_actual_max = somme réelle des max_score — pour la conversion /20 dans compute_final_score().
    # Les deux peuvent différer si le document source a une incohérence (ex: items somment à 18.5 mais
    # meta déclare 20). La séparation garantit : affichage /20, ET élève parfait = 20/20.
    if rubric is not None and rubric.items:
        actual_max = sum(item.max_score for item in rubric.items)
        expected_possible = rubric.total_points if rubric.total_points > 0 else float(len(questions))
    else:
        actual_max = 0.0
        expected_possible = float(len(questions))
    if abs(grade.total_possible - expected_possible) > 1e-9:
        issues.append(ValidationIssue(
            code="POSSIBLE_COUNT_MISMATCH",
            severity="warning",
            message=(
                f"total_possible déclaré ({grade.total_possible}) ≠ "
                f"attendu ({expected_possible}). "
                f"Corrigé : {grade.total_possible} → {expected_possible}."
            ),
            auto_fixed=True,
        ))
        grade = _rebuild_grade(grade, total_possible=expected_possible)

    # ── Correction auto : requires_review sur faible confiance ────────────────
    fixed_qs: list[QuestionGrade] = []
    n_forced = 0
    for q in grade.questions:
        if q.confidence < low_conf_threshold and not q.requires_review:
            fixed_qs.append(QuestionGrade(
                rubric_item_id=q.rubric_item_id,
                score=q.score,
                confidence=q.confidence,
                comment=q.comment,
                observed_answer=q.observed_answer,
                requires_review=True,
            ))
            n_forced += 1
        else:
            fixed_qs.append(q)

    if n_forced:
        issues.append(ValidationIssue(
            code="LOW_CONF_REVIEW_FORCED",
            severity="warning",
            message=(
                f"{n_forced} question(s) avec confiance < {low_conf_threshold:.0%} : "
                f"requires_review forcé à True pour révision enseignant."
            ),
            auto_fixed=True,
        ))
        grade = _rebuild_grade(grade, questions=fixed_qs)

    # ── Avertissement : IDs dupliqués ─────────────────────────────────────────
    ids = [q.rubric_item_id for q in grade.questions]
    duplicates = sorted({qid for qid in ids if ids.count(qid) > 1})
    if duplicates:
        issues.append(ValidationIssue(
            code="DUPLICATE_QUESTION_IDS",
            severity="warning",
            message=f"Identifiants de questions dupliqués : {', '.join(duplicates)}.",
        ))

    # ── Avertissement : résultat suspect sans barème ──────────────────────────
    if not rubric_provided and len(grade.questions) >= 3:
        n_zero = sum(1 for q in grade.questions if q.score == 0)
        n_positive = sum(1 for q in grade.questions if q.score > 0)
        total = len(grade.questions)

        if n_zero == total:
            issues.append(ValidationIssue(
                code="SUSPICIOUS_ALL_ZERO",
                severity="warning",
                message=(
                    f"Tous les {total} scores sont à 0 sans barème fourni — résultat suspect. "
                    "Conseil : fournissez un barème ou vérifiez la qualité du scan."
                ),
            ))
        elif n_positive == total:
            issues.append(ValidationIssue(
                code="SUSPICIOUS_ALL_ONE",
                severity="warning",
                message=(
                    f"Tous les {total} scores sont positifs sans barème fourni — "
                    "résultat peut-être trop indulgent. Vérification recommandée."
                ),
            ))
        elif n_zero / total >= suspicious_ratio:
            issues.append(ValidationIssue(
                code="SUSPICIOUS_HIGH_ZERO_RATIO",
                severity="warning",
                message=f"{n_zero}/{total} scores à 0 sans barème ({n_zero/total:.0%}) — vérification recommandée.",
            ))
        elif n_positive / total >= suspicious_ratio:
            issues.append(ValidationIssue(
                code="SUSPICIOUS_HIGH_ONE_RATIO",
                severity="warning",
                message=f"{n_positive}/{total} scores positifs sans barème ({n_positive/total:.0%}) — vérification recommandée.",
            ))

    # Stocker la somme réelle des items du barème pour le calcul /20 dans compute_final_score().
    # total_possible reste l'officiel (ex: 20) — affichage ; rubric_actual_max sert au dénominateur
    # de la conversion /20 (garantit qu'un élève parfait obtient 20/20 même si les items ne somment
    # pas exactement au total officiel déclaré dans meta.total_possible).
    if actual_max > 0 and abs(actual_max - grade.total_possible) > 1e-9:
        grade = _rebuild_grade(grade, rubric_actual_max=actual_max)

    return _done("Correction", grade, issues)


def consolider_corrections(grades: list[CopyGrade], rubric: "Rubric") -> CopyGrade:
    """Fusionne plusieurs corrections IA indépendantes d'une même copie,
    chacune déjà passée par `validate_grading` (scores sur la grille du barème).

    Par question : score médian (médiane basse pour un nombre pair — on
    n'accorde pas un point que la moitié des passages refuse). La question
    reprend le commentaire et la lecture du passage qui a donné ce score.
    Si les passages divergent de plus d'un pas, `requires_review` est levé et
    le commentaire le dit : c'est là que l'enseignant doit regarder.
    """
    if len(grades) == 1:
        return grades[0]

    par_id = {item.id: item for item in rubric.items}
    questions: list[QuestionGrade] = []
    for q0 in grades[0].questions:
        variantes = [
            next((q for q in g.questions if q.rubric_item_id == q0.rubric_item_id), None) for g in grades
        ]
        variantes = sorted((q for q in variantes if q is not None), key=lambda q: q.score)
        retenue = variantes[(len(variantes) - 1) // 2]
        item = par_id.get(q0.rubric_item_id)
        pas = (item.score_step or item.max_score) if item is not None else 1.0
        ecart = variantes[-1].score - variantes[0].score
        maj: dict = {}
        if ecart > pas + 1e-6:
            notes = " / ".join(f"{q.score:g}" for q in variantes)
            maj = {
                "requires_review": True,
                "confidence": min(retenue.confidence, 0.6),
                "comment": f"{retenue.comment} [Corrections IA divergentes ({notes}) — à vérifier.]",
            }
        questions.append(retenue.model_copy(update=maj) if maj else retenue)

    return _rebuild_grade(
        grades[0],
        total_score=sum(q.score for q in questions),
        questions=questions,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Validateur ③ — Diagnostic
# ══════════════════════════════════════════════════════════════════════════════

def validate_diagnostic(
    diagnostic: DiagnosticResult,
    grade: CopyGrade,
) -> ValidationResult[DiagnosticResult]:
    """
    Valide la cohérence du diagnostic pédagogique par rapport aux scores.

    Corrections automatiques :
    - Supprime des "strengths" toute entrée qui mentionne une question à score=0.
    - Supprime des "weaknesses" toute entrée qui mentionne une question à score=1.
    - Supprime des root_causes les linked_questions ne faisant pas partie
      des questions évaluées.

    Avertissements non bloquants :
    - Plan de remédiation vide malgré des lacunes identifiées.
    - Diagnostic entièrement vide (ni forces ni lacunes).

    Args :
        diagnostic  DiagnosticResult issu du client de diagnostic.
        grade       CopyGrade validé (après validate_grading).

    Returns :
        ValidationResult[DiagnosticResult]
    """
    issues: list[ValidationIssue] = []

    import re as _re

    # Table de correspondance id → score
    score_by_id: dict[str, float] = {q.rubric_item_id: q.score for q in grade.questions}
    all_ids: set[str] = set(score_by_id)

    def _id_in_text(qid: str, text: str) -> bool:
        """True si qid apparaît dans text comme mot entier (évite Q1 ⊂ Q10)."""
        return bool(_re.search(r'(?<![A-Za-z0-9_])' + _re.escape(qid) + r'(?![A-Za-z0-9_])', text))

    def _contains_zero_question(text: str) -> bool:
        return any(_id_in_text(qid, text) and score_by_id.get(qid, 1.0) == 0 for qid in all_ids)

    def _contains_one_question(text: str) -> bool:
        # Question entièrement réussie (taux 1). Une réussite partielle peut
        # porter une faiblesse : ce qui a manqué (démarche, justification).
        return any(_id_in_text(qid, text) and score_by_id.get(qid, 0.0) >= 1 - 1e-6 for qid in all_ids)

    # ── Correction auto : forces incohérentes ─────────────────────────────────
    # Ne supprimer une force que si elle mentionne explicitement un ID à score=0.
    # Garder au moins une force pour ne pas décourager l'élève/le parent.
    candidate_strengths = [s for s in diagnostic.strengths if not _contains_zero_question(s)]
    n_removed_s = len(diagnostic.strengths) - len(candidate_strengths)
    if n_removed_s and candidate_strengths:
        # Des forces ont été nettoyées, et il en reste — on applique le nettoyage
        clean_strengths = candidate_strengths
        issues.append(ValidationIssue(
            code="STRENGTH_ON_ZERO_SCORE",
            severity="warning",
            message=(
                f"{n_removed_s} force(s) supprimée(s) : mentionnaient explicitement "
                f"une question ayant score=0."
            ),
            auto_fixed=True,
        ))
    else:
        # Soit rien à supprimer, soit supprimer tout laisserait la liste vide → conserver
        clean_strengths = diagnostic.strengths

    # ── Correction auto : lacunes incohérentes ────────────────────────────────
    candidate_weaknesses = [w for w in diagnostic.weaknesses if not _contains_one_question(w)]
    n_removed_w = len(diagnostic.weaknesses) - len(candidate_weaknesses)
    if n_removed_w and candidate_weaknesses:
        clean_weaknesses = candidate_weaknesses
        issues.append(ValidationIssue(
            code="WEAKNESS_ON_ONE_SCORE",
            severity="warning",
            message=(
                f"{n_removed_w} lacune(s) supprimée(s) : mentionnaient explicitement "
                f"une question ayant score=1."
            ),
            auto_fixed=True,
        ))
    else:
        clean_weaknesses = diagnostic.weaknesses

    # ── Correction auto : root_causes avec IDs invalides ─────────────────────
    clean_rc: list[RootCauseError] = []
    n_removed_rc = 0
    for rc in diagnostic.root_causes:
        valid_links = [qid for qid in rc.linked_questions if qid in all_ids]
        if rc.linked_questions and not valid_links:
            # Tous les liens pointent vers des questions inexistantes → suppression
            n_removed_rc += 1
        else:
            clean_rc.append(RootCauseError(
                visible_error=rc.visible_error,
                hidden_cause=rc.hidden_cause,
                linked_questions=valid_links,
            ))
    if n_removed_rc:
        issues.append(ValidationIssue(
            code="ROOT_CAUSE_INVALID_LINKS",
            severity="warning",
            message=(
                f"{n_removed_rc} cause(s) cachée(s) supprimée(s) : "
                f"liaient uniquement des questions absentes de la correction."
            ),
            auto_fixed=True,
        ))

    # ── Avertissement : plan de remédiation vide avec lacunes ─────────────────
    if clean_weaknesses and not diagnostic.remediation_plan:
        issues.append(ValidationIssue(
            code="EMPTY_REMEDIATION_PLAN",
            severity="warning",
            message=(
                f"{len(clean_weaknesses)} lacune(s) identifiée(s) mais plan de remédiation vide. "
                "Le module de remédiation ne sera pas alimenté correctement."
            ),
        ))

    # ── Avertissement : diagnostic entièrement vide ───────────────────────────
    if not clean_strengths and not clean_weaknesses:
        issues.append(ValidationIssue(
            code="EMPTY_DIAGNOSTIC",
            severity="warning",
            message=(
                "Le diagnostic ne contient ni forces ni lacunes — "
                "analyse probablement insuffisante. Révision manuelle recommandée."
            ),
        ))

    fixed = DiagnosticResult(
        copy_id=diagnostic.copy_id,
        strengths=clean_strengths,
        weaknesses=clean_weaknesses,
        root_causes=clean_rc,
        skills=diagnostic.skills,
        remediation_plan=diagnostic.remediation_plan,
    )
    return _done("Diagnostic", fixed, issues)


# ══════════════════════════════════════════════════════════════════════════════
# Validateur ④ — Remédiation
# ══════════════════════════════════════════════════════════════════════════════

def validate_remediation(
    remediation: RemediationSubject,
    diagnostic: DiagnosticResult,
) -> ValidationResult[RemediationSubject]:
    """
    Valide l'alignement du sujet de remédiation avec le diagnostic.

    Corrections automatiques :
    - Renumérote les exercices si la séquence n'est pas 1, 2, 3, …

    Erreurs bloquantes :
    - Aucun exercice généré.

    Avertissements non bloquants :
    - Nombre de séries ≠ nombre de lacunes (5 exercices par lacune attendus).
    - Exercices sans énoncé (champ question vide).

    Args :
        remediation  RemediationSubject issu du client de remédiation.
        diagnostic   DiagnosticResult validé (après validate_diagnostic).

    Returns :
        ValidationResult[RemediationSubject]
    """
    issues: list[ValidationIssue] = []
    exercises = list(remediation.exercises)

    # ── Erreur bloquante : aucun exercice ─────────────────────────────────────
    if not exercises:
        issues.append(ValidationIssue(
            code="NO_EXERCISES",
            severity="error",
            message=(
                "Le sujet de remédiation est vide — aucun exercice généré. "
                "Vérifiez que le diagnostic contient des lacunes."
            ),
        ))
        return _done("Remédiation", remediation, issues)

    # ── Avertissement : nombre de séries incohérent ───────────────────────────
    n_weaknesses = len(diagnostic.weaknesses) or len(diagnostic.root_causes)
    n_series = len({ex.topic for ex in exercises})
    if n_weaknesses > 0 and n_series != n_weaknesses:
        issues.append(ValidationIssue(
            code="SERIES_COUNT_MISMATCH",
            severity="warning",
            message=(
                f"{n_series} série(s) générée(s) pour {n_weaknesses} lacune(s). "
                f"Attendu : {n_weaknesses} série(s) × 5 exercices = {n_weaknesses * 5} exercices."
            ),
        ))

    # ── Avertissement : exercices sans énoncé ─────────────────────────────────
    empty_nums = [ex.number for ex in exercises if not ex.question.strip()]
    if empty_nums:
        issues.append(ValidationIssue(
            code="EMPTY_EXERCISE_QUESTIONS",
            severity="warning",
            message=f"Exercice(s) sans énoncé : numéros {empty_nums}.",
        ))

    # ── Correction auto : renumérote si non séquentiel ─────────────────────────
    expected = list(range(1, len(exercises) + 1))
    actual = [ex.number for ex in exercises]
    if actual != expected:
        preview = str(actual[:6]) + ("…" if len(actual) > 6 else "")
        fixed_exercises = [
            Exercise(number=i + 1, topic=ex.topic, question=ex.question, hint=ex.hint)
            for i, ex in enumerate(exercises)
        ]
        issues.append(ValidationIssue(
            code="EXERCISE_RENUMBERED",
            severity="warning",
            message=f"Numérotation corrigée : {preview} → 1, 2, 3, …",
            auto_fixed=True,
        ))
        remediation = RemediationSubject(copy_id=remediation.copy_id, exercises=fixed_exercises)

    return _done("Remédiation", remediation, issues)


def validate_confirmation(
    confirmation: ConfirmationSubject,
    request: ConfirmationRequest,
) -> ValidationResult[ConfirmationSubject]:
    """
    Valide l'alignement du sujet T1 avec les hypothèses demandées.

    Même forme que `validate_remediation`, avec un ratio de 2 questions par
    hypothèse au lieu de 5 exercices par lacune.

    Corrections automatiques :
    - Renumérote les questions si la séquence n'est pas 1, 2, 3, …

    Erreurs bloquantes :
    - Aucune question générée.

    Avertissements non bloquants :
    - Nombre de sujets ≠ nombre d'hypothèses (2 questions par hypothèse attendues).
    - Questions sans énoncé (champ question vide).
    """
    issues: list[ValidationIssue] = []
    exercises = list(confirmation.exercises)

    if not exercises:
        issues.append(ValidationIssue(
            code="NO_EXERCISES",
            severity="error",
            message=(
                "Le sujet de confirmation T1 est vide — aucune question générée. "
                "Vérifiez que des hypothèses ont été fournies."
            ),
        ))
        return _done("Confirmation T1", confirmation, issues)

    n_hypotheses = len(request.hypotheses)
    n_series = len({ex.topic for ex in exercises})
    if n_hypotheses > 0 and n_series != n_hypotheses:
        issues.append(ValidationIssue(
            code="SERIES_COUNT_MISMATCH",
            severity="warning",
            message=(
                f"{n_series} hypothèse(s) couverte(s) pour {n_hypotheses} attendue(s). "
                f"Attendu : {n_hypotheses} × 2 questions = {n_hypotheses * 2} questions."
            ),
        ))

    empty_nums = [ex.number for ex in exercises if not ex.question.strip()]
    if empty_nums:
        issues.append(ValidationIssue(
            code="EMPTY_EXERCISE_QUESTIONS",
            severity="warning",
            message=f"Question(s) sans énoncé : numéros {empty_nums}.",
        ))

    expected = list(range(1, len(exercises) + 1))
    actual = [ex.number for ex in exercises]
    if actual != expected:
        preview = str(actual[:6]) + ("…" if len(actual) > 6 else "")
        fixed_exercises = [
            Exercise(number=i + 1, topic=ex.topic, question=ex.question, hint=ex.hint)
            for i, ex in enumerate(exercises)
        ]
        issues.append(ValidationIssue(
            code="EXERCISE_RENUMBERED",
            severity="warning",
            message=f"Numérotation corrigée : {preview} → 1, 2, 3, …",
            auto_fixed=True,
        ))
        confirmation = ConfirmationSubject(copy_id=confirmation.copy_id, exercises=fixed_exercises)

    return _done("Confirmation T1", confirmation, issues)


def validate_verification(
    verification: VerificationSubject,
    request: VerificationRequest,
) -> ValidationResult[VerificationSubject]:
    """
    Valide l'alignement du sujet T3/T4/T5 avec les problèmes demandés.

    Même forme que `validate_confirmation`, avec un nombre de questions par
    problème qui dépend du type (2 pour T3, 1 pour T4/T5) plutôt que fixé à 2 —
    le ratio attendu se déduit du nombre d'exercices retourné, pas d'une
    constante, pour ne pas dupliquer une règle déjà posée dans le prompt.

    Corrections automatiques :
    - Renumérote les questions si la séquence n'est pas 1, 2, 3, …

    Erreurs bloquantes :
    - Aucune question générée.

    Avertissements non bloquants :
    - Nombre de séries (topics) ≠ nombre de problèmes fournis.
    - Questions sans énoncé (champ question vide).
    - `type_evaluation` renvoyé différent de celui demandé.
    """
    issues: list[ValidationIssue] = []
    exercises = list(verification.exercises)
    etape = f"Vérification {request.type_evaluation}"

    if not exercises:
        issues.append(ValidationIssue(
            code="NO_EXERCISES",
            severity="error",
            message=(
                f"Le sujet {request.type_evaluation} est vide — aucune question générée. "
                "Vérifiez que des problèmes ont été fournis."
            ),
        ))
        return _done(etape, verification, issues)

    n_problemes = len(request.items)
    n_series = len({ex.topic for ex in exercises})
    if n_problemes > 0 and n_series != n_problemes:
        issues.append(ValidationIssue(
            code="SERIES_COUNT_MISMATCH",
            severity="warning",
            message=(
                f"{n_series} problème(s) couvert(s) pour {n_problemes} attendu(s)."
            ),
        ))

    if verification.type_evaluation != request.type_evaluation:
        issues.append(ValidationIssue(
            code="TYPE_EVALUATION_MISMATCH",
            severity="warning",
            message=(
                f"Le sujet porte le type « {verification.type_evaluation} » au lieu de "
                f"« {request.type_evaluation} » demandé."
            ),
        ))

    empty_nums = [ex.number for ex in exercises if not ex.question.strip()]
    if empty_nums:
        issues.append(ValidationIssue(
            code="EMPTY_EXERCISE_QUESTIONS",
            severity="warning",
            message=f"Question(s) sans énoncé : numéros {empty_nums}.",
        ))

    expected = list(range(1, len(exercises) + 1))
    actual = [ex.number for ex in exercises]
    if actual != expected:
        preview = str(actual[:6]) + ("…" if len(actual) > 6 else "")
        fixed_exercises = [
            Exercise(number=i + 1, topic=ex.topic, question=ex.question, hint=ex.hint)
            for i, ex in enumerate(exercises)
        ]
        issues.append(ValidationIssue(
            code="EXERCISE_RENUMBERED",
            severity="warning",
            message=f"Numérotation corrigée : {preview} → 1, 2, 3, …",
            auto_fixed=True,
        ))
        verification = VerificationSubject(
            copy_id=verification.copy_id,
            type_evaluation=verification.type_evaluation,
            exercises=fixed_exercises,
        )

    return _done(etape, verification, issues)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes
# ══════════════════════════════════════════════════════════════════════════════

def _done(stage: str, data: T, issues: list[ValidationIssue]) -> ValidationResult[T]:
    """Log le résultat et retourne le ValidationResult."""
    if not issues:
        logger.warning("Orchestrateur [%s] → OK", stage)
    else:
        for issue in issues:
            if issue.severity == "error":
                logger.error("Orchestrateur [%s] %s", stage, issue)
            else:
                logger.warning("Orchestrateur [%s] %s", stage, issue)
    return ValidationResult(data=data, issues=issues)


def _rebuild_grade(
    grade: CopyGrade,
    *,
    total_score: float | None = None,
    total_possible: float | None = None,
    questions: list[QuestionGrade] | None = None,
    rubric_actual_max: float | None = None,
) -> CopyGrade:
    """Recrée un CopyGrade immuable avec les champs modifiés."""
    return CopyGrade(
        copy_id=grade.copy_id,
        total_score=total_score if total_score is not None else grade.total_score,
        total_possible=total_possible if total_possible is not None else grade.total_possible,
        questions=questions if questions is not None else grade.questions,
        expert_instructions_used=grade.expert_instructions_used,
        rubric_actual_max=rubric_actual_max if rubric_actual_max is not None else grade.rubric_actual_max,
    )
