import { lazy, Suspense } from "react"
import { Routes, Route, Navigate } from "react-router-dom"
import { RouteProtegee, RouteAdmin } from "@/components/RouteProtegee"
import { Spinner } from "@/components/ui/Etat"

// Vitrine publique : chargée à part pour que GSAP/Lenis ne pèsent pas sur l'app.
const Accueil = lazy(() => import("@/routes/Accueil"))
const Connexion = lazy(() => import("@/routes/Connexion"))
const Administration = lazy(() => import("@/routes/Administration"))
const Parcours = lazy(() => import("@/routes/Parcours"))
const ProfilEleve = lazy(() => import("@/routes/ProfilEleve"))
const SessionDetail = lazy(() => import("@/routes/SessionDetail"))
const Sujets = lazy(() => import("@/routes/Sujets"))
const APropos = lazy(() => import("@/routes/APropos"))
const Parametres = lazy(() => import("@/routes/Parametres"))
const NouvelleCorrection = lazy(() => import("@/routes/correction/Nouvelle"))
const Lot = lazy(() => import("@/routes/correction/Lot"))
const SoumettreConfirmation = lazy(() => import("@/routes/correction/SoumettreConfirmation"))
const SoumettreVerification = lazy(() => import("@/routes/correction/SoumettreVerification"))
const Suivre = lazy(() => import("@/routes/correction/Suivre"))

function ChargementPage() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner label="Chargement…" />
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<ChargementPage />}>
      <Routes>
        <Route path="/connexion" element={<Connexion />} />
        {/* Fond marine pendant le chargement de la vitrine : pas d'écran blanc
            « Chargement… » avant le hero (lui-même marine). */}
        <Route path="/" element={<Suspense fallback={<div className="min-h-screen bg-marine" />}><Accueil /></Suspense>} />
        <Route path="/a-propos" element={<RouteProtegee><APropos /></RouteProtegee>} />
        <Route path="/parcours" element={<RouteProtegee><Parcours /></RouteProtegee>} />
        <Route path="/eleves/:jeton" element={<RouteProtegee><ProfilEleve /></RouteProtegee>} />
        <Route path="/sessions/:jeton" element={<RouteProtegee><SessionDetail /></RouteProtegee>} />
        <Route path="/sujets" element={<RouteProtegee><Sujets /></RouteProtegee>} />
        <Route path="/parametres" element={<RouteProtegee><Parametres /></RouteProtegee>} />
        <Route path="/administration" element={<RouteAdmin><Administration /></RouteAdmin>} />
        <Route path="/analyse-de-copie" element={<RouteProtegee><NouvelleCorrection /></RouteProtegee>} />
        <Route path="/corrections/nouvelle" element={<RouteProtegee><NouvelleCorrection /></RouteProtegee>} />
        <Route path="/corrections/lot" element={<RouteProtegee><Lot /></RouteProtegee>} />
        <Route path="/corrections/confirmation/:jeton" element={<RouteProtegee><SoumettreConfirmation /></RouteProtegee>} />
        <Route path="/corrections/verification/:jeton/:type" element={<RouteProtegee><SoumettreVerification /></RouteProtegee>} />
        <Route path="/corrections/:jeton" element={<RouteProtegee><Suivre /></RouteProtegee>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
