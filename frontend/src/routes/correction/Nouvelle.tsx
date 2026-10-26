import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate, useSearchParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur } from "@/components/ui/Etat"
import { ComboboxRecherche } from "@/components/ui/ComboboxRecherche"
import { correctionsApi, elevesApi, ApiError } from "@/lib/api"
import { UploadCloud } from "lucide-react"

const TYPES_EVALUATION = [
  { valeur: "T0", libelle: "T0 — test de niveau" },
  { valeur: "T3", libelle: "T3 — vérification après remédiation" },
  { valeur: "T4", libelle: "T4 — consolidation à 45 jours" },
  { valeur: "T5", libelle: "T5 — consolidation à 3 mois" },
]

export default function Nouvelle() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const { data: accueil } = useQuery({ queryKey: ["accueil-picker"], queryFn: () => elevesApi.accueil() })
  const { data: tests } = useQuery({ queryKey: ["tests"], queryFn: correctionsApi.tests })

  const eleves = useMemo(() => accueil?.lignes.map((l) => l.eleve as { identifiant_hakili: string; nom: string; prenom: string }) ?? [], [accueil])

  const [eleveId, setEleveId] = useState("")
  const [testId, setTestId] = useState("")
  const [typeEvaluation, setTypeEvaluation] = useState("T0")
  const [instructions, setInstructions] = useState("")
  const [copie, setCopie] = useState<FileList | null>(null)
  const [sujet, setSujet] = useState<File | null>(null)
  const [erreur, setErreur] = useState("")
  const [envoi, setEnvoi] = useState(false)

  useEffect(() => {
    const jetonEleve = params.get("eleve")
    if (jetonEleve) {
      elevesApi.detail(jetonEleve).then((d) => {
        const trouve = eleves.find((e) => `${e.nom}${e.prenom}` === `${d.eleve.nom}${d.eleve.prenom}`)
        if (trouve) setEleveId(trouve.identifiant_hakili)
      }).catch(() => {})
    }
    const te = params.get("type_evaluation")
    if (te) setTypeEvaluation(te)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eleves.length])

  async function soumettre(e: React.FormEvent) {
    e.preventDefault()
    setErreur("")
    if (!eleveId) return setErreur("Sélectionnez un élève.")
    if (!testId) return setErreur("Sélectionnez le test que l'élève a passé.")
    if (!copie || copie.length === 0) return setErreur("Ajoutez la copie scannée de l'élève.")
    if (testId === "libre" && !sujet) return setErreur("En test personnalisé, ajoutez le sujet.")

    const corps = new FormData()
    corps.append("eleve", eleveId)
    corps.append("test", testId)
    corps.append("type_evaluation", typeEvaluation)
    corps.append("instructions", instructions)
    Array.from(copie).forEach((f) => corps.append("copie", f))
    if (sujet) corps.append("sujet", sujet)

    setEnvoi(true)
    try {
      const rep = await correctionsApi.nouvelle(corps)
      navigate(`/corrections/${rep.jeton}`)
    } catch (err) {
      setErreur(err instanceof ApiError ? err.message : "Dépôt impossible.")
      setEnvoi(false)
    }
  }

  return (
    <AppShell titre="Nouvelle correction">
      <Card className="w-full">
        <div className="flex items-center gap-2 mb-4">
          <span className="w-5 h-[3px] rounded-rond bg-orange" />
          <span className="text-petit font-semibold uppercase tracking-[0.16em] text-bleu-sombre">Analyser une copie</span>
        </div>
        <form onSubmit={soumettre} className="flex flex-col gap-4 max-w-2xl">
          <ComboboxRecherche
            label="Élève"
            items={eleves}
            getCle={(el) => el.identifiant_hakili}
            getLibelle={(el) => `${el.nom} ${el.prenom}`}
            valeur={eleveId}
            onSelect={(c) => setEleveId(c)}
          />

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Test</label>
            <select value={testId} onChange={(e) => setTestId(e.target.value)} className="w-full h-10 rounded border border-bord-fort px-3 text-menu">
              <option value="">Sélectionner…</option>
              {tests?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label} ({t.questions} questions)
                </option>
              ))}
              <option value="libre">Test personnalisé (mode libre)</option>
            </select>
          </div>

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Étape du suivi</label>
            <select value={typeEvaluation} onChange={(e) => setTypeEvaluation(e.target.value)} className="w-full h-10 rounded border border-bord-fort px-3 text-menu">
              {TYPES_EVALUATION.map((t) => (
                <option key={t.valeur} value={t.valeur}>{t.libelle}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Copie scannée (PDF/JPG/PNG)</label>
            <label className="flex items-center gap-2 border border-dashed border-bord-fort rounded p-4 cursor-pointer hover:border-bleu text-petit text-texte-doux">
              <UploadCloud className="size-5" />
              {copie && copie.length > 0 ? `${copie.length} fichier(s) sélectionné(s)` : "Choisir un ou plusieurs fichiers"}
              <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => setCopie(e.target.files)} />
            </label>
          </div>

          {testId === "libre" && (
            <div>
              <label className="block text-petit font-medium text-texte-doux mb-1">Sujet (obligatoire en mode libre)</label>
              <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setSujet(e.target.files?.[0] ?? null)} className="text-petit" />
            </div>
          )}

          <div>
            <label className="block text-petit font-medium text-texte-doux mb-1">Instructions particulières (facultatif)</label>
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2} className="w-full rounded border border-bord-fort p-2 text-menu" />
          </div>

          {erreur && <EtatErreur message={erreur} />}

          <Button type="submit" chargement={envoi} className="w-full">
            Lancer la correction
          </Button>
        </form>
      </Card>
    </AppShell>
  )
}
