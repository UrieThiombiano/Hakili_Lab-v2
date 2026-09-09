import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ToastProvider } from "@/hooks/useToast"
import type { PreferencesModelesReponse } from "@/types/api"

const { adminApiMock } = vi.hoisted(() => ({
  adminApiMock: {
    preferencesModeles: vi.fn(),
    majPreferencesModeles: vi.fn(),
  },
}))

vi.mock("@/lib/api", () => ({
  adminApi: adminApiMock,
  ApiError: class ApiError extends Error {},
}))

import { CarteModelesIA } from "./Parametres"

function reponse(modifiable: boolean): PreferencesModelesReponse {
  return {
    modifiable,
    variantes_claude: ["sonnet", "opus"],
    preferences: {
      transcription: { fournisseur: "gemini", variante_claude: "sonnet" },
      correction: { fournisseur: "deepseek", variante_claude: "sonnet" },
      analyse: { fournisseur: "claude", variante_claude: "opus" },
    },
    taches: [
      {
        cle: "transcription",
        libelle: "Transcription (lecture des copies)",
        fournisseurs: [
          { cle: "claude", libelle: "Claude (Anthropic)", cle_presente: true },
          { cle: "gemini", libelle: "Gemini (Google)", cle_presente: true },
          { cle: "openai", libelle: "ChatGPT (OpenAI)", cle_presente: false },
        ],
      },
      {
        cle: "correction",
        libelle: "Correction",
        fournisseurs: [
          { cle: "deepseek", libelle: "DeepSeek", cle_presente: true },
          { cle: "claude", libelle: "Claude (Anthropic)", cle_presente: true },
          { cle: "gemini", libelle: "Gemini (Google)", cle_presente: true },
        ],
      },
      {
        cle: "analyse",
        libelle: "Analyse et génération des rapports",
        fournisseurs: [
          { cle: "gemini", libelle: "Gemini (Google)", cle_presente: true },
          { cle: "claude", libelle: "Claude (Anthropic)", cle_presente: true },
        ],
      },
    ],
  }
}

function afficher() {
  return render(
    <ToastProvider>
      <CarteModelesIA />
    </ToastProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("CarteModelesIA", () => {
  it("affiche en lecture seule pour un non-admin (pas de bouton Enregistrer)", async () => {
    adminApiMock.preferencesModeles.mockResolvedValue(reponse(false))
    afficher()
    await screen.findByText("Correction")
    expect(screen.queryByRole("button", { name: /enregistrer/i })).toBeNull()
    expect(screen.getByText(/administrateur uniquement/i)).toBeInTheDocument()
  })

  it("désactive un fournisseur sans clé API", async () => {
    adminApiMock.preferencesModeles.mockResolvedValue(reponse(true))
    afficher()
    const chatgpt = (await screen.findAllByRole("button", { name: /ChatGPT/i }))[0]
    expect(chatgpt).toBeDisabled()
  })

  it("enregistre le brouillon modifié via l'API", async () => {
    adminApiMock.preferencesModeles.mockResolvedValue(reponse(true))
    adminApiMock.majPreferencesModeles.mockResolvedValue(reponse(true))
    afficher()

    const boutonsClaude = await screen.findAllByRole("button", { name: /^Claude/i })
    // 1er bloc = transcription : bascule gemini -> claude
    await userEvent.click(boutonsClaude[0])

    const enregistrer = screen.getByRole("button", { name: /enregistrer/i })
    expect(enregistrer).toBeEnabled()
    await userEvent.click(enregistrer)

    await waitFor(() => expect(adminApiMock.majPreferencesModeles).toHaveBeenCalledTimes(1))
    const corps = adminApiMock.majPreferencesModeles.mock.calls[0][0]
    expect(corps.preferences.transcription.fournisseur).toBe("claude")
  })
})
