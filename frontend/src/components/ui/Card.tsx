import { cn } from "@/lib/utils"
import { useRevealOnScroll } from "@/hooks/useRevealOnScroll"
import type { HTMLAttributes } from "react"

/** Port de `.carte` (base.html) — variantes `appel` (fond bleu pâle, mise
 * en avant) et `plate` (sans ombre, encart dans un encart). Se révèle au
 * défilement (`useRevealOnScroll`) : chaque carte de l'app en profite sans
 * réglage par page. */
export function Card({ className, variant, ...props }: HTMLAttributes<HTMLDivElement> & { variant?: "appel" | "plate" }) {
  const { ref, visible } = useRevealOnScroll<HTMLDivElement>()
  return (
    <div
      ref={ref}
      className={cn(
        "au-scroll rounded-lg border border-bord bg-surface p-5 shadow-carte transition-shadow duration-200",
        visible && "est-visible",
        variant === "appel" && "bg-bleu-pale border-transparent shadow-none",
        variant === "plate" && "shadow-none",
        className,
      )}
      {...props}
    />
  )
}

export function CardTitre({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-h3 font-semibold text-marine mb-3", className)} {...props} />
}
