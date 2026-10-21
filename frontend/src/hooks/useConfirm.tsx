import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react"
import { TriangleAlert } from "lucide-react"

interface DemandeConfirmation {
  titre?: string
  message: string
  texteConfirmer?: string
  texteAnnuler?: string
}

interface ConfirmState {
  confirmer: (demande: DemandeConfirmation | string) => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmState | null>(null)

/** Remplace `window.confirm()` — un dialogue signé Hakili Lab (fond
 * assombri, sans flou, accent orange) plutôt que la boîte "localhost
 * indique…" du navigateur. `confirmer()` renvoie une promesse résolue à
 * `true`/`false`, exactement comme l'appel synchrone qu'elle remplace. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [demande, setDemande] = useState<DemandeConfirmation | null>(null)
  const resolveRef = useRef<(v: boolean) => void>(null)

  const confirmer = useCallback((d: DemandeConfirmation | string) => {
    setDemande(typeof d === "string" ? { message: d } : d)
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve
    })
  }, [])

  function repondre(v: boolean) {
    setDemande(null)
    resolveRef.current?.(v)
  }

  return (
    <ConfirmContext.Provider value={{ confirmer }}>
      {children}
      {demande && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-marine/50 p-4" onClick={() => repondre(false)}>
          <div
            role="alertdialog"
            aria-modal="true"
            className="w-full max-w-sm rounded-lg border border-bord bg-surface p-5 shadow-haute animate-entree-menu"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3 mb-4">
              <span className="flex items-center justify-center size-9 rounded-rond bg-orange-pale text-orange shrink-0">
                <TriangleAlert className="size-5" />
              </span>
              <div>
                {demande.titre && <p className="text-menu font-semibold text-marine mb-0.5">{demande.titre}</p>}
                <p className="text-petit text-texte-doux">{demande.message}</p>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => repondre(false)}
                className="h-10 px-4 rounded-lg text-menu font-medium bg-surface text-texte border border-bord-fort hover:bg-surface-creuse transition-colors duration-150"
              >
                {demande.texteAnnuler ?? "Annuler"}
              </button>
              <button
                onClick={() => repondre(true)}
                autoFocus
                className="h-10 px-4 rounded-lg text-menu font-medium bg-orange text-white hover:brightness-90 shadow-carte hover:shadow-haute transition-all duration-150"
              >
                {demande.texteConfirmer ?? "Confirmer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm(): ConfirmState {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error("useConfirm doit être utilisé sous <ConfirmProvider>")
  return ctx
}
