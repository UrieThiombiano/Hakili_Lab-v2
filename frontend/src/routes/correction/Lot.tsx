import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur } from "@/components/ui/Etat"
import { correctionsApi, ApiError } from "@/lib/api"
import { UploadCloud, TriangleAlert } from "lucide-react"

/** Port de `correction_web/views.py::lot` — dépôt d'une classe entière.
 * L'élève de chaque copie vient du **nom du fichier**, mis en
 * correspondance avec les Sheets côté serveur : rien n'est choisi ici,
 * seul le test et les fichiers le sont (D-CEO-20 — rien n'est deviné, une
 * copie sans correspondance unique est écartée et signalée). */
export default function Lot() {
  const navigate = useNavigate()
  const { data: tests } = useQuery({ queryKey: ["tests"], queryFn: correctionsApi.tests })

  const [testId, setTestId] = useState("")
  const [instructions, setInstructions] = useState("")
  const [copies, setCopies] = useState<FileList | null>(null)
  const [erreur, setErreur] = useState("")
  const [envoi, setEnvoi] = useState(false)
  const [ecartees, setEcartees] = useState<string[]>([])

  async function soumettre(e: React.FormEvent) {
    e.preventDefault()
    setErreur("")
    setEcartees([])
    if (!testId) return setErreur("Sélectionnez le test que la classe a passé.")
    if (!copies || copies.length === 0) return setErreur("Ajoutez au moins une copie.")

    const corps = new FormData()
    corps.append("test", testId)
    corps.append("instructions", instructions)
    Array.from(copies).forEach((f) => corps.append("copies", f))

    setEnvoi(true)
    try {
      const rep = await correctionsApi.lot(corps)
      if (rep.ecartees.length > 0) setEcartees(rep.ecartees)
      if (rep.lancees > 0) {
        if (rep.ecartees.length === 0) {
          navigate("/analyse-de-copie")
          return
        }
      } else {
        setErreur("Aucune copie n'a pu être appariée à un élève — voir le détail ci-dessous.")
      }
    } catch (err) {
      setErreur(err instanceof ApiError ? err.message : "Dépôt impossible.")
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <AppShell titre="Dépôt en lot">
      <Card className="max-w-xl">
        <p className="text-petit text-texte-doux mb-4">
          Déposez les copies scannées d'une classe entière. Chaque fichier doit être nommé avec le nom et le prénom de l'élève —
          l'appariement se fait automatiquement contre les Sheets ; une copie sans correspondance unique est écartée, jamais attribuée au hasard.
        </p>

        <form onSubmit={soumettre} className="flex flex-col gap-4">
          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Test</label>
            <select value={testId} onChange={(e) => setTestId(e.target.value)} className="w-full h-10 rounded border border-bord-fort px-3 text-menu">
              <option value="">Sélectionner…</option>
              {tests?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label} ({t.questions} questions)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Copies scannées (PDF/JPG/PNG)</label>
            <label className="flex items-center gap-2 border border-dashed border-bord-fort rounded p-4 cursor-pointer hover:border-bleu text-petit text-texte-doux">
              <UploadCloud className="size-5" />
              {copies && copies.length > 0 ? `${copies.length} fichier(s) sélectionné(s)` : "Choisir les fichiers de la classe"}
              <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => setCopies(e.target.files)} />
            </label>
            {copies && copies.length > 0 && (
              <ul className="mt-2 text-petit text-texte-doux max-h-32 overflow-y-auto">
                {Array.from(copies).map((f) => (
                  <li key={f.name} className="truncate">{f.name}</li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Instructions particulières (facultatif)</label>
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2} className="w-full rounded border border-bord-fort p-2 text-menu" />
          </div>

          {erreur && <EtatErreur message={erreur} />}

          {ecartees.length > 0 && (
            <div className="rounded-lg border border-te-prq-bd bg-orange-pale p-3">
              <p className="flex items-center gap-1.5 text-petit font-medium text-orange mb-2">
                <TriangleAlert className="size-4" /> {ecartees.length} copie{ecartees.length > 1 ? "s" : ""} écartée{ecartees.length > 1 ? "s" : ""}
              </p>
              <ul className="text-petit text-texte-doux flex flex-col gap-1">
                {ecartees.map((motif, i) => <li key={i}>{motif}</li>)}
              </ul>
            </div>
          )}

          <div className="flex gap-3">
            <Button type="submit" chargement={envoi} className="flex-1">
              Lancer les corrections
            </Button>
            {ecartees.length > 0 && (
              <Button type="button" variant="discret" onClick={() => navigate("/analyse-de-copie")}>
                Voir les corrections lancées
              </Button>
            )}
          </div>
        </form>
      </Card>
    </AppShell>
  )
}
