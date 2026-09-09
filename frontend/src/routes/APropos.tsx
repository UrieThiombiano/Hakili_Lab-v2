import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import heroEleve from "@/assets/eleve-tableau.jpg"
import {
  FileEdit,
  Search,
  ShieldCheck,
  ClipboardList,
  Users,
  RefreshCw,
  CalendarCheck2,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
} from "lucide-react"

const ETAPES = [
  {
    badge: "Étape 1 : T0",
    titre: "Test de niveau",
    icon: FileEdit,
    texte: "Un sujet standard, dans les conditions d'un contrôle normal. Le système corrige et repère les pistes de difficulté.",
  },
  {
    badge: "Diagnostic",
    titre: "Des pistes, pas un verdict",
    icon: Search,
    texte: "Une erreur peut venir d'une vraie lacune… ou d'une étourderie. On ne s'arrête pas à cette première impression.",
  },
  {
    badge: "Étape 2 : T1",
    titre: "Test de confirmation",
    icon: ShieldCheck,
    texte: "Un second test, court et ciblé, départage chaque piste : lacune réelle ou simple maladresse.",
    aparte: "Aucune lacune confirmée ? Retour en cours, sans remédiation facturée.",
  },
  {
    badge: "Plan",
    titre: "Un plan chiffré",
    icon: ClipboardList,
    texte: "Un temps de travail réaliste (30 min à 4h) par lacune, ordonné selon les prérequis.",
  },
  {
    badge: "Accompagnement",
    titre: "Le tuteur prend le relais",
    icon: Users,
    texte: "Un tuteur humain — pas une IA — accompagne votre enfant, séance après séance, sur le plan établi.",
  },
  {
    badge: "Étape 3 : T2",
    titre: "Vérification",
    icon: RefreshCw,
    texte: "Un nouveau test porte sur ce qui a été travaillé. Acquis validé, ou reprise ciblée jusqu'à maîtrise.",
  },
  {
    badge: "Étape 4 : T3 & T4",
    titre: "Le suivi dans la durée",
    icon: CalendarCheck2,
    texte: "45 jours puis 3 mois plus tard, on revérifie discrètement que ça tient dans la durée.",
  },
]

const CONFIANCE = [
  {
    titre: "Diagnostic avant remédiation",
    icon: CheckCircle2,
    texte: "On ne vend jamais une heure de cours sans savoir précisément à quoi elle sert.",
  },
  {
    titre: "Honnête sur les cas lourds",
    icon: AlertTriangle,
    texte:
      "Si les besoins dépassent ce qu'une remédiation courte peut résoudre, on le dit clairement plutôt que de promettre un miracle en quelques semaines.",
  },
  {
    titre: "Un humain, toujours",
    icon: UserCheck,
    texte: "L'IA diagnostique et prépare le plan ; un enseignant accompagne. Elle ne remplace jamais le tuteur.",
  },
]

const CHIFFRES = [
  { valeur: "0h", label: "de remédiation vendue sans lacune confirmée" },
  { valeur: "2", label: "tests avant toute décision — niveau (T0), puis confirmation (T1)" },
  { valeur: "45j + 3 mois", label: "de vérification de la rétention après le parcours" },
]

export default function APropos() {
  return (
    <AppShell titre="À propos">
      <div className="flex flex-col gap-14 pb-10">
        {/* Hero */}
        <div
          className="relative rounded-2xl overflow-hidden h-[380px] lg:h-[460px] bg-cover bg-center shadow-haute"
          style={{ backgroundImage: `url(${heroEleve})` }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-marine via-marine/85 lg:via-marine/60 to-marine/10" />
          <div className="relative h-full flex flex-col justify-center gap-5 px-6 sm:px-10 lg:px-14 max-w-2xl">
            <span className="text-petit font-semibold uppercase tracking-[0.16em] text-white/70">Maïya</span>
            <h2 className="text-[2rem] leading-[1.15] sm:text-[2.5rem] sm:leading-[1.12] font-bold text-white">
              Chaque lacune, confirmée avant d'être travaillée.
            </h2>
            <p className="text-lead text-white/85 leading-relaxed max-w-lg">
              Un diagnostic en deux temps, un plan chiffré, un tuteur humain — pour que chaque heure de remédiation
              corresponde à un besoin réel, jamais deviné.
            </p>
          </div>
        </div>

        {/* Intro + chiffres clés */}
        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr] items-stretch">
          <Card className="flex items-center">
            <p className="text-lead text-texte leading-relaxed">
              Beaucoup de dispositifs de soutien scolaire vendent des heures de cours sans savoir précisément ce qui
              manque à l'élève. Maïya fait l'inverse : chaque heure de remédiation proposée correspond à une
              difficulté identifiée, puis <strong className="font-semibold">confirmée</strong> — jamais devinée.
            </p>
          </Card>
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-4">
            {CHIFFRES.map(({ valeur, label }) => (
              <Card key={label} variant="appel" className="flex flex-col gap-1">
                <span className="text-chiffre font-bold text-marine leading-none">{valeur}</span>
                <span className="text-petit text-texte-doux leading-snug">{label}</span>
              </Card>
            ))}
          </div>
        </div>

        {/* Étapes */}
        <div>
          <span className="text-petit font-semibold uppercase tracking-[0.16em] text-bleu-sombre">Méthode</span>
          <h2 className="text-h1 font-bold mt-1 mb-6">Le parcours, étape par étape</h2>
          <ol className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
            {ETAPES.map(({ badge, titre, icon: Icon, texte, aparte }) => (
              <li key={titre}>
                <Card className="flex flex-col gap-2.5 h-full p-4 rounded-xl hover:shadow-haute">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center size-8 rounded-lg bg-bleu-pale text-bleu-sombre shrink-0">
                      <Icon className="size-4" />
                    </div>
                    <span className="w-5 h-[3px] rounded-rond bg-orange" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-micro font-semibold text-bleu-sombre uppercase tracking-wide">{badge}</span>
                    <h3 className="text-petit font-semibold">{titre}</h3>
                    <p className="text-micro text-texte-doux leading-relaxed">{texte}</p>
                    {aparte && (
                      <p className="text-micro text-texte-doux italic border-l-2 border-orange pl-2 mt-1.5 leading-relaxed">
                        {aparte}
                      </p>
                    )}
                  </div>
                </Card>
              </li>
            ))}
          </ol>
        </div>

        {/* Confiance */}
        <div>
          <span className="text-petit font-semibold uppercase tracking-[0.16em] text-bleu-sombre">Confiance</span>
          <h2 className="text-h1 font-bold mt-1 mb-6">Pourquoi les familles peuvent nous faire confiance</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {CONFIANCE.map(({ titre, icon: Icon, texte }) => (
              <Card key={titre} className="flex flex-col gap-2">
                <Icon className="size-5 text-bleu" />
                <h3 className="text-menu font-semibold">{titre}</h3>
                <p className="text-petit text-texte-doux leading-relaxed">{texte}</p>
              </Card>
            ))}
          </div>
        </div>

        {/* Citation */}
        <Card variant="appel" className="max-w-3xl mx-auto text-center py-8 px-8">
          <p className="text-h2 font-semibold text-texte leading-snug">
            « 14 problèmes ouverts, 11 résolus en quatre semaines, 9 encore acquis 45 jours plus tard. »
          </p>
          <p className="text-petit text-texte-doux mt-3">
            Le type de compte rendu reçu par une famille en fin de parcours — clair, chiffré, sans jargon.
          </p>
        </Card>
      </div>
    </AppShell>
  )
}
