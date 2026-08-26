import { FileText, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/** Lien vers un PDF généré à la demande : « Voir » ouvre un aperçu (nouvel
 * onglet, `Content-Disposition: inline`), « Télécharger » l'enregistre
 * (`attachment`) — sans ça, la seule façon de voir un document était de le
 * télécharger d'abord. Même mots que `ProfilEleve.tsx` (déjà ce patron pour
 * les documents d'une copie), pour ne pas introduire un second vocabulaire. */
export function LienPdf({
  label,
  hrefVoir,
  hrefTelecharger,
  icon: Icon = FileText,
  className,
}: {
  label: string
  hrefVoir: string
  hrefTelecharger: string
  icon?: LucideIcon
  className?: string
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <Icon className="size-3.5 shrink-0 text-texte-faible" />
      {label}
      <a href={hrefVoir} target="_blank" rel="noreferrer" className="text-bleu hover:text-bleu-sombre">
        Voir
      </a>
      <a href={hrefTelecharger} className="text-bleu hover:text-bleu-sombre">
        Télécharger
      </a>
    </span>
  )
}
