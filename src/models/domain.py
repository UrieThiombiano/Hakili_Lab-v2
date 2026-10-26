from enum import Enum
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Validation enseignant ──────────────────────────────────────────────────────

class TeacherDecision(str, Enum):
    pending  = "pending"   # pas encore décidé
    accepted = "accepted"  # enseignant accepte la note IA
    refused  = "refused"   # enseignant refuse et saisit sa propre note


# ── Transcription ──────────────────────────────────────────────────────────────

class PageTranscription(BaseModel):
    page_number: int
    content: str
    formulas: list[str] = Field(default_factory=list)
    diagrams: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class TranscriptionResult(BaseModel):
    copy_id: str
    global_quality: Literal["good", "medium", "poor"]
    pages: list[PageTranscription]


# ── Barème ─────────────────────────────────────────────────────────────────────

class RubricItem(BaseModel):
    id: str                       # "Q1", "Q2a", "Q2b"
    label: str
    max_score: float = 1.0        # Points de la question (ex : 0.25, 0.5, 1.0, 2.0)
    parent_id: str | None = None  # Non-None si sous-question
    # Tests du référentiel (barèmes socle) : points de la question dans le
    # corrigé enseignant (ex : 2 sur 60), et pas de note admis sur l'échelle
    # max_score — max_score lui-même pour un tout-ou-rien (partie A), un
    # demi-point du corrigé sinon. None = barème binaire historique.
    points_corrige: float | None = None
    score_step: float | None = None


class Rubric(BaseModel):
    subject: Literal["mathematics"]
    total_points: float
    items: list[RubricItem]


# ── Correction ─────────────────────────────────────────────────────────────────

class QuestionGrade(BaseModel):
    rubric_item_id: str
    score: float                  # proposition IA : 0, max_score, ou multiple de score_step
    confidence: float = Field(ge=0.0, le=1.0)
    comment: str
    observed_answer: str          # ce que l'élève a écrit ("—" si absent/illisible)
    correct_answer: str = ""      # bonne réponse (corrigé officiel ou calculée par l'IA)
    requires_review: bool
    # Barème détaillé (item avec points_corrige) : points DU CORRIGÉ obtenus,
    # ex. 1 sur 2. Le modèle compte des critères ; la conversion vers
    # max_score est faite par validate_grading, pas par le modèle — il s'y
    # trompait (0,5/2 au lieu de 1/2 en recette du 2026-10-16).
    points_obtenus: float | None = None
    # ── Validation enseignant ──────────────────────────────────────────────────
    teacher_decision: TeacherDecision = TeacherDecision.pending
    teacher_score: float | None = None  # note saisie par l'enseignant si refus


class CopyGrade(BaseModel):
    copy_id: str
    total_score: float            # somme des propositions IA
    total_possible: float         # total officiel du test (meta.total_possible) — pour l'affichage
    questions: list[QuestionGrade]
    expert_instructions_used: bool = False
    # Somme réelle des max_score du barème (peut différer de total_possible si incohérence source)
    # Utilisé comme dénominateur pour la conversion /20 — garantit qu'un élève parfait obtient 20/20.
    rubric_actual_max: float | None = None
    # ── Score validé ──────────────────────────────────────────────────────────
    final_score: float | None = None        # calculé après validation enseignant
    final_score_on_20: float | None = None  # note /20 convertie
    validation_complete: bool = False       # True quand toutes les questions ont été décidées

    @model_validator(mode="before")
    @classmethod
    def _totaux_manquants(cls, data: Any) -> Any:
        # Claude Sonnet 5 omet parfois total_score/total_possible alors que toutes
        # les questions sont notées (prod du 2026-10-21) : la copie entière était
        # rejetée. validate_grading() recalcule les deux totaux depuis le barème,
        # une valeur provisoire suffit ici.
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            if "total_score" not in data or "total_possible" not in data:
                data = dict(data)
                data.setdefault("total_score", sum(
                    float(q.get("score") or 0) if isinstance(q, dict) else float(q.score)
                    for q in data["questions"]
                ))
                data.setdefault("total_possible", 0.0)
        return data

    def compute_final_score(self) -> "CopyGrade":
        """Calcule final_score en priorisant les décisions enseignant."""
        total = 0.0
        for q in self.questions:
            if q.teacher_decision == TeacherDecision.refused and q.teacher_score is not None:
                total += q.teacher_score
            else:
                total += q.score  # note IA (accepted ou pending)
        self.final_score = total
        # Dénominateur = total_possible (officiel du test, ex: 20).
        # rubric_actual_max n'est pas utilisé ici : l'élève voit son score sur le total déclaré.
        denom = self.total_possible
        if denom > 0:
            # Arrondi au 0.25 le plus proche — cohérent avec le barème binaire 0/0.25/0.5/0.75/1
            self.final_score_on_20 = round(round(total / denom * 20 * 4) / 4, 2)
        self.validation_complete = all(
            q.teacher_decision != TeacherDecision.pending for q in self.questions
        )
        return self


# ── Diagnostic et remédiation ─────────────────────────────────────────────────

class SkillAssessment(BaseModel):
    name: str
    # Niveaux français : acquis | part_acquis | non_acquis | unknown
    # Valeurs anglaises acceptées pour rétrocompatibilité : mastered→acquis, partial→part_acquis, weak→non_acquis
    level: str = "unknown"
    evidence: str
    chunk_ids: list[str] = Field(default_factory=list)  # IDs RAG du programme (classe+chapitre)
    note: str = ""  # contexte complémentaire, ex: "Erreur de vigilance isolée — compétence réussie en Q_NUM_05"

    @field_validator("level", mode="before")
    @classmethod
    def _normalise_level(cls, v: str) -> str:
        _compat = {"mastered": "acquis", "partial": "part_acquis", "weak": "non_acquis"}
        return _compat.get(str(v).lower(), str(v).lower())


class RootCauseError(BaseModel):
    """Erreur cachée derrière une erreur visible — cœur du diagnostic pédagogique."""
    visible_error: str
    hidden_cause: str
    # "dette_cycle_anterieur" | "lacune_contemporaine" | "erreur_inattention"
    nature: str = "lacune_contemporaine"
    pedagogical_trigger: str = ""
    linked_questions: list[str] = Field(default_factory=list)


class RemediationItem(BaseModel):
    priority: int
    topic: str
    action: str
    pedagogical_trigger: str = ""


class CompetencyGap(BaseModel):
    """Lacune de compétence ancrée sur le programme officiel (résultat du RAG)."""
    chunk_id: str                          # ex: "5e_NUM_Ch3_L1"
    classe: str                            # "5e"
    domaine: str                           # "numerique" | "geometrique"
    chapitre: str
    lecon: str
    description: str                       # texte court de synthèse
    savoir_faire: list[str] = Field(default_factory=list)
    erreurs_frequentes: list[str] = Field(default_factory=list)

    @field_validator("savoir_faire", "erreurs_frequentes", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        # PyYAML parse "- texte : formule" en dict — on reconstitue la chaîne.
        result = []
        for item in (v or []):
            if isinstance(item, dict):
                parts = [f"{k} : {val}" if val is not None else str(k) for k, val in item.items()]
                result.append(" ".join(parts))
            else:
                result.append(str(item))
        return result


class DiagnosticResult(BaseModel):
    copy_id: str
    academic_profile: str = ""  # synthèse du profil élève pour le tuteur
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    root_causes: list[RootCauseError] = Field(default_factory=list)
    skills: list[SkillAssessment] = Field(default_factory=list)
    remediation_plan: list[RemediationItem] = Field(default_factory=list)
    competency_gaps: list[CompetencyGap] = Field(default_factory=list)


# ── Diagnostic contraint (module 4, chantier v2) ──────────────────────────────
#
# Ces schémas remplacent `DiagnosticResult` pour les niveaux couverts par le
# référentiel. La différence n'est pas de format mais de nature : `DiagnosticResult`
# porte de la prose (`academic_profile`, `weaknesses`…), qu'on ne peut ni compter,
# ni comparer d'une passation à l'autre, ni chiffrer. Ici chaque sortie est un
# **problème** — compétence × type d'erreur — c'est-à-dire une ligne de la table
# `probleme`, avec un coût et un cycle de vie.
#
# Ils vivent dans `src/` parce que les clients d'API s'en servent, et `src/` ne
# dépend d'aucun framework. Les codes, eux, viennent du référentiel Django :
# ces modèles ne les valident pas, `referentiel/diagnostic.py` s'en charge.


class SourceProbleme(str, Enum):
    """D'où vient un problème — ça décide de la confiance qu'on lui accorde.

    `qcm` est mécanique et sans appel de modèle : la lettre cochée donne le type
    d'erreur par la table `option_qcm`. `modele` demande une reconnaissance et
    peut se tromper. Les distinguer permet de mesurer l'écart du module 4 sur ce
    qui est réellement diagnostiqué, sans le flatter avec les QCM.
    """

    qcm = "qcm"
    modele = "modele"


class ProblemeDetecte(BaseModel):
    """Une lacune relevée sur une question — trois champs, pas quatre.

    `citation` est ce qu'on lit sur la copie, pas un commentaire : c'est elle qui
    rend un désaccord avec le corpus de référence arbitrable (elle alimente
    `Probleme.justification`).
    """

    code_question: str
    code_competence: str
    code_type_erreur: str
    citation: str
    source: SourceProbleme = SourceProbleme.modele


class SortieDiagnosticContraint(BaseModel):
    """Ce que le modèle rend, et rien d'autre — aucune prose n'est acceptée."""

    problemes: list[ProblemeDetecte] = Field(default_factory=list)


class DiagnosticContraint(BaseModel):
    """Le diagnostic complet d'une copie, une fois les codes validés.

    `questions_ecartees` est aussi importante que `problemes` : une question
    écartée est une question que **personne** n'a diagnostiquée. Sans la lister,
    l'absence de problème se lirait comme une réussite.
    """

    copy_id: str
    niveau_test: str
    problemes: list[ProblemeDetecte] = Field(default_factory=list)
    questions_diagnostiquees: list[str] = Field(default_factory=list)
    #: code de question → motif de mise à l'écart, en clair.
    questions_ecartees: dict[str, str] = Field(default_factory=dict)
    #: Sorties du modèle rejetées faute d'un code admissible, conservées pour
    #: pouvoir mesurer le taux de validité exigé par le jalon du module 4.
    rejets: list[str] = Field(default_factory=list)
    appels_modele: int = 0

    @property
    def valide(self) -> bool:
        """Vrai si aucune sortie du modèle n'a été rejetée.

        C'est l'unité que compte le jalon « 100 sorties consécutives valides ».
        """
        return not self.rejets


# ── Sujet de remédiation ───────────────────────────────────────────────────────

class Exercise(BaseModel):
    number: int
    topic: str
    question: str
    hint: str | None = None  # None pour les exercices 3-5 (pas de guidage)


class RemediationSubject(BaseModel):
    copy_id: str
    exercises: list[Exercise]
    is_enrichment: bool = False  # True quand score parfait → exercices d'approfondissement


# ── Plan de remédiation (cahier élève, un seul PDF) ─────────────────────────────
# Remplace le sujet de remédiation/enrichissement : un cahier qui reprend la
# copie compétence par compétence, dans l'ordre de travail, avec 5 exercices
# chacune et les réponses en annexe. Gabarit : templates/plan_remediation/,
# modèle validé : l'exemplaire NIKIEMA K. Amale (tests/fixtures/).
# Le texte est en LaTeX entre \( \) et \[ \], rendu par MathJax.

#: Durée d'une séance de travail, en heures (« séances de 1 h 30 »).
DUREE_SEANCE_H = 1.5
#: Rythme hebdomadaire annoncé à l'élève.
SEANCES_PAR_SEMAINE = 2
#: Note sur 20 à partir de laquelle aucun plan n'est produit.
SEUIL_SANS_PLAN = 19.0


class LigneEcrit(BaseModel):
    """Une ligne de « Ce que tu as écrit »."""
    question: str                 # "N1", ou "N4, P2.2, P3.3"
    reponse_eleve: str = ""       # vide si `reussie`
    reponse_attendue: str
    #: Question réussie : une seule cellule « réussie : <reponse_attendue> ».
    reussie: bool = False


class ExercicePlan(BaseModel):
    enonce: str
    niveau: int = Field(ge=1, le=3)
    reponse: str                  # reprise dans l'annexe « Réponses des exercices »


class CompetencePlan(BaseModel):
    titre: str
    titre_tableau: str | None = None  # libellé dans « Le plan, séance par séance », sinon `titre`
    titre_court: str              # titre de la rubrique dans l'annexe
    duree_h: float = Field(gt=0)
    questions: list[str] = Field(min_length=1)
    #: Numéros d'ordre (1 = première section) des sections à faire avant.
    prerequis: list[int] = Field(default_factory=list)
    ecrits: list[LigneEcrit] = Field(min_length=1)
    #: Paragraphes séparés par une ligne vide ; un paragraphe qui n'est qu'une
    #: formule \[ … \] est centré hors paragraphe ; *mot* met en italique.
    ce_qui_ne_va_pas: str
    causes: list[str] = Field(min_length=1)
    a_retenir: list[str] = Field(min_length=1)
    methode_titre: str = "Méthode"
    methode: list[str] = Field(default_factory=list)  # bloc omis si vide
    #: Consigne commune en tête de « A toi de jouer » (« Pour les exercices 1 à 3 : … »).
    consigne_exercices: str | None = None
    exercices: list[ExercicePlan] = Field(min_length=5, max_length=5)
    code_competence: str | None = None  # code canonique du référentiel, si connu


class PlanRemediation(BaseModel):
    copy_id: str
    eleve_nom: str                # "NIKIEMA K. Amale"
    prenom: str                   # "Amale" — l'introduction tutoie l'élève
    classe: str                   # "1ère D"
    test_libelle: str             # "test diagnostique d'entrée en 1ère D"
    date: str                     # "24 octobre 2026"
    acquis: list[str] = Field(default_factory=list)  # « Ce que tu sais déjà faire »
    competences: list[CompetencePlan] = Field(min_length=1)

    @model_validator(mode="after")
    def _prerequis_anterieurs(self) -> "PlanRemediation":
        for i, c in enumerate(self.competences, start=1):
            if any(not 1 <= p < i for p in c.prerequis):
                raise ValueError(f"section {i} : un prérequis doit désigner une section antérieure")
        return self

    @property
    def total_h(self) -> float:
        return sum(c.duree_h for c in self.competences)

    @property
    def nb_seances(self) -> int:
        return int(-(-self.total_h // DUREE_SEANCE_H))

    @property
    def nb_semaines(self) -> int:
        return -(-self.nb_seances // SEANCES_PAR_SEMAINE)

    def seances(self) -> list[tuple[int, int]]:
        """Première et dernière séance de chaque section, dans l'ordre : une
        séance peut finir une compétence et commencer la suivante."""
        bornes, debut = [], 0.0
        for c in self.competences:
            fin = debut + c.duree_h
            bornes.append((int(debut // DUREE_SEANCE_H) + 1, int(-(-fin // DUREE_SEANCE_H))))
            debut = fin
        return bornes


# Génération du plan : le squelette (quelles compétences, dans quel ordre,
# combien d'heures, quelles questions) est déterministe — diagnostic contraint,
# référentiel, formule de coût. Le modèle ne rédige que le contenu de chaque
# section ; il ne choisit ni les compétences ni les durées.

class QuestionPlan(BaseModel):
    """Une question de la copie, telle que la correction l'a relevée."""
    code: str                     # "N1", "P4.1"
    intitule: str = ""            # libellé de la question dans le barème
    reponse_eleve: str = ""       # "—" si rien n'est écrit
    reponse_attendue: str = ""
    reussie: bool = False
    commentaire: str = ""         # commentaire de la correction
    citation: str = ""            # ce que le diagnostic a lu sur la copie


class TypeErreurPlan(BaseModel):
    code: str                     # "CPT", "PRC"…
    libelle: str
    definition: str = ""


class SectionPlanDemande(BaseModel):
    """Squelette d'une section : tout ce que le modèle ne doit pas décider."""
    ordre: int
    code_competence: str
    libelle_competence: str
    description_competence: str = ""
    niveau_intro: str = ""
    types_erreur: list[TypeErreurPlan] = Field(default_factory=list)
    questions: list[QuestionPlan] = Field(min_length=1)
    #: « ce que l'élève a probablement écrit → ce que ça révèle » (référentiel).
    signatures: list[str] = Field(default_factory=list)
    duree_h: float = Field(gt=0)
    prerequis: list[int] = Field(default_factory=list)
    #: Libellés des sections prérequises, pour que la rédaction s'y réfère.
    libelles_prerequis: list[str] = Field(default_factory=list)


class DemandePlan(BaseModel):
    copy_id: str
    eleve_nom: str
    prenom: str
    classe: str                   # "1ère D"
    test_libelle: str             # "test diagnostique d'entrée en 1ère D"
    date: str
    sections: list[SectionPlanDemande]
    questions_reussies: list[QuestionPlan] = Field(default_factory=list)


#: Les cinq exercices d'une section, un par emplacement nommé : l'outil de
#: rédaction les demande ainsi, pour qu'aucun ne puisse manquer ni changer de
#: niveau (le mode strict garantit la présence de chaque clé).
EMPLACEMENTS_EXERCICES: dict[str, int] = {
    "niveau_1_a": 1, "niveau_1_b": 1, "niveau_2_a": 2, "niveau_2_b": 2, "niveau_3": 3,
}


class ContenuSection(BaseModel):
    """Ce que le modèle rédige pour une section — rien d'autre.

    Une section acceptée est complète : aucun texte obligatoire vide (une
    cellule blanche dans le cahier d'un élève est un trou, pas un détail),
    cinq exercices de niveaux 1, 1, 2, 2, 3. Les messages d'erreur sont
    rendus au modèle tels quels : ils disent quoi corriger."""
    titre: str
    titre_tableau: str | None = None
    titre_court: str
    ecrits: list[LigneEcrit] = Field(min_length=1)
    ce_qui_ne_va_pas: str
    causes: list[str] = Field(min_length=1)
    a_retenir: list[str] = Field(min_length=1)
    methode_titre: str = "Méthode"
    methode: list[str] = Field(default_factory=list)
    consigne_exercices: str | None = None
    exercices: list[ExercicePlan] = Field(min_length=5, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def _exercices_par_emplacement(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("exercices"), dict):
            emplacements = data["exercices"]
            manquants = [nom for nom in EMPLACEMENTS_EXERCICES if not isinstance(emplacements.get(nom), dict)]
            if manquants:
                raise ValueError(f"exercices : emplacement(s) manquant(s) : {', '.join(manquants)}")
            data = {**data, "exercices": [
                {**emplacements[nom], "niveau": niveau} for nom, niveau in EMPLACEMENTS_EXERCICES.items()
            ]}
        return data

    @model_validator(mode="after")
    def _complete(self) -> "ContenuSection":
        vides: list[str] = []

        def verifier(champ: str, valeur: str | None) -> None:
            if not (valeur or "").strip():
                vides.append(champ)

        for champ in ("titre", "titre_court", "ce_qui_ne_va_pas", "methode_titre"):
            verifier(champ, getattr(self, champ))
        for i, ligne in enumerate(self.ecrits, start=1):
            verifier(f"ecrits[{i}].question", ligne.question)
            verifier(f"ecrits[{i}].reponse_attendue", ligne.reponse_attendue)
            if not ligne.reussie:
                verifier(f"ecrits[{i}].reponse_eleve", ligne.reponse_eleve)
        for champ in ("causes", "a_retenir", "methode"):
            for i, texte in enumerate(getattr(self, champ), start=1):
                verifier(f"{champ}[{i}]", texte)
        noms = list(EMPLACEMENTS_EXERCICES)
        for nom, exercice in zip(noms, self.exercices):
            verifier(f"exercices.{nom}.enonce", exercice.enonce)
            verifier(f"exercices.{nom}.reponse", exercice.reponse)
        if vides:
            raise ValueError(f"texte vide : {', '.join(vides)}")
        if [e.niveau for e in self.exercices] != list(EMPLACEMENTS_EXERCICES.values()):
            raise ValueError("exercices : niveaux attendus 1, 1, 2, 2, 3 dans cet ordre")
        return self


class ContenuAcquis(BaseModel):
    acquis: list[str] = Field(default_factory=list)


# ── Sujet de confirmation (T1, module 5) ────────────────────────────────────────
# À ne pas confondre avec `RemediationSubject` : T1 ne cherche pas à faire
# progresser l'élève, il départage une hypothèse de lacune (`suivi.Probleme`,
# état `hypothese`) entre confirmée et écartée. Voir docs/cycle_de_suivi.md §3.

class ConfirmationHypothesis(BaseModel):
    """Une hypothèse de lacune (compétence × type d'erreur) telle qu'écrite en
    base par le module 4 — l'entrée du module 5, pas sa propre détection."""

    competence_label: str
    type_erreur_label: str
    justification: str
    is_att: bool = False  # ATT ne peut être que confirmé « écarté » — jamais remédié
    # Ajoutés pour Arbitrage C (D-CEO-41) : sans eux, le prompt ne sait ni à
    # quel niveau calibrer la question, ni sur quelle leçon de `remediation/`
    # s'appuyer pour un exemple de la bonne difficulté. `competence_code` et
    # `niveau` viennent directement de `Probleme.competence` côté appelant
    # (correction_web/taches.py) — aucune requête supplémentaire.
    competence_code: str | None = None
    niveau: str | None = None
    reference_pedagogique: str | None = None
    # Énoncé de la (des) question(s) T0 qui ont fait naître l'hypothèse. Le
    # libellé de compétence est souvent bien plus large que l'erreur observée
    # (« Polygones et sections de solides » pour un volume de pyramide raté) :
    # sans lui, T1 testait une autre notion (recette du 2026-10-17).
    question_t0: str | None = None


class ConfirmationRequest(BaseModel):
    copy_id: str
    hypotheses: list[ConfirmationHypothesis]


class ConfirmationSubject(BaseModel):
    """Sujet T1 : deux questions par hypothèse (`exercises`, réutilisant la
    forme d'`Exercise` pour le rendu PDF), construites pour départager une cause
    conceptuelle d'une cause procédurale — jamais pour enseigner."""

    copy_id: str
    exercises: list[Exercise]


# ── Sujet de vérification / rétention (T3, T4, T5) ──────────────────────────
# À ne pas confondre avec la confirmation (T1) : la cause du problème est déjà
# établie (`suivi.Probleme` en `en_remediation` pour T3, en `resolu` pour T4/T5).
# Il ne s'agit plus de départager deux hypothèses mais de vérifier si la
# maîtrise est là (T3) ou si elle tient dans le temps (T4/T5). Voir
# docs/cycle_de_suivi.md §3 et `suivi/generation.py`.

class VerificationItem(BaseModel):
    """Un problème à vérifier — confirmé et en remédiation (T3), ou déjà
    résolu et à recontrôler (T4/T5)."""

    competence_label: str
    type_erreur_label: str
    contexte: str  # ce qui avait été relevé (justification du problème)
    # Même ajout que `ConfirmationHypothesis`, même raison (D-CEO-41).
    competence_code: str | None = None
    niveau: str | None = None
    reference_pedagogique: str | None = None


class VerificationRequest(BaseModel):
    copy_id: str
    type_evaluation: str  # "T3", "T4" ou "T5" — choisit le prompt et le titre du PDF
    items: list[VerificationItem]


class VerificationSubject(BaseModel):
    """Sujet T3 (vérification après remédiation) ou T4/T5 (contrôle de
    rétention) : une à deux questions par problème visé, réutilisant `Exercise`
    pour le rendu PDF — même moteur que la confirmation et la remédiation."""

    copy_id: str
    type_evaluation: str
    exercises: list[Exercise]


# ── Ingestion ────────────────────────────────────────────────────────────────

class IngestionResult(BaseModel):
    copy_id: str
    total_pages: int
    pages: list[Path]  # Paths to extracted images
    output_dir: Path   # Directory containing the pages


# ── Claude API responses ─────────────────────────────────────────────────────

class ClaudeResponse(BaseModel):
    """Generic wrapper for Claude API responses."""
    success: bool
    data: Any  # Parsed Pydantic model (TranscriptionResult, CopyGrade, etc.)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str
    error: str | None = None
