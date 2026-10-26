import { useState } from "react"
import { Menu, ChevronDown, LogOut } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import { useNavigate } from "react-router-dom"

const LIBELLES_CASQUETTE: Record<string, string> = {
  administrateur: "Administrateur",
  responsable: "Responsable",
  enseignant: "Enseignant",
}

export function Topbar({ ouvrirSidebar, titre }: { ouvrirSidebar: () => void; titre?: string }) {
  const { personne, casquette, casquettesPossibles, changerCasquette, logout } = useAuth()
  const [menuOuvert, setMenuOuvert] = useState(false)
  const navigate = useNavigate()

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-4 border-b-2 border-orange/30 bg-gradient-to-r from-bleu-pale/80 via-surface/95 to-surface/95 backdrop-blur px-5 py-3 shadow-[0_1px_0_0_rgba(0,30,74,0.04)]">
      <div className="flex items-center gap-3 min-w-0">
        <button onClick={ouvrirSidebar} className="lg:hidden text-texte-doux hover:text-texte">
          <Menu className="size-5" />
        </button>
        {titre && <h1 className="text-h2 font-semibold text-marine truncate">{titre}</h1>}
      </div>

      {personne && (
        <div className="relative shrink-0">
          <button
            onClick={() => setMenuOuvert((o) => !o)}
            className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-creuse text-menu transition-colors duration-150"
          >
            <span className="size-8 rounded-rond bg-bleu-pale text-bleu-sombre flex items-center justify-center font-semibold text-petit">
              {personne.prenom?.[0]}
              {personne.nom?.[0]}
            </span>
            <span className="hidden sm:block text-left">
              <span className="block leading-tight">{personne.prenom} {personne.nom}</span>
              {casquette && <span className="block text-petit text-texte-doux leading-tight">{LIBELLES_CASQUETTE[casquette] ?? casquette}</span>}
            </span>
            <ChevronDown className={`size-4 text-texte-doux transition-transform duration-150 ${menuOuvert ? "rotate-180" : ""}`} />
          </button>

          {menuOuvert && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOuvert(false)} />
              <div className="absolute right-0 mt-1 w-56 rounded-lg border border-bord bg-surface shadow-haute z-20 py-1 animate-entree-menu">
                {casquettesPossibles.length > 1 && (
                  <div className="px-3 py-2 border-b border-bord">
                    <p className="text-micro uppercase tracking-wide text-texte-faible mb-1">Travailler comme</p>
                    {casquettesPossibles.map((c) => (
                      <button
                        key={c.valeur}
                        onClick={() => {
                          changerCasquette(c.valeur)
                          setMenuOuvert(false)
                        }}
                        className={`block w-full text-left px-2 py-1.5 rounded text-menu ${c.valeur === casquette ? "bg-bleu-pale text-bleu-sombre font-medium" : "hover:bg-surface-creuse"}`}
                      >
                        {c.libelle}
                      </button>
                    ))}
                  </div>
                )}
                <button
                  onClick={async () => {
                    await logout()
                    navigate("/connexion")
                  }}
                  className="flex items-center gap-2 w-full text-left px-3 py-2 text-menu text-rouge hover:bg-rouge-pale"
                >
                  <LogOut className="size-4" /> Déconnexion
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </header>
  )
}
