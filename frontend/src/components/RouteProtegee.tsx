import { Navigate } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { Spinner } from "@/components/ui/Etat"
import type { ReactNode } from "react"

/** Équivalent de `connexion_requise` (`comptes/session.py`). */
export function RouteProtegee({ children }: { children: ReactNode }) {
  const { personne, pret } = useAuth()
  if (!pret) return <Spinner label="Chargement…" />
  if (!personne) return <Navigate to="/connexion" replace />
  return <>{children}</>
}

/** Équivalent de `admin_requis`. */
export function RouteAdmin({ children }: { children: ReactNode }) {
  const { personne, pret, casquette } = useAuth()
  if (!pret) return <Spinner label="Chargement…" />
  if (!personne) return <Navigate to="/connexion" replace />
  if (casquette !== "administrateur") return <Navigate to="/a-propos" replace />
  return <>{children}</>
}
