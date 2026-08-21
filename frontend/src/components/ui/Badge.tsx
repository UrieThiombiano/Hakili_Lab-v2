import { cn } from "@/lib/utils"
import type { EtatAcces, EtatProbleme, EtatSession, Palier, Tendance } from "@/types/api"

function Pastille({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-rond border px-2.5 py-0.5 text-petit font-medium leading-tight", className)}>
      {children}
    </span>
  )
}

const LIBELLES_TENDANCE: Record<Tendance, string> = {
  progresse: "Progresse",
  stagne: "Stagne",
  regresse: "En baisse",
  insuffisant: "Pas assez de données",
}
const STYLE_TENDANCE: Record<Tendance, string> = {
  progresse: "bg-vert text-white border-transparent",
  stagne: "bg-orange text-white border-transparent",
  regresse: "bg-rouge text-white border-transparent",
  insuffisant: "bg-gris text-white border-transparent",
}

export function TendanceBadge({ tendance }: { tendance: Tendance }) {
  return <Pastille className={STYLE_TENDANCE[tendance]}>{LIBELLES_TENDANCE[tendance]}</Pastille>
}

/** Accès plateforme (`suivi_web/views.py::personnel`) — même taxonomie de
 * couleur que `TendanceBadge` (regresse/stagne/progresse), le libellé vient
 * du backend plutôt que d'un dictionnaire fixe ici. */
const STYLE_ACCES: Record<EtatAcces, string> = {
  progresse: "bg-vert text-white border-transparent",
  stagne: "bg-orange text-white border-transparent",
  regresse: "bg-rouge text-white border-transparent",
}

export function AccesBadge({ etat, libelle }: { etat: EtatAcces; libelle: string }) {
  return <Pastille className={STYLE_ACCES[etat]}>{libelle}</Pastille>
}

/** 7 types d'erreur, liste fermée (protocole-v2.md §3) — mêmes teintes que
 * `templates_django/base.html` (`.pastille.te-*`). */
const LIBELLES_TYPE_ERREUR: Record<string, string> = {
  PRQ: "Prérequis manquant",
  CPT: "Conceptuelle",
  MOD: "Modélisation",
  PRC: "Procédurale",
  CNS: "Connaissance absente",
  RED: "Rédaction",
  ATT: "Inattention",
}
const STYLE_TYPE_ERREUR: Record<string, string> = {
  CPT: "bg-te-cpt-bg text-te-cpt border-te-cpt-bd",
  PRQ: "bg-te-prq-bg text-te-prq border-te-prq-bd",
  MOD: "bg-te-mod-bg text-te-mod border-te-mod-bd",
  PRC: "bg-te-prc-bg text-te-prc border-te-prc-bd",
  CNS: "bg-te-cns-bg text-te-cns border-te-cns-bd",
  RED: "bg-te-red-bg text-te-red border-te-red-bd",
  ATT: "bg-te-att-bg text-te-att border-te-att-bd",
}

export function TypeErreurBadge({ code }: { code: string }) {
  return (
    <Pastille className={STYLE_TYPE_ERREUR[code] ?? "bg-gris-pale text-texte-doux border-bord-fort"}>
      {code} — {LIBELLES_TYPE_ERREUR[code] ?? code}
    </Pastille>
  )
}

const LIBELLES_ETAT_PROBLEME: Record<EtatProbleme, string> = {
  hypothese: "Hypothèse",
  confirme: "Confirmé",
  ecarte: "Écarté",
  en_remediation: "En remédiation",
  resolu: "Résolu",
  non_resolu: "Non résolu",
  regresse: "Régressé",
  clos: "Clos",
}
const STYLE_ETAT_PROBLEME: Record<EtatProbleme, string> = {
  hypothese: "bg-surface text-texte-doux border-bord-fort",
  confirme: "bg-bleu-pale text-bleu-sombre border-transparent",
  ecarte: "bg-gris-pale text-gris border-bord-fort",
  en_remediation: "bg-orange-pale text-orange border-transparent",
  resolu: "bg-vert-pale text-vert border-transparent",
  non_resolu: "bg-rouge-pale text-rouge border-transparent",
  regresse: "bg-rouge-pale text-rouge border-transparent",
  clos: "bg-vert-pale text-vert border-transparent",
}

export function EtatProblemeBadge({ etat }: { etat: EtatProbleme }) {
  return <Pastille className={STYLE_ETAT_PROBLEME[etat]}>{LIBELLES_ETAT_PROBLEME[etat]}</Pastille>
}

const LIBELLES_ETAT_SESSION: Record<EtatSession, string> = {
  diagnostic: "Diagnostic en cours",
  attente_inscription: "Plan établi",
  remediation: "Inscrit en remédiation",
  close: "Cycle clos",
  sans_suite: "Sans suite",
  hors_dispositif: "Hors dispositif",
  abandonnee: "Abandonnée",
}
const STYLE_ETAT_SESSION: Record<EtatSession, string> = {
  diagnostic: "bg-bleu-pale text-bleu-sombre border-transparent",
  attente_inscription: "bg-orange-pale text-orange border-transparent",
  remediation: "bg-bleu-pale text-bleu-sombre border-transparent",
  close: "bg-gris-pale text-gris border-bord-fort",
  sans_suite: "bg-vert-pale text-vert border-transparent",
  hors_dispositif: "bg-rouge-pale text-rouge border-transparent",
  abandonnee: "bg-gris-pale text-gris border-bord-fort",
}

export function EtatSessionBadge({ etat }: { etat: EtatSession }) {
  return <Pastille className={STYLE_ETAT_SESSION[etat]}>{LIBELLES_ETAT_SESSION[etat]}</Pastille>
}

const LIBELLES_PALIER: Record<string, string> = {
  A: "A — ciblé (< 8 h)",
  B: "B — complet (8-20 h)",
  C: "C — hors dispositif (> 20 h)",
}
const STYLE_PALIER: Record<string, string> = {
  A: "text-vert",
  B: "text-orange",
  C: "text-rouge",
}

export function PalierBadge({ palier }: { palier: Palier }) {
  if (!palier) return null
  return <span className={cn("font-bold", STYLE_PALIER[palier])}>{LIBELLES_PALIER[palier] ?? palier}</span>
}
