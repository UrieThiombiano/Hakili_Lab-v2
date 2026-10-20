import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { Card, CardTitre } from "@/components/ui/Card"
import { Spinner, EtatVide } from "@/components/ui/Etat"
import { EtatSessionBadge, PalierBadge, TypeErreurBadge, DiagnosticLisible } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { LigneDocument } from "@/components/ui/LigneDocument"
import { elevesApi, sessionsApi } from "@/lib/api"
import { formatDate, formatHeures } from "@/lib/format"
import { useToast } from "@/hooks/useToast"
import { useSupprimerDocument } from "@/hooks/useSupprimerDocument"
import {
  ArrowUpRight,
  CircleCheck,
  ClipboardList,
  Clock,
  FilePlus2,
  FlaskConical,
  GraduationCap,
  ListChecks,
  UploadCloud,
  Wrench,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { PrerequisBloquant, ProblemeSchema } from "@/types/api"

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

function LigneProbleme({
  numero,
  probleme,
  actions,
  cout,
  prerequisBloquants,
}: {
  numero?: number
  probleme: ProblemeSchema
  actions?: React.ReactNode
  /** Coût estimé de cette lacune — affiché quand la ligne vient d'un plan (confirmé ou provisoire). */
  cout?: string
  /** Prérequis eux-mêmes en difficulté, dans l'ordre du plan — voir `EtapePlanSchema`. */
  prerequisBloquants?: PrerequisBloquant[]
}) {
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
            {cout != null && <span className="text-petit text-texte-doux font-medium">{formatHeures(cout)}</span>}
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
          {prerequisBloquants && prerequisBloquants.length > 0 && (
            <p className="text-micro text-texte-doux mt-1.5">
              À traiter d'abord : {prerequisBloquants.map((p) => p.libelle).join(", ")}
            </p>
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
  const [sujetPret, setSujetPret] = useState<{ url: string; nom: string } | null>(null)
  const sujetUrlRef = useRef<string | null>(null)

  // Libère l'URL blob du dernier sujet généré au démontage.
  useEffect(() => () => { if (sujetUrlRef.current) URL.revokeObjectURL(sujetUrlRef.current) }, [])

  const { data, isLoading } = useQuery({
    queryKey: ["session", jeton],
    queryFn: () => sessionsApi.detail(jeton),
  })

  const invalider = () => queryClient.invalidateQueries({ queryKey: ["session", jeton] })
  const supprimerDocument = useSupprimerDocument([["session", jeton]])

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

  const genererTest = useMutation({
    mutationFn: () => sessionsApi.sujetTestBlob(jeton),
    onSuccess: (blob) => {
      if (sujetUrlRef.current) URL.revokeObjectURL(sujetUrlRef.current)
      const url = URL.createObjectURL(blob)
      sujetUrlRef.current = url
      setSujetPret({ url, nom: `sujet_test_${nom.replace(/\s+/g, "_") || "eleve"}.pdf` })
      invalider()
      notifier("Sujet de test généré à partir des lacunes actuelles.")
    },
    onError: (err: unknown) => notifier(err instanceof Error ? err.message : "Génération du sujet impossible.", "erreur"),
  })

  if (isLoading) return <AppShell><Spinner label="Chargement du parcours…" /></AppShell>
  if (!data) return <AppShell><EtatVide titre="Session introuvable" /></AppShell>

  const nomEleve = String(data.eleve.nom ?? "")
  const prenomEleve = String(data.eleve.prenom ?? "")
  const nom = `${nomEleve} ${prenomEleve}`.trim()

  const peutGenererTest = data.hypotheses.length > 0 || data.en_remediation.length > 0 || data.resolus.length > 0
  const phaseTest =
    data.hypotheses.length > 0
      ? "confirmation (T1)"
      : data.en_remediation.length > 0
        ? "vérification (T3)"
        : data.resolus.length > 0
          ? "rétention (T4)"
          : null

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
              <Button taille="petit" variant="discret">Introduire une nouvelle analyse</Button>
            </Link>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-bord flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <p className="text-petit text-texte-doux">
            Parcours ouvert le {formatDate(data.date_debut)}
            {data.date_inscription && <> · inscrit en remédiation le {formatDate(data.date_inscription)}</>}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              taille="petit"
              chargement={genererTest.isPending}
              disabled={!peutGenererTest}
              onClick={() => genererTest.mutate()}
              title={peutGenererTest ? undefined : "Aucune lacune à évaluer pour l'instant"}
            >
              <FlaskConical className="size-4" />
              {genererTest.isPending ? "Génération en cours…" : "Générer un sujet de test"}
            </Button>
            <span className="text-micro text-texte-doux">
              {genererTest.isPending
                ? "cela peut prendre une minute…"
                : phaseTest
                  ? `à partir des lacunes actuelles — ${phaseTest}`
                  : null}
            </span>
          </div>
        </div>

        {sujetPret && (
          <div className="mt-3 flex flex-wrap items-center gap-4 rounded-lg border border-vert-pale bg-vert-pale/40 px-3.5 py-2.5 text-petit">
            <span className="inline-flex items-center gap-1.5 font-medium text-texte">
              <CircleCheck className="size-4 text-vert" /> Sujet de test prêt
            </span>
            <a href={sujetPret.url} target="_blank" rel="noreferrer" className="font-medium text-bleu hover:text-bleu-sombre">
              Ouvrir le PDF
            </a>
            <a href={sujetPret.url} download={sujetPret.nom} className="font-medium text-bleu hover:text-bleu-sombre">
              Télécharger
            </a>
            <span className="text-texte-doux">Régénère à tout moment pour refléter les dernières décisions.</span>
          </div>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 flex flex-col gap-5">
          {/* ── Contenu textuel : où en est le parcours ─────────────────── */}
          <Card>
            <CardTitre>Plan de remédiation</CardTitre>
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
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-micro text-texte-doux mt-3 pt-3 border-t border-bord">
                  Fiches de travail, plan PDF et sujets à générer : voir « Documents &amp; sujets » plus bas.
                </p>
              </>
            )}
          </Card>

          {data.hypotheses.length > 0 && (
            <Card>
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <CardTitre className="mb-0">Plan provisoire (non confirmé)</CardTitre>
                <span className="inline-flex items-center px-2 h-6 rounded-rond bg-orange-pale text-orange text-micro font-bold uppercase tracking-wide">
                  Provisoire
                </span>
              </div>
              <p className="text-petit text-orange mb-3">
                Estimation construite à partir de lacunes non encore confirmées — à confirmer par le test de confirmation (T1) avant toute décision d'inscription.
              </p>
              <div className="flex flex-wrap gap-6 mb-3">
                <StatIcone icon={ListChecks} value={data.plan_provisoire.nb_problemes} label="Lacunes (hypothèses)" tint="bg-orange-pale text-orange" />
                <StatIcone icon={Clock} value={formatHeures(data.plan_provisoire.total_heures)} label="Volume estimé" tint="bg-orange-pale text-orange" />
              </div>
              {data.sujet_t1_disponible && (
                <p className="text-petit text-texte-doux mb-2 pb-3 border-b border-bord">
                  Récupérez le sujet T1 dans « Documents &amp; sujets », faites-le passer, puis déposez le scan des réponses :
                  le système corrige et confirme ou écarte chaque hypothèse automatiquement. La saisie manuelle ci-dessous reste possible.
                </p>
              )}
              <div className="flex flex-col divide-y divide-bord">
                {data.plan_provisoire.etapes.map((etape) => {
                  const p = data.hypotheses.find((h) => h.id === etape.probleme_id)
                  if (!p) return null
                  return (
                    <LigneProbleme
                      key={p.id}
                      numero={etape.rang}
                      probleme={p}
                      cout={etape.cout}
                      prerequisBloquants={etape.prerequis_bloquants}
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
                  )
                })}
              </div>
            </Card>
          )}

          {data.en_remediation.length > 0 && (
            <Card>
              <div className="flex items-center justify-between mb-2 gap-3 flex-wrap">
                <CardTitre className="mb-0">En remédiation — vérification (T3)</CardTitre>
                <Link to={`/corrections/verification/${jeton}/T3`} className="inline-flex items-center gap-1.5 text-petit text-bleu hover:text-bleu-sombre font-medium">
                  <UploadCloud className="size-3.5" /> Déposer la copie corrigée
                </Link>
              </div>
              <p className="text-petit text-texte-doux mb-2">
                Une fois le volume horaire écoulé, générez le sujet T3 (bouton « Générer un sujet de test »),
                faites-le passer, puis déposez la copie corrigée pour un diagnostic automatique — ou reportez le résultat ci-dessous.
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
              <div className="flex items-center justify-between mb-2 gap-3 flex-wrap">
                <CardTitre className="mb-0">Résolus — contrôle de rétention</CardTitre>
                <div className="flex gap-4 text-petit">
                  {["T4", "T5"].map((t) => (
                    <Link key={t} to={`/corrections/verification/${jeton}/${t}`} className="inline-flex items-center gap-1 text-bleu hover:text-bleu-sombre font-medium">
                      <UploadCloud className="size-3.5" /> Déposer {t}
                    </Link>
                  ))}
                </div>
              </div>
              <p className="text-petit text-texte-doux mb-2">
                Contrôle à 45 jours (T4) puis 3 mois (T5). Générez le sujet avec « Générer un sujet de test » le moment venu.
              </p>
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

          {/* ── Puis les téléchargeables, regroupés ─────────────────────── */}
          <Card>
            <CardTitre className="mb-1">Documents &amp; sujets</CardTitre>
            <p className="text-petit text-texte-doux mb-1">
              Tous les fichiers du parcours. Les rapports et plans sont régénérés à l'ouverture et reflètent l'état actuel.
            </p>
            <div className="grid gap-x-10 sm:grid-cols-2">
              <LigneDocument
                icon={GraduationCap}
                titre="Rapport diagnostique"
                description="État des lieux complet : hypothèses, confirmées, écartées, résolues."
                hrefVoir={sessionsApi.rapportDiagnostiqueUrl(jeton)}
                hrefTelecharger={sessionsApi.rapportDiagnostiqueUrl(jeton, true)}
              />

              {data.plan.etapes.length > 0 && (
                <LigneDocument
                  icon={ListChecks}
                  titre="Plan de remédiation"
                  description="Ordre des séances, volume horaire et palier."
                  hrefVoir={sessionsApi.planUrl(jeton)}
                  hrefTelecharger={sessionsApi.planUrl(jeton, true)}
                />
              )}

              {data.hypotheses.length > 0 && (
                <LigneDocument
                  icon={ListChecks}
                  titre="Plan de remédiation provisoire"
                  description="Estimation avant le test de confirmation — non contractuelle."
                  hrefVoir={sessionsApi.planProvisoireUrl(jeton)}
                  hrefTelecharger={sessionsApi.planProvisoireUrl(jeton, true)}
                />
              )}

              {data.sujet_t1_disponible && data.sujet_t1_jeton_copie && (
                <LigneDocument
                  icon={ClipboardList}
                  titre="Sujet du test de confirmation (T1)"
                  description="Le dernier sujet T1 généré pour cet élève."
                  hrefVoir={elevesApi.documentUrl(data.sujet_t1_jeton_copie, "sujet_confirmation")}
                  hrefTelecharger={elevesApi.documentUrl(data.sujet_t1_jeton_copie, "sujet_confirmation", true)}
                  onSupprimer={() => supprimerDocument(data.sujet_t1_jeton_copie as string, "sujet_confirmation", "Sujet du test de confirmation (T1)")}
                  extra={
                    <Link to={`/corrections/confirmation/${jeton}`} className="text-petit font-medium text-bleu hover:text-bleu-sombre">
                      Déposer la copie T1
                    </Link>
                  }
                />
              )}

              {data.plan.etapes.map((etape) => (
                <LigneDocument
                  key={`fiche-${etape.probleme_id}`}
                  icon={Wrench}
                  titre={`Fiche de travail — ${etape.competence_id}`}
                  description={`${etape.competence_libelle} · ${etape.type_erreur_id}`}
                  hrefVoir={sessionsApi.ficheTravailUrl(jeton, etape.probleme_id)}
                  hrefTelecharger={sessionsApi.ficheTravailUrl(jeton, etape.probleme_id, true)}
                />
              ))}
            </div>

            <p className="mt-4 pt-4 border-t border-bord text-petit text-texte-doux inline-flex items-start gap-2">
              <FilePlus2 className="size-4 text-texte-faible shrink-0 mt-0.5" />
              Un sujet d'évaluation (T1, T3, T4…) n'est pas stocké : il se génère à la demande via
              «&nbsp;Générer un sujet de test&nbsp;» en haut de page, toujours à partir des lacunes actuelles.
            </p>
          </Card>
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
