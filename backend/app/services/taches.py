"""Port de `correction_web/taches.py` — exécution du pipeline en arrière-plan.

Même choix qu'en Django : **un thread, pas une file de tâches** (voir le
fichier d'origine pour la justification — un enseignant qui corrige ses
copies une par une n'a pas besoin de Celery/Redis, et le suivi de
progression passe par la base, donc il fonctionne même si la requête
suivante est servie par un autre worker uvicorn).

Ce qui change par rapport à Django : pas de `close_old_connections()` à
appeler — chaque fonction de thread ouvre sa propre session SQLAlchemy
(`SessionLocal()`) et la ferme à la fin, le même geste que `DepotFastAPI`
utilise déjà pour la même raison (une session par tâche de fond, jamais
partagée avec celle de la requête qui a lancé le thread).
"""
from __future__ import annotations

import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session as SQLASession

from app.db import SessionLocal
from app.models import Correction, Evaluation, Probleme
from app.models.correction import ETATS_EN_COURS
from app.services import diagnostic_referentiel as diag_ref
from app.services import diagnostic_suivi as diag_suivi
from app.services.contexte import contexte_diagnostic, lacunes_competences

logger = logging.getLogger(__name__)

#: Au-delà, une correction « en cours » est considérée comme abandonnée
#: (voir `correction_web/taches.py` pour la justification du délai).
DELAI_ABANDON = timedelta(minutes=15)

_LIBELLES_ETAPE = {
    "ingestion": "Lecture de la copie",
    "transcription": "Transcription de l'écriture",
    "correction": "Correction question par question",
    "rag": "Recherche dans le programme officiel",
    "diagnostic": "Diagnostic pédagogique",
    "remediation": "Plan de remédiation",
    "export": "Génération du rapport",
}


def _liberer_connexion(db: SQLASession) -> None:
    """Termine la transaction de lecture avant les appels IA : sans ça, la
    connexion reste empruntée pendant toute la correction (plusieurs minutes
    depuis le champ `analyse`), Neon la coupe, et l'écriture finale échoue
    (« SSL connection has been closed unexpectedly », copie-6ec656923aeb,
    2026-10-17) — la copie reste figée en « correction ». Rendue au pool, la
    connexion est revalidée par `pool_pre_ping` au moment d'écrire."""
    db.commit()


def _rapporteur(correction_id: int):
    """Callback `on_progress` du pipeline → progression en base."""

    def rapporter(etape: str, pourcentage: int) -> None:
        try:
            db = SessionLocal()
            try:
                db.query(Correction).filter(Correction.id == correction_id).update(
                    {
                        "etape": _LIBELLES_ETAPE.get(etape, etape),
                        "progression": max(0, min(100, pourcentage)),
                        "maj_le": datetime.utcnow(),
                    }
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.debug("[%s] Progression non enregistrée.", correction_id)

    return rapporter


def _dans_un_thread(cible, *args) -> None:
    threading.Thread(target=cible, args=args, daemon=True).start()


def _echouer(db: SQLASession, correction: Correction, message: str) -> None:
    correction.etat = "echec"
    correction.erreurs = list(correction.erreurs or []) + [message]
    db.add(correction)
    db.commit()


# ── Phase A, première moitié : transcription ─────────────────────────────────


def lancer_transcription(
    db: SQLASession,
    correction: Correction,
    chemins: list[Path],
    rubric,
    test,
    sujet: Path | None = None,
    subject_text: str = "",
) -> None:
    """`test` vaut None en mode libre. `subject_text`, fourni, prime sur
    `test.subject_text` (cas de la confirmation T1, énoncé déjà connu)."""
    correction.etat = "transcription"
    correction.etape = "Lecture de la copie"
    correction.progression = 2
    db.add(correction)
    db.commit()
    _dans_un_thread(_executer_transcription, correction.id, chemins, rubric, test, sujet, subject_text)


def _executer_transcription(correction_id: int, chemins: list[Path], rubric, test, sujet: Path | None, subject_text: str) -> None:
    from src.pipeline.pipeline import run_transcription
    from src.pipeline.serialisation import serialiser

    db = SessionLocal()
    try:
        correction = db.get(Correction, correction_id)
        _liberer_connexion(db)
        try:
            resultat = run_transcription(
                copy_id=correction.copy_id,
                identifiant_hakili=correction.identifiant_hakili,
                student_name=f"{correction.eleve_prenom} {correction.eleve_nom}".strip(),
                file_paths=chemins,
                rubric=rubric,
                subject_text=subject_text or getattr(test, "subject_text", ""),
                subject_file_path=sujet,
                expert_instructions=correction.instructions_expert,
                bareme_id=correction.bareme_id,
                official_answers=getattr(test, "official_answers", ""),
                on_progress=_rapporteur(correction_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Transcription interrompue : %s", correction.copy_id, exc)
            _echouer(db, correction, f"Transcription interrompue : {exc}")
            return

        correction.resultat = serialiser(resultat)
        correction.erreurs = list(resultat.errors or [])
        if resultat.errors or resultat.transcription is None:
            correction.etat = "echec"
        else:
            correction.etat = "relecture"
            correction.etape = "Relecture de la transcription"
            correction.progression = 40
        db.add(correction)
        db.commit()
    finally:
        db.close()


# ── Phase A, seconde moitié : correction ─────────────────────────────────────


def lancer_correction(db: SQLASession, correction: Correction) -> None:
    correction.etat = "correction"
    correction.etape = "Correction question par question"
    correction.progression = 45
    db.add(correction)
    db.commit()
    _dans_un_thread(_executer_correction, correction.id)


def _executer_correction(correction_id: int) -> None:
    from src.pipeline.pipeline import run_grading
    from src.pipeline.serialisation import deserialiser, serialiser

    db = SessionLocal()
    try:
        correction = db.get(Correction, correction_id)
        _liberer_connexion(db)
        try:
            resultat = run_grading(result=deserialiser(correction.resultat), on_progress=_rapporteur(correction_id))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Correction interrompue : %s", correction.copy_id, exc)
            _echouer(db, correction, f"Correction interrompue : {exc}")
            return

        correction.resultat = serialiser(resultat)
        correction.erreurs = list(resultat.errors or [])
        if resultat.grade is None:
            correction.etat = "echec"
        else:
            correction.etat = "validation"
            correction.etape = "Validation des notes"
            correction.progression = 60
        db.add(correction)
        db.commit()
    finally:
        db.close()


# ── Dépôt en lot : Phase A complète, sans arrêt de relecture ─────────────────


def lancer_phase_a_complete(db: SQLASession, correction: Correction, chemins: list[Path], rubric, test) -> None:
    """Transcription **et** correction d'affilée — le tableau de validation
    reste néanmoins traversé (D-CEO-16 : « la correction automatique sans
    validation est inacceptable pour un document officiel »)."""
    correction.etat = "transcription"
    correction.etape = "Lecture de la copie"
    correction.progression = 2
    db.add(correction)
    db.commit()
    _dans_un_thread(_executer_phase_a_complete, correction.id, chemins, rubric, test)


def _executer_phase_a_complete(correction_id: int, chemins: list[Path], rubric, test) -> None:
    from src.pipeline.pipeline import run_phase_a
    from src.pipeline.serialisation import serialiser

    db = SessionLocal()
    try:
        correction = db.get(Correction, correction_id)
        _liberer_connexion(db)
        try:
            resultat = run_phase_a(
                copy_id=correction.copy_id,
                identifiant_hakili=correction.identifiant_hakili,
                student_name=f"{correction.eleve_prenom} {correction.eleve_nom}".strip(),
                file_paths=chemins,
                rubric=rubric,
                subject_text=getattr(test, "subject_text", ""),
                expert_instructions=correction.instructions_expert,
                bareme_id=correction.bareme_id,
                official_answers=getattr(test, "official_answers", ""),
                on_progress=_rapporteur(correction_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Correction interrompue : %s", correction.copy_id, exc)
            _echouer(db, correction, f"Correction interrompue : {exc}")
            return

        correction.resultat = serialiser(resultat)
        correction.erreurs = list(resultat.errors or [])
        if resultat.grade is None:
            correction.etat = "echec"
        else:
            correction.etat = "validation"
            correction.etape = "Validation des notes"
            correction.progression = 60
        db.add(correction)
        db.commit()
    finally:
        db.close()


# ── Phase B : diagnostic, remédiation, rapport ───────────────────────────────


def lancer_diagnostic(db: SQLASession, correction: Correction) -> None:
    correction.etat = "diagnostic"
    correction.etape = "Recherche dans le programme officiel"
    correction.progression = 65
    db.add(correction)
    db.commit()
    _dans_un_thread(_executer_diagnostic, correction.id)


def _ancrage_referentiel(db: SQLASession, niveau_test: str):
    """Fonction d'ancrage passée au pipeline — `None` si le test n'est pas au
    référentiel (mode libre, ancien test) : le pipeline retombe sur son
    ancrage historique."""
    if not niveau_test:
        return None

    def ancrer(codes_questions: list[str]) -> tuple[str, list[dict]]:
        ancrage = (contexte_diagnostic(db, niveau_test, codes_questions), lacunes_competences(db, niveau_test, codes_questions))
        # Appelé juste avant le diagnostic (plusieurs minutes) : sans ça, la
        # transaction de lecture garde la connexion et Neon la coupe
        # (copie-b50db36edb7f, 2026-10-17).
        _liberer_connexion(db)
        return ancrage

    return ancrer


def _niveau_test(bareme_id: str) -> str:
    return bareme_id[len("socle_"):] if bareme_id.startswith("socle_") else ""


def _executer_diagnostic(correction_id: int) -> None:
    from src.pipeline.pipeline import run_phase_b
    from src.pipeline.serialisation import deserialiser, serialiser

    db = SessionLocal()
    try:
        correction = db.get(Correction, correction_id)
        _liberer_connexion(db)
        try:
            resultat = run_phase_b(
                result=deserialiser(correction.resultat),
                on_progress=_rapporteur(correction_id),
                ancrage=_ancrage_referentiel(db, _niveau_test(correction.bareme_id)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Diagnostic interrompu : %s", correction.copy_id, exc)
            _echouer(db, correction, f"Diagnostic interrompu : {exc}")
            return

        _ecrire_hypotheses_module4(db, correction, resultat)

        correction.resultat = serialiser(resultat)
        correction.erreurs = list(resultat.errors or [])
        correction.etat = "echec" if resultat.errors else "terminee"
        correction.etape = "Terminée"
        correction.progression = 100
        db.add(correction)
        db.commit()
    finally:
        db.close()


def _client_diagnostic_module4():
    """Absent plutôt qu'en échec : une clé d'API absente ne doit pas
    empêcher la part mécanique (QCM) de tourner."""
    try:
        from src.api.claude_client import ClaudeClient

        return ClaudeClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[module 4] Aucun client de diagnostic (%s) — QCM seuls.", exc)
        return None


def _ecrire_hypotheses_module4(db: SQLASession, correction: Correction, resultat) -> None:
    """Point d'injection module 4 : écrit les lacunes de cette copie comme
    hypothèses, ou pour une copie T1, tranche automatiquement les hypothèses
    déjà ouvertes. Best-effort : un échec ici ne fait jamais échouer une
    correction déjà terminée."""
    if correction.type_evaluation == "T1":
        _confirmer_hypotheses_module4(db, correction, resultat)
        return

    if correction.type_evaluation in ("T3", "T4", "T5"):
        _trancher_verification_module5(db, correction, resultat)
        return

    if not correction.bareme_id.startswith("socle_"):
        return
    if resultat.grade is None or resultat.rubric is None:
        return

    niveau = _niveau_test(correction.bareme_id)
    try:
        reponses = diag_ref.reponses_depuis_correction(resultat.grade, resultat.rubric)
        diagnostic = diag_ref.diagnostiquer(db, niveau_test=niveau, reponses=reponses, client=_client_diagnostic_module4(), copy_id=correction.copy_id)
        evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili=correction.identifiant_hakili, type_evaluation=correction.type_evaluation, copy_id=correction.copy_id)
        ecriture = diag_suivi.enregistrer(db, evaluation, diagnostic)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[%s] Module 4 : hypothèses non écrites (%s)", correction.copy_id, exc)
        return

    logger.info(
        "[%s] Module 4 — %d hypothèse(s) écrite(s) sur la session %s (%.1f h estimées).",
        correction.copy_id, len(ecriture.crees), evaluation.session_id, ecriture.cout_total,
    )

    # Note T0 < 10/20 (D-CEO-46) : pas de test de confirmation — les
    # hypothèses sont confirmées d'office, le plan est définitif dès le T0.
    note = getattr(resultat.grade, "final_score_on_20", None)
    if correction.type_evaluation == "T0" and diag_suivi.t1_dispense(note):
        _confirmer_sans_t1(db, correction, evaluation, note)
        return

    # Sujet T1 : on le génère dès qu'un T0 laisse des hypothèses ouvertes non
    # encore couvertes par un sujet — pas seulement quand ce T0 a créé des
    # problèmes. Réanalyser la copie d'un élève qui a déjà une session ouverte
    # (cas courant en test, et en production quand un collègue a déjà lancé un
    # T0) ne crée rien de neuf (`ecriture.crees` vide, tout est « déjà suivi »)
    # mais doit quand même produire le sujet si aucun n'existe.
    if correction.type_evaluation == "T0" and (ecriture.crees or not _session_a_un_sujet_t1(db, evaluation.session_id)):
        _generer_sujet_confirmation(db, correction, evaluation)


def _session_a_un_sujet_t1(db: SQLASession, session_id: int) -> bool:
    """Vrai si un T0 de cette session porte déjà un sujet de confirmation
    persisté (`Evaluation.sujet_confirmation`) — même critère que
    `sessions.py::session_detail` pour afficher le lien « Sujet T1 »."""
    return (
        db.query(Evaluation.id)
        .filter(Evaluation.session_id == session_id, Evaluation.type == "T0", Evaluation.sujet_confirmation.isnot(None))
        .first()
        is not None
    )


def _confirmer_sans_t1(db: SQLASession, correction: Correction, evaluation, note: float) -> None:
    """Confirmation d'office des hypothèses d'un T0 sous la barre des 10/20.
    Best-effort, comme le reste du module 5 : en cas d'échec les hypothèses
    restent ouvertes et l'enseignant peut trancher à la main."""
    try:
        ecriture = diag_suivi.confirmer_sans_t1(db, evaluation, note)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[%s] Note < 10 : confirmation sans T1 impossible (%s)", correction.copy_id, exc)
        return

    logger.info(
        "[%s] Note T0 %.2f/20 — pas de T1 : %d confirmé(s), %d écarté(s) sur la session %s.",
        correction.copy_id, note, len(ecriture.confirmes), len(ecriture.ecartes), evaluation.session_id,
    )


def _confirmer_hypotheses_module4(db: SQLASession, correction: Correction, resultat) -> None:
    """Point d'injection module 5 (suite) : tranche automatiquement les
    hypothèses ouvertes à partir d'une copie T1 corrigée et validée.
    Best-effort — l'enseignant garde la main via la saisie manuelle si ce
    circuit ne peut pas trancher."""
    if resultat.grade is None:
        return

    try:
        evaluation = diag_suivi.preparer_evaluation(db, identifiant_hakili=correction.identifiant_hakili, type_evaluation=correction.type_evaluation, copy_id=correction.copy_id)
        ecriture = diag_suivi.confirmer_depuis_correction(db, evaluation, resultat.grade)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[%s] Module 5 : confirmation automatique impossible (%s)", correction.copy_id, exc)
        return

    logger.info(
        "[%s] Module 5 — %d confirmé(s), %d écarté(s) sur la session %s.",
        correction.copy_id, len(ecriture.confirmes), len(ecriture.ecartes), evaluation.session_id,
    )


def _trancher_verification_module5(db: SQLASession, correction: Correction, resultat) -> None:
    """Point d'injection module 5 (T3/T4/T5) : tranche automatiquement les
    problèmes ciblés par le sujet de vérification déposé — résolu/non résolu
    (T3), régressé/silencieux (T4), clos/régressé (T5). Miroir de
    `_confirmer_hypotheses_module4`, avec deux différences : l'évaluation
    n'existe pas encore (elle est créée ici, au retour de la copie — jamais à
    la génération, pour que le rang ne soit consommé que par un dépôt réel),
    et le sujet en attente porté par la session est effacé une fois consommé."""
    if resultat.grade is None:
        return

    try:
        evaluation = diag_suivi.preparer_evaluation(
            db, identifiant_hakili=correction.identifiant_hakili, type_evaluation=correction.type_evaluation, copy_id=correction.copy_id
        )
        evaluation.sujet_confirmation = evaluation.session.sujet_verification_exercices
        ecriture = diag_suivi.trancher_verification_depuis_correction(db, evaluation, resultat.grade, correction.type_evaluation)
        evaluation.session.sujet_verification_type = None
        evaluation.session.sujet_verification_exercices = None
        db.add(evaluation.session)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[%s] Module 5 : vérification %s automatique impossible (%s)", correction.copy_id, correction.type_evaluation, exc)
        return

    logger.info(
        "[%s] Module 5 — %s : %d résolu(s), %d non résolu(s), %d régressé(s), %d clos.",
        correction.copy_id, correction.type_evaluation,
        len(ecriture.resolus), len(ecriture.non_resolus), len(ecriture.regresses), len(ecriture.clos),
    )


def _libelles_questions(bareme_id: str) -> dict[str, str]:
    """Libellé de chaque question du test T0 (`N1` → « Ecrire lequel de … »),
    pour dire au générateur T1 sur quelle question précise l'erreur est née."""
    if not bareme_id:
        return {}
    try:
        from src.knowledge.test_registry import get_registry

        test = get_registry().get_test(bareme_id)
    except Exception:  # best-effort, comme tout le module 5
        return {}
    return {item.id: item.label for item in test.rubric.items} if test else {}


def _generer_sujet_confirmation(db: SQLASession, correction: Correction, evaluation) -> None:
    """Point d'injection module 5 : génère le sujet T1 à partir des
    hypothèses encore ouvertes, et l'attache à la copie T0 qui les a
    révélées. Best-effort — ne tourne qu'à la suite d'un T0."""
    hypotheses = [
        p for p in db.query(Probleme).filter(Probleme.session_id == evaluation.session_id, Probleme.etat == "hypothese").all()
    ]
    if not hypotheses:
        return

    try:
        from src.core.config import settings
        from src.models.domain import ConfirmationHypothesis, ConfirmationRequest
        from src.pipeline.depot import depot
        from src.pipeline.orchestrator import validate_confirmation
        from src.pipeline.pdf_remediation_html import generate_remediation_pdf
        from src.knowledge.remediation_retriever import get_remediation_retriever

        client = _client_diagnostic_module4()
        if client is None:
            logger.warning("[%s] Module 5 : aucun client disponible, sujet T1 non généré.", correction.copy_id)
            return

        niveau = _niveau_test(correction.bareme_id)
        retriever = get_remediation_retriever()
        libelles = _libelles_questions(correction.bareme_id)

        def _hypothese(p: Probleme) -> ConfirmationHypothesis:
            chunk = retriever.get_by_competence(p.competence.code, niveau) if niveau else None
            codes = re.findall(r"\[([^\]]+)\]", p.justification or "")
            question_t0 = " ; ".join(
                f"{code} — {libelles[code]}" for code in codes if code in libelles
            )
            return ConfirmationHypothesis(
                question_t0=question_t0 or None,
                competence_label=p.competence.libelle,
                type_erreur_label=p.type_erreur.libelle,
                justification=p.justification,
                is_att=p.type_erreur_id == "ATT",
                competence_code=p.competence.code,
                niveau=niveau or None,
                reference_pedagogique=chunk.to_context_text() if chunk else None,
            )

        request = ConfirmationRequest(copy_id=correction.copy_id, hypotheses=[_hypothese(p) for p in hypotheses])
        _liberer_connexion(db)  # génération T1 : plusieurs minutes
        reponse = client.generate_confirmation_subject(request)
        if not reponse.success or reponse.data is None:
            logger.warning("[%s] Module 5 : génération T1 échouée (%s)", correction.copy_id, reponse.error)
            return

        validation = validate_confirmation(reponse.data, request)
        if not validation.valid:
            logger.warning(
                "[%s] Module 5 : sujet T1 invalide, non attaché (%s)",
                correction.copy_id, [i.message for i in validation.issues if i.severity == "error"],
            )
            return

        pdf_path = Path(settings.runs_dir) / correction.copy_id / "sujet_confirmation.pdf"
        generate_remediation_pdf(
            output_path=pdf_path,
            copy_id=correction.copy_id,
            student_name=f"{correction.eleve_nom} {correction.eleve_prenom}".strip(),
            remediation_subject=validation.data,
        )
        depot().ajouter_document(copy_id=correction.copy_id, type_document="sujet_confirmation", contenu=pdf_path.read_bytes())
        _persister_sujet_confirmation(db, evaluation, hypotheses, validation.data)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[%s] Module 5 : sujet T1 non généré (%s)", correction.copy_id, exc)
        return

    logger.info("[%s] Module 5 — sujet T1 généré et attaché (%d hypothèse(s)).", correction.copy_id, len(hypotheses))


def _persister_sujet_confirmation(db: SQLASession, evaluation, hypotheses: list[Probleme], sujet) -> None:
    """Enregistre le sujet T1 et le lien exercice → hypothèse, par
    correspondance de `topic` (voir `prompts/confirmation_subject_prompt.md`) —
    jamais par position dans la liste, plus fragile."""
    numeros_par_topic: dict[str, list[int]] = defaultdict(list)
    for exercice in sujet.exercises:
        numeros_par_topic[exercice.topic].append(exercice.number)

    for probleme in hypotheses:
        topic = f"{probleme.competence.libelle} × {probleme.type_erreur.libelle}"
        numeros = numeros_par_topic.get(topic)
        if not numeros:
            continue
        probleme.exercices_confirmation = numeros
        db.add(probleme)

    evaluation.sujet_confirmation = [
        {"numero": e.number, "topic": e.topic, "question": e.question, "hint": e.hint} for e in sujet.exercises
    ]
    db.add(evaluation)


# ── Corrections abandonnées ──────────────────────────────────────────────────


def signaler_si_abandonnee(db: SQLASession, correction: Correction) -> bool:
    """Passe en échec une correction « en cours » qui ne bouge plus (process
    arrêté pendant qu'un thread travaillait)."""
    if correction.etat not in ETATS_EN_COURS:
        return False
    if datetime.utcnow() - correction.maj_le < DELAI_ABANDON:
        return False

    logger.warning("[%s] Correction abandonnée après %s sans progression.", correction.copy_id, DELAI_ABANDON)
    _echouer(db, correction, "Le traitement s'est interrompu (le serveur a probablement redémarré). Relancez la correction de cette copie.")
    return True
