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
