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
from app.services import etats, generation
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


#: Note /20 au T0 sous laquelle le test de confirmation est sauté (D-CEO-46) :
#: les lacunes sont assez nombreuses pour que T1 n'apporte rien — les
#: hypothèses sont confirmées d'office et le plan est définitif dès le T0.
SEUIL_CONFIRMATION_T1 = 10.0


def t1_dispense(note_sur_20: float | None) -> bool:
    """Vrai si un T0 noté `note_sur_20` se passe du test de confirmation.
    Note inconnue → pas de dispense : on garde le circuit T1 par défaut."""
    return note_sur_20 is not None and note_sur_20 < SEUIL_CONFIRMATION_T1


def confirmer_sans_t1(db: SQLASession, evaluation: Evaluation, note_sur_20: float) -> ResultatConfirmation:
    """Tranche toutes les hypothèses ouvertes de la session sans test T1, pour
    un T0 sous `SEUIL_CONFIRMATION_T1`. Chaque transition est rattachée au T0.
    `ATT` est écarté (jamais de remédiation pour une étourderie)."""
    resultat = ResultatConfirmation()

    if evaluation.session.corpus_reference:
        return resultat

    hypotheses = db.query(Probleme).filter(Probleme.session_id == evaluation.session_id, Probleme.etat == "hypothese").all()
    for probleme in hypotheses:
        if probleme.type_erreur_id == "ATT":
            etats.changer_etat(db, probleme, "ecarte", evaluation=evaluation)
            resultat.ecartes.append(probleme)
        else:
            etats.changer_etat(db, probleme, "confirme", evaluation=evaluation)
            resultat.confirmes.append(probleme)
    return resultat


def _reussite_par_numero(grade: CopyGrade) -> dict[int, bool]:
    """Réussite par numéro d'exercice (`rubric_item_id`), décision enseignant
    prioritaire sur le score automatique — partagé entre `confirmer_depuis_correction`
    (T1) et `trancher_verification_depuis_correction` (T3/T4/T5), pour que les
    deux lisent le score de la même façon."""
    reussite: dict[int, bool] = {}
    for question in grade.questions:
        try:
            numero = int(question.rubric_item_id)
        except (TypeError, ValueError):
            continue
        if question.teacher_decision == TeacherDecision.refused and question.teacher_score is not None:
            score = question.teacher_score
        else:
            score = question.score
        reussite[numero] = score >= 1.0
    return reussite


def confirmer_depuis_correction(db: SQLASession, evaluation: Evaluation, grade: CopyGrade) -> ResultatConfirmation:
    """Tranche automatiquement chaque hypothèse ouverte à partir d'une copie
    T1 déjà corrigée et validée. Règle binaire : l'élève rate au moins une
    des questions ciblant l'hypothèse → confirmé ; il réussit tout → écarté.
    `ATT` est toujours écarté (`Probleme.clean()` l'interdit en confirmé)."""
    resultat = ResultatConfirmation()

    if evaluation.session.corpus_reference:
        return resultat

    reussite_par_numero = _reussite_par_numero(grade)

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


@dataclass
class ResultatVerification:
    resolus: list[Probleme] = field(default_factory=list)
    non_resolus: list[Probleme] = field(default_factory=list)
    regresses: list[Probleme] = field(default_factory=list)
    clos: list[Probleme] = field(default_factory=list)


#: Verdict par type d'évaluation : `si_reussi=None` signifie qu'un succès à
#: T4 ne déclenche aucune transition (le problème reste `resolu` en silence —
#: cf. `docs/cycle_de_suivi.md` §3, seul un problème qui régresse à T4 produit
#: un mouvement). `etat_source` vient de `generation.ETAT_CIBLE`, seule source
#: de vérité sur l'état ciblé par chaque type (partagée avec la génération du
#: sujet et l'endpoint manuel `trancher`, `app/routers/sessions.py`).
_REGLES_AUTO = {
    "T3": {"si_reussi": "resolu", "si_echec": "non_resolu"},
    "T4": {"si_reussi": None, "si_echec": "regresse"},
    "T5": {"si_reussi": "clos", "si_echec": "regresse"},
}


def trancher_verification_depuis_correction(
    db: SQLASession, evaluation: Evaluation, grade: CopyGrade, type_evaluation: str
) -> ResultatVerification:
    """Tranche automatiquement chaque problème ciblé par le sujet T3/T4/T5
    déposé. Règle binaire, symétrique à `confirmer_depuis_correction` :
    l'élève réussit tous les exercices de `probleme.exercices_verification` →
    verdict de réussite (résolu / silencieux / clos selon le type) ; il en
    rate au moins un → verdict d'échec (non résolu / régressé / régressé)."""
    resultat = ResultatVerification()

    if evaluation.session.corpus_reference:
        return resultat

    regles = _REGLES_AUTO[type_evaluation]
    etat_source = generation.ETAT_CIBLE[type_evaluation]
    reussite_par_numero = _reussite_par_numero(grade)

    problemes = [
        p
        for p in db.query(Probleme).filter(Probleme.session_id == evaluation.session_id, Probleme.etat == etat_source).all()
        if p.exercices_verification
    ]

    listes = {"resolu": resultat.resolus, "non_resolu": resultat.non_resolus, "regresse": resultat.regresses, "clos": resultat.clos}

    for probleme in problemes:
        numeros = probleme.exercices_verification
        reussi = all(reussite_par_numero.get(n, False) for n in numeros)
        cible = regles["si_reussi"] if reussi else regles["si_echec"]
        if cible is None:
            continue
        etats.changer_etat(db, probleme, cible, evaluation=evaluation)
        listes[cible].append(probleme)

    logger.info(
        "[%s] Module 5 — %s : %d résolu(s), %d non résolu(s), %d régressé(s), %d clos automatiquement.",
        evaluation.copy_id or evaluation.id, type_evaluation,
        len(resultat.resolus), len(resultat.non_resolus), len(resultat.regresses), len(resultat.clos),
    )
    return resultat
