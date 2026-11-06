import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import Accueil from "@/routes/Accueil"

function monter() {
  return render(
    <MemoryRouter>
      <Accueil />
    </MemoryRouter>,
  )
}

describe("Accueil (vitrine publique)", () => {
  it("affiche l'accroche", () => {
    monter()
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Savoir exactement ce qui bloque votre enfant en maths.")
  })

  it("mène à la connexion, à l'inscription et au site officiel", () => {
    monter()
    for (const lien of screen.getAllByRole("link", { name: /se connecter à maya/i })) {
      expect(lien).toHaveAttribute("href", "/connexion")
    }
    for (const lien of screen.getAllByRole("link", { name: /inscrire mon enfant/i })) {
      expect(lien).toHaveAttribute("href", "https://forms.gle/FMWP9KZtjrxyVT3x6")
      expect(lien).toHaveAttribute("target", "_blank")
    }
    expect(screen.getByRole("link", { name: /visiter le site web officiel de hakili$/i })).toHaveAttribute("href", "https://hakililab.com/")
  })

  it("ne dévoile pas le protocole interne", () => {
    const { container } = monter()
    const texte = container.textContent ?? ""
    for (const interdit of ["T0", "T1", "T3", "palier", "référentiel", "Claude", "Gemini"]) {
      expect(texte).not.toContain(interdit)
    }
  })
})
