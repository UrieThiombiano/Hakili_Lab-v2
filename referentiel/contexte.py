"""
Contexte de diagnostic construit depuis le référentiel.

Le problème que ça résout
-------------------------
L'ancien ancrage passait par le champ `chunk_ids` des barèmes, qui reliait chaque
question à une leçon du curriculum. Les barèmes générés depuis le classeur n'ont
pas ce champ — le classeur ne le fournit pas. Résultat mesuré : le diagnostic des
7 nouveaux tests tournait avec **zéro caractère** de contexte programme, là où un
ancien test en recevait 2 048. C'était perdre ce que D-CEO-12 désigne comme la
valeur différenciante du produit : « un diagnostic qui dit *lacune en algèbre* est
inutilisable ».

Pourquoi le référentiel plutôt que le curriculum
------------------------------------------------
Le rapprochement leçon ↔ compétence (arbitrage C) n'est pas encore validé, mais il
n'est pas nécessaire : le référentiel porte déjà tout ce qu'il faut, et de façon
**vérifiée** (module 0, zéro violation d'intégrité).

  · `Question.competence` — le lien question → compétence, fiable et complet ;
  · `Prerequis` — la chaîne remontante, qui est précisément ce que le protocole
    demande : « remonter d'un échec vers la lacune ancienne qui l'explique, au
    lieu de traiter le symptôme » ;
  · `SignatureErreur` — 1 031 signatures **par question** : ce qu'on lit sur la
    copie et la lacune que cela révèle.

Ce dernier point rend le contexte meilleur que l'ancien : les signatures sont
propres à la question posée, là où un chunk de curriculum décrivait une leçon
entière. Le modèle n'a plus à deviner, il reconnaît.

Arbitrage C tranché (D-CEO-41, docs/harmonisation_donnees.md §7) : `remediation/`
enrichit désormais ce contexte, comme annoncé ci-dessus — il s'ajoute, il ne
remplace rien. Voir `src/knowledge/remediation_retriever.py`.
"""
from __future__ import annotations

from referentiel.models import Competence, Question
from src.knowledge.remediation_retriever import get_remediation_retriever

#: Au-delà, la remontée des prérequis noie le contexte plus qu'elle ne l'éclaire.
PROFONDEUR_PREREQUIS = 2


def chaine_prerequis(
    competence: Competence, profondeur: int = PROFONDEUR_PREREQUIS
) -> list[Competence]:
    """Prérequis directs puis indirects, sans doublon ni boucle.

    Le graphe est censé être acyclique — une contrainte l'interdit en base — mais
    on garde une trace des codes visités : une boucle introduite par un import mal
    formé ferait tourner cette fonction indéfiniment.
    """
    vus: set[str] = {competence.code}
    chaine: list[Competence] = []
    courant = [competence]

    for _ in range(profondeur):
        suivant = []
        for comp in courant:
            for lien in comp.prerequis.select_related("prerequis"):
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


def contexte_diagnostic(niveau_test: str, codes_questions: list[str]) -> str:
    """Texte injecté dans `{{CURRICULUM_CONTEXT}}` du prompt de diagnostic.

    Vide si aucune question échouée, ou si le référentiel n'a pas été importé —
    le pipeline tourne alors sans ancrage, comme avant, plutôt que d'échouer.
    """
    if not codes_questions:
        return ""

    questions = (
        Question.objects.filter(
            niveau_test=niveau_test, code_question__in=codes_questions
        )
        .select_related("competence")
        .prefetch_related("signatures__type_erreur")
    )

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
            f"Introduite en {competence.niveau_intro}"
            + (f", {competence.chapitre_intro}" if competence.chapitre_intro else "")
        )

        prerequis = chaine_prerequis(competence, PROFONDEUR_PREREQUIS)
        if prerequis:
            lignes.append(
                "Prérequis à vérifier si l'échec persiste : "
                + " ; ".join(f"[{p.code}] {p.libelle}" for p in prerequis)
            )

        signatures = list(question.signatures.all())
        if signatures:
            lignes.append("Erreurs attendues sur cette question :")
            for signature in signatures:
                lignes.append(
                    f"  - [{signature.type_erreur_id}] si l'élève écrit "
                    f"« {signature.production_eleve} » → {signature.interpretation}"
                )

        chunk_remediation = get_remediation_retriever().get_by_competence(
            competence.code, niveau_test
        )
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


def lacunes_competences(niveau_test: str, codes_questions: list[str]) -> list[dict]:
    """Lacunes prêtes à devenir des `CompetencyGap`, une par compétence échouée.

    Une compétence peut être ratée sur plusieurs questions : on la remonte une
    seule fois, sinon le rapport la répéterait.
    """
    if not codes_questions:
        return []

    questions = (
        Question.objects.filter(
            niveau_test=niveau_test, code_question__in=codes_questions
        )
        .select_related("competence")
        .prefetch_related("signatures")
    )

    par_competence: dict[str, dict] = {}
    for question in questions:
        competence = question.competence
        entree = par_competence.setdefault(
            competence.code,
            {
                # `chunk_id` portait l'identifiant de leçon du curriculum. Le
                # code canonique le remplace : il est stable entre niveaux, ce
                # que l'identifiant de leçon n'était pas.
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
        for signature in question.signatures.all():
            texte = f"{signature.production_eleve} → {signature.interpretation}"
            if texte not in entree["erreurs_frequentes"]:
                entree["erreurs_frequentes"].append(texte)

    return list(par_competence.values())
