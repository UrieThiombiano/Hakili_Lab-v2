import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Spinner, EtatVide } from "@/components/ui/Etat"
import { EtatSessionBadge, PalierBadge, TypeErreurBadge, DiagnosticLisible } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { sessionsApi } from "@/lib/api"
import { formatDate, formatHeures } from "@/lib/format"
import { useToast } from "@/hooks/useToast"
import { Download, FileText, ListChecks, Clock, ArrowUpRight, UploadCloud } from "lucide-react"
import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"
import type { ProblemeSchema } from "@/types/api"

function initiales(nom: string, prenom: string) {
  return `${nom[0] ?? ""}${prenom[0] ?? ""}`.toUpperCase() || "?"
}

function StatIcone({ icon: Icon, value, label, tint }: { icon: LucideIcon; value: string | number; label: string; tint: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className={cn("flex items-center justify-center size-10 rounded-rond shrink-0", tint)}>
        <Icon className="size-4.5" />
      </span>
      <div>
        <p className="text-h2 font-bold text-marine leading-none">{value}</p>
        <p className="text-petit text-texte-doux mt-0.5">{label}</p>
      </div>
    </div>
  )
}

function LigneProbleme({ numero, probleme, actions }: { numero?: number; probleme: ProblemeSchema; actions?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 px-2 -mx-2 rounded transition-colors duration-150 hover:bg-surface-creuse">
      <div className="flex items-start gap-3 min-w-0">
        {numero != null && (
          <span className="mt-0.5 size-6 rounded-rond bg-surface-creuse text-texte-doux text-micro font-bold flex items-center justify-center shrink-0">
            {numero}
          </span>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-menu font-semibold text-marine">{probleme.competence_id}</span>
            <TypeErreurBadge code={probleme.type_erreur_id} />
          </div>
          <p className="text-petit text-texte-doux mt-0.5">{probleme.competence_libelle}</p>
          <p className="text-petit text-texte mt-1">
            <DiagnosticLisible typeErreurId={probleme.type_erreur_id} interpretation={probleme.interpretation} />
          </p>
          {probleme.justification && (
            <details className="mt-1.5 group">
              <summary className="text-micro text-bleu hover:text-bleu-sombre cursor-pointer list-none inline-flex items-center gap-1">
                Voir la preuve sur la copie
              </summary>
              <p className="text-petit text-texte-doux font-mono mt-1.5 bg-surface-creuse rounded px-2 py-1 break-words">
                {probleme.justification}
              </p>
            </details>
          )}
        </div>
      </div>
      {actions && <div className="flex gap-2 shrink-0 pt-0.5">{actions}</div>}
    </div>
  )
}

export default function SessionDetail() {
  const { jeton = "" } = useParams()
  const queryClient = useQueryClient()
  const { notifier } = useToast()
  const [motifInscription, setMotifInscription] = useState("")
  const [forcerInscription, setForcerInscription] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["session", jeton],
    queryFn: () => sessionsApi.detail(jeton),
  })

  const invalider = () => queryClient.invalidateQueries({ queryKey: ["session", jeton] })

  const trancher = useMutation({
    mutationFn: ({ type, id, decision }: { type: string; id: number; decision: string }) => sessionsApi.trancher(jeton, type, { [id]: decision }),
    onSuccess: () => {
      invalider()
      notifier("Décision enregistrée.")
    },
    onError: () => notifier("Échec de l'enregistrement.", "erreur"),
  })

  const relancer = useMutation({
    mutationFn: (id: number) => sessionsApi.relancer(jeton, id, ""),
    onSuccess: () => {
      invalider()
      notifier("Problème relancé en remédiation.")
    },
  })

  const inscrire = useMutation({
    mutationFn: () => sessionsApi.inscrire(jeton, forcerInscription, motifInscription),
    onSuccess: (rep) => {
      invalider()
      notifier(`${rep.nb_problemes_en_remediation} problème(s) en remédiation — ${formatHeures(rep.cout_total_confirme)} prévues.`)
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : "Inscription impossible."
      notifier(message, "erreur")
    },
  })

  if (isLoading) return <AppShell><Spinner label="Chargement du parcours…" /></AppShell>
  if (!data) return <AppShell><EtatVide titre="Session introuvable" /></AppShell>

  const nomEleve = String(data.eleve.nom ?? "")
  const prenomEleve = String(data.eleve.prenom ?? "")
  const nom = `${nomEleve} ${prenomEleve}`.trim()

  return (
    <AppShell titre={`Parcours — ${nom}`}>
      <Card className="mb-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3.5 min-w-0">
            <span className="flex items-center justify-center size-12 rounded-rond bg-bleu-pale text-bleu-sombre font-semibold text-lead shrink-0">
              {initiales(nomEleve, prenomEleve)}
            </span>
            <div className="min-w-0">
              <p className="text-h3 font-semibold text-marine leading-tight truncate">{nom}</p>
              <div className="flex items-center gap-2 flex-wrap mt-1.5">
                <EtatSessionBadge etat={data.etat} />
                {data.palier && <PalierBadge palier={data.palier} />}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 flex-wrap shrink-0">
            <Link
              to={`/eleves/${data.jeton_eleve}`}
              className="inline-flex items-center gap-1 text-petit text-bleu hover:text-bleu-sombre font-medium"
            >
              Voir le profil élève <ArrowUpRight className="size-3.5" />
            </Link>
            <Link to={`/corrections/nouvelle?eleve=${data.jeton_eleve}`}>
              <Button taille="petit">Introduire une nouvelle analyse</Button>
            </Link>
          </div>
        </div>
        <p className="text-petit text-texte-doux mt-4 pt-4 border-t border-bord">
          Parcours ouvert le {formatDate(data.date_debut)}
          {data.date_inscription && <> · inscrit en remédiation le {formatDate(data.date_inscription)}</>}
        </p>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 flex flex-col gap-5">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <CardTitre className="mb-0">Plan de remédiation</CardTitre>
              {data.plan.etapes.length > 0 && (
                <a href={sessionsApi.planUrl(jeton, true)} className="inline-flex items-center gap-1.5 text-petit text-bleu hover:text-bleu-sombre">
                  <Download className="size-3.5" /> Plan PDF
                </a>
              )}
            </div>
            {data.plan.etapes.length === 0 ? (
              <EtatVide titre="Aucun problème confirmé" description="Le plan apparaît une fois le test de confirmation passé." />
            ) : (
              <>
                <div className="flex flex-wrap gap-6">
                  <StatIcone icon={ListChecks} value={data.plan.nb_problemes} label="Problèmes" tint="bg-bleu-pale text-bleu-sombre" />
                  <StatIcone icon={Clock} value={formatHeures(data.plan.total_heures)} label="Volume estimé" tint="bg-orange-pale text-orange" />
                </div>
                {data.plan.repose_sur_estimation && (
                  <p className="text-petit text-orange mt-3">⚠ Ce plan repose en partie sur un volume horaire estimé (compétence de lycée sans donnée officielle).</p>
                )}
                <div className="flex flex-col divide-y divide-bord mt-4">
                  {data.plan.etapes.map((etape) => (
                    <div
                      key={`${etape.competence_id}-${etape.type_erreur_id}`}
                      className="py-3 px-2 -mx-2 rounded transition-colors duration-150 hover:bg-surface-creuse"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className="mt-0.5 size-6 rounded-rond bg-bleu-pale text-bleu-sombre text-micro font-bold flex items-center justify-center shrink-0">
                          {etape.rang}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3 flex-wrap">
                            <div className="flex items-center gap-2 flex-wrap min-w-0">
                              <span className="text-menu font-medium">{etape.competence_id}</span>
                              <TypeErreurBadge code={etape.type_erreur_id} />
                            </div>
                            <span className="text-petit text-texte-doux font-medium shrink-0">{formatHeures(etape.cout)}</span>
                          </div>
                          <p className="text-petit text-texte mt-0.5">{etape.competence_libelle}</p>
                          <p className="text-petit text-texte mt-1">
                            <DiagnosticLisible typeErreurId={etape.type_erreur_id} interpretation={etape.signatures[0]?.interpretation ?? ""} />
                          </p>
                          {etape.signatures[0] && (
                            <details className="mt-1.5 group">
                              <summary className="text-micro text-bleu hover:text-bleu-sombre cursor-pointer list-none inline-flex items-center gap-1">
                                Voir un exemple sur une copie
                              </summary>
                              <p className="text-petit text-texte-doux font-mono mt-1.5 bg-surface-creuse rounded px-2 py-1 break-words">
                                « {etape.signatures[0].production_eleve} »
                              </p>
                            </details>
                          )}
                          {etape.prerequis_bloquants.length > 0 && (
                            <p className="text-micro text-texte-doux mt-1.5">
                              À traiter d'abord : {etape.prerequis_bloquants.map((p) => p.libelle).join(", ")}
                            </p>
                          )}
                          <a
                            href={sessionsApi.ficheTravailUrl(jeton, etape.probleme_id, true)}
                            className="inline-flex items-center gap-1 text-micro text-bleu hover:text-bleu-sombre mt-1.5"
                          >
                            <FileText className="size-3" /> Fiche de travail (séance)
                          </a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>

          {data.hypotheses.length > 0 && (
            <Card>
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <CardTitre className="mb-0">Hypothèses à confirmer (T1)</CardTitre>
                  <span className="inline-flex items-center justify-center min-w-6 h-6 px-1.5 rounded-rond bg-orange-pale text-orange text-micro font-bold">
                    {data.hypotheses.length}
                  </span>
                </div>
                {data.sujet_t1_disponible && (
                  <Link to={`/corrections/confirmation/${jeton}`} className="text-petit text-bleu hover:text-bleu-sombre font-medium">
                    Déposer la copie T1
                  </Link>
                )}
              </div>
              <p className="text-petit text-texte-doux mb-2">
                Volume estimé (hypothèses, avant confirmation) : <span className="font-medium text-texte">{formatHeures(data.cout_total_hypothese)}</span>
              </p>
              {data.sujet_t1_disponible && (
                <p className="text-petit text-texte-doux mb-2 pb-3 border-b border-bord">
                  Dépose le scan des réponses de l'élève : le système corrige, puis confirme ou écarte chaque hypothèse automatiquement.
                  La saisie manuelle ci-dessous reste disponible si vous préférez trancher vous-même.
                </p>
              )}
              <div className="flex flex-col divide-y divide-bord">
                {data.hypotheses.map((p, i) => (
                  <LigneProbleme
                    key={p.id}
                    numero={i + 1}
                    probleme={p}
                    actions={
                      p.type_erreur_id === "ATT" ? (
                        <Button taille="petit" variant="discret" onClick={() => trancher.mutate({ type: "T1", id: p.id, decision: "ecarte" })}>
                          Écarter
                        </Button>
                      ) : (
                        <>
                          <Button taille="petit" variant="discret" onClick={() => trancher.mutate({ type: "T1", id: p.id, decision: "ecarte" })}>
                            Écarter
                          </Button>
                          <Button taille="petit" onClick={() => trancher.mutate({ type: "T1", id: p.id, decision: "confirme" })}>
                            Confirmer
                          </Button>
                        </>
                      )
                    }
                  />
                ))}
              </div>
            </Card>
          )}

          {data.en_remediation.length > 0 && (
            <Card>
              <div className="flex items-center justify-between mb-2">
                <CardTitre className="mb-0">En remédiation — vérification (T3)</CardTitre>
                <div className="flex items-center gap-3">
                  <a href={sessionsApi.sujetUrl(jeton, "T3", true)} className="inline-flex items-center gap-1.5 text-petit text-bleu hover:text-bleu-sombre">
                    <FileText className="size-3.5" /> Sujet T3
                  </a>
                  <Link to={`/corrections/verification/${jeton}/T3`} className="inline-flex items-center gap-1.5 text-petit text-bleu hover:text-bleu-sombre">
                    <UploadCloud className="size-3.5" /> Déposer la copie corrigée
                  </Link>
                </div>
              </div>
              <p className="text-petit text-texte-doux mb-2">
                Générez le sujet une fois le volume horaire prévu écoulé. Déposez la copie corrigée pour un
                diagnostic automatique, ou reportez le résultat vous-même ci-dessous.
              </p>
              <div className="flex flex-col divide-y divide-bord">
                {data.en_remediation.map((p) => (
                  <LigneProbleme
                    key={p.id}
                    probleme={p}
                    actions={
                      <>
                        <Button taille="petit" variant="discret" onClick={() => trancher.mutate({ type: "T3", id: p.id, decision: "non_resolu" })}>
                          Non résolu
                        </Button>
                        <Button taille="petit" onClick={() => trancher.mutate({ type: "T3", id: p.id, decision: "resolu" })}>
                          Résolu
                        </Button>
                      </>
                    }
                  />
                ))}
              </div>
            </Card>
          )}

          {data.non_resolus.length > 0 && (
            <Card>
              <CardTitre>Non résolus</CardTitre>
              <div className="flex flex-col divide-y divide-bord">
                {data.non_resolus.map((p) => (
                  <LigneProbleme key={p.id} probleme={p} actions={<Button taille="petit" chargement={relancer.isPending} onClick={() => relancer.mutate(p.id)}>Relancer en remédiation</Button>} />
                ))}
              </div>
            </Card>
          )}

          {data.resolus.length > 0 && (
            <Card>
              <div className="flex items-center justify-between mb-2">
                <CardTitre className="mb-0">Résolus — contrôle de rétention</CardTitre>
                <div className="flex gap-3">
                  {["T4", "T5"].map((t) => (
                    <span key={t} className="flex items-center gap-3">
                      <a href={sessionsApi.sujetUrl(jeton, t, true)} className="inline-flex items-center gap-1 text-petit text-bleu hover:text-bleu-sombre">
                        <FileText className="size-3.5" /> Sujet {t}
                      </a>
                      <Link to={`/corrections/verification/${jeton}/${t}`} className="inline-flex items-center gap-1 text-petit text-bleu hover:text-bleu-sombre">
                        <UploadCloud className="size-3.5" /> Déposer
                      </Link>
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-col divide-y divide-bord">
                {data.resolus.map((p) => (
                  <LigneProbleme
                    key={p.id}
                    probleme={p}
                    actions={
                      <>
                        <Button taille="petit" variant="discret" onClick={() => trancher.mutate({ type: "T4", id: p.id, decision: "regresse" })}>
                          Régressé
                        </Button>
                        <Button taille="petit" onClick={() => trancher.mutate({ type: "T5", id: p.id, decision: "clos" })}>
                          Clore (T5)
                        </Button>
                      </>
                    }
                  />
                ))}
              </div>
            </Card>
          )}

          {data.regresses.length > 0 && (
            <Card>
              <CardTitre>Régressés</CardTitre>
              <div className="flex flex-col divide-y divide-bord">
                {data.regresses.map((p) => (
                  <LigneProbleme key={p.id} probleme={p} actions={<Button taille="petit" chargement={relancer.isPending} onClick={() => relancer.mutate(p.id)}>Relancer en remédiation</Button>} />
                ))}
              </div>
            </Card>
          )}

          {data.ecartes.length > 0 && (
            <Card variant="plate">
              <CardTitre>Écartés</CardTitre>
              <div className="flex flex-col divide-y divide-bord">
                {data.ecartes.map((p) => (
                  <LigneProbleme key={p.id} probleme={p} />
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-5">
          <Card variant="plate">
            <CardTitre>Résumé de la session</CardTitre>
            <dl className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-petit text-texte-doux">État</dt>
                <dd><EtatSessionBadge etat={data.etat} /></dd>
              </div>
              {data.palier && (
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-petit text-texte-doux">Palier</dt>
                  <dd><PalierBadge palier={data.palier} /></dd>
                </div>
              )}
              <div className="flex items-center justify-between gap-3">
                <dt className="text-petit text-texte-doux">Ouverte le</dt>
                <dd className="text-petit font-medium text-texte">{formatDate(data.date_debut)}</dd>
              </div>
              {data.date_inscription && (
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-petit text-texte-doux">Inscrite le</dt>
                  <dd className="text-petit font-medium text-texte">{formatDate(data.date_inscription)}</dd>
                </div>
              )}
            </dl>
          </Card>

          {data.peut_inscrire && (
            <Card variant="appel">
              <CardTitre>Inscription au programme</CardTitre>
              {data.palier_c && (
                <div className="mb-3">
                  <p className="text-petit text-rouge mb-2">Palier C : plus de 20 h estimées. Une dérogation motivée est requise.</p>
                  <label className="flex items-center gap-2 text-petit mb-2">
                    <input type="checkbox" checked={forcerInscription} onChange={(e) => setForcerInscription(e.target.checked)} />
                    Inscrire malgré tout
                  </label>
                  {forcerInscription && (
                    <textarea
                      value={motifInscription}
                      onChange={(e) => setMotifInscription(e.target.value)}
                      placeholder="Motif de la dérogation…"
                      className="w-full rounded border border-bord-fort p-2 text-petit"
                      rows={2}
                    />
                  )}
                </div>
              )}
              <Button
                className="w-full"
                chargement={inscrire.isPending}
                disabled={data.palier_c && (!forcerInscription || !motifInscription.trim())}
                onClick={() => inscrire.mutate()}
              >
                Inscrire au programme
              </Button>
            </Card>
          )}
        </div>
      </div>
    </AppShell>
  )
}
