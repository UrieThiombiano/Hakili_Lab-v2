"""Squelette du plan de remédiation d'une copie — ce que le modèle ne décide pas.

Du diagnostic contraint (module 4) d'une copie, on tire les compétences à
reprendre, leur ordre (prérequis d'abord, `plan.ordonner_competences`), leur
durée (formule de coût, D-CEO-29) et les questions de la copie qui s'y
rattachent. Le pipeline (`src/pipeline/plan_remediation.py`) fait ensuite
rédiger le contenu de chaque section.

Lecture seule : rien n'est écrit en base. Le plan sert l'élève dès la fin de
l'analyse ; ce qui est conservé ne l'est que sur décision de l'enseignant.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session as SQLASession

from app.models import Competence, Question, SignatureErreur, TypeErreur
from app.services.couts import VOLUME_REPLI_LYCEE, cout_precalcule, cout_remediation
from app.services.diagnostic_referentiel import MARQUEUR_ABSENCE
from app.services.plan import dependances_entre, ordonner_competences
from src.models.domain import (
    CopyGrade,
    DemandePlan,
    DiagnosticContraint,
    ProblemeDetecte,
    QuestionPlan,
    Rubric,
    SectionPlanDemande,
    TeacherDecision,
    TypeErreurPlan,
)

_MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]

#: Signatures d'erreur du référentiel montrées au modèle par section.
SIGNATURES_PAR_SECTION = 4


def date_fr(jour: date | None = None) -> str:
    jour = jour or date.today()
    return f"{jour.day} {_MOIS[jour.month]} {jour.year}"


def libelles_test(titre: str) -> tuple[str, str]:
    """« Test diagnostique d'entrée en 1ère D » → (« test diagnostique
    d'entrée en 1ère D », « 1ère D »)."""
    libelle = titre[:1].lower() + titre[1:] if titre else "test diagnostique"
    classe = re.search(r"\ben\s+(.+)$", titre or "")
    return libelle, classe.group(1).strip() if classe else ""


def _questions_de_la_copie(grade: CopyGrade, rubric: Rubric) -> dict[str, QuestionPlan]:
    """Chaque question telle que la correction validée l'a relevée — même
    critère de réussite que `diagnostic_referentiel.reponses_depuis_correction`."""
    items = {item.id: item for item in rubric.items}
    questions: dict[str, QuestionPlan] = {}
    for q in grade.questions:
        score = (q.teacher_score if q.teacher_decision == TeacherDecision.refused
                 and q.teacher_score is not None else q.score)
        item = items.get(q.rubric_item_id)
        questions[q.rubric_item_id] = QuestionPlan(
            code=q.rubric_item_id,
            intitule=item.label if item else "",
            reponse_eleve=(q.observed_answer or "").strip() or MARQUEUR_ABSENCE,
            reponse_attendue=q.correct_answer,
            reussie=item is not None and score >= item.max_score,
            commentaire=q.comment,
        )
    return questions


def _duree(db: SQLASession, competence: Competence, types: list[TypeErreur]) -> Decimal:
    """Somme des coûts des types d'erreur relevés sur la compétence. Un coût
    absent du classeur est recalculé par la formule plutôt que compté nul :
    une section sans durée fausserait tout le calendrier."""
    total = Decimal("0")
    for type_erreur in types:
        cout = cout_precalcule(db, competence.code, type_erreur.code)
        if cout <= 0:
            volume = Decimal(competence.volume_horaire) if competence.volume_horaire else VOLUME_REPLI_LYCEE
            cout = cout_remediation(volume, Decimal(type_erreur.coefficient))
        total += cout
    return total


# ── Copies hors référentiel de questions : mode libre, T1, T3… ────────────────

#: Classe canonique (`classe_normalizer`) → niveau du référentiel.
_NIVEAU_DE_CLASSE = {
    "CP": "Primaire", "CE": "Primaire", "CM": "Primaire",
    "6e": "6eme", "5e": "5eme", "4e": "4eme", "3e": "3eme",
    "2nde": "2ndeC", "1ere": "1ereD", "Tle": "tleD",
}
#: Classe inconnue : tout le référentiel plutôt qu'aucun plan.
NIVEAU_PAR_DEFAUT = "tleD"
#: Libellé d'un exercice de sujet T1/T3… : « compétence × type d'erreur »
#: (`generation.persister_sujet_verification`, `_persister_sujet_confirmation`).
SEPARATEUR_SUJET = " × "


def niveau_de_classe(classe: str | None) -> str:
    from src.core.classe_normalizer import normalize_classe

    return _NIVEAU_DE_CLASSE.get(normalize_classe(classe) or "", NIVEAU_PAR_DEFAUT)


def rattacher_par_libelle(db: SQLASession, grade: CopyGrade, rubric: Rubric) -> tuple[list[ProblemeDetecte], list[str]]:
    """Questions ratées d'un sujet T1/T3… : chaque exercice cible un problème
    nommé « compétence × type d'erreur », retrouvé dans le référentiel sans
    appel de modèle. Rend les problèmes et les questions ratées restées sans
    rattachement (libellé inconnu : mode libre, sujet ancien)."""
    competences = {c.libelle: c.code for c in db.query(Competence).all()}
    types = {t.libelle: t.code for t in db.query(TypeErreur).all()}
    problemes: list[ProblemeDetecte] = []
    restantes: list[str] = []
    for q in _questions_de_la_copie(grade, rubric).values():
        if q.reussie:
            continue
        libelle_competence, _, libelle_type = q.intitule.partition(SEPARATEUR_SUJET)
        competence = competences.get(libelle_competence.strip())
        type_erreur = types.get(libelle_type.strip())
        if competence and type_erreur:
            problemes.append(ProblemeDetecte(
                code_question=q.code, code_competence=competence, code_type_erreur=type_erreur,
                citation=q.reponse_eleve,
            ))
        else:
            restantes.append(q.code)
    return problemes, restantes


def diagnostic_hors_referentiel(
    db: SQLASession,
    *,
    copy_id: str,
    classe: str,
    evaluation: str,
    grade: CopyGrade,
    rubric: Rubric,
    client,
) -> DiagnosticContraint:
    """Diagnostic d'une copie dont les questions ne sont pas au référentiel.
    Les exercices T1/T3… se rattachent par leur libellé ; les autres questions
    ratées passent par le diagnostic sans ancrage (`diagnostiquer_sans_ancrage`),
    contraint au catalogue des compétences du niveau de l'élève. Dans les deux
    cas, aucun code n'est inventé."""
    from app.services.diagnostic_referentiel import ProductionEleve, diagnostiquer_sans_ancrage

    niveau = niveau_de_classe(classe)
    problemes, restantes = rattacher_par_libelle(db, grade, rubric)
    diagnostic = DiagnosticContraint(copy_id=copy_id, niveau_test=niveau, problemes=problemes,
                                     questions_diagnostiquees=[p.code_question for p in problemes])
    if not restantes:
        return diagnostic

    questions = _questions_de_la_copie(grade, rubric)
    productions = [
        ProductionEleve(
            repere=code,
            enonce=" — ".join(filter(None, [questions[code].intitule,
                                            f"réponse attendue : {questions[code].reponse_attendue}"
                                            if questions[code].reponse_attendue else ""])),
            production="" if questions[code].reponse_eleve == MARQUEUR_ABSENCE else questions[code].reponse_eleve,
        )
        for code in restantes
    ]
    libre = diagnostiquer_sans_ancrage(db, niveau_test=niveau, productions=productions, client=client,
                                       copy_id=copy_id, inclus=True, evaluation=evaluation)
    diagnostic.problemes += libre.problemes
    diagnostic.questions_diagnostiquees += libre.questions_diagnostiquees
    diagnostic.questions_ecartees.update(libre.questions_ecartees)
    diagnostic.rejets += libre.rejets
    diagnostic.appels_modele += libre.appels_modele
    return diagnostic


def demande_plan(
    db: SQLASession,
    *,
    copy_id: str,
    nom: str,
    prenom: str,
    titre_test: str,
    niveau_test: str,
    grade: CopyGrade,
    rubric: Rubric,
    diagnostic: DiagnosticContraint,
) -> DemandePlan:
    """Squelette du plan. Les problèmes de type non remédiable (ATT) sont
    ignorés ; une demande sans section signifie qu'il n'y a rien à reprendre."""
    questions = _questions_de_la_copie(grade, rubric)
    types = {t.code: t for t in db.query(TypeErreur).all()}

    problemes_par_competence: dict[str, list] = {}
    for p in diagnostic.problemes:
        type_erreur = types.get(p.code_type_erreur)
        if type_erreur is None or not type_erreur.remediable:
            continue
        problemes_par_competence.setdefault(p.code_competence, []).append(p)

    competences = [db.get(Competence, code) for code in problemes_par_competence]
    ordre = ordonner_competences(db, [c for c in competences if c is not None])
    rang = {c.code: i for i, c in enumerate(ordre, start=1)}
    dependances = dependances_entre(db, set(rang))

    # Questions sans problème relevé (réussies, ou écartées par le diagnostic) :
    # rattachées à leur compétence principale si elle est dans le plan.
    avec_probleme = {p.code_question for lot in problemes_par_competence.values() for p in lot}
    principale = {
        q.code_question: q.competence_id
        for q in db.query(Question).filter(Question.niveau_test == niveau_test).all()
    }

    sections: list[SectionPlanDemande] = []
    for competence in ordre:
        lot = problemes_par_competence[competence.code]
        codes_types = sorted({p.code_type_erreur for p in lot})
        citations = {p.code_question: p.citation for p in lot}
        codes_questions = list(dict.fromkeys(p.code_question for p in lot))
        codes_questions += [
            code for code in questions
            if code not in avec_probleme and principale.get(code) == competence.code
        ]
        section_questions = [
            questions[code].model_copy(update={"citation": citations.get(code, "")})
            for code in codes_questions if code in questions
        ]
        if not any(not q.reussie for q in section_questions):
            continue  # un problème sur une question absente de la copie : rien à montrer

        signatures = (
            db.query(SignatureErreur)
            .filter(SignatureErreur.competence_id == competence.code,
                    SignatureErreur.type_erreur_id.in_(codes_types))
            .limit(SIGNATURES_PAR_SECTION)
            .all()
        )
        prerequis = sorted(rang[code] for code in dependances[competence.code])
        sections.append(SectionPlanDemande(
            ordre=rang[competence.code],
            code_competence=competence.code,
            libelle_competence=competence.libelle,
            description_competence=competence.description,
            niveau_intro=competence.niveau_intro,
            types_erreur=[
                TypeErreurPlan(code=c, libelle=types[c].libelle, definition=types[c].definition)
                for c in codes_types
            ],
            questions=section_questions,
            signatures=[f"{s.production_eleve} → {s.interpretation}" for s in signatures],
            duree_h=float(_duree(db, competence, [types[c] for c in codes_types])),
            prerequis=prerequis,
            libelles_prerequis=[ordre[i - 1].libelle for i in prerequis],
        ))

    # Une section sautée décale les rangs : on renumérote, prérequis compris.
    renumerotation = {s.ordre: i for i, s in enumerate(sections, start=1)}
    for s in sections:
        s.prerequis = [renumerotation[p] for p in s.prerequis if p in renumerotation]
        s.ordre = renumerotation[s.ordre]

    test_libelle, classe = libelles_test(titre_test)
    return DemandePlan(
        copy_id=copy_id,
        eleve_nom=f"{nom.upper()} {prenom}".strip(),
        prenom=prenom or nom,
        classe=classe,
        test_libelle=test_libelle,
        date=date_fr(),
        sections=sections,
        questions_reussies=[q for q in questions.values() if q.reussie],
    )
