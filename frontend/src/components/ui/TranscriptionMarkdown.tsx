import { useState, type ComponentPropsWithoutRef } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkBreaks from "remark-breaks"
import { Check, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { remarkOcrMarks, replaceNthMarker, type OcrMarkKind } from "@/lib/transcriptionHighlight"

/**
 * Rendu Markdown de la transcription d'une page pour la relecture enseignant.
 * Les zones de confiance basse posées par le modèle (`⟦…⟧`, `[ILLISIBLE]`,
 * cf. `lib/transcriptionHighlight.ts`) sont surlignées et affichées entre
 * crochets. Double-clic sur une zone → petit champ en place pour la corriger ;
 * valider remplace le marqueur par le texte saisi (la zone est réglée).
 *
 * Le modèle peut aussi se tromper sans le signaler : double-clic ailleurs sur
 * une ligne → la ligne entière passe en édition. Les chevrons `⟦⟧` sont retirés
 * (la ligne relue est réputée validée) ; un `[ILLISIBLE]` laissé tel quel reste
 * signalé. Un tableau Markdown (lignes `|…` consécutives) s'édite d'un bloc.
 *
 * `value` est le Markdown brut de la page (avec marqueurs) ; `onChange` reçoit
 * la nouvelle version après chaque correction de zone ou de ligne.
 */
export function TranscriptionMarkdown({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string) => void
}) {
  const blocs = decouperBlocs(value)
  const remplacer = (i: number, texte: string) => onChange(blocs.map((b, j) => (j === i ? texte : b)).join("\n"))

  return (
    <div
      className={cn(
        "text-petit leading-relaxed text-texte break-words",
        "[&_p]:my-0 [&_ol]:my-0 [&_ol]:pl-5 [&_ul]:my-0 [&_ul]:pl-5 [&_ul]:list-disc [&_ol]:list-decimal",
        "[&_strong]:font-semibold [&_h1]:text-menu [&_h2]:text-menu [&_h3]:text-menu [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold",
        "[&_code]:rounded [&_code]:bg-surface-creuse [&_code]:px-1 [&_code]:text-[0.95em]",
      )}
    >
      {blocs.map((bloc, i) => (
        <LigneTranscription key={i} texte={bloc} onChange={(t) => remplacer(i, t)} />
      ))}
    </div>
  )
}

/** Une ligne par bloc, sauf les tableaux Markdown (lignes `|…` consécutives), gardés d'un seul tenant. */
function decouperBlocs(value: string): string[] {
  const blocs: string[] = []
  for (const ligne of value.split("\n")) {
    const precedent = blocs[blocs.length - 1]
    if (ligne.trimStart().startsWith("|") && precedent?.trimStart().startsWith("|")) {
      blocs[blocs.length - 1] = `${precedent}\n${ligne}`
    } else {
      blocs.push(ligne)
    }
  }
  return blocs
}

function LigneTranscription({ texte, onChange }: { texte: string; onChange: (next: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")

  const components: Components = {
    // Les liens n'ont aucun sens dans une transcription — `[a](b)` reste du texte.
    a: ({ children }) => <>{children}</>,
    mark: ({ node, children }) => {
      const props = (node?.properties ?? {}) as unknown as Record<string, string | undefined>
      const rawIndex = Number(props["data-ocr-index"] ?? NaN)
      if (!Number.isInteger(rawIndex)) return <mark>{children}</mark>
      const kind: OcrMarkKind = props["data-ocr-kind"] === "illisible" ? "illisible" : "uncertain"
      return (
        <OcrMark
          index={rawIndex}
          kind={kind}
          texte={props["data-ocr-text"] ?? ""}
          value={texte}
          onChange={onChange}
        />
      )
    },
  }

  if (!texte.trim()) return <div className="h-3" />

  if (editing) {
    const commit = () => {
      if (draft !== texte) onChange(draft)
      setEditing(false)
    }
    return (
      <div className="flex items-start gap-1 py-0.5">
        <textarea
          autoFocus
          value={draft}
          rows={draft.split("\n").length}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              commit()
            } else if (e.key === "Escape") {
              setEditing(false)
            }
          }}
          className="flex-1 resize-none rounded border border-bleu bg-surface px-1 py-0.5 font-mono text-petit focus:outline-none"
          aria-label="Corriger la ligne transcrite"
        />
        <button type="button" onClick={commit} title="Valider la ligne" className="mt-1 text-vert hover:opacity-80">
          <Check className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          title="Annuler"
          className="mt-1 text-texte-faible hover:text-rouge"
        >
          <X className="size-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div
      onDoubleClick={() => {
        setDraft(texte.replace(/⟦([^⟦⟧]*)⟧/g, "$1"))
        setEditing(true)
      }}
      title="Double-cliquez pour modifier la ligne"
      className="-mx-1 cursor-text rounded px-1 py-0.5 hover:bg-surface-creuse"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks, remarkOcrMarks]} components={components}>
        {texte}
      </ReactMarkdown>
    </div>
  )
}

function OcrMark({
  index,
  kind,
  texte,
  value,
  onChange,
}: {
  index: number
  kind: OcrMarkKind
  texte: string
  value: string
  onChange: (next: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(texte)

  if (editing) {
    const commit = () => {
      onChange(replaceNthMarker(value, index, draft.trim()))
      setEditing(false)
    }
    return (
      <span className="inline-flex items-center gap-1 align-baseline">
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              commit()
            } else if (e.key === "Escape") {
              setEditing(false)
            }
          }}
          size={Math.max(draft.length + 1, 4)}
          className="rounded border border-bleu bg-surface px-1 py-0.5 font-mono text-petit focus:outline-none"
          aria-label={kind === "illisible" ? "Saisir le texte de la zone illisible" : "Corriger la lecture incertaine"}
        />
        <button type="button" onClick={commit} title="Valider la correction" className="text-vert hover:opacity-80">
          <Check className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          title="Annuler"
          className="text-texte-faible hover:text-rouge"
        >
          <X className="size-3.5" />
        </button>
      </span>
    )
  }

  return (
    <mark
      onDoubleClick={(e) => {
        // La zone a son propre champ — ne pas ouvrir aussi l'édition de la ligne.
        e.stopPropagation()
        setDraft(texte)
        setEditing(true)
      }}
      title={
        kind === "illisible"
          ? "Zone illisible — double-cliquez pour saisir le texte"
          : "Lecture incertaine — double-cliquez pour corriger"
      }
      className={cn(
        "cursor-text rounded px-1 font-medium ring-1",
        kind === "illisible" ? "bg-rouge-pale text-rouge ring-rouge/30" : "bg-orange-pale text-orange ring-orange/30",
      )}
    >
      {kind === "illisible" ? "[illisible]" : `[${texte}]`}
    </mark>
  )
}

/** Légende des couleurs — à poser près du rendu. */
export function TranscriptionLegende(props: ComponentPropsWithoutRef<"p">) {
  return (
    <p {...props} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-micro text-texte-doux", props.className)}>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block size-2.5 rounded-sm bg-orange-pale ring-1 ring-orange/30" />
        lecture incertaine
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block size-2.5 rounded-sm bg-rouge-pale ring-1 ring-rouge/30" />
        illisible
      </span>
      <span>· double-cliquez sur une zone ou une ligne pour la corriger</span>
    </p>
  )
}
