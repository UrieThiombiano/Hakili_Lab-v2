import { useEffect, type RefObject } from "react"
import { useBlocker } from "react-router-dom"
import { Save, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/Button"

/** Une analyse terminée n'est conservée que sur « Sauvegarder » : quitter la
 * page sans y penser la perd. Tant qu'elle n'est pas sauvegardée, toute sortie
 * passe par un choix explicite — sauvegarder et partir, partir sans
 * sauvegarder, ou rester.
 *
 * - Navigation dans l'application (liens, menu, bouton précédent) : bloquée
 *   par `useBlocker`, puis tranchée dans le toast ci-dessous.
 * - Fermeture de l'onglet, rechargement, URL tapée : le navigateur n'autorise
 *   que sa propre boîte de confirmation (`beforeunload`), sans texte
 *   personnalisé — c'est la seule protection possible à ce niveau.
 *
 * `sortieLibre` laisse passer une sortie déjà décidée ailleurs (copie
 * supprimée). La page de connexion n'est pas gardée : la déconnexion a déjà eu
 * lieu quand on y navigue, une sauvegarde échouerait. */
export function GardeSauvegarde({
  actif,
  eleve,
  sortieLibre,
  enCours,
  erreur,
  onSauvegarder,
}: {
  actif: boolean
  eleve: string
  sortieLibre: RefObject<boolean>
  enCours: boolean
  erreur: boolean
  onSauvegarder: (apres: () => void) => void
}) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      actif &&
      !sortieLibre.current &&
      nextLocation.pathname !== "/connexion" &&
      currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!actif) return
    function avantDechargement(e: BeforeUnloadEvent) {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", avantDechargement)
    return () => window.removeEventListener("beforeunload", avantDechargement)
  }, [actif])

  const bloque = blocker.state === "blocked"

  useEffect(() => {
    if (!bloque) return
    function echap(e: KeyboardEvent) {
      if (e.key === "Escape" && !enCours) blocker.reset?.()
    }
    window.addEventListener("keydown", echap)
    return () => window.removeEventListener("keydown", echap)
  }, [bloque, enCours, blocker])

  if (!bloque) return null

  return (
    <div
      role="alertdialog"
      aria-modal="false"
      aria-labelledby="garde-titre"
      aria-describedby="garde-message"
      className="fixed bottom-4 right-4 z-50 w-[min(27rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-orange/40 bg-surface shadow-haute animate-entree-toast"
    >
      <div className="h-1 bg-orange" />
      <div className="p-4">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-rond bg-orange-pale text-orange">
            <TriangleAlert className="size-5" />
          </span>
          <div className="min-w-0">
            <p id="garde-titre" className="text-menu font-semibold text-marine">
              Attention : analyse non sauvegardée
            </p>
            <p id="garde-message" className="mt-0.5 text-petit text-texte-doux">
              Si vous quittez cette page sans sauvegarder, la note, le rapport, le plan de remédiation et le diagnostic
              {eleve ? <> de <strong className="font-medium text-texte">{eleve}</strong></> : null} ne seront pas
              ajoutés au dossier de l'élève.
            </p>
            {erreur && (
              <p className="mt-1.5 text-petit text-rouge">La sauvegarde a échoué. Réessayez, ou quittez sans sauvegarder.</p>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row-reverse sm:flex-wrap">
          <Button autoFocus taille="petit" chargement={enCours} onClick={() => onSauvegarder(() => blocker.proceed?.())}>
            {!enCours && <Save className="size-3.5" />} Sauvegarder et quitter
          </Button>
          <Button variant="discret" taille="petit" disabled={enCours} onClick={() => blocker.proceed?.()}>
            Quitter sans sauvegarder
          </Button>
          <Button variant="fantome" taille="petit" disabled={enCours} onClick={() => blocker.reset?.()} className="sm:mr-auto">
            Rester sur la page
          </Button>
        </div>
      </div>
    </div>
  )
}
