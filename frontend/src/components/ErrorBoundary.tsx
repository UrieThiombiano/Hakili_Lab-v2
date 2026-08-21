import { Component, type ReactNode } from "react"

interface Props {
  children: ReactNode
}
interface State {
  erreur: Error | null
}

/** Filet de sécurité : sans elle, une exception de rendu (ex. un champ API
 * dont la forme diffère du type attendu) laisse une page blanche sans
 * indice — constaté en vérifiant `/sujets` (`niveaux` rendu en chaîne côté
 * API, pas en tableau). Mieux vaut un message qu'un écran vide. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { erreur: null }

  static getDerivedStateFromError(erreur: Error): State {
    return { erreur }
  }

  componentDidCatch(erreur: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", erreur, info.componentStack)
  }

  render() {
    if (this.state.erreur) {
      return (
        <div className="min-h-screen flex items-center justify-center fond-cahier px-4">
          <div className="max-w-md rounded-lg border border-bord bg-surface p-6 shadow-carte text-center">
            <p className="text-h3 font-semibold text-marine mb-2">Une erreur est survenue</p>
            <p className="text-petit text-texte-doux mb-4">{this.state.erreur.message}</p>
            <button onClick={() => window.location.assign("/")} className="text-menu text-bleu hover:text-bleu-sombre">
              Retour à l'accueil
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
