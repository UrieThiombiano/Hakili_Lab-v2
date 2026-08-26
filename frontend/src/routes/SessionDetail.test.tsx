import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ToastProvider } from "@/hooks/useToast"
import type { SessionDetailReponse } from "@/types/api"

// `AppShell` tire `useAuth` (Sidebar/Topbar) — hors sujet ici : SessionDetail
// est ce qu'on teste, pas la coquille applicative.
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const { sessionsApiMock, elevesApiMock } = vi.hoisted(() => ({
  sessionsApiMock: {
    detail: vi.fn(),
    trancher: vi.fn(),
    relancer: vi.fn(),
    inscrire: vi.fn(),
    planUrl: () => "#",
    planProvisoireUrl: () => "#",
    rapportDiagnostiqueUrl: () => "#",
    ficheTravailUrl: () => "#",
    sujetUrl: () => "#",
  },
  elevesApiMock: {
    documentUrl: () => "#",
  },
}))
vi.mock("@/lib/api", () => ({ sessionsApi: sessionsApiMock, elevesApi: elevesApiMock }))

import SessionDetail from "./SessionDetail"

function reponseBase(overrides: Partial<SessionDetailReponse> = {}): SessionDetailReponse {
  return {
    id: 1,
    etat: "diagnostic",
    palier: "",
    date_debut: "2026-01-01",
    date_inscription: null,
    jeton: "jeton-session",
    jeton_eleve: "jeton-eleve",
    eleve: { nom: "Sanou", prenom: "Feryel" },
    plan: { etapes: [], total_heures: "0", palier: "", nb_problemes: 0, repose_sur_estimation: false },
    plan_provisoire: { etapes: [], total_heures: "0", palier: "", nb_problemes: 0, repose_sur_estimation: false },
    cout_total_hypothese: "2.00",
    sujet_t1_disponible: false,
    sujet_t1_jeton_copie: null,
    peut_inscrire: false,
    palier_c: false,
    hypotheses: [],
    ecartes: [],
    en_remediation: [],
    resolus: [],
    non_resolus: [],
    regresses: [],
    ...overrides,
  }
}

function rendre() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/sessions/jeton-session"]}>
          <Routes>
            <Route path="/sessions/:jeton" element={<SessionDetail />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("SessionDetail", () => {
  it("confirme une hypothèse via l'API avec la bonne décision", async () => {
    sessionsApiMock.detail.mockResolvedValue(
      reponseBase({
        hypotheses: [{ id: 42, competence_id: "L.IDR", competence_libelle: "Identifier", type_erreur_id: "CPT", etat: "hypothese", cout_estime: "2.00", justification: "", interpretation: "" }],
        plan_provisoire: {
          etapes: [{ rang: 1, probleme_id: 42, cout: "2.00", competence_id: "L.IDR", competence_libelle: "Identifier", type_erreur_id: "CPT", prerequis_bloquants: [], signatures: [] }],
          total_heures: "2.00", palier: "A", nb_problemes: 1, repose_sur_estimation: false,
        },
      }),
    )
    sessionsApiMock.trancher.mockResolvedValue({ compte: { confirme: 1 }, erreurs: [] })

    rendre()
    const bouton = await screen.findByRole("button", { name: "Confirmer" })
    await userEvent.click(bouton)

    await waitFor(() => {
      expect(sessionsApiMock.trancher).toHaveBeenCalledWith("jeton-session", "T1", { 42: "confirme" })
    })
  })

  it("une hypothèse ATT ne propose que \"Écarter\", jamais \"Confirmer\"", async () => {
    sessionsApiMock.detail.mockResolvedValue(
      reponseBase({
        hypotheses: [{ id: 7, competence_id: "N.CALC", competence_libelle: "Calculer", type_erreur_id: "ATT", etat: "hypothese", cout_estime: "0.00", justification: "", interpretation: "" }],
        plan_provisoire: {
          etapes: [{ rang: 1, probleme_id: 7, cout: "0.00", competence_id: "N.CALC", competence_libelle: "Calculer", type_erreur_id: "ATT", prerequis_bloquants: [], signatures: [] }],
          total_heures: "0.00", palier: "A", nb_problemes: 1, repose_sur_estimation: false,
        },
      }),
    )

    rendre()
    await screen.findByText(/ATT/)
    expect(screen.queryByRole("button", { name: "Confirmer" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Écarter" })).toBeInTheDocument()
  })

  it("relance un problème non résolu en remédiation", async () => {
    sessionsApiMock.detail.mockResolvedValue(
      reponseBase({
        non_resolus: [{ id: 9, competence_id: "G.PARA", competence_libelle: "Paramétrer", type_erreur_id: "PRC", etat: "non_resolu", cout_estime: "1.00", justification: "", interpretation: "" }],
      }),
    )
    sessionsApiMock.relancer.mockResolvedValue({ ok: true })

    rendre()
    const bouton = await screen.findByRole("button", { name: "Relancer en remédiation" })
    await userEvent.click(bouton)

    await waitFor(() => {
      expect(sessionsApiMock.relancer).toHaveBeenCalledWith("jeton-session", 9, "")
    })
  })

  it("affiche le bouton d'inscription seulement quand peut_inscrire est vrai", async () => {
    sessionsApiMock.detail.mockResolvedValue(reponseBase({ peut_inscrire: false }))
    rendre()
    await screen.findByText("Voir le profil élève")
    expect(screen.queryByRole("button", { name: "Inscrire au programme" })).not.toBeInTheDocument()
  })

  it("inscrit au programme et affiche le résultat", async () => {
    sessionsApiMock.detail.mockResolvedValue(reponseBase({ peut_inscrire: true, palier_c: false }))
    sessionsApiMock.inscrire.mockResolvedValue({ nb_problemes_en_remediation: 2, cout_total_confirme: "4.00" })

    rendre()
    const bouton = await screen.findByRole("button", { name: "Inscrire au programme" })
    await userEvent.click(bouton)

    await waitFor(() => {
      expect(sessionsApiMock.inscrire).toHaveBeenCalledWith("jeton-session", false, "")
    })
  })
})
