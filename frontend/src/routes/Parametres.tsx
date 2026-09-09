import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { AppShell, CLE_REDUITE, lireReduite } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { useAuth } from "@/hooks/useAuth"
import { useToast } from "@/hooks/useToast"
import { adminApi, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { PreferenceTache, PreferencesModelesReponse } from "@/types/api"
import { LogOut } from "lucide-react"

const LIBELLES_CASQUETTE: Record<string, string> = {
  administrateur: "Administrateur",
  responsable: "Responsable",
  enseignant: "Enseignant",
}

/** Écran squelette : infos du compte, préférences d'affichage locales, déconnexion.
 * Pas d'appel API dédié — le compte vient du Sheet personnel (`useAuth`), les
 * préférences vivent en `localStorage` (comme la largeur de la sidebar). */
export default function Parametres() {
  const { personne, casquette, casquettesPossibles, changerCasquette, logout } = useAuth()
  const { notifier } = useToast()
  const navigate = useNavigate()

  const [menuReduit, setMenuReduit] = useState(lireReduite)

  function basculerMenuReduit() {
    setMenuReduit((v) => {
      const next = !v
      try {
        localStorage.setItem(CLE_REDUITE, next ? "1" : "0")
      } catch {
        /* stockage indisponible (navigation privée…) — la préférence ne survit juste pas à un rechargement */
      }
      return next
    })
    notifier("Préférence enregistrée — effet au prochain chargement.")
  }

  async function changer(valeur: string) {
    if (valeur === casquette) return
    await changerCasquette(valeur)
    notifier(`Casquette : ${LIBELLES_CASQUETTE[valeur] ?? valeur}.`)
  }

  return (
    <AppShell titre="Paramètres">
      <div className="flex flex-col gap-6 max-w-2xl pb-10">
        {/* Compte */}
        <Card>
          <CardTitre>Compte</CardTitre>
          {personne ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-menu">
              <dt className="text-texte-doux">Nom</dt>
              <dd>{personne.prenom} {personne.nom}</dd>
              <dt className="text-texte-doux">Rôle{(personne.roles?.length ?? 0) > 1 ? "s" : ""}</dt>
              <dd>
                {(personne.roles?.length ? personne.roles : [personne.role])
                  .map((r) => LIBELLES_CASQUETTE[r] ?? r)
                  .join(", ")}
              </dd>
            </dl>
          ) : (
            <p className="text-menu text-texte-doux">Non connecté.</p>
          )}
          <p className="text-petit text-texte-doux mt-3">
            Ces informations viennent du Google Sheet du personnel. Pour les corriger, passer par un responsable.
          </p>
        </Card>

        {/* Casquette de travail */}
        {casquettesPossibles.length > 1 && (
          <Card>
            <CardTitre>Casquette de travail</CardTitre>
            <p className="text-petit text-texte-doux mb-3">
              Détermine l'accès à l'administration. Modifiable à tout moment.
            </p>
            <div className="flex flex-wrap gap-2">
              {casquettesPossibles.map((c) => (
                <button
                  key={c.valeur}
                  onClick={() => changer(c.valeur)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-menu transition-colors",
                    c.valeur === casquette
                      ? "border-bleu bg-bleu-pale text-bleu-sombre font-medium"
                      : "border-bord hover:bg-surface-creuse",
                  )}
                >
                  {c.libelle}
                </button>
              ))}
            </div>
          </Card>
        )}

        {/* Préférences d'affichage */}
        <Card>
          <CardTitre>Affichage</CardTitre>
          <label className="flex items-center justify-between gap-4 cursor-pointer">
            <span className="text-menu">
              Menu latéral réduit au démarrage
              <span className="block text-petit text-texte-doux">
                Le menu s'ouvre en version compacte (icônes seules) au chargement de l'application.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={menuReduit}
              onChange={basculerMenuReduit}
              className="size-5 shrink-0 rounded border-bord-fort text-bleu focus:ring-bleu"
            />
          </label>
        </Card>

        {/* Modèles IA */}
        <CarteModelesIA />

        {/* Session */}
        <Card>
          <CardTitre>Session</CardTitre>
          <Button
            variant="grave"
            onClick={async () => {
              await logout()
              navigate("/connexion")
            }}
          >
            <LogOut className="size-4" /> Déconnexion
          </Button>
        </Card>
      </div>
    </AppShell>
  )
}

/** Choix du fournisseur IA par famille de tâches (transcription, correction,
 * analyse). Config globale : lisible par tous, modifiable par l'administrateur
 * seul (`modifiable`, renvoyé par l'API). Le détail vit côté serveur dans
 * `data/preferences_modeles.json` (D-CEO-44). */
export function CarteModelesIA() {
  const { notifier } = useToast()
  const [data, setData] = useState<PreferencesModelesReponse | null>(null)
  const [brouillon, setBrouillon] = useState<Record<string, PreferenceTache>>({})
  const [chargement, setChargement] = useState(true)
  const [enregistrement, setEnregistrement] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    let vivant = true
    adminApi
      .preferencesModeles()
      .then((r) => {
        if (!vivant) return
        setData(r)
        setBrouillon(structuredClone(r.preferences))
      })
      .catch((e) => {
        if (!vivant) return
        setErreur(e instanceof ApiError ? e.message : "Chargement impossible.")
      })
      .finally(() => vivant && setChargement(false))
    return () => {
      vivant = false
    }
  }, [])

  if (chargement) {
    return (
      <Card>
        <CardTitre>Modèles IA</CardTitre>
        <p className="text-menu text-texte-doux">Chargement…</p>
      </Card>
    )
  }

  if (erreur || !data) {
    return (
      <Card>
        <CardTitre>Modèles IA</CardTitre>
        <p className="text-menu text-rouge">{erreur ?? "Indisponible."}</p>
      </Card>
    )
  }

  const modifiable = data.modifiable
  const sale =
    JSON.stringify(brouillon) !== JSON.stringify(data.preferences)

  function definir(tache: string, champ: keyof PreferenceTache, valeur: string) {
    setBrouillon((b) => ({ ...b, [tache]: { ...b[tache], [champ]: valeur } }))
  }

  async function enregistrer() {
    setEnregistrement(true)
    try {
      const r = await adminApi.majPreferencesModeles({ preferences: brouillon })
      setData(r)
      setBrouillon(structuredClone(r.preferences))
      notifier("Préférences enregistrées — effet aux prochaines corrections.")
    } catch (e) {
      notifier(
        e instanceof ApiError ? e.message : "Enregistrement impossible.",
        "erreur",
      )
    } finally {
      setEnregistrement(false)
    }
  }

  return (
    <Card>
      <CardTitre>Modèles IA</CardTitre>
      <p className="text-petit text-texte-doux mb-4">
        Fournisseur utilisé à chaque étape de la correction. Réglage commun à
        toute la plateforme.
        {!modifiable && " Modifiable par un administrateur uniquement."}
      </p>

      <div className="flex flex-col gap-5">
        {data.taches.map((tache) => {
          const choix = brouillon[tache.cle]
          return (
            <div key={tache.cle}>
              <div className="text-menu font-medium mb-2">{tache.libelle}</div>
              <div className="flex flex-wrap gap-2">
                {tache.fournisseurs.map((f) => {
                  const actif = choix?.fournisseur === f.cle
                  const desactive = !modifiable || (!f.cle_presente && !actif)
                  return (
                    <button
                      key={f.cle}
                      type="button"
                      disabled={desactive}
                      onClick={() => definir(tache.cle, "fournisseur", f.cle)}
                      className={cn(
                        "rounded-lg border px-3 py-1.5 text-menu transition-colors",
                        actif
                          ? "border-bleu bg-bleu-pale text-bleu-sombre font-medium"
                          : "border-bord hover:bg-surface-creuse",
                        desactive && "opacity-40 cursor-not-allowed hover:bg-transparent",
                      )}
                    >
                      {f.libelle}
                      {!f.cle_presente && (
                        <span className="block text-petit text-texte-doux">clé absente</span>
                      )}
                    </button>
                  )
                })}
              </div>

              {choix?.fournisseur === "claude" && (
                <div className="flex gap-2 mt-2">
                  {data.variantes_claude.map((v) => (
                    <button
                      key={v}
                      type="button"
                      disabled={!modifiable}
                      onClick={() => definir(tache.cle, "variante_claude", v)}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-petit transition-colors capitalize",
                        choix.variante_claude === v
                          ? "border-bleu bg-bleu-pale text-bleu-sombre font-medium"
                          : "border-bord hover:bg-surface-creuse",
                        !modifiable && "opacity-40 cursor-not-allowed hover:bg-transparent",
                      )}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {modifiable && (
        <div className="mt-5">
          <Button onClick={enregistrer} disabled={!sale || enregistrement}>
            {enregistrement ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </div>
      )}
    </Card>
  )
}
