"""Port de `referentiel/diagnostic.py` — le moteur de diagnostic contraint
(module 4). Voir le fichier d'origine pour la justification de chaque règle
(les trois barrières contre un code inventé, le court-circuit des QCM, la
règle « ce qui n'est pas diagnostiqué est dit »). Algorithme inchangé,
seules les requêtes passent de l'ORM Django à SQLAlchemy.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as SQLASession

from app.models import Competence, OptionQcm, Question, SignatureErreur, TypeErreur
from app.services.contexte import PROFONDEUR_PREREQUIS, chaine_prerequis
from app.services.niveaux import deja_enseigne
from src.models.domain import (
    CopyGrade,
    DiagnosticContraint,
    ProblemeDetecte,
    Rubric,
    SortieDiagnosticContraint,
    SourceProbleme,
    TeacherDecision,
)

logger = logging.getLogger(__name__)

REDEMANDES_MAX = 1
CITATION_VIDE = "(aucune réponse)"

_LETTRE_SEULE = re.compile(r"^[^\w]*([A-Za-z])[\s).:\-]*$")
_LETTRE_MARQUEE = re.compile(r"^[^\w]*([A-Za-z])[).:]")

MARQUEUR_ABSENCE = "—"
MARQUEUR_ILLISIBLE = "[ILLISIBLE]"


@dataclass(frozen=True)
class ReponseEleve:
    code_question: str
    contenu: str = ""
    vide: bool = False
    illisible: bool = False
    correcte: bool | None = None


def reponses_depuis_correction(grade: CopyGrade, rubric: Rubric) -> list[ReponseEleve]:
    """Les réponses de l'élève, telles que la correction les a déjà relevées
    — pur (aucune requête), copié à l'identique de `referentiel/diagnostic.py`."""
    maxima = {item.id: item.max_score for item in rubric.items}
    reponses: list[ReponseEleve] = []

    for question in grade.questions:
        if question.teacher_decision == TeacherDecision.refused and question.teacher_score is not None:
            score = question.teacher_score
        else:
            score = question.score

        maximum = maxima.get(question.rubric_item_id)
        correcte = None if maximum is None else score >= maximum

        contenu = (question.observed_answer or "").strip()
        reponses.append(
            ReponseEleve(
                code_question=question.rubric_item_id,
                contenu=contenu,
                vide=contenu in ("", MARQUEUR_ABSENCE),
                illisible=MARQUEUR_ILLISIBLE in contenu,
                correcte=correcte,
            )
        )

    return reponses


@dataclass
class _Lot:
    charge: list[dict] = field(default_factory=list)
    admis_par_question: dict[str, set[str]] = field(default_factory=dict)
    problemes: list[ProblemeDetecte] = field(default_factory=list)
    ecartees: dict[str, str] = field(default_factory=dict)
    traitees: list[str] = field(default_factory=list)


def codes_competence_admis(db: SQLASession, question: Question) -> list[str]:
    codes = [question.competence_id]
    if question.competence_secondaire_id:
        codes.append(question.competence_secondaire_id)
    for requis in chaine_prerequis(db, question.competence, PROFONDEUR_PREREQUIS):
        if requis.code not in codes:
            codes.append(requis.code)
    return codes


def lettre_cochee(contenu: str, lettres_possibles: set[str]) -> str | None:
    texte = (contenu or "").strip()
    if not texte:
        return None
    for motif in (_LETTRE_SEULE, _LETTRE_MARQUEE):
        trouve = motif.match(texte)
        if trouve:
            lettre = trouve.group(1).lower()
            if lettre in lettres_possibles:
                return lettre
            return None
    return None


def diagnostiquer_qcm(db: SQLASession, question: Question, reponse: ReponseEleve) -> tuple[ProblemeDetecte | None, str]:
    options = {o.lettre.lower(): o for o in db.query(OptionQcm).filter(OptionQcm.question_id == question.id).all()}
    if not options:
        return None, "QCM sans options au référentiel — l'import du classeur est incomplet."

    if reponse.vide or not (reponse.contenu or "").strip():
        return None, "aucune option cochée — à trancher par l'enseignant"

    lettre = lettre_cochee(reponse.contenu, set(options))
    if lettre is None:
        return None, f"réponse « {reponse.contenu.strip()[:40]} » non interprétable comme une option ({', '.join(sorted(options))})"

    option = options[lettre]
    if option.correcte:
        return None, ""

    return (
        ProblemeDetecte(
            code_question=question.code_question,
            code_competence=question.competence_id,
            code_type_erreur=option.type_erreur_id,
            citation=f"option {option.lettre} cochée — {option.texte}".strip(),
            source=SourceProbleme.qcm,
        ),
        "",
    )


def _charge_utile(db: SQLASession, question: Question, reponse: ReponseEleve, admis: list[str]) -> dict:
    competence = question.competence
    signatures = db.query(SignatureErreur).filter(SignatureErreur.question_id == question.id).all()
    return {
        "code_question": question.code_question,
        "partie": question.partie,
        "format": question.format,
        "enonce": question.objet,
        "competence_evaluee": {
            "code": competence.code,
            "libelle": competence.libelle,
            "description": competence.description or "",
            "introduite_en": competence.niveau_intro,
        },
        "codes_competence_admis": admis,
        "reponse_attendue": question.reponse_attendue or "",
        "demarche_attendue": question.solution or "",
        "reponse_eleve": CITATION_VIDE if reponse.vide or not reponse.contenu.strip() else reponse.contenu.strip(),
        "zone_vierge": bool(reponse.vide or not reponse.contenu.strip()),
        "signatures_erreur": [
            {"type_erreur": s.type_erreur_id, "production_eleve": s.production_eleve, "lacune_revelee": s.interpretation}
            for s in signatures
        ],
    }


def preparer(db: SQLASession, niveau_test: str, reponses: list[ReponseEleve]) -> _Lot:
    lot = _Lot()

    a_diagnostiquer = [r for r in reponses if r.correcte is not True]
    codes = [r.code_question for r in a_diagnostiquer]
    questions = {
        q.code_question: q
        for q in db.query(Question).filter(Question.niveau_test == niveau_test, Question.code_question.in_(codes)).all()
    }

    for reponse in a_diagnostiquer:
        question = questions.get(reponse.code_question)
        if question is None:
            lot.ecartees[reponse.code_question] = f"question absente du référentiel pour le niveau {niveau_test}"
            continue

        if reponse.illisible:
            lot.ecartees[reponse.code_question] = "réponse non déchiffrée à la lecture — à relire sur la copie"
            continue

        if question.format == "construction":
            lot.ecartees[reponse.code_question] = "construction géométrique — relève de la saisie humaine (module 8)"
            continue

        if question.format == "qcm":
            probleme, motif = diagnostiquer_qcm(db, question, reponse)
            if probleme is not None:
                lot.problemes.append(probleme)
                lot.traitees.append(reponse.code_question)
            elif motif:
                lot.ecartees[reponse.code_question] = motif
            else:
                lot.traitees.append(reponse.code_question)
            continue

        admis = codes_competence_admis(db, question)
        lot.admis_par_question[question.code_question] = set(admis)
        lot.charge.append(_charge_utile(db, question, reponse, admis))

    return lot


def valider(sortie: SortieDiagnosticContraint, admis_par_question: dict[str, set[str]], codes_types: set[str]) -> tuple[list[ProblemeDetecte], list[str]]:
    retenus: list[ProblemeDetecte] = []
    rejets: list[str] = []
    vus: set[str] = set()

    for probleme in sortie.problemes:
        code_q = probleme.code_question
        admis = admis_par_question.get(code_q)

        if admis is None:
            rejets.append(f"{code_q} : cette question ne fait pas partie de celles soumises. Ne diagnostiquer que les questions fournies.")
            continue
        if code_q in vus:
            rejets.append(f"{code_q} : deux problèmes pour la même question. Une question ne révèle qu'une lacune — garder celle qui explique le plus.")
            continue
        if probleme.code_competence not in admis:
            rejets.append(f"{code_q} : compétence {probleme.code_competence!r} non admise. Codes possibles pour cette question : {', '.join(sorted(admis))}.")
            continue
        if probleme.code_type_erreur not in codes_types:
            rejets.append(f"{code_q} : type d'erreur {probleme.code_type_erreur!r} inconnu. Liste fermée : {', '.join(sorted(codes_types))}.")
            continue
        if not probleme.citation.strip():
            rejets.append(f"{code_q} : citation vide. Sans elle, un désaccord sur ce problème est inarbitrable — citer ce qui est écrit sur la copie.")
            continue

        vus.add(code_q)
        retenus.append(probleme)

    return retenus, rejets


def diagnostiquer(db: SQLASession, *, niveau_test: str, reponses: list[ReponseEleve], client=None, copy_id: str = "") -> DiagnosticContraint:
    lot = preparer(db, niveau_test, reponses)
    codes_types = {t[0] for t in db.query(TypeErreur.code).all()}

    resultat = DiagnosticContraint(
        copy_id=copy_id,
        niveau_test=niveau_test,
        problemes=list(lot.problemes),
        questions_diagnostiquees=list(lot.traitees),
        questions_ecartees=dict(lot.ecartees),
    )

    if not lot.charge:
        return resultat

    if client is None:
        for charge in lot.charge:
            resultat.questions_ecartees[charge["code_question"]] = "aucun client de diagnostic — seuls les QCM ont été traités"
        return resultat

    if not codes_types:
        raise RuntimeError("Le référentiel est vide : importer le classeur avant tout diagnostic. Sans lui, aucun code ne peut être validé.")

    codes_competences = sorted({code for admis in lot.admis_par_question.values() for code in admis})
    corrections = ""

    for tentative in range(REDEMANDES_MAX + 1):
        reponse_api = client.diagnose_constrained(
            copy_id=copy_id,
            niveau_test=niveau_test,
            questions=lot.charge,
            codes_competences=codes_competences,
            codes_types=sorted(codes_types),
            corrections=corrections,
        )
        resultat.appels_modele += 1

        if not reponse_api.success or reponse_api.data is None:
            logger.warning("[%s] Diagnostic contraint sans réponse : %s", copy_id, reponse_api.error)
            for charge in lot.charge:
                resultat.questions_ecartees.setdefault(charge["code_question"], f"le modèle n'a pas répondu ({reponse_api.error or 'erreur inconnue'})")
            return resultat

        retenus, rejets = valider(reponse_api.data, lot.admis_par_question, codes_types)
        if not rejets:
            resultat.problemes.extend(retenus)
            break

        logger.warning("[%s] Diagnostic contraint — %d sortie(s) refusée(s), tentative %d/%d", copy_id, len(rejets), tentative + 1, REDEMANDES_MAX + 1)
        if tentative == REDEMANDES_MAX:
            resultat.problemes.extend(retenus)
            resultat.rejets.extend(rejets)
            break
        corrections = "\n".join(f"- {motif}" for motif in rejets)

    diagnostiquees = {p.code_question for p in resultat.problemes}
    for charge in lot.charge:
        code = charge["code_question"]
        if code in diagnostiquees:
            resultat.questions_diagnostiquees.append(code)
        else:
            resultat.questions_ecartees.setdefault(code, "aucun problème retenu par le modèle pour cette question")

    return resultat


@dataclass(frozen=True)
class ProductionEleve:
    repere: str
    enonce: str
    production: str


def catalogue_competences(db: SQLASession, niveau_test: str) -> list[dict]:
    competences = [c for c in db.query(Competence).order_by(Competence.domaine, Competence.code).all() if deja_enseigne(c.niveau_intro, niveau_test)]
    return [
        {"code": c.code, "libelle": c.libelle, "description": c.description or "", "domaine": c.domaine, "introduite_en": c.niveau_intro}
        for c in competences
    ]


def diagnostiquer_sans_ancrage(db: SQLASession, *, niveau_test: str, productions: list[ProductionEleve], client, copy_id: str = "") -> DiagnosticContraint:
    catalogue = catalogue_competences(db, niveau_test)
    codes_admis = {c["code"] for c in catalogue}
    codes_types = {t[0] for t in db.query(TypeErreur.code).all()}

    resultat = DiagnosticContraint(copy_id=copy_id, niveau_test=niveau_test)

    if not codes_admis:
        raise RuntimeError(f"Aucune compétence n'est enseignée avant le niveau {niveau_test!r} dans le référentiel — vérifier l'import du classeur et le niveau donné.")

    charge = [
        {"repere": p.repere, "enonce": p.enonce, "production_eleve": p.production.strip() or CITATION_VIDE, "zone_vierge": not p.production.strip()}
        for p in productions
    ]
    admis_par_repere = {c["repere"]: codes_admis for c in charge}
    corrections = ""

    for tentative in range(REDEMANDES_MAX + 1):
        reponse_api = client.diagnose_unanchored(
            copy_id=copy_id,
            niveau_test=niveau_test,
            productions=charge,
            catalogue=catalogue,
            codes_types=sorted(codes_types),
            corrections=corrections,
        )
        resultat.appels_modele += 1

        if not reponse_api.success or reponse_api.data is None:
            logger.warning("[%s] Mesure plancher sans réponse : %s", copy_id, reponse_api.error)
            for item in charge:
                resultat.questions_ecartees[item["repere"]] = f"le modèle n'a pas répondu ({reponse_api.error or 'erreur inconnue'})"
            return resultat

        retenus, rejets = valider(reponse_api.data, admis_par_repere, codes_types)
        if not rejets:
            resultat.problemes.extend(retenus)
            break
        if tentative == REDEMANDES_MAX:
            resultat.problemes.extend(retenus)
            resultat.rejets.extend(rejets)
            break
        corrections = "\n".join(f"- {motif}" for motif in rejets)

    diagnostiques = {p.code_question for p in resultat.problemes}
    for item in charge:
        if item["repere"] in diagnostiques:
            resultat.questions_diagnostiquees.append(item["repere"])
        else:
            resultat.questions_ecartees.setdefault(item["repere"], "aucun problème retenu par le modèle")

    return resultat
