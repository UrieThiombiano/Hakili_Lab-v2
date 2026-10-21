import { describe, expect, it } from "vitest"
import { formatHeures, heures } from "./format"

describe("heures", () => {
  it("convertit une chaîne Decimal en nombre", () => {
    expect(heures("4.00")).toBe(4)
    expect(heures("1.5")).toBe(1.5)
    expect(heures("0")).toBe(0)
  })
})

describe("formatHeures", () => {
  it("n'affiche pas de décimale pour un nombre entier", () => {
    expect(formatHeures("4.00")).toBe("4 h")
  })

  it("affiche une décimale pour un nombre non entier", () => {
    expect(formatHeures("1.50")).toBe("1.5 h")
  })

  it("gère zéro (ATT, non remédiable)", () => {
    expect(formatHeures("0")).toBe("0 h")
  })
})
