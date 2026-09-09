import type { ReactNode } from "react"
import { Download, Eye, FileText, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/** Une ligne de fichier téléchargeable : icône, nom clair, courte description,
 * puis les actions Voir / Télécharger (et une action libre facultative).
 *
 * Regroupées sous un même titre, ces lignes forment la section « Documents »
 * d'une page de résultats — le contenu se lit d'abord, les fichiers se
 * récupèrent ensuite. Utilisée par la page de correction (`Suivre.tsx`) et le
 * parcours (`SessionDetail.tsx`). */
export function LigneDocument({
  icon: Icon = FileText,
  titre,
  description,
  hrefVoir,
  hrefTelecharger,
  extra,
  className,
}: {
  icon?: LucideIcon
  titre: string
  description?: ReactNode
  hrefVoir?: string
  hrefTelecharger?: string
  /** Action supplémentaire (ex. « Déposer la copie ») — passe sous les boutons. */
  extra?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-bord py-3.5", className)}>
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-bleu-pale text-bleu-sombre">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1 basis-44">
        <p className="text-menu font-medium text-texte">{titre}</p>
        {description && <p className="text-petit text-texte-doux leading-snug">{description}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {hrefVoir && (
          <a
            href={hrefVoir}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-bord px-3 text-petit font-medium text-texte transition-colors hover:bg-surface-creuse"
          >
            <Eye className="size-3.5" /> Voir
          </a>
        )}
        {hrefTelecharger && (
          <a
            href={hrefTelecharger}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-bord px-3 text-petit font-medium text-texte transition-colors hover:bg-surface-creuse"
          >
            <Download className="size-3.5" /> Télécharger
          </a>
        )}
      </div>
      {extra && <div className="w-full sm:ml-2 sm:w-auto">{extra}</div>}
    </div>
  )
}
