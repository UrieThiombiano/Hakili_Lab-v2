import { useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur, Spinner } from "@/components/ui/Etat"
import { Stat } from "@/components/ui/Stat"
import { TypeErreurBadge, DiagnosticLisible, PalierBadge } from "@/components/ui/Badge"
import { LigneDocument } from "@/components/ui/LigneDocument"
import { TranscriptionMarkdown, TranscriptionLegende } from "@/components/ui/TranscriptionMarkdown"
import { hasOcrMarkers, ancrerIncertitudes } from "@/lib/transcriptionHighlight"
import { correctionsApi, elevesApi, sessionsApi } from "@/lib/api"
import { formatHeures } from "@/lib/format"
import { useToast } from "@/hooks/useToast"
import { useConfirm } from "@/hooks/useConfirm"
import { useSupprimerDocument } from "@/hooks/useSupprimerDocument"
import { cn } from "@/lib/utils"
import {
  ArrowUpRight,
  CheckCheck,
  CircleCheck,
  ClipboardList,
  FileCheck2,
  GraduationCap,
  ListChecks,
  Pencil,
  ScanText,
  SquareCheck,
  ThumbsUp,
  Trash2,
  TriangleAlert,
  Wrench,
  type LucideIcon,
} from "lucide-react"

/** Documents portés par la copie elle-même (`data.documents`, `document.type`
 * en base) — nom clair + phrase d'explication, pour la section « Documents à
 * télécharger » regroupée en bas de la page de résultats. */
const DOC_COPIE: Record<string, { icon: LucideIcon; titre: string; description: string }> = {
  scan: { icon: ScanText, titre: "Copie de l'élève", description: "Le scan de la copie qui vient d'être corrigée." },
  rapport: { icon: FileCheck2, titre: "Rapport de correction", description: "Note question par question, réponse attendue et réponse observée." },
  remediation: { icon: Wrench, titre: "Plan de remédiation", description: "Le cahier de l'élève : séances, rappels de cours et exercices corrigés." },
  sujet_confirmation: {
    icon: ClipboardList,
    titre: "Sujet du test de confirmation (T1)",
    description: "À faire passer pour confirmer ou écarter chaque hypothèse de lacune.",
  },
}

/** Formatage FR compact — les barèmes portent des fractions (1/3 pt…), on ne
 * veut jamais afficher `0.333333` à l'écran. */
function formatNombre(n: number): string {
  return (Math.round(n * 100) / 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })
}

export default function Suivre() {
  const { jeton = "" } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notifier } = useToast()

  const { data } = useQuery({
    queryKey: ["correction", jeton],
    queryFn: () => correctionsApi.statut(jeton),
    refetchInterval: (query) => (query.state.data && (query.state.data.en_cours || query.state.data.etat === "creee") ? 2000 : false),
  })

  const supprimer = useMutation({
    mutationFn: () => correctionsApi.supprimer(jeton),
    onSuccess: () => {
      notifier("Copie supprimée.")
      navigate("/analyse-de-copie")
    },
  })

  const reprendrePlan = useMutation({
    mutationFn: () => correctionsApi.reprendrePlan(jeton),
    onSuccess: (statut) => queryClient.setQueryData(["correction", jeton], statut),
    onError: () => notifier("La reprise du plan n'a pas pu être lancée.", "erreur"),
  })

  if (!data) return <AppShell><Spinner label="Chargement…" /></AppShell>

  const eleve = data.resultat?.student_name ?? ""
  const large = data.etat === "relecture" || data.etat === "validation"
  // La page de résultats occupe toute la largeur disponible (sections
  // empilées, grilles internes) ; les autres états restent en colonne lisible.
  const contrainte = data.terminee ? "" : large ? "max-w-5xl" : "max-w-2xl"

  return (
    <AppShell titre={eleve ? `Correction — ${eleve}` : "Correction"}>
      <div className={cn("flex flex-col gap-5", contrainte)}>
        {(data.en_cours || data.etat === "creee") && <Progression etape={data.etape} progression={data.progression} />}
        {data.plan_a_reprendre && (
          <PlanAReprendre
            motif={data.resultat?.plan_erreur ?? ""}
            enCours={reprendrePlan.isPending}
            onReprendre={() => reprendrePlan.mutate()}
          />
        )}
        {data.etat === "echec" && <Echec erreurs={data.erreurs} onSupprimer={() => supprimer.mutate()} />}
        {data.etat === "relecture" && data.resultat && <Relecture jeton={jeton} resultat={data.resultat} onValide={() => queryClient.invalidateQueries({ queryKey: ["correction", jeton] })} />}
        {data.etat === "validation" && data.resultat && (
          <Validation
            jeton={jeton}
            resultat={data.resultat}
            seuilSansT1={data.seuil_sans_t1}
            onValide={() => queryClient.invalidateQueries({ queryKey: ["correction", jeton] })}
          />
        )}
        {data.terminee && data.resultat && (
          <Resultats
            jeton={jeton}
            resultat={data.resultat}
            documents={data.documents}
            jetonSession={data.jeton_session}
            onSupprimer={() => supprimer.mutate()}
          />
        )}
      </div>
    </AppShell>
  )
}

/** Le plan de remédiation manque (une section n'a pas abouti, ou son PDF) :
 * les sections déjà rédigées sont gardées, la reprise n'écrit que le reste. */
function PlanAReprendre({ motif, enCours, onReprendre }: { motif: string; enCours: boolean; onReprendre: () => void }) {
  return (
    <Card className="border-orange/40 bg-orange-pale">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="inline-flex items-center gap-1.5 font-semibold text-marine">
            <TriangleAlert className="size-4 text-orange" /> Plan de remédiation incomplet
          </p>
          <p className="mt-1 text-petit text-texte-doux">
            Une partie du plan n'a pas pu être rédigée. Les sections déjà écrites sont conservées : la reprise
            ne rédige que celles qui manquent, sans refaire l'analyse de la copie.
          </p>
          {motif && <p className="mt-1.5 break-words text-petit text-texte-faible">{motif}</p>}
        </div>
        <Button onClick={onReprendre} disabled={enCours}>
          {enCours ? "Lancement…" : "Relancer la rédaction du plan"}
        </Button>
      </div>
    </Card>
  )
}

function Progression({ etape, progression }: { etape: string; progression: number }) {
  return (
    <div className="min-h-[65vh] flex flex-col items-center justify-center gap-8">
      <div className="relative flex items-center justify-center size-56" title={etape || undefined}>
        <span className="absolute inset-0 rounded-rond bg-bleu/20 blur-2xl spectacle-halo" />

        <span className="absolute inset-0 rounded-rond spectacle-anneau" />
        <span className="absolute inset-6 rounded-rond spectacle-anneau-inverse" />

        <span className="absolute inset-0 spectacle-orbite">
          <span className="absolute top-1/2 left-1/2 size-2.5 rounded-rond bg-orange shadow-[0_0_10px_2px_rgba(201,112,13,0.55)]" style={{ transform: "rotate(0deg) translate(-50%, -116px)" }} />
          <span className="absolute top-1/2 left-1/2 size-2 rounded-rond bg-bleu shadow-[0_0_10px_2px_rgba(47,111,196,0.5)]" style={{ transform: "rotate(120deg) translate(-50%, -116px)" }} />
          <span className="absolute top-1/2 left-1/2 size-1.5 rounded-rond bg-marine-clair shadow-[0_0_8px_2px_rgba(10,58,122,0.5)]" style={{ transform: "rotate(240deg) translate(-50%, -116px)" }} />
        </span>

        <div className="relative flex items-center justify-center size-32 rounded-rond bg-surface shadow-haute spectacle-coeur">
          <img src="/hakili_logo.png" alt="" className="size-16 rounded-full object-cover" />
        </div>
      </div>

      <p className="text-chiffre font-bold text-marine tabular-nums">{progression}%</p>

      <Link to="/analyse-de-copie" className="text-petit text-bleu hover:text-bleu-sombre">
        Voir toutes les corrections
      </Link>
    </div>
  )
}

function Echec({ erreurs, onSupprimer }: { erreurs: string[]; onSupprimer: () => void }) {
  const navigate = useNavigate()
  return (
    <Card>
      <CardTitre>La correction a échoué</CardTitre>
      <div className="flex flex-col gap-2 mb-4">
        {erreurs.map((e, i) => <EtatErreur key={i} message={e} />)}
      </div>
      <div className="flex gap-3">
        <Button onClick={() => navigate("/corrections/nouvelle")}>Relancer une correction</Button>
        <Button variant="grave" onClick={onSupprimer}>Supprimer</Button>
      </div>
    </Card>
  )
}

function Relecture({ jeton, resultat, onValide }: { jeton: string; resultat: NonNullable<import("@/types/api").CorrectionStatut["resultat"]>; onValide: () => void }) {
  const { notifier } = useToast()
  const [pages, setPages] = useState<Record<number, string>>(
    Object.fromEntries(
      (resultat.transcription?.pages ?? []).map((p) => [
        p.page_number,
        ancrerIncertitudes(p.content, p.uncertainties),
      ]),
    ),
  )
  const valider = useMutation({
    mutationFn: () => correctionsApi.validerTranscription(jeton, pages),
    onSuccess: () => {
      notifier("Transcription validée — correction en cours.")
      onValide()
    },
  })

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardTitre>Relecture de la transcription</CardTitre>
        <p className="text-petit text-texte-doux mb-2">
          Les passages où le modèle hésite sont surlignés et affichés entre crochets. Double-cliquez sur une zone pour la
          corriger — ou sur n'importe quelle ligne si la transcription diffère de la copie — puis validez pour lancer
          la correction.
        </p>
        <p className="text-petit text-texte-doux">
          <span className="text-rouge font-medium">[illisible]</span> : rien de fiable n'a pu être déchiffré — ce que
          vous saisissez sert de base à la correction.
        </p>
      </Card>

      {(resultat.transcription?.pages ?? []).map((page) => {
        const confiancePct = Math.round(page.confidence * 100)
        return (
          <Card key={page.page_number} className="p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-surface-creuse border-b border-bord">
              <span className="text-petit font-semibold text-texte-doux">Page {page.page_number}</span>
              <span
                className={cn(
                  "text-micro font-medium px-2 py-0.5 rounded-rond",
                  confiancePct >= 90 ? "bg-vert-pale text-vert" : confiancePct >= 70 ? "bg-orange-pale text-orange" : "bg-rouge-pale text-rouge",
                )}
              >
                confiance {confiancePct}%
              </span>
            </div>

            {page.uncertainties.length > 0 && (
              <p className="flex items-start gap-1.5 px-4 pt-3 text-petit text-orange">
                <TriangleAlert className="size-3.5 shrink-0 mt-0.5" />
                Zones incertaines : {page.uncertainties.join(" · ")}
              </p>
            )}

            {hasOcrMarkers(pages[page.page_number] ?? "") && <TranscriptionLegende className="px-4 pt-2" />}

            <div className="grid lg:grid-cols-2 gap-px bg-bord mt-3">
              <div className="bg-surface p-3 flex items-start justify-center">
                <img
                  src={correctionsApi.pageImageUrl(jeton, page.page_number)}
                  alt={`Page ${page.page_number}`}
                  className="max-h-[480px] w-full rounded border border-bord object-contain"
                  onError={(e) => (e.currentTarget.style.display = "none")}
                />
              </div>
              <div className="bg-surface p-3 max-h-[480px] overflow-auto">
                <TranscriptionMarkdown
                  value={pages[page.page_number] ?? ""}
                  onChange={(next) => setPages((p) => ({ ...p, [page.page_number]: next }))}
                />
              </div>
            </div>
          </Card>
        )
      })}

      <Button className="self-start" chargement={valider.isPending} onClick={() => valider.mutate()}>
        Valider la transcription
      </Button>
    </div>
  )
}

function ScorePill({ score, max }: { score: number; max: number }) {
  const plein = max > 0 && score >= max
  const nul = score <= 0
  return (
    <span
      className={cn(
        "shrink-0 rounded-rond px-2.5 py-1 text-petit font-semibold tabular-nums",
        plein ? "bg-vert-pale text-vert" : nul ? "bg-rouge-pale text-rouge" : "bg-orange-pale text-orange",
      )}
    >
      {formatNombre(score)} / {formatNombre(max)}
    </span>
  )
}

function scoreCourant(q: { rubric_item_id: string; score: number }, decisions: Record<string, { decision: string; note?: string | null }>): number {
  const d = decisions[q.rubric_item_id]
  if (d?.decision === "refused") {
    const n = parseFloat(d.note ?? "")
    return Number.isFinite(n) ? n : 0
  }
  return q.score
}

function Validation({
  jeton,
  resultat,
  seuilSansT1,
  onValide,
}: {
  jeton: string
  resultat: NonNullable<import("@/types/api").CorrectionStatut["resultat"]>
  seuilSansT1: number | null
  onValide: () => void
}) {
  const { notifier } = useToast()
  const { confirmer } = useConfirm()
  const [decisions, setDecisions] = useState<Record<string, { decision: string; note?: string | null }>>({})

  const bareme = Object.fromEntries((resultat.rubric?.items ?? []).map((i) => [i.id, i]))
  const questions = resultat.grade?.questions ?? []
  const totalPossible = resultat.rubric?.total_points ?? Object.values(bareme).reduce((s, i) => s + i.max_score, 0)
  const noteActuelle = questions.reduce((s, q) => s + scoreCourant(q, decisions), 0)
  // Même conversion que `CopyGrade.compute_final_score()` côté serveur
  // (dénominateur `total_possible`, arrondi au quart de point).
  const denominateur = resultat.grade?.total_possible || totalPossible
  const noteSur20 = denominateur > 0 ? Math.round((noteActuelle / denominateur) * 20 * 4) / 4 : null
  // D-CEO-46 : sous le seuil, pas de test T1 — l'élève passe directement en remédiation.
  const remediationDirecte = seuilSansT1 != null && noteSur20 != null && noteSur20 < seuilSansT1

  const valider = useMutation({
    mutationFn: () => correctionsApi.validerNotes(jeton, decisions),
    onSuccess: () => {
      notifier(remediationDirecte ? "Note < 10 : l'élève passe directement à la remédiation !" : "Notes validées — diagnostic en cours.")
      onValide()
    },
  })

  async function validerNotes() {
    if (
      remediationDirecte &&
      !(await confirmer({
        titre: "Note < 10 : remédiation directe",
        message: `Note ${formatNombre(noteSur20 ?? 0)}/20 : l'élève passe directement à la remédiation, sans test de confirmation (T1).`,
        texteConfirmer: "Continuer",
      }))
    ) {
      return
    }
    valider.mutate()
  }
  const totalARevoir = questions.filter((q) => q.requires_review).length
  const aRevoirRestant = questions.filter((q) => q.requires_review && !decisions[q.rubric_item_id]).length

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitre className="mb-1">Validation des notes</CardTitre>
            <p className="text-petit text-texte-doux">L'IA propose une note par question — acceptez ou corrigez chacune avant de lancer le diagnostic.</p>
          </div>
          <Button variant="discret" taille="petit" onClick={() => setDecisions({})} title="Revenir aux propositions de l'IA pour toutes les questions">
            <CheckCheck className="size-4" /> Tout accepter
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 pt-4 border-t border-bord text-petit">
          <span className="text-texte-doux">
            <span className="font-semibold text-texte">{questions.length}</span> question{questions.length > 1 ? "s" : ""}
          </span>
          {totalARevoir > 0 && (
            <span className={cn("inline-flex items-center gap-1.5 font-medium", aRevoirRestant > 0 ? "text-orange" : "text-vert")}>
              {aRevoirRestant > 0 ? <TriangleAlert className="size-3.5" /> : <CircleCheck className="size-3.5" />}
              {aRevoirRestant > 0 ? `${aRevoirRestant} signalée${aRevoirRestant > 1 ? "s" : ""} à confirmer` : "Toutes les questions signalées ont été revues"}
            </span>
          )}
          <span className="ml-auto text-marine font-semibold tabular-nums">
            Note actuelle : {formatNombre(noteActuelle)} <span className="text-texte-doux font-normal">/ {formatNombre(totalPossible)} pts</span>
          </span>
        </div>
      </Card>

      <div className="flex flex-col gap-3 pb-20">
        {questions.map((q, i) => {
          const item = bareme[q.rubric_item_id]
          const max = item?.max_score ?? 1
          const decision = decisions[q.rubric_item_id]?.decision ?? "accepted"
          return (
            <div
              key={q.rubric_item_id}
              className={cn(
                "rounded-lg border p-4 transition-colors",
                q.requires_review ? "border-orange/40 bg-orange-pale/40" : "border-bord bg-surface",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-rond bg-surface-creuse text-micro font-semibold text-texte-doux">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-menu font-medium text-texte">{item?.label ?? q.rubric_item_id}</p>
                    {q.requires_review && (
                      <span className="mt-1 inline-flex items-center gap-1 text-micro font-medium text-orange">
                        <TriangleAlert className="size-3" /> À revoir — l'IA n'est pas sûre
                      </span>
                    )}
                  </div>
                </div>
                <ScorePill score={q.score} max={max} />
              </div>

              <div className="mt-3 grid sm:grid-cols-2 gap-3">
                <div className="rounded-md bg-surface-creuse px-3 py-2">
                  <p className="text-micro font-semibold uppercase tracking-wide text-texte-faible mb-0.5">Réponse attendue</p>
                  <p className="text-petit text-texte">{q.correct_answer || "—"}</p>
                </div>
                <div className="rounded-md bg-surface-creuse px-3 py-2">
                  <p className="text-micro font-semibold uppercase tracking-wide text-texte-faible mb-0.5">Réponse de l'élève</p>
                  <p className="text-petit text-texte">{q.observed_answer || "—"}</p>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <div className="inline-flex rounded-lg border border-bord-fort overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setDecisions((d) => ({ ...d, [q.rubric_item_id]: { decision: "accepted" } }))}
                    className={cn(
                      "inline-flex items-center gap-1.5 h-8 px-3 text-petit font-medium transition-colors",
                      decision === "accepted" ? "bg-vert text-white" : "bg-surface text-texte-doux hover:bg-surface-creuse",
                    )}
                  >
                    <SquareCheck className="size-3.5" /> Accepter
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setDecisions((d) => ({
                        ...d,
                        [q.rubric_item_id]: { decision: "refused", note: d[q.rubric_item_id]?.note ?? String(Math.round(q.score * 100) / 100) },
                      }))
                    }
                    className={cn(
                      "inline-flex items-center gap-1.5 h-8 px-3 text-petit font-medium border-l border-bord-fort transition-colors",
                      decision === "refused" ? "bg-bleu text-white" : "bg-surface text-texte-doux hover:bg-surface-creuse",
                    )}
                  >
                    <Pencil className="size-3.5" /> Corriger
                  </button>
                </div>
                {decision === "refused" && (
                  <label className="inline-flex items-center gap-1.5 text-petit text-texte-doux">
                    Note
                    <input
                      type="number"
                      step="0.01"
                      min={0}
                      max={max}
                      autoFocus
                      value={decisions[q.rubric_item_id]?.note ?? ""}
                      onChange={(e) => setDecisions((d) => ({ ...d, [q.rubric_item_id]: { decision: "refused", note: e.target.value } }))}
                      className="w-20 h-8 rounded border border-bord-fort px-2 text-petit focus:border-bleu focus:outline-none"
                    />
                    / {formatNombre(max)}
                  </label>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="sticky bottom-4 z-10 flex items-center justify-end gap-4 rounded-lg border border-bord bg-surface/95 backdrop-blur px-4 py-3 shadow-haute">
        <span className="text-menu font-semibold text-marine tabular-nums mr-auto sm:mr-0">
          {formatNombre(noteActuelle)} <span className="text-texte-doux font-normal">/ {formatNombre(totalPossible)} pts</span>
        </span>
        <Button chargement={valider.isPending} onClick={validerNotes}>
          Valider les notes
        </Button>
      </div>
    </div>
  )
}

/** Note finale d'une question : la décision de l'enseignant prime toujours
 * sur la proposition de l'IA (D-CEO-16) — même règle que
 * `correction_web/views.py::_note_finale`. */
function noteFinale(q: { teacher_decision: string; teacher_score: number | null; score: number }): number {
  if (q.teacher_decision === "refused" && q.teacher_score != null) return q.teacher_score
  return q.score
}

/** Petite liste colorée — points d'appui / de fragilité du diagnostic. */
function BlocConstat({ titre, items, icon: Icon, ton }: { titre: string; items: string[]; icon: LucideIcon; ton: "vert" | "orange" }) {
  if (items.length === 0) return null
  return (
    <div className={cn("rounded-lg border p-4", ton === "vert" ? "border-vert-pale bg-vert-pale/40" : "border-orange-pale bg-orange-pale/40")}>
      <p className={cn("flex items-center gap-1.5 text-petit font-semibold uppercase tracking-wide mb-2", ton === "vert" ? "text-vert" : "text-orange")}>
        <Icon className="size-3.5" /> {titre}
      </p>
      <ul className="flex flex-col gap-1.5">
        {items.map((it, i) => (
          <li key={i} className="text-petit text-texte leading-snug">{it}</li>
        ))}
      </ul>
    </div>
  )
}


type DocTelechargeable = {
  cle: string
  icon: LucideIcon
  titre: string
  description?: string
  hrefVoir: string
  hrefTelecharger: string
  extra?: ReactNode
  /** Documents stockés sur le serveur seulement — pas le plan ni le rapport
   * diagnostique, générés à la demande et jamais conservés. */
  onSupprimer?: () => void
}

/** Seuil de couleur du bilan chiffré — mêmes bornes que `ScorePill`. */
function tonNote(note: number): string {
  return note >= 10 ? "bg-vert" : note >= 5 ? "bg-orange" : "bg-rouge"
}

function Resultats({
  jeton,
  resultat,
  documents,
  jetonSession,
  onSupprimer,
}: {
  jeton: string
  resultat: NonNullable<import("@/types/api").CorrectionStatut["resultat"]>
  documents: string[]
  jetonSession: string | null
  onSupprimer: () => void
}) {
  const navigate = useNavigate()
  const { confirmer } = useConfirm()

  // Le parcours (diagnostic structuré + plan) est chargé ici pour être rendu
  // dans le flux de la page, et pour regrouper ses PDF avec ceux de la copie.
  const { data: session } = useQuery({
    queryKey: ["session", jetonSession],
    queryFn: () => sessionsApi.detail(jetonSession as string),
    enabled: !!jetonSession,
  })

  const note = resultat.grade?.final_score_on_20
  const questions = resultat.grade?.questions ?? []
  const reussies = questions.filter((q) => noteFinale(q) > 0).length
  const ratees = questions.filter((q) => noteFinale(q) <= 0).length
  const diag = resultat.diagnostic
  const aDiagnostic =
    !!diag &&
    (!!diag.academic_profile || diag.strengths.length > 0 || diag.weaknesses.length > 0 || diag.competency_gaps.length > 0 || diag.root_causes.length > 0)

  const plan = session ? (session.plan_provisoire.nb_problemes > 0 ? session.plan_provisoire : session.plan) : null
  const planProvisoire = !!session && plan === session.plan_provisoire

  const deposerT1 = jetonSession ? (
    <Link to={`/corrections/confirmation/${jetonSession}`} className="text-petit font-medium text-bleu hover:text-bleu-sombre">
      Déposer la copie T1
    </Link>
  ) : undefined

  const supprimerDocument = useSupprimerDocument([["correction", jeton], ["session", jetonSession]])

  // ── Tous les fichiers téléchargeables : copie + parcours, une seule liste ──
  const docs: DocTelechargeable[] = []
  for (const type of documents) {
    const meta = DOC_COPIE[type]
    if (!meta) continue
    docs.push({
      cle: `copie-${type}`,
      icon: meta.icon,
      titre: meta.titre,
      description: meta.description,
      hrefVoir: elevesApi.documentUrl(jeton, type),
      hrefTelecharger: elevesApi.documentUrl(jeton, type, true),
      extra: type === "sujet_confirmation" ? deposerT1 : undefined,
      onSupprimer: () => supprimerDocument(jeton, type, meta.titre),
    })
  }
  if (session && jetonSession) {
    docs.push({
      cle: "rapport-diagnostique",
      icon: GraduationCap,
      titre: "Rapport diagnostique complet",
      description: "Profil scolaire, lacunes rattachées au programme et causes profondes, en détail.",
      hrefVoir: sessionsApi.rapportDiagnostiqueUrl(jetonSession),
      hrefTelecharger: sessionsApi.rapportDiagnostiqueUrl(jetonSession, true),
    })
    if (plan && plan.etapes.length > 0) {
      docs.push({
        cle: "plan",
        icon: ListChecks,
        titre: planProvisoire ? "Plan de remédiation provisoire" : "Plan de remédiation",
        description: planProvisoire
          ? "Estimation avant le test de confirmation — non contractuelle."
          : "Ordre des séances, volume horaire et palier.",
        hrefVoir: planProvisoire ? sessionsApi.planProvisoireUrl(jetonSession) : sessionsApi.planUrl(jetonSession),
        hrefTelecharger: planProvisoire ? sessionsApi.planProvisoireUrl(jetonSession, true) : sessionsApi.planUrl(jetonSession, true),
      })
    }
    if (session.sujet_t1_disponible && session.sujet_t1_jeton_copie && !documents.includes("sujet_confirmation")) {
      const jetonT1 = session.sujet_t1_jeton_copie
      docs.push({
        cle: "sujet-t1",
        icon: ClipboardList,
        titre: "Sujet du test de confirmation (T1)",
        description: "À faire passer pour confirmer ou écarter chaque hypothèse de lacune.",
        hrefVoir: elevesApi.documentUrl(session.sujet_t1_jeton_copie, "sujet_confirmation"),
        hrefTelecharger: elevesApi.documentUrl(session.sujet_t1_jeton_copie, "sujet_confirmation", true),
        extra: deposerT1,
        onSupprimer: () => supprimerDocument(jetonT1, "sujet_confirmation", "Sujet du test de confirmation (T1)"),
      })
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── 1. Bilan chiffré ──────────────────────────────────────────────── */}
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="inline-flex items-center gap-1.5 text-petit font-semibold uppercase tracking-wide text-vert">
              <CircleCheck className="size-4" /> Correction terminée
            </p>
            <h2 className="text-h2 font-semibold text-marine mt-1">{resultat.student_name || "Copie corrigée"}</h2>
          </div>
          <button
            onClick={async () => {
              if (await confirmer({ titre: "Supprimer cette copie ?", message: "Cette action est définitive : le scan et les documents associés seront supprimés.", texteConfirmer: "Supprimer" })) {
                onSupprimer()
              }
            }}
            className="shrink-0 text-texte-faible hover:text-rouge"
            title="Supprimer cette copie"
          >
            <Trash2 className="size-4" />
          </button>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-x-10 gap-y-4">
          {note != null && (
            <div className="min-w-[200px] flex-1">
              <div className="flex items-end gap-1.5">
                <span className="text-[2.75rem] font-bold leading-none text-marine tabular-nums">{formatNombre(note)}</span>
                <span className="text-h3 text-texte-doux mb-1.5">/ 20</span>
              </div>
              <div className="mt-2.5 h-2 overflow-hidden rounded-rond bg-surface-creuse">
                <div className={cn("h-full rounded-rond", tonNote(note))} style={{ width: `${Math.max(0, Math.min(100, (note / 20) * 100))}%` }} />
              </div>
            </div>
          )}
          <div className="flex gap-8">
            <div>
              <div className="text-chiffre font-bold leading-none text-vert tabular-nums">{reussies}</div>
              <div className="text-petit text-texte-doux mt-1">Question{reussies > 1 ? "s" : ""} réussie{reussies > 1 ? "s" : ""}</div>
            </div>
            <div>
              <div className="text-chiffre font-bold leading-none text-rouge tabular-nums">{ratees}</div>
              <div className="text-petit text-texte-doux mt-1">Question{ratees > 1 ? "s" : ""} ratée{ratees > 1 ? "s" : ""}</div>
            </div>
          </div>
        </div>
      </Card>

      {/* ── 2. Diagnostic — contenu textuel ───────────────────────────────── */}
      {aDiagnostic && diag && (
        <Card>
          <CardTitre>Diagnostic</CardTitre>

          {diag.academic_profile && <p className="max-w-[75ch] text-corps leading-relaxed text-texte">{diag.academic_profile}</p>}

          {(diag.strengths.length > 0 || diag.weaknesses.length > 0) && (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <BlocConstat titre="Points d'appui" items={diag.strengths} icon={ThumbsUp} ton="vert" />
              <BlocConstat titre="Points de fragilité" items={diag.weaknesses} icon={TriangleAlert} ton="orange" />
            </div>
          )}

          {diag.competency_gaps.length > 0 && (
            <div className="mt-6">
              <p className="mb-2.5 text-petit font-semibold uppercase tracking-wide text-texte-doux">Lacunes ancrées sur le programme officiel</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {diag.competency_gaps.map((lacune, i) => (
                  <div key={i} className="rounded-lg border border-bord bg-surface-creuse/60 p-3.5">
                    <p className="text-menu font-medium text-texte">{lacune.lecon}</p>
                    <p className="mt-0.5 text-petit text-texte-doux">{lacune.classe} · {lacune.chapitre}</p>
                    {lacune.description && <p className="mt-1.5 text-petit leading-snug text-texte">{lacune.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {diag.root_causes.length > 0 && (
            <div className="mt-6">
              <p className="mb-2.5 text-petit font-semibold uppercase tracking-wide text-texte-doux">Causes derrière les erreurs visibles</p>
              <div className="grid gap-x-8 sm:grid-cols-2">
                {diag.root_causes.map((cause, i) => (
                  <p key={i} className="border-t border-bord py-2.5 text-petit leading-snug">
                    <strong className="text-texte">{cause.visible_error}</strong>
                    <span className="text-texte-doux"> — {cause.hidden_cause}</span>
                  </p>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ── 3. Plan de remédiation — contenu textuel ──────────────────────── */}
      {session && plan && (
        <Card>
          <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
            <CardTitre className="mb-0">Plan de remédiation</CardTitre>
            {plan.palier && <PalierBadge palier={plan.palier} />}
          </div>

          {plan.etapes.length === 0 ? (
            <p className="mt-2 text-petit text-texte-doux">Aucune lacune détectée sur cette copie — pas de remédiation nécessaire.</p>
          ) : (
            <>
              {planProvisoire && (
                <p className="mt-1 mb-3 text-petit text-orange">
                  Estimation provisoire — à confirmer par le test de confirmation (T1) avant toute décision d'inscription.
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-x-10 gap-y-3">
                <Stat label="Lacunes" value={plan.nb_problemes} />
                <Stat label="Volume estimé" value={formatHeures(plan.total_heures)} />
              </div>
              <div className="mt-4 grid gap-x-8 sm:grid-cols-2">
                {plan.etapes.map((etape) => (
                  <div key={`${etape.competence_id}-${etape.type_erreur_id}`} className="border-t border-bord py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-menu font-medium text-texte">{etape.competence_id}</span>
                      <TypeErreurBadge code={etape.type_erreur_id} />
                      <span className="ml-auto text-petit font-medium text-texte-doux">{formatHeures(etape.cout)}</span>
                    </div>
                    <p className="mt-0.5 text-petit text-texte-doux">{etape.competence_libelle}</p>
                    <p className="mt-1 text-petit leading-snug text-texte">
                      <DiagnosticLisible typeErreurId={etape.type_erreur_id} interpretation={etape.signatures[0]?.interpretation ?? ""} />
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      )}

      {/* ── 4. Documents à télécharger — regroupés ────────────────────────── */}
      {docs.length > 0 && (
        <Card>
          <CardTitre className="mb-1">Documents à télécharger</CardTitre>
          <p className="mb-1 text-petit text-texte-doux">Tous les fichiers produits pour cette copie et ce parcours.</p>
          <div className="grid gap-x-10 sm:grid-cols-2">
            {docs.map((d) => (
              <LigneDocument
                key={d.cle}
                icon={d.icon}
                titre={d.titre}
                description={d.description}
                hrefVoir={d.hrefVoir}
                hrefTelecharger={d.hrefTelecharger}
                extra={d.extra}
                onSupprimer={d.onSupprimer}
              />
            ))}
          </div>
        </Card>
      )}

      {/* ── Actions ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4">
        <Button variant="discret" onClick={() => navigate("/corrections/nouvelle")}>Corriger une autre copie</Button>
        {jetonSession && (
          <Link to={`/sessions/${jetonSession}`} className="inline-flex items-center gap-1 text-petit font-medium text-bleu hover:text-bleu-sombre">
            Voir le parcours complet <ArrowUpRight className="size-3.5" />
          </Link>
        )}
      </div>
    </div>
  )
}
