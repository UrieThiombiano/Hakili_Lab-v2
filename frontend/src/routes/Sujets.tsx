import { useQuery } from "@tanstack/react-query"
import { AppShell } from "@/components/layout/AppShell"
import { Card } from "@/components/ui/Card"
import { Spinner } from "@/components/ui/Etat"
import { correctionsApi } from "@/lib/api"
import { FileText, FileCheck2 } from "lucide-react"

export default function Sujets() {
  const { data, isLoading } = useQuery({ queryKey: ["sujets"], queryFn: correctionsApi.sujets })

  return (
    <AppShell titre="Sujets tests">
      {isLoading && <Spinner label="Chargement…" />}
      <div className="grid gap-2 sm:grid-cols-2">
        {data?.map((s) => (
          <Card key={s.id} className="flex flex-col gap-2">
            <p className="text-menu font-medium">{s.label}</p>
            <p className="text-petit text-texte-doux">{s.questions} questions · {s.niveaux}</p>
            <div className="flex gap-4 mt-1">
              {s.imprimable && (
                <a href={correctionsApi.sujetPdfUrl(s.id)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-petit text-bleu hover:text-bleu-sombre">
                  <FileText className="size-3.5" /> Sujet
                </a>
              )}
              {s.corrige_disponible && (
                <a href={correctionsApi.corrigePdfUrl(s.id)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-petit text-orange hover:brightness-90">
                  <FileCheck2 className="size-3.5" /> Corrigé
                </a>
              )}
            </div>
          </Card>
        ))}
      </div>
    </AppShell>
  )
}
