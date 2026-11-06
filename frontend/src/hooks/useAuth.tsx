import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { authApi } from "@/lib/api"
import type { CasquettePossible, Personne } from "@/types/api"

interface AuthState {
  personne: Personne | null
  casquette: string
  casquettesPossibles: CasquettePossible[]
  accesLibre: boolean
  pret: boolean
  login: (cle: string, pin: string) => Promise<void>
  logout: () => Promise<void>
  changerCasquette: (casquette: string) => Promise<void>
  rafraichir: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [personne, setPersonne] = useState<Personne | null>(null)
  const [casquette, setCasquette] = useState("")
  const [casquettesPossibles, setCasquettesPossibles] = useState<CasquettePossible[]>([])
  const [accesLibre, setAccesLibre] = useState(false)
  const [pret, setPret] = useState(false)

  async function rafraichir() {
    const moi = await authApi.me()
    setPersonne(moi.personne)
    setCasquette(moi.casquette ?? "")
    setCasquettesPossibles(moi.casquettes_possibles ?? [])
    setAccesLibre(moi.acces_libre)
  }

  useEffect(() => {
    rafraichir().finally(() => setPret(true))
  }, [])

  async function login(cle: string, pin: string) {
    await authApi.login(cle, pin)
    await rafraichir()
  }

  async function logout() {
    await authApi.logout()
    setPersonne(null)
    setCasquette("")
    setCasquettesPossibles([])
  }

  async function changerCasquette(nouvelleCasquette: string) {
    await authApi.casquette(nouvelleCasquette)
    setCasquette(nouvelleCasquette)
  }

  return (
    <AuthContext.Provider value={{ personne, casquette, casquettesPossibles, accesLibre, pret, login, logout, changerCasquette, rafraichir }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth doit être utilisé sous <AuthProvider>")
  return ctx
}
