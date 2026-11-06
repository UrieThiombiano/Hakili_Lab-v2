import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { EtatProblemeBadge, EtatSessionBadge, PalierBadge, TendanceBadge, TypeErreurBadge } from "./Badge"
import type { EtatProbleme, EtatSession, Tendance } from "@/types/api"

// Découvert en Phase 3 (verifier_installation-équivalent) : une valeur de
// taxonomie non gérée par un composant plante le rendu en silence (page
// blanche, cf. `SujetDisponible.niveaux`). Ces tests couvrent chaque valeur
// de chaque union type de taxonomie — le genre d'erreur qu'un test attrape
// avant le navigateur.

describe("TendanceBadge", () => {
  const cas: [Tendance, string][] = [
    ["progresse", "Progresse"],
    ["stagne", "Stagne"],
    ["regresse", "En baisse"],
    ["insuffisant", "Pas assez de données"],
  ]
  it.each(cas)("rend le libellé pour %s", (tendance, libelleAttendu) => {
    render(<TendanceBadge tendance={tendance} />)
    expect(screen.getByText(libelleAttendu)).toBeInTheDocument()
  })
})

describe("TypeErreurBadge", () => {
  // Liste fermée à 7 codes (protocole-v2.md §3) — un 8e code serait un bug,
  // pas une variante (même règle que côté référentiel).
  const codes = ["PRQ", "CPT", "MOD", "PRC", "CNS", "RED", "ATT"]
  it.each(codes)("rend un badge pour le code %s sans lever", (code) => {
    render(<TypeErreurBadge code={code} />)
    expect(screen.getByText(new RegExp(code))).toBeInTheDocument()
  })

  it("retombe sur un style neutre pour un code inconnu plutôt que de planter", () => {
    render(<TypeErreurBadge code="ZZZ" />)
    expect(screen.getByText(/ZZZ/)).toBeInTheDocument()
  })
})

describe("EtatProblemeBadge", () => {
  const etats: EtatProbleme[] = ["hypothese", "confirme", "ecarte", "en_remediation", "resolu", "non_resolu", "regresse", "clos"]
  it.each(etats)("rend le badge pour l'état %s", (etat) => {
    render(<EtatProblemeBadge etat={etat} />)
    expect(screen.getByText(/./)).toBeInTheDocument()
  })
})

describe("EtatSessionBadge", () => {
  const etats: EtatSession[] = ["diagnostic", "attente_inscription", "remediation", "close", "sans_suite", "hors_dispositif", "abandonnee"]
  it.each(etats)("rend le badge pour l'état %s", (etat) => {
    render(<EtatSessionBadge etat={etat} />)
    expect(screen.getByText(/./)).toBeInTheDocument()
  })
})

describe("PalierBadge", () => {
  it("ne rend rien pour un palier vide (avant T1)", () => {
    const { container } = render(<PalierBadge palier="" />)
    expect(container).toBeEmptyDOMElement()
  })

  it.each(["A", "B", "C"] as const)("rend le palier %s", (palier) => {
    render(<PalierBadge palier={palier} />)
    expect(screen.getByText(new RegExp(`^${palier} —`))).toBeInTheDocument()
  })
})
