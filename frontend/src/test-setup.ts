import "@testing-library/jest-dom/vitest"

// jsdom n'implémente ni matchMedia ni IntersectionObserver —
// `useRevealOnScroll` (derrière chaque `Card`, voir
// src/components/ui/Card.tsx) utilise les deux et plante sans ces shims, ce
// qui faisait échouer tout test montant une route réelle (pas seulement un
// composant isolé).
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList
}

if (typeof window.IntersectionObserver !== "function") {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
  }
  window.IntersectionObserver = IntersectionObserverStub as unknown as typeof IntersectionObserver
}
