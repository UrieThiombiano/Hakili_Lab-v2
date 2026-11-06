/**
 * lib/transcriptionHighlight.ts
 * Rend visibles, dans la relecture de transcription, les deux marqueurs de
 * confiance posés par le modèle (voir `prompts/transcription_prompt.md`) :
 *   - `⟦…⟧`      : lecture plausible mais pas garantie (écriture ambiguë)
 *   - `[ILLISIBLE]` : rien de fiable à proposer
 *
 * Même principe que le `markdownHighlight.ts` d'un collègue (une extension de
 * syntaxe au niveau du parseur, pas une recherche/remplacement sur le DOM
 * rendu) : ici un plugin remark découpe les nœuds texte et insère un `<mark>`
 * par marqueur, numéroté dans l'ordre du document. Le numéro (`data-ocr-index`)
 * permet à l'UI de retrouver le marqueur exact dans le texte brut quand
 * l'enseignant double-clique pour le corriger — cf. `replaceNthMarker`.
 *
 * Jamais appliqué au texte envoyé au correcteur : `pages[...]` reste le
 * Markdown brut, marqueurs compris.
 */

/** `⟦contenu⟧` (lecture incertaine) ou `[ILLISIBLE]` (indéchiffrable). */
export const OCR_MARKER_SOURCE = "⟦([^⟦⟧]*)⟧|\\[ILLISIBLE\\]"

export type OcrMarkKind = "uncertain" | "illisible"

/** Nœud mdast minimal — on n'a besoin que de ces champs pour marcher l'arbre. */
interface MdNode {
  type: string
  value?: string
  children?: MdNode[]
  data?: {
    hName?: string
    hProperties?: Record<string, unknown>
  }
}

/**
 * Plugin remark : remplace chaque `⟦…⟧` / `[ILLISIBLE]` d'un nœud texte par un
 * nœud rendu en `<mark>`, porteur de `data-ocr-index` (rang dans le document),
 * `data-ocr-kind` et `data-ocr-text` (lecture proposée, vide si illisible).
 */
export function remarkOcrMarks() {
  return (tree: MdNode) => {
    walk(tree, { n: 0 })
  }
}

function walk(node: MdNode, counter: { n: number }): void {
  const children = node.children
  if (!children) return
  for (let i = 0; i < children.length; i++) {
    const child = children[i]
    if (child.type === "text" && typeof child.value === "string") {
      const parts = splitOnMarkers(child.value, counter)
      if (parts) {
        children.splice(i, 1, ...parts)
        i += parts.length - 1
      }
    } else {
      walk(child, counter)
    }
  }
}

/** `null` si aucun marqueur ; sinon la liste des nœuds texte + `<mark>`. */
function splitOnMarkers(value: string, counter: { n: number }): MdNode[] | null {
  const re = new RegExp(OCR_MARKER_SOURCE, "g")
  const out: MdNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(value)) !== null) {
    if (match.index > last) out.push({ type: "text", value: value.slice(last, match.index) })
    const illisible = match[0] === "[ILLISIBLE]"
    const inner = illisible ? "" : match[1] ?? ""
    out.push({
      type: "ocrMark",
      data: {
        hName: "mark",
        hProperties: {
          className: illisible ? ["ocr-illisible"] : ["ocr-uncertain"],
          "data-ocr-index": String(counter.n++),
          "data-ocr-kind": illisible ? "illisible" : "uncertain",
          "data-ocr-text": inner,
        },
      },
      children: [{ type: "text", value: inner }],
    })
    last = match.index + match[0].length
  }
  if (out.length === 0) return null
  if (last < value.length) out.push({ type: "text", value: value.slice(last) })
  return out
}

/** Vrai si le texte contient au moins un marqueur `⟦…⟧` ou `[ILLISIBLE]`. */
export function hasOcrMarkers(content: string): boolean {
  return new RegExp(OCR_MARKER_SOURCE).test(content)
}

/**
 * Rattache au texte les entrées de `uncertainties` qui citent un passage précis.
 *
 * Le modèle liste ses doutes en clair dans `uncertainties` (bandeau « Zones
 * incertaines ») mais n'entoure pas toujours de `⟦…⟧` le passage visé dans
 * `content` — l'enseignant voit alors l'alerte sans savoir où regarder dans la
 * transcription. Ici, pour chaque incertitude, on extrait les bouts cités entre
 * guillemets et, si on les retrouve mot pour mot dans `content` hors d'un
 * marqueur existant, on les entoure de `⟦…⟧` : la zone devient un marqueur
 * normal — surlignée, et corrigeable au double-clic comme les autres.
 *
 * Sans effet sur les incertitudes qui ne citent aucun passage (figures,
 * remarques globales sur la page) : elles restent au bandeau seul.
 */
export function ancrerIncertitudes(content: string, uncertainties: string[]): string {
  if (!content || !uncertainties || uncertainties.length === 0) return content
  let result = content
  for (const phrase of uncertainties) {
    for (const cand of extraireCitations(phrase)) {
      if (cand.length < 4) continue
      // Un token court et isolé (« 25 », « BC ») risque de viser la mauvaise
      // occurrence — on le laisse au bandeau plutôt que de surligner à tort.
      if (!/\s/.test(cand) && cand.length < 8) continue
      if (/[⟦⟧]/.test(cand) || cand.includes("[ILLISIBLE]")) continue
      const idx = result.indexOf(cand)
      if (idx < 0) continue
      if (result[idx - 1] === "⟦" && result[idx + cand.length] === "⟧") continue
      const fin = idx + cand.length
      if (rangsMarqueurs(result).some(([d, f]) => idx < f && fin > d)) continue
      result = `${result.slice(0, idx)}⟦${cand}⟧${result.slice(fin)}`
    }
  }
  return result
}

/** Bouts de texte cités (guillemets droits, français, courbes, backticks). */
function extraireCitations(phrase: string): string[] {
  const out: string[] = []
  const patterns = [
    /"([^"]{3,200})"/g,
    /«\s*([^«»]{3,200}?)\s*»/g,
    /`([^`]{3,200})`/g,
    /“([^”]{3,200})”/g,
    /‘([^’]{3,200})’/g,
    /'([^']{3,200})'/g,
  ]
  for (const re of patterns) {
    let match: RegExpExecArray | null
    while ((match = re.exec(phrase)) !== null) {
      const c = match[1].trim()
      if (c) out.push(c)
    }
  }
  return out
}

/** Rang `[début, fin)` de chaque marqueur `⟦…⟧` / `[ILLISIBLE]` du texte. */
function rangsMarqueurs(texte: string): Array<[number, number]> {
  const re = new RegExp(OCR_MARKER_SOURCE, "g")
  const rangs: Array<[number, number]> = []
  let match: RegExpExecArray | null
  while ((match = re.exec(texte)) !== null) rangs.push([match.index, match.index + match[0].length])
  return rangs
}

/**
 * Remplace le `index`-ième marqueur (`⟦…⟧` ou `[ILLISIBLE]`, ordre de lecture)
 * par `replacement`, sans marqueur : la zone est validée par l'enseignant, elle
 * redevient du texte normal. Renvoie `content` inchangé si l'index n'existe pas.
 */
export function replaceNthMarker(content: string, index: number, replacement: string): string {
  const re = new RegExp(OCR_MARKER_SOURCE, "g")
  let match: RegExpExecArray | null
  let i = 0
  while ((match = re.exec(content)) !== null) {
    if (i === index) {
      return content.slice(0, match.index) + replacement + content.slice(match.index + match[0].length)
    }
    i++
  }
  return content
}
