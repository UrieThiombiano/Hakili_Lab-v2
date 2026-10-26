import { Loader2 } from "lucide-react"

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-texte-doux py-8 justify-center">
      <Loader2 className="size-5 animate-spin" />
      {label && <span className="text-menu">{label}</span>}
    </div>
  )
}

export function EtatVide({ titre, description }: { titre: string; description?: string }) {
  return (
    <div className="text-center py-12 text-texte-doux">
      <p className="text-menu font-medium text-texte">{titre}</p>
      {description && <p className="text-petit mt-1">{description}</p>}
    </div>
  )
}

export function EtatErreur({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-te-cpt-bd bg-rouge-pale text-rouge px-4 py-3 text-menu">
      {message}
    </div>
  )
}
