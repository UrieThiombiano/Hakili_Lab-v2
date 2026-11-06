import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { TranscriptionMarkdown } from "./TranscriptionMarkdown"

describe("TranscriptionMarkdown", () => {
  it("surligne les zones incertaines entre crochets et masque les chevrons", () => {
    render(<TranscriptionMarkdown value={"L8 E = ⟦4x²⟧ + 9"} onChange={() => {}} />)
    const zone = screen.getByText("[4x²]")
    expect(zone.tagName).toBe("MARK")
    expect(screen.queryByText(/⟦/)).not.toBeInTheDocument()
  })

  it("affiche [illisible] pour un [ILLISIBLE]", () => {
    render(<TranscriptionMarkdown value={"N7 [ILLISIBLE]"} onChange={() => {}} />)
    expect(screen.getByText("[illisible]").tagName).toBe("MARK")
  })

  it("double-clic sur une zone → correction en place, valider remonte le texte sans marqueur", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TranscriptionMarkdown value={"a ⟦b⟧ c ⟦d⟧"} onChange={onChange} />)

    await user.dblClick(screen.getByText("[d]"))
    const champ = screen.getByRole("textbox")
    await user.clear(champ)
    await user.type(champ, "D")
    await user.click(screen.getByTitle("Valider la correction"))

    expect(onChange).toHaveBeenCalledWith("a ⟦b⟧ c D")
  })

  it("double-clic sur une ligne → édition de la ligne seule, Entrée remonte la page entière", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TranscriptionMarkdown value={"L1 x = 4\nF = (3x - 5)(3x + 5)\nL3 y = 2"} onChange={onChange} />)

    await user.dblClick(screen.getByText("F = (3x - 5)(3x + 5)"))
    const champ = screen.getByRole("textbox")
    expect(champ).toHaveValue("F = (3x - 5)(3x + 5)")
    await user.clear(champ)
    await user.type(champ, "F = (9x - 5)(9x + 5){Enter}")

    expect(onChange).toHaveBeenCalledWith("L1 x = 4\nF = (9x - 5)(9x + 5)\nL3 y = 2")
  })

  it("l'édition de ligne retire les chevrons mais garde [ILLISIBLE]", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TranscriptionMarkdown value={"N2 ⟦6⟧√5 et [ILLISIBLE]"} onChange={onChange} />)

    await user.dblClick(screen.getByText(/N2/))
    expect(screen.getByRole("textbox")).toHaveValue("N2 6√5 et [ILLISIBLE]")
  })

  it("double-clic sur une zone n'ouvre pas l'édition de la ligne", async () => {
    const user = userEvent.setup()
    render(<TranscriptionMarkdown value={"a ⟦b⟧ c"} onChange={() => {}} />)

    await user.dblClick(screen.getByText("[b]"))
    expect(screen.getAllByRole("textbox")).toHaveLength(1)
    expect(screen.getByRole("textbox")).toHaveValue("b")
  })

  it("Échap annule sans rien remonter", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TranscriptionMarkdown value={"a ⟦b⟧"} onChange={onChange} />)

    await user.dblClick(screen.getByText("[b]"))
    await user.keyboard("{Escape}")

    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText("[b]")).toBeInTheDocument()
  })
})
