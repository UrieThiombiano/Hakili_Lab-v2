import { describe, expect, it } from "vitest"
import { ancrerIncertitudes, replaceNthMarker } from "./transcriptionHighlight"

describe("replaceNthMarker", () => {
  it("remplace le marqueur incertain visé et retire les chevrons", () => {
    expect(replaceNthMarker("E = ⟦4x²⟧ + 9 - ⟦4x²⟧ - 9", 1, "4x²")).toBe("E = ⟦4x²⟧ + 9 - 4x² - 9")
  })

  it("remplace un [ILLISIBLE] par le texte saisi", () => {
    expect(replaceNthMarker("N7 [ILLISIBLE]\nL8 ⟦25⟧", 0, "x = 75 pagnes")).toBe("N7 x = 75 pagnes\nL8 ⟦25⟧")
  })

  it("compte incertain et illisible dans le même ordre de lecture", () => {
    expect(replaceNthMarker("a ⟦b⟧ c [ILLISIBLE] d ⟦e⟧", 2, "E")).toBe("a ⟦b⟧ c [ILLISIBLE] d E")
  })

  it("laisse le texte intact si l'index n'existe pas", () => {
    expect(replaceNthMarker("a ⟦b⟧", 5, "z")).toBe("a ⟦b⟧")
  })
})

describe("ancrerIncertitudes", () => {
  it("entoure de ⟦…⟧ la ligne citée entre guillemets par une incertitude", () => {
    const content = "1. Je calcule BC\nMN = AC - BA / MN - BM\nBC = 100 m"
    const u = ["La ligne de calcul 'MN = AC - BA / MN - BM' est confuse et semble une erreur de transcription"]
    expect(ancrerIncertitudes(content, u)).toBe(
      "1. Je calcule BC\n⟦MN = AC - BA / MN - BM⟧\nBC = 100 m",
    )
  })

  it("accepte les guillemets doubles et français", () => {
    expect(ancrerIncertitudes('a b c d', ['doute sur "a b c d"'])).toBe("⟦a b c d⟧")
    expect(ancrerIncertitudes("a b c d", ["doute sur « a b c d »"])).toBe("⟦a b c d⟧")
  })

  it("ne touche pas au texte quand l'incertitude ne cite aucun passage", () => {
    const content = "N7 [ILLISIBLE]\nL8 E = ⟦4x²⟧ + 9"
    expect(ancrerIncertitudes(content, ["N7 : ligne masquée par une tache"])).toBe(content)
  })

  it("ignore une citation absente du texte", () => {
    expect(ancrerIncertitudes("BC = 100 m", ["cf. 'AB = 60 m et AC = 80 m'"])).toBe("BC = 100 m")
  })

  it("ne double pas un passage déjà marqué", () => {
    const content = "⟦MN = AC - BA⟧ suite"
    expect(ancrerIncertitudes(content, ["'MN = AC - BA' douteux"])).toBe(content)
  })

  it("ne surligne pas un token court et ambigu", () => {
    expect(ancrerIncertitudes("BC = 100 m, BC vaut BC", ["chiffre lu 'BC'"])).toBe("BC = 100 m, BC vaut BC")
  })

  it("n'entoure que la première occurrence", () => {
    expect(ancrerIncertitudes("x y z et x y z", ["'x y z' incertain"])).toBe("⟦x y z⟧ et x y z")
  })
})
