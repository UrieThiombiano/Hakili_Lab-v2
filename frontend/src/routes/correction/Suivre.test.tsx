import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ToastProvider } from "@/hooks/useToast"
import { ConfirmProvider } from "@/hooks/useConfirm"
import type { CorrectionStatut, SessionDetailReponse } from "@/types/api"

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const { correctionsApiMock, elevesApiMock, sessionsApiMock } = vi.hoisted(() => ({
  correctionsApiMock: {
    statut: vi.fn(),
    supprimer: vi.fn(),
    validerTranscription: vi.fn(),
    pageImageUrl: (_jeton: string, page: number) => `#page-${page}`,
  },
  elevesApiMock: { documentUrl: (_jeton: string, type: string) => `#doc-${type}` },
  sessionsApiMock: {
    detail: vi.fn(),
    planUrl: () => "#plan",
    planProvisoireUrl: () => "#plan-provisoire",
    rapportDiagnostiqueUrl: () => "#rapport-diagnostique",
  },
}))
vi.mock("@/lib/api", () => ({
  correctionsApi: correctionsApiMock,
  elevesApi: elevesApiMock,
  sessionsApi: sessionsApiMock,
}))

import Suivre from "./Suivre"

function resultatBase(): NonNullable<CorrectionStatut["resultat"]> {
  return {
    copy_id: "copie-1",
    student_name: "Feryel Sanou",
    transcription: null,
    grade: { copy_id: "copie-1", total_score: 0, total_possible: 20, questions: [], final_score: 0, final_score_on_20: 0 },
    diagnostic: null,
    rubric: null,
    pdf_path: null,
    remediation_pdf_path: null,
    errors: [],
  }
}

function statutBase(overrides: Partial<CorrectionStatut> = {}): CorrectionStatut {
  return {
    etat: "terminee",
    etape: "Terminée",
    progression: 100,
    en_cours: false,
    en_attente: false,
    terminee: true,
    echouee: false,
    erreurs: [],
    resultat: resultatBase(),
    documents: [],
    jeton_session: null,
    ...overrides,
  }
}

function planVide(): SessionDetailReponse["plan"] {
  return { etapes: [], total_heures: "0", palier: "", nb_problemes: 0, repose_sur_estimation: false }
}

function sessionBase(overrides: Partial<SessionDetailReponse> = {}): SessionDetailReponse {
  return {
    id: 1,
    etat: "diagnostic",
    palier: "",
    date_debut: "2026-08-26",
    date_inscription: null,
    jeton: "jeton-session",
    jeton_eleve: "jeton-eleve",
    eleve: { nom: "Sanou", prenom: "Feryel" },
    plan: planVide(),
    plan_provisoire: planVide(),
    cout_total_hypothese: "0",
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
        <ConfirmProvider>
          <MemoryRouter initialEntries={["/corrections/jeton-copie"]}>
            <Routes>
              <Route path="/corrections/:jeton" element={<Suivre />} />
            </Routes>
          </MemoryRouter>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("Suivre — Relecture", () => {
  function statutRelecture() {
    return statutBase({
      etat: "relecture",
      terminee: false,
      en_cours: false,
      resultat: {
        ...resultatBase(),
        transcription: {
          copy_id: "copie-1",
          global_quality: "medium",
          pages: [
            {
              page_number: 1,
              content: "L8 E = ⟦4x²⟧ + 9\nN7 [ILLISIBLE]",
              formulas: [],
              diagrams: [],
              uncertainties: ["N7 : ligne masquée"],
              confidence: 0.9,
            },
          ],
        },
      },
    })
  }

  it("surligne les zones incertaines entre crochets au lieu d'un textarea brut", async () => {
    correctionsApiMock.statut.mockResolvedValue(statutRelecture())

    rendre()

    const zone = await screen.findByText("[4x²]")
    expect(zone.tagName).toBe("MARK")
    expect(screen.getAllByText("[illisible]").some((el) => el.tagName === "MARK")).toBe(true)
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("double-clic sur une zone → correction en place, envoyée sans marqueur à la validation", async () => {
    const user = userEvent.setup()
    correctionsApiMock.statut.mockResolvedValue(statutRelecture())
    correctionsApiMock.validerTranscription.mockResolvedValue(statutRelecture())

    rendre()

    await user.dblClick(await screen.findByText("[4x²]"))
    const champ = screen.getByRole("textbox")
    await user.clear(champ)
    await user.type(champ, "4x²")
    await user.click(screen.getByTitle("Valider la correction"))

    await user.click(screen.getByRole("button", { name: "Valider la transcription" }))

    expect(correctionsApiMock.validerTranscription).toHaveBeenCalledWith("jeton-copie", {
      1: "L8 E = 4x² + 9\nN7 [ILLISIBLE]",
    })
  })
})

describe("Suivre — Resultats", () => {
  it("n'affiche que les documents réellement générés (plus de lien mort vers « remediation »)", async () => {
    correctionsApiMock.statut.mockResolvedValue(statutBase({ documents: ["rapport"] }))

    rendre()

    await screen.findByText("Correction terminée")
    expect(screen.getByText("Documents à télécharger")).toBeInTheDocument()
    expect(screen.getByText("Rapport de correction")).toBeInTheDocument()
    expect(screen.queryByText(/Sujet de remédiation/)).not.toBeInTheDocument()
    expect(screen.queryByText("Plan de remédiation")).not.toBeInTheDocument()
  })

  it("affiche le diagnostic structuré et le plan provisoire quand un parcours existe déjà", async () => {
    correctionsApiMock.statut.mockResolvedValue(statutBase({ jeton_session: "jeton-session" }))
    sessionsApiMock.detail.mockResolvedValue(
      sessionBase({
        plan_provisoire: {
          etapes: [
            {
              rang: 1,
              probleme_id: 42,
              cout: "1.00",
              competence_id: "D.PROP",
              competence_libelle: "Proportionnalité",
              type_erreur_id: "PRC",
              prerequis_bloquants: [],
              signatures: [],
            },
          ],
          total_heures: "1.00",
          palier: "A",
          nb_problemes: 1,
          repose_sur_estimation: false,
        },
      }),
    )

    rendre()

    await waitFor(() => expect(screen.getByText("Plan de remédiation")).toBeInTheDocument())
    expect(screen.getByText("D.PROP")).toBeInTheDocument()
    expect(screen.getByText(/Estimation provisoire/)).toBeInTheDocument()
    expect(screen.getByText("Plan de remédiation provisoire")).toBeInTheDocument()
  })

  it("propose le sujet T1 quand il est disponible", async () => {
    correctionsApiMock.statut.mockResolvedValue(statutBase({ jeton_session: "jeton-session" }))
    sessionsApiMock.detail.mockResolvedValue(
      sessionBase({ sujet_t1_disponible: true, sujet_t1_jeton_copie: "jeton-copie-t0" }),
    )

    rendre()

    await waitFor(() => expect(screen.getByText("Sujet du test de confirmation (T1)")).toBeInTheDocument())
    expect(screen.getByText("Déposer la copie T1")).toBeInTheDocument()
  })

  it("n'affiche pas le plan de remédiation sans session existante", async () => {
    correctionsApiMock.statut.mockResolvedValue(statutBase())

    rendre()

    await screen.findByText("Correction terminée")
    expect(screen.queryByText("Plan de remédiation")).not.toBeInTheDocument()
    expect(screen.queryByText("Documents à télécharger")).not.toBeInTheDocument()
  })
})
