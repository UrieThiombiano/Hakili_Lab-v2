/**
 * Types miroir de `backend/app/schemas.py`. Les champs `Decimal` (coûts, en
 * heures) sont sérialisés en **chaîne** par Pydantic (`"4.00"`, pas `4.0`) —
 * voir `lib/format.ts::heures()` pour la conversion à l'affichage plutôt que
 * de parser à chaque endroit qui les consomme.
 */

export type Tendance = "progresse" | "stagne" | "regresse" | "insuffisant"
export type EtatProbleme =
  | "hypothese"
  | "confirme"
  | "ecarte"
  | "en_remediation"
  | "resolu"
  | "non_resolu"
  | "regresse"
  | "clos"
export type EtatSession =
  | "diagnostic"
  | "attente_inscription"
  | "remediation"
  | "close"
  | "sans_suite"
  | "hors_dispositif"
  | "abandonnee"
export type Palier = "" | "A" | "B" | "C"
export type TypeEvaluation = "T0" | "T1" | "T3" | "T4" | "T5"
export type EtatCorrection =
  | "creee"
  | "transcription"
  | "relecture"
  | "correction"
  | "validation"
  | "diagnostic"
  | "terminee"
  | "echec"

// ── Auth ─────────────────────────────────────────────────────────────────

export interface Personne {
  nom: string
  prenom: string
  role: string
  roles: string[]
  [key: string]: unknown
}

export interface CasquettePossible {
  valeur: string
  libelle: string
}

export interface MeReponse {
  acces_libre: boolean
  personne: Personne | null
  casquette?: string
  casquettes_possibles?: CasquettePossible[]
}

export interface PersonneListe {
  cle: string
  libelle: string
}

// ── Élèves ───────────────────────────────────────────────────────────────

export interface EleveLigne {
  eleve: Record<string, unknown>
  jeton: string
  tendance: Tendance
  nb_copies: number
  derniere_note: number | null
}

export interface AccueilReponse {
  lignes: EleveLigne[]
  en_baisse: number
  lecture_impossible: boolean
}

export interface DocumentResume {
  type: string
  libelle: string
}

export interface CopieEntree {
  copy_id: string
  jeton: string
  classe: string
  date_soumission: string
  notes_finales: number | null
  documents: DocumentResume[]
}

export interface PointCourbe {
  date: string
  note: number
}

export interface ProblemeHypothese {
  id: number
  competence_id: string
  type_erreur_id: string
  justification: string
}

export interface SessionResume {
  id: number
  jeton: string
  etat: EtatSession
  hypotheses: ProblemeHypothese[]
}

export interface EleveDetailReponse {
  eleve: { nom?: string; prenom?: string; [key: string]: unknown }
  entrees: CopieEntree[]
  tendance: Tendance
  nb_copies: number
  derniere_note: number | null
  courbe: PointCourbe[]
  parcours: SessionResume[]
  jeton_nouvelle_analyse: string
}

// ── Sessions / parcours ──────────────────────────────────────────────────

export interface ProblemeSchema {
  id: number
  competence_id: string
  competence_libelle: string
  type_erreur_id: string
  etat: EtatProbleme
  cout_estime: string
  justification: string
  interpretation: string
}

export interface PrerequisBloquant {
  code: string
  libelle: string
}

export interface EtapePlanSchema {
  rang: number
  probleme_id: number
  cout: string
  competence_id: string
  competence_libelle: string
  type_erreur_id: string
  prerequis_bloquants: PrerequisBloquant[]
  signatures: { production_eleve: string; interpretation: string }[]
}

export interface PlanSchema {
  etapes: EtapePlanSchema[]
  total_heures: string
  palier: Palier
  nb_problemes: number
  repose_sur_estimation: boolean
}

export interface SessionDetailReponse {
  id: number
  etat: EtatSession
  palier: Palier
  date_debut: string
  date_inscription: string | null
  jeton: string
  jeton_eleve: string
  eleve: { nom?: string; prenom?: string; [key: string]: unknown }
  plan: PlanSchema
  /** Estimation avant T1, à partir des hypothèses non confirmées — jamais contractuelle. */
  plan_provisoire: PlanSchema
  cout_total_hypothese: string
  sujet_t1_disponible: boolean
  /** Jeton de la copie T0 portant le document `sujet_confirmation` — `null` si `sujet_t1_disponible` est faux. */
  sujet_t1_jeton_copie: string | null
  peut_inscrire: boolean
  palier_c: boolean
  hypotheses: ProblemeSchema[]
  ecartes: ProblemeSchema[]
  en_remediation: ProblemeSchema[]
  resolus: ProblemeSchema[]
  non_resolus: ProblemeSchema[]
  regresses: ProblemeSchema[]
}

export interface TrancherReponse {
  compte: Record<string, number>
  erreurs: string[]
}

// ── Corrections ──────────────────────────────────────────────────────────

export interface TestDisponible {
  id: string
  label: string
  questions: number
}

export interface CorrectionCreeReponse {
  jeton: string
}

export interface PageTranscription {
  page_number: number
  content: string
  formulas: string[]
  diagrams: string[]
  uncertainties: string[]
  confidence: number
}

export interface QuestionGrade {
  rubric_item_id: string
  score: number
  confidence: number
  comment: string
  observed_answer: string
  correct_answer: string
  requires_review: boolean
  teacher_decision: "pending" | "accepted" | "refused"
  teacher_score: number | null
}

export interface RubricItem {
  id: string
  label: string
  max_score: number
  parent_id: string | null
}

export interface CompetencyGap {
  chunk_id: string
  classe: string
  domaine: string
  chapitre: string
  lecon: string
  description: string
  savoir_faire: string[]
  erreurs_frequentes: string[]
}

export interface RootCauseError {
  visible_error: string
  hidden_cause: string
  nature: string
  pedagogical_trigger: string
  linked_questions: string[]
}

/** Diagnostic « legacy » en texte libre (`src/models/domain.py::DiagnosticResult`)
 * — distinct du diagnostic contraint v2 (module 4, compétence × type
 * d'erreur), qui n'est pas encore exposé par l'API (Phase 1 suite). */
export interface DiagnosticResult {
  copy_id: string
  academic_profile: string
  strengths: string[]
  weaknesses: string[]
  root_causes: RootCauseError[]
  competency_gaps: CompetencyGap[]
}

export interface ResultatPipeline {
  copy_id: string
  student_name: string
  transcription: { copy_id: string; global_quality: string; pages: PageTranscription[] } | null
  grade: { copy_id: string; total_score: number; total_possible: number; questions: QuestionGrade[]; final_score: number | null; final_score_on_20: number | null } | null
  diagnostic: DiagnosticResult | null
  rubric: { subject: string; total_points: number; items: RubricItem[] } | null
  pdf_path: string | null
  remediation_pdf_path: string | null
  /** Motif d'absence du plan de remédiation alors qu'il est dû — vide sinon. */
  plan_erreur?: string
  /** Motif de l'échec de la dernière génération du sujet T1, vide si elle a abouti. */
  t1_erreur?: string
  errors: string[]
}

export interface CorrectionStatut {
  etat: EtatCorrection
  etape: string
  progression: number
  en_cours: boolean
  en_attente: boolean
  terminee: boolean
  echouee: boolean
  erreurs: string[]
  resultat: ResultatPipeline | null
  /** Types de documents réellement persistés pour cette copie ("rapport", "sujet_confirmation"...). */
  documents: string[]
  /** Jeton du parcours (session) de l'élève, si un existe déjà. */
  jeton_session: string | null
  /** Note /20 sous laquelle l'élève passe directement en remédiation, sans T1 (D-CEO-46) — null si la règle ne s'applique pas. */
  seuil_sans_t1: number | null
  /** Plan de remédiation manquant mais reprenable sans refaire l'analyse (`POST /corrections/{jeton}/plan`). */
  plan_a_reprendre: boolean
  /** Analyse conservée en base (« Sauvegarder ») — sinon elle n'existe que dans l'espace de travail. */
  sauvegardee: boolean
  /** Bouton « Générer le T1 » proposé (`POST /corrections/{jeton}/t1`). */
  t1_a_generer: boolean
}

export interface CorrectionResume {
  jeton: string
  copy_id: string
  eleve_nom: string
  eleve_prenom: string
  etat: EtatCorrection
  etape: string
  progression: number
  cree_le: string
}

export interface LotReponse {
  lancees: number
  ecartees: string[]
}

export interface SujetDisponible {
  id: string
  label: string
  niveaux: string
  questions: number
  imprimable: boolean
  corrige_disponible: boolean
}

export interface ApiErreur {
  detail: string | { code: string; message: string }
}

// ── Admin ────────────────────────────────────────────────────────────────

export type EtatAcces = "regresse" | "stagne" | "progresse"

export interface PersonnelLigne {
  personne: Record<string, unknown>
  roles: string
  centres: string
  etat: EtatAcces
  libelle: string
}

export interface PersonnelReponse {
  lignes: PersonnelLigne[]
  probleme: number
  lecture_impossible: boolean
}

export interface StatistiquesReponse {
  nb_eleves: number | null
  nb_centres: number
  nb_copies: number | null
  centres: string[]
  centres_suspects: string[]
}

// ── Préférences de modèles IA ────────────────────────────────────────────

export interface PreferenceTache {
  fournisseur: string
  variante_claude: string
}

export interface FournisseurOption {
  cle: string
  libelle: string
  cle_presente: boolean
}

export interface TacheOption {
  cle: string
  libelle: string
  fournisseurs: FournisseurOption[]
}

export interface PreferencesModelesReponse {
  taches: TacheOption[]
  variantes_claude: string[]
  preferences: Record<string, PreferenceTache>
  modifiable: boolean
}

export interface PreferencesModelesRequete {
  preferences: Record<string, PreferenceTache>
}
