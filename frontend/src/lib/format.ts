/** Les champs `Decimal` de l'API arrivent en chaîne ("4.00") — un seul point
 * de conversion, pas un `Number()` semé partout. */
export function heures(valeur: string): number {
  return Number.parseFloat(valeur)
}

export function formatHeures(valeur: string): string {
  const n = heures(valeur)
  return `${n % 1 === 0 ? n : n.toFixed(1)} h`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })
}

export function formatDateHeure(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
}
