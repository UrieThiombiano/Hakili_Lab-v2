import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Search, TrendingDown, TrendingUp, ChevronRight, X, Users } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { elevesApi } from "@/lib/api"
import { TendanceBadge } from "@/components/ui/Badge"
import { Card } from "@/components/ui/Card"
import { EtatVide, EtatErreur } from "@/components/ui/Etat"
import { useDebounce } from "@/hooks/useDebounce"
import { cn } from "@/lib/utils"
import type { Tendance } from "@/types/api"

const STYLE_AVATAR: Record<Tendance, string> = {
  progresse: "bg-vert-pale text-vert",
  stagne: "bg-orange-pale text-orange",
  regresse: "bg-rouge-pale text-rouge",
  insuffisant: "bg-gris-pale text-gris",
}

function initiales(nom: string, prenom: string) {
  return `${nom[0] ?? ""}${prenom[0] ?? ""}`.toUpperCase() || "?"
}

function LigneSquelette() {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-bord bg-surface p-4 animate-pulse">
      <div className="size-11 rounded-rond bg-surface-creuse shrink-0" />
      <div className="flex-1 flex flex-col gap-2">
        <div className="h-3.5 w-40 rounded bg-surface-creuse" />
        <div className="h-3 w-56 rounded bg-surface-creuse" />
      </div>
      <div className="h-6 w-24 rounded-rond bg-surface-creuse shrink-0" />
    </div>
  )
}

export default function Parcours() {
  const [recherche, setRecherche] = useState("")
  const rechercheDiff = useDebounce(recherche, 250)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["accueil", rechercheDiff],
    queryFn: () => elevesApi.accueil(rechercheDiff),
  })

  const total = data?.lignes.length ?? 0
  const progressent = data?.lignes.filter((l) => l.tendance === "progresse").length ?? 0

  return (
    <AppShell titre="Parcours">
      <div className="flex flex-col gap-5">
        {data && !data.lecture_impossible && total > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex items-center gap-3 rounded-lg border border-bord bg-surface px-4 py-3.5 shadow-carte">
              <span className="flex items-center justify-center size-9 rounded-rond bg-bleu-pale text-bleu-sombre shrink-0">
                <Users className="size-4.5" />
              </span>
              <div>
                <p className="text-h3 font-bold text-marine leading-none">{total}</p>
                <p className="text-petit text-texte-doux mt-0.5">élève{total > 1 ? "s" : ""} suivi{total > 1 ? "s" : ""}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-bord bg-surface px-4 py-3.5 shadow-carte">
              <span className="flex items-center justify-center size-9 rounded-rond bg-vert-pale text-vert shrink-0">
                <TrendingUp className="size-4.5" />
              </span>
              <div>
                <p className="text-h3 font-bold text-marine leading-none">{progressent}</p>
                <p className="text-petit text-texte-doux mt-0.5">en progression</p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-bord bg-surface px-4 py-3.5 shadow-carte">
              <span className="flex items-center justify-center size-9 rounded-rond bg-rouge-pale text-rouge shrink-0">
                <TrendingDown className="size-4.5" />
              </span>
              <div>
                <p className="text-h3 font-bold text-marine leading-none">{data.en_baisse}</p>
                <p className="text-petit text-texte-doux mt-0.5">en baisse</p>
              </div>
            </div>
          </div>
        )}

        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-texte-faible" />
          <input
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            placeholder="Rechercher un élève…"
            className="w-full h-11 rounded-lg border border-bord-fort bg-surface pl-10 pr-9 text-menu shadow-carte transition-colors duration-150 focus:border-bleu focus:outline-none"
          />
          {recherche && (
            <button
              onClick={() => setRecherche("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-texte-faible hover:text-texte"
              aria-label="Effacer la recherche"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        {isLoading && (
          <div className="flex flex-col gap-2.5">
            {Array.from({ length: 5 }).map((_, i) => <LigneSquelette key={i} />)}
          </div>
        )}

        {isError && <EtatErreur message="La liste des élèves est momentanément indisponible." />}
        {data?.lecture_impossible && <EtatErreur message="La liste des élèves est momentanément indisponible. Réessayez dans un instant." />}

        {data && !data.lecture_impossible && data.lignes.length === 0 && (
          <EtatVide titre="Aucun élève trouvé" description={recherche ? "Essayez une autre recherche." : undefined} />
        )}

        {data && data.lignes.length > 0 && (
          <div className="flex flex-col gap-2.5">
            {data.lignes.map((ligne) => {
              const nom = String(ligne.eleve.nom ?? "")
              const prenom = String(ligne.eleve.prenom ?? "")
              return (
                <Link key={ligne.jeton} to={`/eleves/${ligne.jeton}`}>
                  <Card className="flex items-center gap-4 hover:border-bleu hover:shadow-haute transition-all duration-200 py-3.5">
                    <span className={cn("flex items-center justify-center size-11 rounded-rond font-semibold text-menu shrink-0", STYLE_AVATAR[ligne.tendance])}>
                      {initiales(nom, prenom)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-menu font-medium text-texte truncate">
                        {nom} {prenom}
                      </p>
                      <p className="text-petit text-texte-doux truncate">
                        {String(ligne.eleve.classe ?? "—")} · {String(ligne.eleve.centre ?? "—")} · {ligne.nb_copies} copie{ligne.nb_copies !== 1 ? "s" : ""}
                        {ligne.derniere_note != null && <> · dernière note {ligne.derniere_note}/20</>}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <TendanceBadge tendance={ligne.tendance} />
                      <ChevronRight className="size-4 text-texte-faible" />
                    </div>
                  </Card>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </AppShell>
  )
}
