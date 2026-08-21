"""Port de `suivi/diagnostic.py` — écriture en base des problèmes produits
par le module 4, et confirmation automatique T1 (module 5, suite). Voir le
fichier d'origine pour les deux règles qui tiennent ce module : le module 4
n'écrit jamais dans une évaluation du corpus, et un problème produit entre
en `hypothese`, jamais `confirme`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as SQLASession

from app.models import ETATS_SESSION_TERMINES, Evaluation, Probleme, Session
from app.services import etats
from app.services.couts import cout_precalcule
from app.services.evaluations import creer_evaluation
from src.models.domain import CopyGrade, DiagnosticContraint, ProblemeDetecte, SourceProbleme, TeacherDecision

logger = logging.getLogger(__name__)


class ErreurDiagnostic(ValueError):
    """Écriture refusée (évaluation/session de corpus) — équivalent du
    `ValidationError` Django ici."""


def resoudre_ou_creer_session(db: SQLASession, identifiant_hakili: str) -> Session:
    """La session ouverte de cet élève, ou une nouvelle si aucune ne l'est.
    « Ouverte » exclut le corpus de référence et les sessions terminales."""
    session = (
        db.query(Session)
        .filter(Session.identifiant_hakili == identifiant_hakili, Session.corpus_reference.is_(False))
        .filter(~Session.etat.in_(ETATS_SESSION_TERMINES))
        .order_by(Session.date_debut.desc())
        .first()
    )
    if session is not None:
        return session
    session = Session(identifiant_hakili=identifiant_hakili)
    db.add(session)
    db.flush()
    return session


def preparer_evaluation(db: SQLASession, *, identifiant_hakili: str, type_evaluation: str, copy_id: str) -> Evaluation:
    """Rattache une copie déposée à son évaluation dans le cycle de suivi —
    provisionne la session au passage. Le rang (`numero`) est attribué par
    `creer_evaluation` (port de `Evaluation.save()`)."""
    session = resoudre_ou_creer_session(db, identifiant_hakili)
    return creer_evaluation(db, session.id, type_evaluation, copy_id=copy_id)


@dataclass
class ResultatEcriture:
    crees: list[Probleme] = field(default_factory=list)
    deja_suivis: list[str] = field(default_factory=list)
    cout_total: float = 0.0


def _fusionner(problemes: list[ProblemeDetecte]) -> list[tuple[str, str, str, str]]:
    """Regroupe les problèmes par couple compétence × type d'erreur."""
    groupes: dict[tuple[str, str], list[ProblemeDetecte]] = {}
    for probleme in problemes:
        groupes.setdefault((probleme.code_competence, probleme.code_type_erreur), []).append(probleme)

    fusionnes = []
    for (competence, type_erreur), lot in groupes.items():
        justification = "\n".join(
            f"[{p.code_question}] {p.citation.strip()}" + (" (QCM)" if p.source == SourceProbleme.qcm else "") for p in lot
        )
        questions = ", ".join(p.code_question for p in lot)
        fusionnes.append((competence, type_erreur, justification, questions))
    return fusionnes


def enregistrer(db: SQLASession, evaluation: Evaluation, diagnostic: DiagnosticContraint) -> ResultatEcriture:
    """Écrit les problèmes d'un diagnostic dans la session de l'évaluation."""
    if evaluation.corpus_reference:
        raise ErreurDiagnostic(
            f"L'évaluation {evaluation.id} appartient au corpus de référence : ses problèmes ont été relevés à la "
            "main et servent d'étalon au module 4. Le diagnostic automatique se compare à eux, il ne les remplace pas."
        )
    if evaluation.session.corpus_reference:
        raise ErreurDiagnostic(
            f"La session {evaluation.session_id} est une session de corpus : elle n'est le parcours de personne "
            "et ne reçoit pas de diagnostic."
        )

    resultat = ResultatEcriture()
    existants = {
        (p.competence_id, p.type_erreur_id)
        for p in db.query(Probleme.competence_id, Probleme.type_erreur_id).filter(Probleme.session_id == evaluation.session_id).all()
    }

    for competence, type_erreur, justification, questions in _fusionner(diagnostic.problemes):
        if (competence, type_erreur) in existants:
            resultat.deja_suivis.append(f"{competence} × {type_erreur} ({questions})")
            continue

        cout = cout_precalcule(db, competence, type_erreur)
        probleme = Probleme(
            session_id=evaluation.session_id,
            competence_id=competence,
            type_erreur_id=type_erreur,
            etat="hypothese",
            cout_estime=cout,
            evaluation_origine_id=evaluation.id,
            justification=justification,
        )
        db.add(probleme)
        db.flush()
        resultat.crees.append(probleme)
        resultat.cout_total += float(cout)

    logger.info(
        "[%s] Module 4 — %d problème(s) écrits, %d déjà suivis, %.1f h estimées.",
        diagnostic.copy_id or evaluation.id, len(resultat.crees), len(resultat.deja_suivis), resultat.cout_total,
    )
    return resultat


@dataclass
class ResultatConfirmation:
    confirmes: list[Probleme] = field(default_factory=list)
    ecartes: list[Probleme] = field(default_factory=list)


def confirmer_depuis_correction(db: SQLASession, evaluation: Evaluation, grade: CopyGrade) -> ResultatConfirmation:
    """Tranche automatiquement chaque hypothèse ouverte à partir d'une copie
    T1 déjà corrigée et validée. Règle binaire : l'élève rate au moins une
    des questions ciblant l'hypothèse → confirmé ; il réussit tout → écarté.
    `ATT` est toujours écarté (`Probleme.clean()` l'interdit en confirmé)."""
    resultat = ResultatConfirmation()

    if evaluation.session.corpus_reference:
        return resultat

    reussite_par_numero: dict[int, bool] = {}
    for question in grade.questions:
        try:
            numero = int(question.rubric_item_id)
        except (TypeError, ValueError):
            continue
        if question.teacher_decision == TeacherDecision.refused and question.teacher_score is not None:
            score = question.teacher_score
        else:
            score = question.score
        reussite_par_numero[numero] = score >= 1.0

    hypotheses = [
        p
        for p in db.query(Probleme).filter(Probleme.session_id == evaluation.session_id, Probleme.etat == "hypothese").all()
        if p.exercices_confirmation
    ]

    for probleme in hypotheses:
        if probleme.type_erreur_id == "ATT":
            etats.changer_etat(db, probleme, "ecarte", evaluation=evaluation)
            resultat.ecartes.append(probleme)
            continue

        numeros = probleme.exercices_confirmation
        reussi = all(reussite_par_numero.get(n, False) for n in numeros)
        if reussi:
            etats.changer_etat(db, probleme, "ecarte", evaluation=evaluation)
            resultat.ecartes.append(probleme)
        else:
            etats.changer_etat(db, probleme, "confirme", evaluation=evaluation)
            resultat.confirmes.append(probleme)

    logger.info(
        "[%s] Module 5 — %d confirmé(s), %d écarté(s) automatiquement.",
        evaluation.copy_id or evaluation.id, len(resultat.confirmes), len(resultat.ecartes),
    )
    return resultat
