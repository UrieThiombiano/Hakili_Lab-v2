import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { FileText, Trash2, ArrowUpRight } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Spinner, EtatVide } from "@/components/ui/Etat"
import { TendanceBadge, EtatSessionBadge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Stat, StatRow } from "@/components/ui/Stat"
import { elevesApi } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { useToast } from "@/hooks/useToast"
import { useConfirm } from "@/hooks/useConfirm"
import { useSupprimerDocument } from "@/hooks/useSupprimerDocument"

export default function ProfilEleve() {
  const { jeton = "" } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notifier } = useToast()
  const { confirmer } = useConfirm()

  const { data, isLoading } = useQuery({
    queryKey: ["eleve", jeton],
    queryFn: () => elevesApi.detail(jeton),
  })

  const supprimerDocument = useSupprimerDocument([["eleve", jeton]])

  const supprimer = useMutation({
    mutationFn: (jetonCopie: string) => elevesApi.supprimerCopie(jetonCopie),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eleve", jeton] })
      notifier("Copie supprimée.")
    },
    onError: () => notifier("Suppression impossible.", "erreur"),
  })

  if (isLoading) return <AppShell><Spinner label="Chargement du profil…" /></AppShell>
  if (!data) return <AppShell><EtatVide titre="Élève introuvable" /></AppShell>

  const nom = `${String(data.eleve.nom ?? "")} ${String(data.eleve.prenom ?? "")}`.trim()

  return (
    <AppShell titre={nom}>
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 flex flex-col gap-5">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <StatRow>
                <Stat label="Copies" value={data.nb_copies} />
                <Stat label="Dernière note" value={data.derniere_note != null ? data.derniere_note : "—"} unite={data.derniere_note != null ? "/20" : undefined} />
              </StatRow>
              <TendanceBadge tendance={data.tendance} />
            </div>

            {data.courbe.length >= 2 ? (
              <div className="h-48 -ml-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.courbe.map((p) => ({ ...p, date: formatDate(p.date) }))}>
                    <CartesianGrid stroke="var(--color-bord)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--color-texte-doux)" }} axisLine={{ stroke: "var(--color-bord)" }} tickLine={false} />
                    <YAxis domain={[0, 20]} tick={{ fontSize: 11, fill: "var(--color-texte-doux)" }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={{ fontSize: 13, borderRadius: 8, borderColor: "var(--color-bord)" }} />
                    <Line type="monotone" dataKey="note" stroke="var(--color-bleu)" strokeWidth={2.5} dot={{ r: 3, fill: "var(--color-bleu)" }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-petit text-texte-doux">Pas assez de copies notées pour tracer une courbe.</p>
            )}
          </Card>

          <Card>
            <CardTitre>Copies</CardTitre>
            {data.entrees.length === 0 && <EtatVide titre="Aucune copie déposée" />}
            <div className="flex flex-col divide-y divide-bord">
              {data.entrees.map((entree) => (
                <div key={entree.copy_id} className="py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-menu font-medium">
                      {formatDate(entree.date_soumission)} — {entree.classe}
                      {entree.notes_finales != null && <span className="text-texte-doux font-normal"> · {entree.notes_finales}/20</span>}
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                      {entree.documents.map((doc) => (
                        <span key={doc.type} className="inline-flex items-center gap-1.5 text-petit">
                          <FileText className="size-3.5 text-texte-faible" />
                          {doc.libelle}
                          <a href={elevesApi.documentUrl(entree.jeton, doc.type)} target="_blank" rel="noreferrer" className="text-bleu hover:text-bleu-sombre">
                            Voir
                          </a>
                          <a href={elevesApi.documentUrl(entree.jeton, doc.type, true)} className="text-bleu hover:text-bleu-sombre">
                            Télécharger
                          </a>
                          <button
                            type="button"
                            onClick={() => supprimerDocument(entree.jeton, doc.type, doc.libelle)}
                            className="text-texte-faible hover:text-rouge"
                          >
                            Supprimer
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={async () => {
                      if (await confirmer({ titre: "Supprimer cette copie ?", message: "Cette action est définitive : le scan et les documents associés seront supprimés.", texteConfirmer: "Supprimer" })) {
                        supprimer.mutate(entree.jeton)
                      }
                    }}
                    className="text-texte-faible hover:text-rouge shrink-0"
                    title="Supprimer"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardTitre>Parcours</CardTitre>
            {data.parcours.length === 0 && <EtatVide titre="Aucun parcours ouvert" />}
            <div className="flex flex-col gap-2">
              {data.parcours.map((s) => (
                <Link
                  key={s.id}
                  to={`/sessions/${s.jeton}`}
                  className="flex items-center justify-between rounded border border-bord p-3 hover:border-bleu transition-colors"
                >
                  <div>
                    <EtatSessionBadge etat={s.etat} />
                    {s.hypotheses.length > 0 && <p className="text-petit text-texte-doux mt-1">{s.hypotheses.length} hypothèse{s.hypotheses.length > 1 ? "s" : ""}</p>}
                  </div>
                  <ArrowUpRight className="size-4 text-texte-faible" />
                </Link>
              ))}
            </div>
          </Card>

          <Button variant="discret" onClick={() => navigate(`/corrections/nouvelle?eleve=${data.jeton_nouvelle_analyse}`)} className="w-full">
            Nouvelle correction
          </Button>
        </div>
      </div>
    </AppShell>
  )
}
