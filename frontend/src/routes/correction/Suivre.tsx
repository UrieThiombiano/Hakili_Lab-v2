import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur, Spinner } from "@/components/ui/Etat"
import { Stat, StatRow } from "@/components/ui/Stat"
import { TypeErreurBadge, DiagnosticLisible } from "@/components/ui/Badge"
import { LienPdf } from "@/components/ui/LienPdf"
import { correctionsApi, elevesApi, sessionsApi } from "@/lib/api"
import { formatHeures } from "@/lib/format"
import { useToast } from "@/hooks/useToast"
import { useConfirm } from "@/hooks/useConfirm"
import { cn } from "@/lib/utils"
import { ArrowUpRight, CheckCheck, CircleCheck, Pencil, SquareCheck, Trash2, TriangleAlert } from "lucide-react"

/** Libellés lisibles pour les types de document persistés — voir
 * `document.type` en base (`rapport`, `sujet_confirmation`...). */
const LIBELLES_DOCUMENT: Record<string, string> = {
  rapport: "Rapport (PDF)",
  remediation: "Sujet de remédiation (PDF)",
  sujet_confirmation: "Sujet de confirmation T1 (PDF)",
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

  if (!data) return <AppShell><Spinner label="Chargement…" /></AppShell>

  const eleve = data.resultat?.student_name ?? ""
  const large = data.etat === "relecture" || data.etat === "validation"

  return (
    <AppShell titre={eleve ? `Correction — ${eleve}` : "Correction"}>
      <div className={cn("flex flex-col gap-5", large ? "max-w-5xl" : "max-w-2xl")}>
        {(data.en_cours || data.etat === "creee") && <Progression etape={data.etape} progression={data.progression} />}
        {data.etat === "echec" && <Echec erreurs={data.erreurs} onSupprimer={() => supprimer.mutate()} />}
        {data.etat === "relecture" && data.resultat && <Relecture jeton={jeton} resultat={data.resultat} onValide={() => queryClient.invalidateQueries({ queryKey: ["correction", jeton] })} />}
        {data.etat === "validation" && data.resultat && <Validation jeton={jeton} resultat={data.resultat} onValide={() => queryClient.invalidateQueries({ queryKey: ["correction", jeton] })} />}
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
          <img src="/hakili_logo.png" alt="" className="size-16 object-contain" />
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
    Object.fromEntries((resultat.transcription?.pages ?? []).map((p) => [p.page_number, p.content])),
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
        <p className="text-petit text-texte-doux mb-2">Corrigez le texte reconnu si besoin, puis validez pour lancer la correction.</p>
        <p className="text-petit text-texte-doux">
          Les zones marquées <code className="bg-surface-creuse px-1 rounded">[ILLISIBLE]</code> n'ont pas pu être déchiffrées — ce que vous écrivez ici sert de base à la correction.
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

            <div className="grid lg:grid-cols-2 gap-px bg-bord mt-3">
              <div className="bg-surface p-3 flex items-start justify-center">
                <img
                  src={correctionsApi.pageImageUrl(jeton, page.page_number)}
                  alt={`Page ${page.page_number}`}
                  className="max-h-[480px] w-full rounded border border-bord object-contain"
                  onError={(e) => (e.currentTarget.style.display = "none")}
                />
              </div>
              <div className="bg-surface p-3">
                <textarea
                  value={pages[page.page_number] ?? ""}
                  onChange={(e) => setPages((p) => ({ ...p, [page.page_number]: e.target.value }))}
                  className="w-full h-full min-h-[280px] lg:min-h-[480px] rounded border border-bord-fort p-3 text-petit font-mono resize-y focus:border-bleu focus:outline-none"
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

function Validation({ jeton, resultat, onValide }: { jeton: string; resultat: NonNullable<import("@/types/api").CorrectionStatut["resultat"]>; onValide: () => void }) {
  const { notifier } = useToast()
  const [decisions, setDecisions] = useState<Record<string, { decision: string; note?: string | null }>>({})

  const valider = useMutation({
    mutationFn: () => correctionsApi.validerNotes(jeton, decisions),
    onSuccess: () => {
      notifier("Notes validées — diagnostic en cours.")
      onValide()
    },
  })

  const bareme = Object.fromEntries((resultat.rubric?.items ?? []).map((i) => [i.id, i]))
  const questions = resultat.grade?.questions ?? []
  const totalPossible = resultat.rubric?.total_points ?? Object.values(bareme).reduce((s, i) => s + i.max_score, 0)
  const noteActuelle = questions.reduce((s, q) => s + scoreCourant(q, decisions), 0)
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
        <Button chargement={valider.isPending} onClick={() => valider.mutate()}>
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
  const note = resultat.grade?.final_score_on_20
  const questions = resultat.grade?.questions ?? []
  const reussies = questions.filter((q) => noteFinale(q) > 0).length
  const ratees = questions.filter((q) => noteFinale(q) <= 0).length
  const diagnostic = resultat.diagnostic

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <div className="flex items-center justify-between mb-4">
          <CardTitre className="mb-0">Correction terminée</CardTitre>
          <button
            onClick={async () => {
              if (await confirmer({ titre: "Supprimer cette copie ?", message: "Cette action est définitive : le scan et les documents associés seront supprimés.", texteConfirmer: "Supprimer" })) {
                onSupprimer()
              }
            }}
            className="text-texte-faible hover:text-rouge"
          >
            <Trash2 className="size-4" />
          </button>
        </div>

        <StatRow>
          {note != null && <Stat label="Note finale" value={note} unite="/20" />}
          <Stat label="Réussies" value={reussies} />
          <Stat label="Ratées" value={ratees} />
        </StatRow>

        {diagnostic && (diagnostic.academic_profile || diagnostic.competency_gaps.length > 0 || diagnostic.root_causes.length > 0) && (
          <div className="mt-5 pt-5 border-t border-bord flex flex-col gap-4">
            {diagnostic.academic_profile && <p className="text-menu">{diagnostic.academic_profile}</p>}

            {diagnostic.competency_gaps.length > 0 && (
              <div>
                <p className="text-petit font-semibold text-texte-doux uppercase tracking-wide mb-2">Lacunes ancrées sur le programme officiel</p>
                <div className="flex flex-col gap-3">
                  {diagnostic.competency_gaps.map((lacune, i) => (
                    <div key={i}>
                      <p className="text-menu font-medium">{lacune.lecon}</p>
                      <p className="text-petit text-texte-doux">{lacune.classe} · {lacune.chapitre}</p>
                      <p className="text-petit mt-0.5">{lacune.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {diagnostic.root_causes.length > 0 && (
              <div>
                <p className="text-petit font-semibold text-texte-doux uppercase tracking-wide mb-2">Causes derrière les erreurs visibles</p>
                <div className="flex flex-col divide-y divide-bord">
                  {diagnostic.root_causes.map((cause, i) => (
                    <p key={i} className="py-2 text-petit">
                      <strong>{cause.visible_error}</strong> — {cause.hidden_cause}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {documents.length > 0 && (
          <div className="flex flex-wrap gap-4 mt-5 pt-5 border-t border-bord text-menu">
            {documents.map((type) => (
              <LienPdf key={type} label={LIBELLES_DOCUMENT[type] ?? type} hrefVoir={elevesApi.documentUrl(jeton, type)} hrefTelecharger={elevesApi.documentUrl(jeton, type, true)} />
            ))}
          </div>
        )}
        <div className="flex gap-3 mt-4">
          <Button variant="discret" onClick={() => navigate("/corrections/nouvelle")}>Corriger une autre copie</Button>
        </div>
      </Card>

      {jetonSession && <ApercuParcours jetonSession={jetonSession} />}
    </div>
  )
}

/** Lacunes détectées (diagnostic structuré) et plan de remédiation
 * provisoire, en aperçu lecture seule — le détail interactif (confirmer,
 * écarter, inscrire) reste sur l'écran « Parcours ». Sans ceci, une
 * correction terminée ne montrait ni les lacunes que le module 4 vient
 * d'écrire, ni le sujet de confirmation (T1) déjà généré à côté. */
function ApercuParcours({ jetonSession }: { jetonSession: string }) {
  const { data } = useQuery({
    queryKey: ["session", jetonSession],
    queryFn: () => sessionsApi.detail(jetonSession),
  })
  if (!data) return null

  const plan = data.plan_provisoire.nb_problemes > 0 ? data.plan_provisoire : data.plan

  return (
    <Card>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <CardTitre className="mb-0">Diagnostic structuré &amp; plan de remédiation</CardTitre>
        <div className="flex items-center gap-4 text-petit">
          <LienPdf label="Rapport diagnostique" hrefVoir={sessionsApi.rapportDiagnostiqueUrl(jetonSession)} hrefTelecharger={sessionsApi.rapportDiagnostiqueUrl(jetonSession, true)} />
          {plan.etapes.length > 0 && (
            <LienPdf
              label={`Plan ${plan === data.plan ? "" : "provisoire "}(PDF)`}
              hrefVoir={plan === data.plan ? sessionsApi.planUrl(jetonSession) : sessionsApi.planProvisoireUrl(jetonSession)}
              hrefTelecharger={plan === data.plan ? sessionsApi.planUrl(jetonSession, true) : sessionsApi.planProvisoireUrl(jetonSession, true)}
            />
          )}
        </div>
      </div>

      {plan.etapes.length === 0 ? (
        <p className="text-petit text-texte-doux">Aucune lacune détectée sur cette copie.</p>
      ) : (
        <>
          {plan === data.plan_provisoire && (
            <p className="text-petit text-orange mb-3">
              Estimation provisoire — à confirmer par le test de confirmation (T1) avant toute décision d'inscription.
            </p>
          )}
          <StatRow>
            <Stat label="Lacunes" value={plan.nb_problemes} />
            <Stat label="Volume estimé" value={formatHeures(plan.total_heures)} />
          </StatRow>
          <div className="flex flex-col divide-y divide-bord mt-4">
            {plan.etapes.map((etape) => (
              <div key={`${etape.competence_id}-${etape.type_erreur_id}`} className="py-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-menu font-medium">{etape.competence_id}</span>
                  <TypeErreurBadge code={etape.type_erreur_id} />
                  <span className="text-petit text-texte-doux font-medium ml-auto">{formatHeures(etape.cout)}</span>
                </div>
                <p className="text-petit text-texte-doux mt-0.5">{etape.competence_libelle}</p>
                <p className="text-petit text-texte mt-1">
                  <DiagnosticLisible typeErreurId={etape.type_erreur_id} interpretation={etape.signatures[0]?.interpretation ?? ""} />
                </p>
              </div>
            ))}
          </div>
        </>
      )}

      {data.sujet_t1_disponible && data.sujet_t1_jeton_copie && (
        <div className="mt-5 pt-5 border-t border-bord flex items-center justify-between flex-wrap gap-3">
          <LienPdf
            label="Sujet de confirmation T1 (PDF)"
            className="text-menu"
            hrefVoir={elevesApi.documentUrl(data.sujet_t1_jeton_copie, "sujet_confirmation")}
            hrefTelecharger={elevesApi.documentUrl(data.sujet_t1_jeton_copie, "sujet_confirmation", true)}
          />
          <Link to={`/corrections/confirmation/${jetonSession}`} className="text-petit text-bleu hover:text-bleu-sombre font-medium">
            Déposer la copie T1
          </Link>
        </div>
      )}

      <Link to={`/sessions/${jetonSession}`} className="inline-flex items-center gap-1 text-petit text-bleu hover:text-bleu-sombre font-medium mt-5">
        Voir le parcours complet <ArrowUpRight className="size-3.5" />
      </Link>
    </Card>
  )
}
