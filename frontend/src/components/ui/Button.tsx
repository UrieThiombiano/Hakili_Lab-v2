import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Loader2 } from "lucide-react"
import type { ButtonHTMLAttributes } from "react"

const boutonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-menu font-medium transition-all duration-150 ease-out disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap active:scale-[0.97]",
  {
    variants: {
      variant: {
        primaire: "bg-bleu text-white hover:bg-bleu-sombre shadow-carte hover:shadow-haute",
        discret: "bg-surface text-texte border border-bord-fort hover:bg-surface-creuse hover:border-bord-fort",
        grave: "bg-rouge text-white hover:brightness-90 shadow-carte hover:shadow-haute",
        fantome: "text-bleu hover:bg-bleu-pale",
      },
      taille: {
        defaut: "h-10 px-4",
        petit: "h-8 px-3 text-[length:var(--text-petit)]",
        grand: "h-12 px-6 text-[length:var(--text-corps)]",
      },
    },
    defaultVariants: { variant: "primaire", taille: "defaut" },
  },
)

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof boutonVariants> {
  chargement?: boolean
}

export function Button({ className, variant, taille, chargement, disabled, children, ...props }: ButtonProps) {
  return (
    <button className={cn(boutonVariants({ variant, taille }), className)} disabled={disabled || chargement} {...props}>
      {chargement && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  )
}
