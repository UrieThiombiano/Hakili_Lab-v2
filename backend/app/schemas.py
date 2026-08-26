"""Schémas Pydantic (requêtes/réponses) des routeurs `app/routers/`.

Volontairement légers : le style visuel (couleurs, libellés de pastille) est
laissé au frontend React — l'API rend des valeurs de taxonomie stables
(`tendance: "progresse"|"stagne"|"regresse"|"insuffisant"`, `etat`, `palier`),
pas du HTML ni des libellés déjà mis en forme, contrairement aux gabarits
Django qu'elle remplace.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class EleveLigne(BaseModel):
    eleve: dict
    jeton: str
    tendance: str
    nb_copies: int
    derniere_note: float | None


class AccueilReponse(BaseModel):
    lignes: list[EleveLigne]
    en_baisse: int
    lecture_impossible: bool


class DocumentResume(BaseModel):
    type: str
    libelle: str


class CopieEntree(BaseModel):
    copy_id: str
    jeton: str
    classe: str
    date_soumission: date
    notes_finales: float | None
    documents: list[DocumentResume]


class PointCourbe(BaseModel):
    date: date
    note: float


class ProblemeHypothese(BaseModel):
    id: int
    competence_id: str
    type_erreur_id: str
    justification: str


class SessionResume(BaseModel):
    id: int
    jeton: str
    etat: str
    hypotheses: list[ProblemeHypothese]


class EleveDetailReponse(BaseModel):
    eleve: dict
    entrees: list[CopieEntree]
    tendance: str
    nb_copies: int
    derniere_note: float | None
    courbe: list[PointCourbe]
    parcours: list[SessionResume]
    jeton_nouvelle_analyse: str


class ProblemeSchema(BaseModel):
    id: int
    competence_id: str
    competence_libelle: str
    type_erreur_id: str
    etat: str
    cout_estime: Decimal
    justification: str
    interpretation: str


class PrerequisBloquant(BaseModel):
    code: str
    libelle: str


class EtapePlanSchema(BaseModel):
    rang: int
    probleme_id: int
    cout: Decimal
    competence_id: str
    competence_libelle: str
    type_erreur_id: str
    prerequis_bloquants: list[PrerequisBloquant]
    signatures: list[dict]


class PlanSchema(BaseModel):
    etapes: list[EtapePlanSchema]
    total_heures: Decimal
    palier: str
    nb_problemes: int
    repose_sur_estimation: bool


class ExerciceGradueSchema(BaseModel):
    numero: int
    etoiles: int
    enonce: str
    correction: str


class FicheRemediationCorrection(BaseModel):
    """Corps du PATCH de correction d'une fiche de travail (module 7) — les
    seuls champs qu'un tuteur édite ; `competence`/`type_erreur`/`niveau`
    restent ceux du couple déjà catalogué, jamais réécrits par ce chemin."""

    objectif: str
    prerequis_a_verifier: list[dict] = []
    methode: dict | None = None
    retenir: list[str] = []
    exemple_resolu: str | None = None
    erreurs_frequentes: list[dict] = []
    declic: str | None = None
    deroule_minutes: dict[str, int] = {}
    exercices: list[ExerciceGradueSchema] = []
    critere_reussite: str


class SessionDetailReponse(BaseModel):
    id: int
    etat: str
    palier: str
    date_debut: date
    date_inscription: date | None
    jeton: str
    jeton_eleve: str
    eleve: dict
    plan: PlanSchema
    #: Estimation avant T1, à partir des hypothèses non confirmées — jamais
    #: contractuelle, voir `plan.py::construire(etats=("hypothese",))`.
    plan_provisoire: PlanSchema
    cout_total_hypothese: Decimal
    sujet_t1_disponible: bool
    #: Jeton de la copie T0 qui porte le document `sujet_confirmation` — sert
    #: à construire le lien `elevesApi.documentUrl(jeton, "sujet_confirmation")`.
    #: `None` si `sujet_t1_disponible` est faux.
    sujet_t1_jeton_copie: str | None
    peut_inscrire: bool
    palier_c: bool
    hypotheses: list[ProblemeSchema]
    ecartes: list[ProblemeSchema]
    en_remediation: list[ProblemeSchema]
    resolus: list[ProblemeSchema]
    non_resolus: list[ProblemeSchema]
    regresses: list[ProblemeSchema]


class TrancherRequete(BaseModel):
    """`decisions` associe l'id du problème (en chaîne, comme un champ de
    formulaire `decision_<pk>`) à la décision saisie."""

    decisions: dict[int, str]


class TrancherReponse(BaseModel):
    compte: dict[str, int]
    erreurs: list[str]


class InscrireRequete(BaseModel):
    forcer: bool = False
    motif: str = ""


class RelancerRequete(BaseModel):
    motif: str = ""


# ── Corrections ──────────────────────────────────────────────────────────────


class TestDisponible(BaseModel):
    id: str
    label: str
    questions: int


class CorrectionCreeReponse(BaseModel):
    jeton: str


class CorrectionStatut(BaseModel):
    """Miroir de `correction_web/views.py::suivre` — un seul endpoint, le
    frontend branche l'écran sur `etat` comme le faisait le gabarit Django.
    `resultat` est le dict produit par `src/pipeline/serialisation.py::
    serialiser()` (réutilisé tel quel, framework-independent) : transcription,
    grade, diagnostic, rubric... tout ce qu'un écran peut vouloir en tirer,
    plutôt qu'une pré-mise en forme décidée côté API."""

    etat: str
    etape: str
    progression: int
    en_cours: bool
    en_attente: bool
    terminee: bool
    echouee: bool
    erreurs: list[str]
    resultat: dict | None
    #: Types de documents déjà persistés pour cette copie (`rapport`,
    #: `sujet_confirmation`...) — remplace l'ancien lien "Plan de
    #: remédiation" qui pointait presque toujours vers un document jamais
    #: généré (404) : le frontend n'affiche plus que ce qui existe vraiment.
    documents: list[str] = []
    #: Jeton du parcours (session) de l'élève, si un existe déjà — permet
    #: d'afficher le plan provisoire et le rapport diagnostique sans
    #: attendre que l'enseignant aille chercher l'écran « Parcours ».
    jeton_session: str | None = None


class TranscriptionRequete(BaseModel):
    """Pages corrigées par l'enseignant, `{numero_page: contenu}`."""

    pages: dict[int, str]


class DecisionQuestion(BaseModel):
    decision: str = "accepted"  # "accepted" | "refused"
    note: str | None = None


class NotesRequete(BaseModel):
    """Décisions par question, `{rubric_item_id: décision}`."""

    decisions: dict[str, DecisionQuestion]


class CorrectionResume(BaseModel):
    jeton: str
    copy_id: str
    eleve_nom: str
    eleve_prenom: str
    etat: str
    etape: str
    progression: int
    cree_le: datetime


class LotReponse(BaseModel):
    lancees: int
    ecartees: list[str]


# ── Admin ────────────────────────────────────────────────────────────────────


class PersonnelLigne(BaseModel):
    personne: dict
    roles: str
    centres: str
    etat: str
    libelle: str


class PersonnelReponse(BaseModel):
    lignes: list[PersonnelLigne]
    probleme: int
    lecture_impossible: bool


class StatistiquesReponse(BaseModel):
    nb_eleves: int | None
    nb_centres: int
    nb_copies: int | None
    centres: list[str]
    centres_suspects: list[str]
