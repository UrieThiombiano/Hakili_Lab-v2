import { useMemo, useState } from "react"

/** Minuscule, sans accents — pour comparer sans se soucier de la casse ni
 * des accents (miroir de `fold_texte` côté backend, src/services/identite_service.py). */
function plier(texte: string): string {
  return texte
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
}

interface ComboboxRechercheProps<T> {
  label?: string
  items: T[]
  getCle: (item: T) => string
  getLibelle: (item: T) => string
  valeur: string
  onSelect: (cle: string, item: T | null) => void
  placeholder?: string
}

export function ComboboxRecherche<T>({
  label,
  items,
  getCle,
  getLibelle,
  valeur,
  onSelect,
  placeholder = "Rechercher…",
}: ComboboxRechercheProps<T>) {
  const [recherche, setRecherche] = useState("")
  const [ouvert, setOuvert] = useState(false)

  const choisi = useMemo(() => items.find((i) => getCle(i) === valeur), [items, valeur, getCle])
  const libelleChoisi = choisi ? getLibelle(choisi) : ""

  const filtres = useMemo(() => {
    if (!recherche.trim()) return items
    const mots = plier(recherche).split(/\s+/)
    return items.filter((i) => mots.every((m) => plier(getLibelle(i)).includes(m)))
  }, [items, recherche, getLibelle])

  return (
    <div className="relative">
      {label && <label className="block text-petit font-medium text-texte-doux mb-1">{label}</label>}
      <input
        value={libelleChoisi || recherche}
        onChange={(e) => {
          setRecherche(e.target.value)
          if (valeur) onSelect("", null)
          setOuvert(true)
        }}
        onFocus={() => setOuvert(true)}
        placeholder={placeholder}
        className="w-full h-10 rounded border border-bord-fort px-3 text-menu transition-colors duration-150 focus:border-bleu"
        autoComplete="off"
      />
      {ouvert && filtres.length > 0 && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOuvert(false)} />
          <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto rounded border border-bord bg-surface shadow-haute animate-entree-menu origin-top">
            {filtres.map((item) => {
              const cle = getCle(item)
              return (
                <li key={cle}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(cle, item)
                      setRecherche("")
                      setOuvert(false)
                    }}
                    className="block w-full text-left px-3 py-2 text-menu transition-colors duration-100 hover:bg-surface-creuse"
                  >
                    {getLibelle(item)}
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
