import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import { Spinner } from "@/components/ui/Etat"
import { AccesBadge } from "@/components/ui/Badge"
import { Stat, StatRow } from "@/components/ui/Stat"
import { adminApi } from "@/lib/api"

/** Port de `suivi_web/views.py::personnel`/`statistiques` — même contenu,
 * regroupé en un seul écran à onglets (miroir du sous-onglet « Admin » de
 * l'ancienne interface Streamlit, `src/ui/app.py::_admin_view_stats`).
 * `/admin/` (CRUD référentiel Django natif) reste hors scope (D-CEO-42). */
export default function Administration() {
  const [onglet, setOnglet] = useState<"statistiques" | "personnel">("statistiques")

  return (
    <AppShell titre="Administration">
      <div className="flex gap-2 mb-4 border-b border-bord">
        {(
          [
            ["statistiques", "Statistiques"],
            ["personnel", "Accès"],
          ] as const
        ).map(([valeur, label]) => (
          <button
            key={valeur}
            onClick={() => setOnglet(valeur)}
            className={`px-4 py-2 text-menu font-medium border-b-2 -mb-px transition-colors ${
              onglet === valeur ? "border-orange text-marine" : "border-transparent text-texte-doux hover:text-texte"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {onglet === "statistiques" ? <VueStatistiques /> : <VuePersonnel />}
    </AppShell>
  )
}

function VueStatistiques() {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "statistiques"], queryFn: adminApi.statistiques })

  if (isLoading) return <Spinner label="Chargement…" />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <StatRow>
          <Stat label="Élèves" value={data.nb_eleves ?? "?"} />
          <Stat label="Centres" value={data.nb_centres} />
          <Stat label="Copies corrigées" value={data.nb_copies ?? "?"} />
        </StatRow>
      </Card>

      {data.centres_suspects.length > 0 && (
        <div className="rounded-lg border border-te-cpt-bd bg-orange-pale text-orange px-4 py-3 text-menu">
          Centre(s) vu(s) une seule fois, à vérifier dans les Sheets : {data.centres_suspects.join(", ")}
        </div>
      )}

      {data.centres.length > 0 && (
        <Card>
          <p className="text-menu font-medium mb-1">Centres</p>
          <p className="text-petit text-texte-doux mb-3">
            Dérivés des Sheets, pas d'une liste figée : ajouter un centre se fait en l'écrivant dans un Sheet, sans
            modification de code.
          </p>
          <div className="flex flex-wrap gap-2">
            {data.centres.map((c) => (
              <span key={c} className="rounded-rond border border-bord px-2.5 py-0.5 text-petit">
                {c}
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function VuePersonnel() {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "personnel"], queryFn: adminApi.personnel })

  if (isLoading) return <Spinner label="Chargement…" />
  if (!data) return null

  if (data.lecture_impossible) {
    return <div className="rounded-lg border border-te-cpt-bd bg-rouge-pale text-rouge px-4 py-3 text-menu">La liste du personnel est momentanément indisponible.</div>
  }

  return (
    <div className="flex flex-col gap-3">
      {data.probleme > 0 && (
        <div className="rounded-lg border border-te-cpt-bd bg-orange-pale text-orange px-4 py-3 text-menu">
          {data.probleme} personne{data.probleme > 1 ? "s" : ""} ne peu{data.probleme > 1 ? "vent" : "t"} pas se
          connecter — affichée{data.probleme > 1 ? "s" : ""} en premier.
        </div>
      )}

      <Card className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-menu">
            <thead>
              <tr className="text-left text-petit text-texte-doux border-b border-bord">
                <th className="px-4 py-2.5 font-medium">Personne</th>
                <th className="px-4 py-2.5 font-medium">Rôle</th>
                <th className="px-4 py-2.5 font-medium">Centre</th>
                <th className="px-4 py-2.5 font-medium">Accès</th>
              </tr>
            </thead>
            <tbody>
              {data.lignes.map((ligne, i) => (
                <tr key={i} className="border-b border-bord last:border-0">
                  <td className="px-4 py-2.5">
                    <strong>{String(ligne.personne.nom ?? "")}</strong> {String(ligne.personne.prenom ?? "")}
                  </td>
                  <td className="px-4 py-2.5">{ligne.roles}</td>
                  <td className="px-4 py-2.5">{ligne.centres}</td>
                  <td className="px-4 py-2.5">
                    <AccesBadge etat={ligne.etat} libelle={ligne.libelle} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-petit text-texte-doux">
        {data.lignes.length} personne{data.lignes.length > 1 ? "s" : ""} dans le Google Sheet. Le centre est
        informatif : depuis que Maïya fonctionne comme centre d'encadrement, toute personne autorisée accède à
        tous les élèves.
      </p>
    </div>
  )
}
