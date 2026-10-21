import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur } from "@/components/ui/Etat"
import { correctionsApi, ApiError } from "@/lib/api"
import { UploadCloud } from "lucide-react"

export default function SoumettreConfirmation() {
  const { jeton = "" } = useParams()
  const navigate = useNavigate()
  const [copie, setCopie] = useState<FileList | null>(null)
  const [erreur, setErreur] = useState("")
  const [envoi, setEnvoi] = useState(false)

  async function soumettre(e: React.FormEvent) {
    e.preventDefault()
    if (!copie || copie.length === 0) return setErreur("Ajoutez la copie scannée de l'élève.")

    const corps = new FormData()
    Array.from(copie).forEach((f) => corps.append("copie", f))

    setEnvoi(true)
    try {
      const rep = await correctionsApi.confirmation(jeton, corps)
      navigate(`/corrections/${rep.jeton}`)
    } catch (err) {
      setErreur(err instanceof ApiError ? err.message : "Dépôt impossible.")
      setEnvoi(false)
    }
  }

  return (
    <AppShell titre="Dépôt de la copie T1">
      <Card className="max-w-lg">
        <p className="text-petit text-texte-doux mb-4">Le barème est déjà connu (sujet généré à la suite du test de niveau) — déposez seulement le scan des réponses.</p>
        <form onSubmit={soumettre} className="flex flex-col gap-4">
          <label className="flex items-center gap-2 border border-dashed border-bord-fort rounded p-4 cursor-pointer hover:border-bleu text-petit text-texte-doux">
            <UploadCloud className="size-5" />
            {copie && copie.length > 0 ? `${copie.length} fichier(s) sélectionné(s)` : "Choisir un ou plusieurs fichiers"}
            <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => setCopie(e.target.files)} />
          </label>
          {erreur && <EtatErreur message={erreur} />}
          <Button type="submit" chargement={envoi} className="w-full">Déposer</Button>
        </form>
      </Card>
    </AppShell>
  )
}
