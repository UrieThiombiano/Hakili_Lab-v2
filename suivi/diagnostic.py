"""
Écriture en base des problèmes produits par le module 4, et mesure contre le corpus.

Deux règles tiennent ce fichier
-------------------------------
1. **Le module 4 n'écrit jamais dans une évaluation du corpus de référence.** Le
   corpus est l'instrument de mesure : un étalon qu'on corrige au fur et à mesure
   ne mesure plus rien. La règle est posée dans la fiche du module 3, elle est
   appliquée ici.

2. **Un problème produit entre en `hypothese`, jamais en `confirme`.** C'est T1
   qui confirme ou écarte, et c'est tout l'objet du cycle : un diagnostic
   automatique qui confirmerait ses propres hypothèses ferait payer une famille
   sur la foi d'un modèle de langage.

Pourquoi aucune `Transition` n'est écrite à la création
-------------------------------------------------------
`guide-v2.md` demande « une ligne dans `transition` » à la création du problème.
Ce n'est pas possible tel quel, et ne pas le faire est le bon choix :
`Transition` porte une contrainte `etat_avant != etat_apres`, et `changer_etat()`
refuse une transition vers l'état courant. Une ligne de création exigerait un
`etat_avant` fictif.

Surtout, le corpus de référence (module 3) n'en écrit pas non plus. En écrire ici
rendrait les deux jeux non comparables et fausserait le taux de confirmation du
module 9, qui compte les passages `hypothese → confirme` rapportés au nombre
d'hypothèses. La date de l'hypothèse est portée par `evaluation_origine.date`,
qui est plus juste qu'une date d'écriture en base.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from referentiel.couts import cout_precalcule
from src.models.domain import (
    CopyGrade,
    DiagnosticContraint,
    ProblemeDetecte,
    SourceProbleme,
    TeacherDecision,
)
from suivi.models import ETATS_SESSION_TERMINES, EtatProbleme, Evaluation, Probleme, Session

logger = logging.getLogger(__name__)


def resoudre_ou_creer_session(identifiant_hakili: str) -> Session:
    """La session ouverte de cet élève, ou une nouvelle si aucune ne l'est.

    « Ouverte » exclut les sessions du corpus de référence (pas le parcours
    d'un élève, cf. `enregistrer()`) et les sessions dans un état terminal —
    un élève dont le cycle précédent est clos, sans suite ou hors dispositif
    en ouvre un nouveau plutôt que de rouvrir l'ancien.
    """
    session = (
        Session.objects.filter(identifiant_hakili=identifiant_hakili, corpus_reference=False)
        .exclude(etat__in=ETATS_SESSION_TERMINES)
        .order_by("-date_debut")
        .first()
    )
    if session is not None:
        return session
    return Session.objects.create(identifiant_hakili=identifiant_hakili)


def preparer_evaluation(
    *, identifiant_hakili: str, type_evaluation: str, copy_id: str
) -> Evaluation:
    """Rattache une copie déposée à son évaluation dans le cycle de suivi.

    Provisionne la session au passage : c'est le pendant automatique de ce que
    l'écran de parcours et `manage.py diagnostiquer` font manuellement
    aujourd'hui. Le rang (`numero`) est attribué par `Evaluation.save()`.
    """
    session = resoudre_ou_creer_session(identifiant_hakili)
    return Evaluation.objects.create(
        session=session, type=type_evaluation, copy_id=copy_id
    )


@dataclass
class ResultatEcriture:
    """Ce que l'écriture a fait, et ce qu'elle n'a pas fait.

    `deja_suivis` n'est pas une anomalie : un couple compétence × type d'erreur
    ne se suit qu'une fois par session (contrainte en base). Si T0 l'a déjà
    révélé, une seconde passation le retrouve — c'est attendu, et le signaler
    évite de croire à une perte.
    """

    crees: list[Probleme] = field(default_factory=list)
    deja_suivis: list[str] = field(default_factory=list)
    cout_total: float = 0.0


def _fusionner(problemes: list[ProblemeDetecte]) -> list[tuple[str, str, str, str]]:
    """Regroupe les problèmes par couple compétence × type d'erreur.

    Deux questions peuvent révéler la même lacune — c'est même le cas le plus
    fréquent, et c'est un signal fort. La base n'accepte qu'une ligne par couple
    et par session ; on garde donc toutes les citations, séparées, plutôt que
    d'en perdre. Rend (compétence, type, justification, questions).
    """
    groupes: dict[tuple[str, str], list[ProblemeDetecte]] = {}
    for probleme in problemes:
        groupes.setdefault(
            (probleme.code_competence, probleme.code_type_erreur), []
        ).append(probleme)

    fusionnes = []
    for (competence, type_erreur), lot in groupes.items():
        justification = "\n".join(
            f"[{p.code_question}] {p.citation.strip()}"
            + (" (QCM)" if p.source == SourceProbleme.qcm else "")
            for p in lot
        )
        questions = ", ".join(p.code_question for p in lot)
        fusionnes.append((competence, type_erreur, justification, questions))
    return fusionnes


@transaction.atomic
def enregistrer(
    evaluation: Evaluation, diagnostic: DiagnosticContraint
) -> ResultatEcriture:
    """Écrit les problèmes d'un diagnostic dans la session de l'évaluation."""
    if evaluation.corpus_reference:
        raise ValidationError(
            f"L'évaluation {evaluation.pk} appartient au corpus de référence : ses "
            "problèmes ont été relevés à la main et servent d'étalon au module 4. "
            "Le diagnostic automatique se compare à eux (`mesurer_diagnostic`), il "
            "ne les remplace pas."
        )
    if evaluation.session.corpus_reference:
        raise ValidationError(
            f"La session {evaluation.session_id} est une session de corpus : elle "
            "n'est le parcours de personne et ne reçoit pas de diagnostic."
        )

    resultat = ResultatEcriture()
    existants = set(
        Probleme.objects.filter(session_id=evaluation.session_id).values_list(
            "competence_id", "type_erreur_id"
        )
    )

    for competence, type_erreur, justification, questions in _fusionner(
        diagnostic.problemes
    ):
        if (competence, type_erreur) in existants:
            resultat.deja_suivis.append(f"{competence} × {type_erreur} ({questions})")
            continue

        cout = cout_precalcule(competence, type_erreur)
        probleme = Probleme(
            session_id=evaluation.session_id,
            competence_id=competence,
            type_erreur_id=type_erreur,
            etat=EtatProbleme.HYPOTHESE,
            cout_estime=cout,
            evaluation_origine=evaluation,
            justification=justification,
        )
        probleme.full_clean()
        probleme.save()
        resultat.crees.append(probleme)
        resultat.cout_total += float(cout)

    logger.info(
        "[%s] Module 4 — %d problème(s) écrits, %d déjà suivis, %.1f h estimées.",
        diagnostic.copy_id or evaluation.pk,
        len(resultat.crees),
        len(resultat.deja_suivis),
        resultat.cout_total,
    )
    return resultat


# ── Confirmation automatique (T1, module 5 — suite) ─────────────────────────
#
# La copie T1 est corrigée par le même pipeline que toute copie (transcription,
# proposition IA, tableau de validation enseignant) — ce n'est plus ici qu'une
# question de barème. `Probleme.exercices_confirmation` (écrit à la génération
# du sujet, `correction_web/taches.py::_persister_sujet_confirmation`) donne
# les numéros d'exercice qui ciblent chaque hypothèse ; le barème de la
# correction T1 est construit avec ces mêmes numéros comme `rubric_item_id`
# (voir `suivi_web/views.py::soumettre_confirmation`). Rien n'est deviné après
# coup : la correspondance existe depuis la génération du sujet.


@dataclass
class ResultatConfirmation:
    """Ce que la confirmation automatique a tranché."""

    confirmes: list[Probleme] = field(default_factory=list)
    ecartes: list[Probleme] = field(default_factory=list)


@transaction.atomic
def confirmer_depuis_correction(
    evaluation: Evaluation, grade: CopyGrade
) -> ResultatConfirmation:
    """Tranche automatiquement chaque hypothèse ouverte à partir d'une copie T1
    déjà corrigée et validée par l'enseignant.

    Règle binaire simple : l'élève rate au moins une des questions ciblant
    l'hypothèse → `confirme`. Il réussit tout ce qui la cible → `ecarte`. Une
    question absente de `grade.questions` (non transcrite, non gradée) compte
    comme non réussie plutôt que comme une réussite supposée — même principe
    que `referentiel.diagnostic` : une absence ne se devine jamais en succès.

    `ATT` reste un cas à part : `Probleme.clean()` interdit `confirme` pour ce
    type (protocole §3, une inattention ne se remédie pas), donc un problème
    `ATT` est toujours écarté ici, quel que soit le résultat des exercices —
    même règle que la saisie manuelle (`session_detail.html` masque déjà la
    case « Confirmée » pour ce type).
    """
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

    hypotheses = list(
        evaluation.session.problemes.filter(etat=EtatProbleme.HYPOTHESE)
        .exclude(exercices_confirmation=[])
        .select_related("competence", "type_erreur")
    )

    for probleme in hypotheses:
        if probleme.type_erreur_id == "ATT":
            probleme.changer_etat(EtatProbleme.ECARTE, evaluation=evaluation)
            resultat.ecartes.append(probleme)
            continue

        numeros = probleme.exercices_confirmation
        reussi = all(reussite_par_numero.get(n, False) for n in numeros)
        if reussi:
            probleme.changer_etat(EtatProbleme.ECARTE, evaluation=evaluation)
            resultat.ecartes.append(probleme)
        else:
            probleme.changer_etat(EtatProbleme.CONFIRME, evaluation=evaluation)
            resultat.confirmes.append(probleme)

    logger.info(
        "[%s] Module 5 — %d confirmé(s), %d écarté(s) automatiquement.",
        evaluation.copy_id or evaluation.pk,
        len(resultat.confirmes),
        len(resultat.ecartes),
    )
    return resultat
