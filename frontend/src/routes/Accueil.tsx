import { useEffect, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { SplitText } from "gsap/SplitText"
import { useGSAP } from "@gsap/react"
import Lenis from "lenis"
import "lenis/dist/lenis.css"
import {
  ArrowRight,
  ArrowUpRight,
  Download,
  GraduationCap,
  Map,
  MapPin,
  Mail,
  Phone,
  Route as RouteIcon,
  School,
  Target,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react"
import { cn } from "@/lib/utils"
import logoHakili from "@/assets/vitrine/logo-hakili-lab.webp"
import photoHero from "@/assets/vitrine/hero.webp"
import photoPissy from "@/assets/vitrine/pissy.webp"
import photoTampouy from "@/assets/vitrine/tampouy.webp"
import photoSaaba from "@/assets/vitrine/saaba.webp"

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

/* Page publique (vitrine) servie sur `/` — la seule page de l'app visible
 * sans connexion. Elle vend Maya et HAKILI Lab sans rien dévoiler du
 * protocole interne (tests T0→T5, paliers, coûts, référentiel) : on montre
 * le résultat pour la famille, jamais la mécanique. Contenus repris du site
 * officiel hakililab.com (chiffres, centres, contacts, formulaire).
 *
 * Mouvement : défilement doux (Lenis) + GSAP/ScrollTrigger, branchés sur des
 * attributs `data-*` plutôt que sur chaque composant. Tout est déclaré dans
 * un `gsap.matchMedia` « no-preference » : sans JS, avec « réduire les
 * animations » ou sous jsdom, la page s'affiche directement dans son état
 * final, rien n'est caché par défaut. */

const SITE_OFFICIEL = "https://hakililab.com/"
const FORMULAIRE_INSCRIPTION = "https://forms.gle/FMWP9KZtjrxyVT3x6"
const PLAQUETTE = "https://hakililab.com/plaquette-rentree.pdf"
const TELEPHONES = [
  { affiche: "+226 57 91 91 91", tel: "+22657919191" },
  { affiche: "+226 58 79 50 50", tel: "+22658795050" },
]
const EMAIL = "info@hakililab.com"

const NAV = [
  { href: "#maya", label: "Maya" },
  { href: "#pour-qui", label: "Pour qui" },
  { href: "#inscription", label: "S'inscrire" },
  { href: "#centres", label: "Nos centres" },
]

const CHIFFRES = [
  { valeur: 5, de: 0, suffixe: "", label: "centres à Ouagadougou" },
  { valeur: 79, de: 0, suffixe: "+", label: "enseignants formés" },
  { valeur: 3, de: 0, suffixe: "", label: "matières : maths, PC, SVT" },
  { valeur: 2020, de: 1990, suffixe: "", label: "année de création" },
]

const BANDEAU = [
  "Mathématiques",
  "Physique-Chimie",
  "SVT",
  "Du CP1 à la Terminale",
  "Diagnostic avant remédiation",
  "5 centres à Ouagadougou",
  "Depuis 2020",
]

const APPORTS = [
  { icon: Target, titre: "Un test adapté à sa classe", texte: "Du CP1 à la Terminale, votre enfant est évalué sur ce qu'il doit réellement maîtriser à son niveau." },
  { icon: Map, titre: "Ses lacunes, notion par notion", texte: "Pas une simple note : une carte claire de ce qui est acquis et de ce qui bloque." },
  { icon: RouteIcon, titre: "Un parcours sur mesure", texte: "Un parcours de remédiation proposé pour combler d'abord ce qui manque vraiment." },
  { icon: TrendingUp, titre: "Des progrès qui se mesurent", texte: "Les acquis sont revérifiés dans le temps, pour s'assurer qu'ils tiennent." },
]

const PUBLICS = [
  { icon: Users, titre: "Les familles", texte: "Avant une inscription, pour savoir où en est vraiment votre enfant — et par où commencer." },
  { icon: School, titre: "Les établissements", texte: "Pour situer le niveau d'une classe entière et cibler l'effort là où il compte." },
  { icon: GraduationCap, titre: "Les enseignants", texte: "Pour suivre la progression d'un groupe, séance après séance." },
]

const ETAPES = [
  { titre: "Contactez un centre", texte: "Par téléphone, par e-mail ou via le formulaire en ligne." },
  { titre: "Test de positionnement gratuit", texte: "Votre enfant passe le test au centre, dans le calme." },
  { titre: "Un groupe et des horaires", texte: "Nous vous proposons le groupe adapté à son niveau réel." },
  { titre: "C'est parti", texte: "Inscription, puis suivi régulier de ses progrès." },
]

const CENTRES: { nom: string; photo?: string }[] = [
  { nom: "Pissy", photo: photoPissy },
  { nom: "Tampouy", photo: photoTampouy },
  { nom: "Saaba", photo: photoSaaba },
  { nom: "SIAO" },
  { nom: "Nagrin" },
]

/* Exemple purement illustratif (aucune donnée réelle, aucun code du
 * référentiel) — montre à quoi ressemble « une carte des lacunes ». */
const APERCU = [
  { notion: "Calcul avec les fractions", niveau: 0.92, etat: "Acquis", ton: "vert" },
  { notion: "Proportionnalité", niveau: 0.64, etat: "À consolider", ton: "orange" },
  { notion: "Équations du 1er degré", niveau: 0.3, etat: "À travailler", ton: "rouge" },
  { notion: "Lecture de graphiques", niveau: 0.85, etat: "Acquis", ton: "vert" },
] as const

/* ─────────────────────────────────────────────────────────────────────── */

/** Défilement doux (inertie) synchronisé sur l'horloge de GSAP, pour que
 * ScrollTrigger lise exactement la même position que celle affichée. */
function useDefilementDoux() {
  useEffect(() => {
    if (!window.matchMedia("(prefers-reduced-motion: no-preference)").matches) return
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      anchors: { offset: -72 },
    })
    lenis.on("scroll", ScrollTrigger.update)
    const tic = (temps: number) => lenis.raf(temps * 1000)
    gsap.ticker.add(tic)
    gsap.ticker.lagSmoothing(0)
    return () => {
      gsap.ticker.remove(tic)
      gsap.ticker.lagSmoothing(500, 33)
      lenis.destroy()
    }
  }, [])
}

/** Toutes les animations de la page, déclarées une fois sur le conteneur. */
function useAnimationsVitrine(racine: React.RefObject<HTMLDivElement | null>) {
  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const q = gsap.utils.selector(racine)
        const qe = (sel: string) => q(sel) as HTMLElement[]
        const sortie = "expo.out"

        /* Barre de progression de lecture. */
        gsap.fromTo(q("[data-progression]"), { scaleX: 0 }, { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.3 } })

        /* ── Hero : photo qui se pose, titre révélé ligne par ligne. ── */
        const intro = gsap.timeline({ defaults: { ease: sortie } })
        intro.from(q("[data-hero-photo]"), { scale: 1.25, duration: 2.4 }, 0)
        intro.from(q("[data-hero-badge]"), { y: 24, autoAlpha: 0, duration: 1 }, 0.25)
        SplitText.create(q("[data-hero-titre]"), {
          type: "lines,words",
          mask: "lines",
          autoSplit: true,
          onSplit: (self) =>
            gsap.from(self.words, { yPercent: 115, rotate: 4, duration: 1.3, ease: sortie, stagger: 0.06, delay: 0.35 }),
        })
        intro.from(q("[data-hero-suite]"), { y: 32, autoAlpha: 0, duration: 1.1, stagger: 0.12 }, 0.85)
        intro.from(q("[data-hero-defiler]"), { autoAlpha: 0, duration: 1 }, 1.6)

        /* Hero en parallaxe à la sortie : la photo descend moins vite que la
           page, le contenu s'efface en remontant. */
        const hero = q("[data-hero]")[0]
        gsap.to(q("[data-hero-photo]"), { yPercent: 18, ease: "none", scrollTrigger: { trigger: hero, start: "top top", end: "bottom top", scrub: true } })
        gsap.to(q("[data-hero-contenu]"), { y: -90, autoAlpha: 0.15, ease: "none", scrollTrigger: { trigger: hero, start: "top top", end: "bottom 20%", scrub: true } })

        /* ── Chiffres : la carte monte, les nombres défilent. ── */
        const chiffres = q("[data-chiffres]")[0]
        gsap.from(chiffres, { y: 70, autoAlpha: 0, duration: 1.3, ease: sortie, delay: 0.6, scrollTrigger: { trigger: chiffres, start: "top 95%" } })
        qe("[data-compteur]").forEach((el) => {
          const valeur = Number(el.dataset.compteur)
          const de = Number(el.dataset.de ?? 0)
          const suffixe = el.dataset.suffixe ?? ""
          const etat = { v: de }
          gsap.to(etat, {
            v: valeur,
            duration: 2.2,
            delay: 0.8,
            ease: "power3.out",
            scrollTrigger: { trigger: chiffres, start: "top 95%" },
            onUpdate: () => {
              el.textContent = `${Math.round(etat.v)}${suffixe}`
            },
          })
        })

        /* ── Bandeau défilant : vitesse et sens suivent le défilement. ── */
        const piste = q("[data-bandeau-piste]")[0]
        if (piste) {
          const boucle = gsap.to(piste, { xPercent: -50, ease: "none", duration: 38, repeat: -1 })
          let retour: gsap.core.Tween | undefined
          ScrollTrigger.create({
            onUpdate: (self) => {
              const elan = gsap.utils.clamp(1, 6, 1 + Math.abs(self.getVelocity()) / 400)
              retour?.kill()
              boucle.timeScale(elan)
              retour = gsap.to(boucle, { timeScale: 1, duration: 1.2, ease: "power2.out" })
            },
          })
        }

        /* ── Citation : les mots s'allument au fil du défilement. ── */
        SplitText.create(q("[data-citation]"), {
          type: "words",
          autoSplit: true,
          onSplit: (self) =>
            gsap.from(self.words, {
              opacity: 0.12,
              stagger: 0.1,
              ease: "none",
              scrollTrigger: { trigger: self.elements[0], start: "top 85%", end: "bottom 45%", scrub: true },
            }),
        })

        /* ── Titres de section : lignes qui sortent d'un masque. ── */
        qe("[data-titre]").forEach((titre) => {
          SplitText.create(titre, {
            type: "lines",
            mask: "lines",
            autoSplit: true,
            onSplit: (self) =>
              gsap.from(self.lines, {
                yPercent: 110,
                duration: 1.2,
                ease: sortie,
                stagger: 0.1,
                scrollTrigger: { trigger: titre, start: "top 88%" },
              }),
          })
        })
        qe("[data-surtitre]").forEach((el) => {
          const tl = gsap.timeline({ scrollTrigger: { trigger: el, start: "top 90%" } })
          tl.from(el.querySelector("[data-surtitre-trait]"), { scaleX: 0, transformOrigin: "left center", duration: 0.8, ease: sortie })
          tl.from(el.querySelector("[data-surtitre-texte]"), { x: -12, autoAlpha: 0, duration: 0.8, ease: sortie }, 0.15)
        })

        /* ── Blocs et cartes : entrée en cascade par groupe visible. ── */
        gsap.set(q("[data-reveal]"), { y: 60, autoAlpha: 0 })
        ScrollTrigger.batch(q("[data-reveal]"), {
          start: "top 90%",
          once: true,
          onEnter: (lot) => gsap.to(lot, { y: 0, autoAlpha: 1, duration: 1.1, ease: sortie, stagger: 0.1, overwrite: true }),
        })

        /* ── Aperçu du bilan : entrée inclinée, jauges, flottement. ── */
        const apercu = q("[data-apercu]")[0]
        if (apercu) {
          const tl = gsap.timeline({ scrollTrigger: { trigger: apercu, start: "top 80%" } })
          tl.from(apercu, { y: 90, rotate: -3, autoAlpha: 0, duration: 1.3, ease: sortie })
          tl.from(apercu.querySelectorAll("[data-jauge]"), { scaleX: 0, transformOrigin: "left center", duration: 1.4, ease: "power4.out", stagger: 0.12 }, 0.35)
          tl.from(apercu.querySelectorAll("[data-pastille]"), { scale: 0.7, autoAlpha: 0, duration: 0.6, ease: "back.out(2)", stagger: 0.12 }, 0.6)
          tl.from(apercu.querySelector("[data-apercu-parcours]"), { y: 20, autoAlpha: 0, duration: 0.9, ease: sortie }, 1)
          gsap.to(q("[data-apercu-flotte]"), { y: -50, ease: "none", scrollTrigger: { trigger: apercu, start: "top bottom", end: "bottom top", scrub: true } })
        }

        /* ── Étapes : la ligne se trace au rythme du défilement. ── */
        const etapes = q("[data-etapes]")[0]
        if (etapes) {
          gsap.from(q("[data-etapes-ligne]"), { scaleX: 0, transformOrigin: "left center", ease: "none", scrollTrigger: { trigger: etapes, start: "top 75%", end: "bottom 55%", scrub: true } })
          gsap.from(q("[data-etape-numero]"), { scale: 0.5, autoAlpha: 0, duration: 0.8, ease: "back.out(2.2)", stagger: 0.18, scrollTrigger: { trigger: etapes, start: "top 80%" } })
        }

        /* ── Centres : photos dévoilées de bas en haut, puis parallaxe. ── */
        qe("[data-photo-centre]").forEach((cadre) => {
          const img = cadre.querySelector("img")
          gsap.fromTo(cadre, { clipPath: "inset(100% 0% 0% 0%)" }, { clipPath: "inset(0% 0% 0% 0%)", duration: 1.4, ease: "expo.inOut", scrollTrigger: { trigger: cadre, start: "top 88%" } })
          gsap.fromTo(img, { scale: 1.35 }, { scale: 1.08, duration: 1.8, ease: sortie, scrollTrigger: { trigger: cadre, start: "top 88%" } })
          gsap.fromTo(img, { yPercent: -4 }, { yPercent: 4, ease: "none", scrollTrigger: { trigger: cadre, start: "top bottom", end: "bottom top", scrub: true } })
        })

        /* ── Appel final : le panneau s'ouvre en grandissant. ── */
        gsap.fromTo(
          q("[data-appel]"),
          { scale: 0.86, borderRadius: 64 },
          { scale: 1, borderRadius: 24, ease: "none", scrollTrigger: { trigger: q("[data-appel]")[0], start: "top bottom", end: "top 40%", scrub: true } },
        )
      })

      /* Boutons « aimantés » : ils suivent légèrement le pointeur (souris
         seulement — sans objet au doigt). */
      mm.add("(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)", () => {
        const q = gsap.utils.selector(racine)
        const qe = (sel: string) => q(sel) as HTMLElement[]
        const nettoyages: (() => void)[] = []
        qe("[data-aimant]").forEach((el) => {
          const versX = gsap.quickTo(el, "x", { duration: 0.6, ease: "elastic.out(1, 0.4)" })
          const versY = gsap.quickTo(el, "y", { duration: 0.6, ease: "elastic.out(1, 0.4)" })
          const bouger = (e: PointerEvent) => {
            const r = el.getBoundingClientRect()
            versX((e.clientX - (r.left + r.width / 2)) * 0.25)
            versY((e.clientY - (r.top + r.height / 2)) * 0.35)
          }
          const sortir = () => {
            versX(0)
            versY(0)
          }
          el.addEventListener("pointermove", bouger)
          el.addEventListener("pointerleave", sortir)
          nettoyages.push(() => {
            el.removeEventListener("pointermove", bouger)
            el.removeEventListener("pointerleave", sortir)
          })
        })

        /* Aperçu du bilan : légère inclinaison 3D qui suit la souris. */
        const carte = qe("[data-apercu-tilt]")[0]
        if (carte) {
          gsap.set(carte, { transformPerspective: 900 })
          const rx = gsap.quickTo(carte, "rotationX", { duration: 0.8, ease: "power3.out" })
          const ry = gsap.quickTo(carte, "rotationY", { duration: 0.8, ease: "power3.out" })
          const bouger = (e: PointerEvent) => {
            const r = carte.getBoundingClientRect()
            ry(((e.clientX - r.left) / r.width - 0.5) * 10)
            rx(-((e.clientY - r.top) / r.height - 0.5) * 8)
          }
          const sortir = () => {
            rx(0)
            ry(0)
          }
          carte.addEventListener("pointermove", bouger)
          carte.addEventListener("pointerleave", sortir)
          nettoyages.push(() => {
            carte.removeEventListener("pointermove", bouger)
            carte.removeEventListener("pointerleave", sortir)
          })
        }
        return () => nettoyages.forEach((f) => f())
      })
    },
    { scope: racine },
  )
}

/* ─────────────────────────────────────────────────────────────────────── */

function LienExterne({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  )
}

const BOUTON = "vitrine-bouton group inline-flex items-center justify-center gap-2 rounded-xl font-semibold min-h-12 px-6 text-[length:var(--text-corps)] whitespace-nowrap"
const FLECHE = "size-5 transition-transform duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] group-hover:translate-x-1"

/** Enveloppe « aimantée » — l'effet est porté par l'enveloppe pour ne pas
 * se battre avec le `scale` d'appui du bouton lui-même. */
function Aimant({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span data-aimant className={cn("inline-flex", className)}>
      {children}
    </span>
  )
}

function Surtitre({ children, clair }: { children: ReactNode; clair?: boolean }) {
  return (
    <span data-surtitre className={cn("inline-flex items-center gap-2 text-petit font-semibold uppercase tracking-[0.16em]", clair ? "text-white/75" : "text-bleu-sombre")}>
      <span data-surtitre-trait className="w-5 h-[3px] rounded-rond bg-orange" aria-hidden />
      <span data-surtitre-texte>{children}</span>
    </span>
  )
}

const TITRE_SECTION = "font-display mt-3 text-[2rem] sm:text-[2.75rem] leading-[1.1] font-bold text-marine tracking-[-0.02em] text-balance"

/* ─────────────────────────────────────────────────────────────────────── */

function EnTete() {
  const [defile, setDefile] = useState(false)
  const [cache, setCache] = useState(false)
  useEffect(() => {
    let dernier = window.scrollY
    const surDefilement = () => {
      const y = window.scrollY
      setDefile(y > 12)
      // Se retire quand on descend dans la page, revient dès qu'on remonte.
      if (Math.abs(y - dernier) > 6) {
        setCache(y > dernier && y > 480)
        dernier = y
      }
    }
    surDefilement()
    window.addEventListener("scroll", surDefilement, { passive: true })
    return () => window.removeEventListener("scroll", surDefilement)
  }, [])

  return (
    <header
      className={cn(
        "vitrine-entete fixed inset-x-0 top-0 z-40 border-b",
        defile ? "bg-white/85 backdrop-blur-md border-bord shadow-carte" : "bg-transparent border-transparent",
        cache && "-translate-y-full",
      )}
    >
      <div className="mx-auto max-w-6xl h-16 px-4 sm:px-6 flex items-center justify-between gap-4">
        <a href="#haut" className="flex items-center gap-2.5 shrink-0 rounded-lg" aria-label="Maya par HAKILI Lab — haut de page">
          <span className="flex items-center justify-center size-10 rounded-full bg-white shadow-carte overflow-hidden">
            <img src={logoHakili} alt="" width={102} height={96} className="size-8 object-contain" />
          </span>
          <span className="flex flex-col leading-none">
            <span className={cn("font-display text-[1.35rem] font-bold transition-colors duration-200", defile ? "text-marine" : "text-white")}>Maya</span>
            <span className={cn("text-micro font-medium transition-colors duration-200", defile ? "text-texte-doux" : "text-white/75")}>par HAKILI Lab</span>
          </span>
        </a>

        <nav aria-label="Sections de la page" className="hidden lg:flex items-center gap-1">
          {NAV.map(({ href, label }) => (
            <a
              key={href}
              href={href}
              className={cn(
                "vitrine-lien-nav relative px-3 py-2 rounded-lg text-menu font-medium transition-colors duration-150",
                defile ? "text-texte-doux hover:text-marine" : "text-white/85 hover:text-white",
              )}
            >
              {label}
            </a>
          ))}
        </nav>

        <Link
          to="/connexion"
          className={cn(
            "vitrine-bouton group inline-flex items-center gap-2 rounded-xl min-h-11 px-4 text-menu font-semibold whitespace-nowrap border",
            defile ? "bg-marine text-white border-marine hover:bg-marine-clair" : "bg-white/10 text-white border-white/40 backdrop-blur-sm hover:bg-white/20",
          )}
        >
          <span className="sm:hidden">Se connecter</span>
          <span className="hidden sm:inline">Se connecter à Maya</span>
          <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden />
        </Link>
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section id="haut" data-hero className="relative isolate overflow-hidden bg-marine">
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <img
          data-hero-photo
          src={photoHero}
          alt="Un enseignant HAKILI Lab explique un exercice de mathématiques au tableau devant ses élèves"
          width={1800}
          height={1350}
          fetchPriority="high"
          className="size-full object-cover object-[60%_center] will-change-transform"
        />
      </div>
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-marine/80 via-marine/75 to-marine lg:bg-gradient-to-r lg:from-marine lg:via-marine/80 lg:to-marine/20" aria-hidden />

      <div data-hero-contenu className="mx-auto max-w-6xl px-4 sm:px-6 pt-32 pb-28 sm:pt-36 lg:pt-44 lg:pb-40 min-h-[92svh] flex flex-col justify-center">
        <div className="max-w-2xl flex flex-col gap-6">
          <span data-hero-badge className="self-start inline-flex items-center gap-2 rounded-rond bg-white/10 border border-white/25 backdrop-blur-sm px-3.5 py-1.5 text-petit font-medium text-white">
            <span className="relative flex size-2" aria-hidden>
              <span className="vitrine-pulsation absolute inline-flex size-full rounded-full bg-orange" />
              <span className="relative inline-flex size-2 rounded-full bg-orange" />
            </span>
            Rentrée 2026-2027 · Inscriptions ouvertes dans les 5 centres
          </span>

          <h1 data-hero-titre className="font-display text-white font-bold tracking-[-0.025em] text-[2.6rem] leading-[1.05] sm:text-[3.5rem] lg:text-[4.5rem] text-balance">
            Savoir exactement ce qui bloque votre enfant en maths.
          </h1>

          <p data-hero-suite className="text-lead sm:text-[1.25rem] text-white/85 leading-relaxed max-w-xl text-pretty">
            Avec <strong className="font-semibold text-white">Maya</strong>, l'outil de diagnostic de HAKILI Lab, on situe le
            niveau réel de votre enfant et on identifie ses lacunes une à une — pour travailler d'abord ce qui lui manque
            vraiment.
          </p>

          <div data-hero-suite className="flex flex-col sm:flex-row gap-3 pt-2">
            <Aimant>
              <LienExterne href={FORMULAIRE_INSCRIPTION} className={cn(BOUTON, "w-full bg-orange-cta text-white hover:bg-orange-cta-sombre shadow-haute")}>
                Inscrire mon enfant
                <ArrowRight className={FLECHE} aria-hidden />
              </LienExterne>
            </Aimant>
            <Aimant>
              <Link to="/connexion" className={cn(BOUTON, "w-full bg-white text-marine hover:bg-bleu-pale")}>
                Se connecter à Maya
              </Link>
            </Aimant>
          </div>

          <div data-hero-suite>
            <LienExterne
              href={SITE_OFFICIEL}
              className="group inline-flex items-center gap-1.5 text-menu font-medium text-white/80 hover:text-white underline underline-offset-4 decoration-white/30 hover:decoration-white transition-colors duration-150 rounded"
            >
              Visiter le site web officiel de HAKILI Lab
              <ArrowUpRight className="size-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
            </LienExterne>
          </div>
        </div>
      </div>

      <div data-hero-defiler className="hidden lg:flex absolute bottom-24 right-10 flex-col items-center gap-3 text-micro font-semibold uppercase tracking-[0.2em] text-white/60" aria-hidden>
        <span className="[writing-mode:vertical-rl]">Défiler</span>
        <span className="relative h-14 w-px bg-white/20 overflow-hidden">
          <span className="vitrine-defiler absolute inset-x-0 top-0 h-1/2 bg-white" />
        </span>
      </div>
    </section>
  )
}

function Chiffres() {
  return (
    <section aria-label="HAKILI Lab en chiffres" className="relative z-10 mx-auto max-w-6xl px-4 sm:px-6 -mt-14 lg:-mt-16">
      <div data-chiffres className="grid grid-cols-2 lg:grid-cols-4 rounded-2xl bg-white border border-bord shadow-haute overflow-hidden">
        {CHIFFRES.map(({ valeur, de, suffixe, label }, i) => (
          <div key={label} className={cn("flex flex-col gap-1 p-5 sm:p-7", i % 2 === 1 && "border-l border-bord", i >= 2 && "border-t lg:border-t-0 border-bord", i === 2 && "lg:border-l")}>
            <span
              data-compteur={valeur}
              data-de={de}
              data-suffixe={suffixe}
              className="font-display text-[2rem] sm:text-[2.75rem] font-bold text-marine leading-none tabular-nums"
            >
              {valeur}
              {suffixe}
            </span>
            <span className="text-petit text-texte-doux leading-snug">{label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function Constat() {
  return (
    <section className="mx-auto max-w-6xl px-4 sm:px-6 py-20 lg:py-32 grid gap-10 lg:grid-cols-[1.15fr_1fr] lg:gap-16 items-center">
      <figure className="border-l-4 border-orange pl-6 sm:pl-8">
        <blockquote data-citation className="font-display text-[1.85rem] sm:text-[2.5rem] leading-[1.18] font-semibold text-marine tracking-[-0.015em] text-balance">
          « L'échec en mathématiques n'est presque jamais une question de capacité. »
        </blockquote>
        <figcaption className="mt-4 text-petit font-medium text-texte-doux">HAKILI Lab — notre raison d'être, depuis 2020</figcaption>
      </figure>
      <div data-reveal className="flex flex-col gap-4 text-corps text-texte-doux leading-relaxed">
        <p>
          Beaucoup d'élèves suivent des cours sans progresser : on leur réexplique le programme du moment, alors que la
          difficulté vient souvent d'une notion plus ancienne, jamais vraiment comprise.
        </p>
        <p className="text-texte">
          Chez HAKILI Lab, on fait l'inverse : <strong className="font-semibold text-marine">on diagnostique d'abord, on enseigne ensuite.</strong>{" "}
          Maya est la version numérique de cette première étape.
        </p>
      </div>
    </section>
  )
}

function Bandeau() {
  const groupe = (cache: boolean) => (
    <ul className="flex shrink-0 items-center" aria-hidden={cache || undefined}>
      {BANDEAU.map((texte) => (
        <li key={texte} className="flex items-center whitespace-nowrap">
          <span className="font-display text-[1.6rem] sm:text-[2.1rem] font-semibold text-white px-6 sm:px-8">{texte}</span>
          <span className="size-2.5 rounded-full bg-orange shrink-0" aria-hidden />
        </li>
      ))}
    </ul>
  )
  return (
    <div className="overflow-hidden py-10 -my-4">
      <div className="bg-marine py-5 sm:py-6 -rotate-2 scale-x-110 shadow-haute">
        <div data-bandeau-piste className="flex w-max">
          {groupe(false)}
          {groupe(true)}
        </div>
      </div>
    </div>
  )
}

function ApercuCarte() {
  const couleurs = {
    vert: { barre: "bg-vert", pastille: "bg-vert-pale text-vert" },
    orange: { barre: "bg-orange", pastille: "bg-orange-pale text-te-prq" },
    rouge: { barre: "bg-rouge", pastille: "bg-rouge-pale text-te-cpt" },
  }
  return (
    <div data-apercu-flotte>
      <div data-apercu>
        <div data-apercu-tilt className="rounded-2xl bg-white border border-bord shadow-haute p-5 sm:p-6 will-change-transform">
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 mb-5">
            <div>
              <p className="text-micro font-semibold uppercase tracking-[0.14em] text-texte-faible">Bilan de positionnement</p>
              <p className="font-display text-h2 font-semibold text-marine whitespace-nowrap">Mathématiques · 4e</p>
            </div>
            <span className="text-micro font-medium rounded-rond bg-surface-creuse text-texte-doux px-2.5 py-1 whitespace-nowrap">Exemple illustratif</span>
          </div>
          <ul className="flex flex-col gap-4">
            {APERCU.map(({ notion, niveau, etat, ton }) => (
              <li key={notion} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-menu font-medium text-texte">{notion}</span>
                  <span data-pastille className={cn("text-micro font-semibold rounded-rond px-2 py-0.5 shrink-0", couleurs[ton].pastille)}>{etat}</span>
                </div>
                <div className="h-2 rounded-rond bg-surface-creuse overflow-hidden">
                  <div data-jauge className={cn("h-full rounded-rond", couleurs[ton].barre)} style={{ width: `${niveau * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
          <div data-apercu-parcours className="mt-6 flex items-start gap-3 rounded-xl bg-bleu-pale p-4">
            <RouteIcon className="size-5 text-bleu-sombre shrink-0 mt-0.5" aria-hidden />
            <p className="text-petit text-texte leading-relaxed">
              <strong className="font-semibold">Parcours proposé :</strong> on commence par les équations, puis on consolide la
              proportionnalité.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function Maya() {
  return (
    <section id="maya" className="scroll-mt-20 bg-white border-y border-bord">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-20 lg:py-32">
        <div className="grid gap-12 lg:grid-cols-[1fr_0.9fr] lg:gap-16 items-center">
          <div>
            <Surtitre>Maya · Diagnostic et remédiation numériques</Surtitre>
            <h2 data-titre className={TITRE_SECTION}>
              L'outil qui situe le niveau réel de votre enfant.
            </h2>
            <p data-reveal className="mt-4 text-lead text-texte-doux leading-relaxed max-w-xl">
              Maya repère les notions qui manquent, puis propose un parcours de remédiation. Votre enfant ne refait pas
              tout le programme : il travaille ce dont il a besoin.
            </p>

            <ul className="mt-10 grid gap-x-8 gap-y-7 sm:grid-cols-2">
              {APPORTS.map(({ icon: Icon, titre, texte }) => (
                <li key={titre} data-reveal className="group flex flex-col gap-2">
                  <span className="flex items-center justify-center size-11 rounded-xl bg-bleu-pale text-bleu-sombre transition-[background-color,color,transform] duration-300 group-hover:bg-bleu group-hover:text-white group-hover:-rotate-6">
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <h3 className="text-[1.05rem] font-semibold text-marine">{titre}</h3>
                  <p className="text-menu text-texte-doux leading-relaxed">{texte}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex flex-col gap-4">
            <ApercuCarte />
            <div data-reveal className="flex items-start gap-4 rounded-2xl bg-marine text-white p-5 sm:p-6">
              <span className="flex items-center justify-center size-11 rounded-xl bg-white/10 shrink-0">
                <UserCheck className="size-5" aria-hidden />
              </span>
              <div>
                <h3 className="font-semibold text-[1.05rem]">Un enseignant, toujours</h3>
                <p className="mt-1 text-menu text-white/80 leading-relaxed">
                  Maya éclaire le diagnostic. Ce sont nos enseignants qui accompagnent votre enfant, séance après séance.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function PourQui() {
  return (
    <section id="pour-qui" className="scroll-mt-20 mx-auto max-w-6xl px-4 sm:px-6 py-20 lg:py-32">
      <div className="max-w-2xl">
        <Surtitre>Pour qui</Surtitre>
        <h2 data-titre className={TITRE_SECTION}>
          Un point de départ clair, pour chacun.
        </h2>
      </div>
      <ul className="mt-10 grid gap-4 md:grid-cols-3">
        {PUBLICS.map(({ icon: Icon, titre, texte }) => (
          <li key={titre} data-reveal>
            <div className="vitrine-carte group h-full flex flex-col gap-3 rounded-2xl bg-white border border-bord shadow-carte p-6">
              <span className="flex items-center justify-center size-12 rounded-xl bg-bleu-pale text-bleu transition-[background-color,color,transform] duration-300 group-hover:bg-marine group-hover:text-white group-hover:scale-105">
                <Icon className="size-6" aria-hidden />
              </span>
              <h3 className="text-[1.15rem] font-semibold text-marine">{titre}</h3>
              <p className="text-menu text-texte-doux leading-relaxed">{texte}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Inscription() {
  return (
    <section id="inscription" className="scroll-mt-20 bg-white border-y border-bord">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-20 lg:py-32">
        <div className="max-w-2xl">
          <Surtitre>S'inscrire</Surtitre>
          <h2 data-titre className={TITRE_SECTION}>
            Inscrire votre enfant, en quatre étapes simples.
          </h2>
        </div>

        <ol data-etapes className="relative mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          <span className="hidden lg:block absolute top-[22px] left-[22px] right-[calc(25%-22px)] h-[2px] bg-bord" aria-hidden>
            <span data-etapes-ligne className="absolute inset-0 bg-orange" />
          </span>
          {ETAPES.map(({ titre, texte }, i) => (
            <li key={titre} data-reveal className="relative flex flex-col gap-3">
              <span data-etape-numero className="relative flex items-center justify-center size-11 rounded-full bg-marine text-white font-display font-bold text-[1.1rem] shrink-0 tabular-nums ring-8 ring-white">
                {i + 1}
              </span>
              <h3 className="text-[1.05rem] font-semibold text-marine">{titre}</h3>
              <p className="text-menu text-texte-doux leading-relaxed">{texte}</p>
            </li>
          ))}
        </ol>

        <div data-reveal className="mt-12 flex flex-col sm:flex-row gap-3">
          <Aimant>
            <LienExterne href={FORMULAIRE_INSCRIPTION} className={cn(BOUTON, "w-full bg-orange-cta text-white hover:bg-orange-cta-sombre shadow-carte")}>
              Inscrire mon enfant
              <ArrowRight className={FLECHE} aria-hidden />
            </LienExterne>
          </Aimant>
          <Aimant>
            <LienExterne href={PLAQUETTE} className={cn(BOUTON, "w-full bg-white text-marine border border-bord-fort hover:bg-surface-creuse")}>
              <Download className="size-5 transition-transform duration-300 group-hover:translate-y-0.5" aria-hidden />
              Plaquette de rentrée (PDF)
            </LienExterne>
          </Aimant>
        </div>
      </div>
    </section>
  )
}

function Centres() {
  return (
    <section id="centres" className="scroll-mt-20 mx-auto max-w-6xl px-4 sm:px-6 py-20 lg:py-32">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div className="max-w-2xl">
          <Surtitre>Nos centres</Surtitre>
          <h2 data-titre className={TITRE_SECTION}>
            Cinq centres à Ouagadougou, près de chez vous.
          </h2>
          <p data-reveal className="mt-3 text-corps text-texte-doux">Après l'école en semaine, et le week-end.</p>
        </div>
        <LienExterne
          href={`${SITE_OFFICIEL}centres`}
          className="group self-start sm:self-auto inline-flex items-center gap-1.5 text-menu font-semibold text-bleu-sombre hover:text-marine underline underline-offset-4 decoration-bleu/30 hover:decoration-marine transition-colors duration-150 rounded"
        >
          Voir les centres en détail
          <ArrowUpRight className="size-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
        </LienExterne>
      </div>

      <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        {CENTRES.map(({ nom, photo }) => (
          <li key={nom} data-reveal className={cn(photo ? "lg:col-span-2" : "lg:col-span-3")}>
            <div className="vitrine-carte h-full rounded-2xl bg-white border border-bord shadow-carte overflow-hidden">
              {photo && (
                <div data-photo-centre className="aspect-[4/3] overflow-hidden bg-surface-creuse">
                  <img src={photo} alt={`Élèves en cours au centre HAKILI Lab de ${nom}`} width={900} height={675} loading="lazy" className="size-full object-cover will-change-transform" />
                </div>
              )}
              <div className="flex items-center gap-3 p-5">
                <span className="flex items-center justify-center size-10 rounded-xl bg-bleu-pale text-bleu-sombre shrink-0">
                  <MapPin className="size-5" aria-hidden />
                </span>
                <div>
                  <h3 className="text-[1.05rem] font-semibold text-marine">{nom}</h3>
                  <p className="text-petit text-texte-doux">Ouagadougou</p>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function AppelFinal() {
  return (
    <section className="mx-auto max-w-6xl px-4 sm:px-6 pb-20 lg:pb-32">
      <div data-appel className="vitrine-appel relative overflow-hidden rounded-3xl bg-marine px-6 py-16 sm:px-12 sm:py-20 text-center will-change-transform">
        <Surtitre clair>Rentrée 2026-2027</Surtitre>
        <h2 data-titre className="font-display mx-auto mt-4 max-w-2xl text-[2.1rem] sm:text-[3rem] leading-[1.08] font-bold text-white tracking-[-0.02em] text-balance">
          Donnez à votre enfant un vrai point de départ.
        </h2>
        <p data-reveal className="mx-auto mt-4 max-w-xl text-lead text-white/80 leading-relaxed">
          Le test de positionnement est gratuit. Appelez-nous ou inscrivez votre enfant en ligne.
        </p>
        <div data-reveal className="mt-9 flex flex-col sm:flex-row flex-wrap justify-center gap-3">
          <Aimant>
            <LienExterne href={FORMULAIRE_INSCRIPTION} className={cn(BOUTON, "w-full bg-orange-cta text-white hover:bg-orange-cta-sombre shadow-haute")}>
              Inscrire mon enfant
              <ArrowRight className={FLECHE} aria-hidden />
            </LienExterne>
          </Aimant>
          <Aimant>
            <a href={`tel:${TELEPHONES[0].tel}`} className={cn(BOUTON, "w-full bg-white text-marine hover:bg-bleu-pale")}>
              <Phone className="size-5" aria-hidden />
              {TELEPHONES[0].affiche}
            </a>
          </Aimant>
          <Aimant>
            <LienExterne href={SITE_OFFICIEL} className={cn(BOUTON, "w-full text-white border border-white/40 hover:bg-white/10")}>
              Visiter le site web officiel de HAKILI
              <ArrowUpRight className="size-5 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
            </LienExterne>
          </Aimant>
        </div>
      </div>
    </section>
  )
}

function PiedDePage() {
  const lien = "inline-flex items-center gap-2 text-menu text-white/75 hover:text-white transition-colors duration-150 rounded"
  return (
    <footer className="bg-marine text-white">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-14 grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span className="flex items-center justify-center size-12 rounded-full bg-white overflow-hidden">
              <img src={logoHakili} alt="" width={102} height={96} className="size-10 object-contain" />
            </span>
            <div className="leading-tight">
              <p className="font-display text-[1.25rem] font-bold">HAKILI Lab</p>
              <p className="text-petit text-white/70">Centre d'excellence en mathématiques</p>
            </div>
          </div>
          <p className="text-menu text-white/70 leading-relaxed max-w-xs">
            Mathématiques, physique-chimie et SVT, du CP1 à la Terminale. Depuis 2020 à Ouagadougou.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-petit font-semibold uppercase tracking-[0.14em] text-white/55">Contact</h2>
          {TELEPHONES.map(({ affiche, tel }) => (
            <a key={tel} href={`tel:${tel}`} className={lien}>
              <Phone className="size-4" aria-hidden />
              {affiche}
            </a>
          ))}
          <a href={`mailto:${EMAIL}`} className={lien}>
            <Mail className="size-4" aria-hidden />
            {EMAIL}
          </a>
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-petit font-semibold uppercase tracking-[0.14em] text-white/55">Suivez-nous</h2>
          <LienExterne href="https://web.facebook.com/hakililab" className={lien}>Facebook</LienExterne>
          <LienExterne href="https://www.tiktok.com/@hakililab" className={lien}>TikTok</LienExterne>
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-petit font-semibold uppercase tracking-[0.14em] text-white/55">Liens</h2>
          <LienExterne href={SITE_OFFICIEL} className={lien}>
            Site officiel HAKILI Lab
            <ArrowUpRight className="size-3.5" aria-hidden />
          </LienExterne>
          <LienExterne href={FORMULAIRE_INSCRIPTION} className={lien}>Inscrire mon enfant</LienExterne>
          <Link to="/connexion" className={lien}>Accès personnel</Link>
        </div>
      </div>
      <div className="border-t border-white/10">
        <p className="mx-auto max-w-6xl px-4 sm:px-6 py-5 text-petit text-white/55">
          © {new Date().getFullYear()} HAKILI Lab · Ouagadougou, Burkina Faso
        </p>
      </div>
    </footer>
  )
}

export default function Accueil() {
  const racine = useRef<HTMLDivElement>(null)
  useDefilementDoux()
  useAnimationsVitrine(racine)

  useEffect(() => {
    document.title = "Maya — HAKILI Lab · Diagnostic en mathématiques"
  }, [])

  return (
    <div ref={racine} className="vitrine min-h-screen bg-fond text-texte overflow-x-clip">
      <a href="#contenu" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:shadow-haute">
        Aller au contenu
      </a>
      <div data-progression className="fixed inset-x-0 top-0 z-50 h-[3px] bg-orange origin-left scale-x-0 pointer-events-none" aria-hidden />
      <EnTete />
      <main id="contenu">
        <Hero />
        <Chiffres />
        <Constat />
        <Bandeau />
        <Maya />
        <PourQui />
        <Inscription />
        <Centres />
        <AppelFinal />
      </main>
      <PiedDePage />
    </div>
  )
}
