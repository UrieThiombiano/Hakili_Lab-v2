import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { authApi, ApiError } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/Button"
import { Card } from "@/components/ui/Card"
import { ComboboxRecherche } from "@/components/ui/ComboboxRecherche"
import type { PersonneListe } from "@/types/api"

export default function Connexion() {
  const { login, personne } = useAuth()
  const navigate = useNavigate()

  const [personnel, setPersonnel] = useState<PersonneListe[]>([])
  const [cle, setCle] = useState("")
  const [pin, setPin] = useState("")
  const [erreur, setErreur] = useState("")
  const [envoi, setEnvoi] = useState(false)

  useEffect(() => {
    if (personne) navigate("/", { replace: true })
  }, [personne, navigate])

  useEffect(() => {
    authApi.personnel().then(setPersonnel).catch(() => setErreur("La liste du personnel est momentanément indisponible."))
  }, [])

  async function soumettre(e: React.FormEvent) {
    e.preventDefault()
    setErreur("")
    if (!cle) {
      setErreur("Veuillez sélectionner votre nom dans la liste.")
      return
    }
    setEnvoi(true)
    try {
      await login(cle, pin)
      navigate("/", { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = err.detail as { message?: string } | string
        setErreur(typeof detail === "string" ? detail : detail.message ?? "Connexion refusée.")
      } else {
        setErreur("Connexion impossible.")
      }
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center fond-cahier px-4">
      <Card className="w-full max-w-sm animate-entree-page">
        <div className="flex items-center gap-3 mb-1">
          <img src="/hakili_logo.png" alt="Hakili Lab" className="size-10 object-contain shrink-0" />
          <h1 className="text-h1 font-bold text-marine leading-tight">RÉMÉDIATION MATHS</h1>
        </div>
        <p className="text-petit text-texte-doux mb-6">Sélectionnez votre nom, puis saisissez votre code PIN.</p>

        <form onSubmit={soumettre} className="flex flex-col gap-4">
          <ComboboxRecherche
            label="Nom"
            items={personnel}
            getCle={(p) => p.cle}
            getLibelle={(p) => p.libelle}
            valeur={cle}
            onSelect={(c) => setCle(c)}
            placeholder="Commencez à taper votre nom…"
          />

          <div>
            <label htmlFor="pin" className="block text-petit font-medium text-texte-doux mb-1">Code PIN (4 chiffres)</label>
            <input
              id="pin"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={4}
              required
              className="w-full h-10 rounded border border-bord-fort px-3 text-menu tracking-[0.3em] transition-colors duration-150 focus:border-bleu"
            />
          </div>

          {erreur && <p className="text-petit text-rouge">{erreur}</p>}

          <Button type="submit" chargement={envoi} className="w-full mt-2">
            Se connecter
          </Button>
        </form>
      </Card>
    </div>
  )
}
