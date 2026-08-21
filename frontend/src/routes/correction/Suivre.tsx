import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { EtatErreur, Spinner } from "@/components/ui/Etat"
import { Stat, StatRow } from "@/components/ui/Stat"
import { correctionsApi, elevesApi } from "@/lib/api"
import { useToast } from "@/hooks/useToast"
import { useConfirm } from "@/hooks/useConfirm"
import { cn } from "@/lib/utils"
import { Download, Trash2, TriangleAlert } from "lucide-react"

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
        {data.terminee && data.resultat && <Resultats jeton={jeton} resultat={data.resultat} onSupprimer={() => supprimer.mutate()} />}
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

  return (
    <Card>
      <CardTitre>Validation des notes</CardTitre>
      <p className="text-petit text-texte-doux mb-4">L'IA propose une note par question — acceptez ou corrigez chacune.</p>
      <div className="flex flex-col divide-y divide-bord">
        {(resultat.grade?.questions ?? []).map((q) => {
          const item = bareme[q.rubric_item_id]
          const decision = decisions[q.rubric_item_id]?.decision ?? "accepted"
          return (
            <div key={q.rubric_item_id} className={`py-3 ${q.requires_review ? "bg-orange-pale -mx-5 px-5" : ""}`}>
              <div className="flex items-center justify-between gap-3 mb-1">
                <span className="text-menu font-medium">
                  {item?.label ?? q.rubric_item_id}
                  {q.requires_review && <span className="ml-2 text-petit text-orange font-normal">à revoir</span>}
                </span>
                <span className="text-petit text-texte-doux">IA : {q.score}/{item?.max_score ?? 1}</span>
              </div>
              {q.correct_answer && <p className="text-petit text-texte-doux">Attendu : {q.correct_answer}</p>}
              <p className="text-petit text-texte-doux mb-2">Réponse de l'élève : {q.observed_answer || "—"}</p>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-petit">
                  <input type="radio" name={`d-${q.rubric_item_id}`} checked={decision === "accepted"} onChange={() => setDecisions((d) => ({ ...d, [q.rubric_item_id]: { decision: "accepted" } }))} />
                  Accepter
                </label>
                <label className="flex items-center gap-1.5 text-petit">
                  <input type="radio" name={`d-${q.rubric_item_id}`} checked={decision === "refused"} onChange={() => setDecisions((d) => ({ ...d, [q.rubric_item_id]: { decision: "refused", note: d[q.rubric_item_id]?.note ?? String(q.score) } }))} />
                  Corriger
                </label>
                {decision === "refused" && (
                  <input
                    type="number"
                    step="0.25"
                    min={0}
                    max={item?.max_score ?? 1}
                    value={decisions[q.rubric_item_id]?.note ?? ""}
                    onChange={(e) => setDecisions((d) => ({ ...d, [q.rubric_item_id]: { decision: "refused", note: e.target.value } }))}
                    className="w-20 h-8 rounded border border-bord-fort px-2 text-petit"
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>
      <Button className="mt-4" chargement={valider.isPending} onClick={() => valider.mutate()}>
        Valider les notes
      </Button>
    </Card>
  )
}

/** Note finale d'une question : la décision de l'enseignant prime toujours
 * sur la proposition de l'IA (D-CEO-16) — même règle que
 * `correction_web/views.py::_note_finale`. */
function noteFinale(q: { teacher_decision: string; teacher_score: number | null; score: number }): number {
  if (q.teacher_decision === "refused" && q.teacher_score != null) return q.teacher_score
  return q.score
}

function Resultats({ jeton, resultat, onSupprimer }: { jeton: string; resultat: NonNullable<import("@/types/api").CorrectionStatut["resultat"]>; onSupprimer: () => void }) {
  const navigate = useNavigate()
  const { confirmer } = useConfirm()
  const note = resultat.grade?.final_score_on_20
  const questions = resultat.grade?.questions ?? []
  const reussies = questions.filter((q) => noteFinale(q) > 0).length
  const ratees = questions.filter((q) => noteFinale(q) <= 0).length
  const diagnostic = resultat.diagnostic

  return (
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

      <div className="flex flex-wrap gap-4 mt-5 pt-5 border-t border-bord">
        <a href={elevesApi.documentUrl(jeton, "rapport", true)} className="inline-flex items-center gap-1.5 text-menu text-bleu hover:text-bleu-sombre">
          <Download className="size-4" /> Rapport (PDF)
        </a>
        <a href={elevesApi.documentUrl(jeton, "remediation", true)} className="inline-flex items-center gap-1.5 text-menu text-bleu hover:text-bleu-sombre">
          <Download className="size-4" /> Plan de remédiation (PDF)
        </a>
      </div>
      <div className="flex gap-3 mt-4">
        <Button variant="discret" onClick={() => navigate("/corrections/nouvelle")}>Corriger une autre copie</Button>
      </div>
    </Card>
  )
}
