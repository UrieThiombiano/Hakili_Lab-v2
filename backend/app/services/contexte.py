"""Port de `referentiel/contexte.py` — le contexte de diagnostic construit
depuis le référentiel (compétence, chaîne de prérequis, signatures d'erreur),
injecté dans le prompt de diagnostic (`{{CURRICULUM_CONTEXT}}`). Voir le
fichier d'origine pour la justification (D-CEO-12, D-CEO-41) ; ce module ne
change ni l'algorithme ni le texte produit, seulement l'ORM des requêtes.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as SQLASession

from app.models import Competence, Prerequis, Question, SignatureErreur
from src.knowledge.remediation_retriever import get_remediation_retriever

#: Au-delà, la remontée des prérequis noie le contexte plus qu'elle ne l'éclaire.
PROFONDEUR_PREREQUIS = 2


def chaine_prerequis(db: SQLASession, competence: Competence, profondeur: int = PROFONDEUR_PREREQUIS) -> list[Competence]:
    """Prérequis directs puis indirects, sans doublon ni boucle."""
    vus: set[str] = {competence.code}
    chaine: list[Competence] = []
    courant = [competence]

    for _ in range(profondeur):
        suivant: list[Competence] = []
        for comp in courant:
            liens = db.execute(select(Prerequis).where(Prerequis.competence_id == comp.code)).scalars().all()
            for lien in liens:
                requis = lien.prerequis
                if requis.code in vus:
                    continue
                vus.add(requis.code)
                chaine.append(requis)
                suivant.append(requis)
        if not suivant:
            break
        courant = suivant

    return chaine


def _questions(db: SQLASession, niveau_test: str, codes_questions: list[str]) -> list[Question]:
    return (
        db.query(Question)
        .filter(Question.niveau_test == niveau_test, Question.code_question.in_(codes_questions))
        .all()
    )


def contexte_diagnostic(db: SQLASession, niveau_test: str, codes_questions: list[str]) -> str:
    """Texte injecté dans `{{CURRICULUM_CONTEXT}}` du prompt de diagnostic.
    Vide si aucune question échouée, ou si le référentiel n'a pas été importé."""
    if not codes_questions:
        return ""

    questions = _questions(db, niveau_test, codes_questions)
    blocs: list[str] = []
    for question in questions:
        competence = question.competence
        lignes = [
            f"### Question {question.code_question} — {question.objet}",
            f"Compétence évaluée : [{competence.code}] {competence.libelle}",
        ]
        if competence.description:
            lignes.append(f"Attendu : {competence.description}")
        lignes.append(
            f"Introduite en {competence.niveau_intro}" + (f", {competence.chapitre_intro}" if competence.chapitre_intro else "")
        )

        prerequis = chaine_prerequis(db, competence, PROFONDEUR_PREREQUIS)
        if prerequis:
            lignes.append("Prérequis à vérifier si l'échec persiste : " + " ; ".join(f"[{p.code}] {p.libelle}" for p in prerequis))

        signatures = db.query(SignatureErreur).filter(SignatureErreur.question_id == question.id).all()
        if signatures:
            lignes.append("Erreurs attendues sur cette question :")
            for signature in signatures:
                lignes.append(f"  - [{signature.type_erreur_id}] si l'élève écrit « {signature.production_eleve} » → {signature.interpretation}")

        chunk_remediation = get_remediation_retriever().get_by_competence(competence.code, niveau_test)
        if chunk_remediation:
            lignes.append(chunk_remediation.to_context_text())

        blocs.append("\n".join(lignes))

    if not blocs:
        return ""

    return (
        "Programme officiel et erreurs attendues, pour les questions échouées.\n"
        "Les codes entre crochets sont ceux du référentiel : les reprendre tels "
        "quels, ne jamais en inventer.\n\n" + "\n\n".join(blocs)
    )


def lacunes_competences(db: SQLASession, niveau_test: str, codes_questions: list[str]) -> list[dict]:
    """Lacunes prêtes à devenir des `CompetencyGap`, une par compétence échouée."""
    if not codes_questions:
        return []

    questions = _questions(db, niveau_test, codes_questions)
    par_competence: dict[str, dict] = {}
    for question in questions:
        competence = question.competence
        entree = par_competence.setdefault(
            competence.code,
            {
                "chunk_id": competence.code,
                "classe": competence.niveau_intro,
                "domaine": competence.domaine,
                "chapitre": competence.chapitre_intro or "",
                "lecon": competence.libelle,
                "description": competence.description or competence.libelle,
                "savoir_faire": [],
                "erreurs_frequentes": [],
            },
        )
        signatures = db.query(SignatureErreur).filter(SignatureErreur.question_id == question.id).all()
        for signature in signatures:
            texte = f"{signature.production_eleve} → {signature.interpretation}"
            if texte not in entree["erreurs_frequentes"]:
                entree["erreurs_frequentes"].append(texte)

    return list(par_competence.values())
