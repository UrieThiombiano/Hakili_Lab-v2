import type {
  AccueilReponse,
  CorrectionCreeReponse,
  CorrectionResume,
  CorrectionStatut,
  EleveDetailReponse,
  LotReponse,
  MeReponse,
  PersonneListe,
  PersonnelReponse,
  SessionDetailReponse,
  StatistiquesReponse,
  SujetDisponible,
  TestDisponible,
  TrancherReponse,
} from "@/types/api"

/** Le proxy Vite (`vite.config.ts`) redirige `/api/*` vers FastAPI en dev ;
 * en production, React et FastAPI sont servis derrière le même hôte (voir
 * le plan de migration, Phase 4) — un chemin relatif convient aux deux. */
const BASE = "/api"

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    const message = typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `Erreur ${status}`
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** Lit le cookie CSRF (double-submit, `app/auth/csrf.py`) — non httpOnly,
 * délibérément lisible ici pour être recopié en en-tête. */
function jetonCsrf(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : null
}

const METHODES_MUTANTES = new Set(["POST", "PUT", "PATCH", "DELETE"])

interface RequeteOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>
}

async function requete<T>(chemin: string, options: RequeteOptions = {}): Promise<T> {
  const { headers, ...reste } = options
  // FormData fixe elle-même son Content-Type (avec la boundary) — lui en
  // imposer un casserait l'envoi multipart.
  const enTetes: Record<string, string> = reste.body instanceof FormData ? { ...headers } : { "Content-Type": "application/json", ...headers }
  const methode = (reste.method ?? "GET").toUpperCase()
  if (METHODES_MUTANTES.has(methode)) {
    const jeton = jetonCsrf()
    if (jeton) enTetes["X-CSRF-Token"] = jeton
  }
  const reponse = await fetch(`${BASE}${chemin}`, { credentials: "include", headers: enTetes, ...reste })
  if (!reponse.ok) {
    let detail: unknown
    try {
      detail = (await reponse.json()).detail
    } catch {
      detail = reponse.statusText
    }
    throw new ApiError(reponse.status, detail)
  }
  if (reponse.status === 204) return undefined as T
  return reponse.json() as Promise<T>
}

function get<T>(chemin: string): Promise<T> {
  return requete<T>(chemin)
}
function postJson<T>(chemin: string, corps: unknown): Promise<T> {
  return requete<T>(chemin, { method: "POST", body: JSON.stringify(corps) })
}
function postForm<T>(chemin: string, corps: FormData): Promise<T> {
  return requete<T>(chemin, { method: "POST", body: corps })
}
function del<T>(chemin: string): Promise<T> {
  return requete<T>(chemin, { method: "DELETE" })
}

// ── Auth ─────────────────────────────────────────────────────────────────

export const authApi = {
  personnel: () => get<PersonneListe[]>("/auth/personnel"),
  login: (cle: string, pin: string) => postJson<{ nom: string; prenom: string }>("/auth/login", { cle, pin }),
  logout: () => postJson<{ ok: boolean }>("/auth/logout", {}),
  me: () => get<MeReponse>("/auth/me"),
  casquette: (casquette: string) => postJson<{ casquette: string }>("/auth/casquette", { casquette }),
}

// ── Élèves ───────────────────────────────────────────────────────────────

export const elevesApi = {
  accueil: (q = "") => get<AccueilReponse>(`/eleves${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  detail: (jetonEleve: string) => get<EleveDetailReponse>(`/eleves/${jetonEleve}`),
  documentUrl: (jetonCopie: string, docType: string, telecharger = false) =>
    `${BASE}/eleves/documents/${jetonCopie}/${docType}${telecharger ? "?telecharger=true" : ""}`,
  supprimerCopie: (jetonCopie: string) => del<{ ok: boolean }>(`/eleves/copies/${jetonCopie}`),
}

// ── Sessions / parcours ──────────────────────────────────────────────────

export const sessionsApi = {
  detail: (jetonSession: string) => get<SessionDetailReponse>(`/sessions/${jetonSession}`),
  trancher: (jetonSession: string, typeEvaluation: string, decisions: Record<number, string>) =>
    postJson<TrancherReponse>(`/sessions/${jetonSession}/trancher/${typeEvaluation}`, { decisions }),
  relancer: (jetonSession: string, problemeId: number, motif: string) =>
    postJson<{ ok: boolean }>(`/sessions/${jetonSession}/problemes/${problemeId}/relancer`, { motif }),
  inscrire: (jetonSession: string, forcer: boolean, motif: string) =>
    postJson<{ nb_problemes_en_remediation: number; cout_total_confirme: string }>(`/sessions/${jetonSession}/inscrire`, { forcer, motif }),
  planUrl: (jetonSession: string, telecharger = false) => `${BASE}/sessions/${jetonSession}/plan${telecharger ? "?telecharger=true" : ""}`,
  ficheTravailUrl: (jetonSession: string, problemeId: number, telecharger = false) =>
    `${BASE}/sessions/${jetonSession}/problemes/${problemeId}/fiche${telecharger ? "?telecharger=true" : ""}`,
  sujetUrl: (jetonSession: string, typeEvaluation: string, telecharger = false) =>
    `${BASE}/sessions/${jetonSession}/sujets/${typeEvaluation}${telecharger ? "?telecharger=true" : ""}`,
}

// ── Corrections ──────────────────────────────────────────────────────────

export const correctionsApi = {
  tests: () => get<TestDisponible[]>("/corrections/tests"),
  sujets: () => get<SujetDisponible[]>("/corrections/sujets"),
  sujetPdfUrl: (baremeId: string, telecharger = false) => `${BASE}/corrections/sujets/${baremeId}${telecharger ? "?telecharger=true" : ""}`,
  corrigePdfUrl: (baremeId: string, telecharger = false) => `${BASE}/corrections/sujets/${baremeId}/corrige${telecharger ? "?telecharger=true" : ""}`,
  liste: () => get<CorrectionResume[]>("/corrections"),
  nouvelle: (corps: FormData) => postForm<CorrectionCreeReponse>("/corrections", corps),
  confirmation: (jetonSession: string, corps: FormData) => postForm<CorrectionCreeReponse>(`/corrections/confirmation/${jetonSession}`, corps),
  verification: (jetonSession: string, typeEvaluation: string, corps: FormData) =>
    postForm<CorrectionCreeReponse>(`/corrections/verification/${jetonSession}/${typeEvaluation}`, corps),
  lot: (corps: FormData) => postForm<LotReponse>("/corrections/lot", corps),
  statut: (jetonCopie: string) => get<CorrectionStatut>(`/corrections/${jetonCopie}`),
  validerTranscription: (jetonCopie: string, pages: Record<number, string>) =>
    postJson<CorrectionStatut>(`/corrections/${jetonCopie}/transcription`, { pages }),
  pageImageUrl: (jetonCopie: string, page: number) => `${BASE}/corrections/${jetonCopie}/pages/${page}`,
  validerNotes: (jetonCopie: string, decisions: Record<string, { decision: string; note?: string | null }>) =>
    postJson<CorrectionStatut>(`/corrections/${jetonCopie}/notes`, { decisions }),
  supprimer: (jetonCopie: string) => del<{ ok: boolean }>(`/corrections/${jetonCopie}`),
}

// ── Admin ────────────────────────────────────────────────────────────────

export const adminApi = {
  personnel: () => get<PersonnelReponse>("/admin/personnel"),
  statistiques: () => get<StatistiquesReponse>("/admin/statistiques"),
}
