"""
pipeline/ancrage_incertitudes.py
Rattache au texte transcrit les doutes que le modèle liste dans
`uncertainties`, en entourant le passage visé de `⟦…⟧`.

Le prompt de transcription demande au modèle de poser lui-même ces marqueurs
dans `content` ; en pratique (Gemini Flash-Lite surtout) il liste ses doutes
mais n'entoure presque jamais le passage — l'écran de relecture n'a alors rien
à surligner ni à proposer au double-clic. Ici, côté serveur et quel que soit
le fournisseur, on retrouve dans `content` les passages cités par chaque doute :

  - les bouts entre guillemets (`"…"`, `« … »`, `` `…` ``, `“…”`) ;
  - à défaut, les fragments d'allure mathématique écrits sans guillemets
    (`(3x-5)(3x+5)`, `x=4`) — c'est ce que fait le modèle quand il ignore
    la consigne de citation.

La recherche ignore les espaces et confond les tirets (`-`, `−`, `–`) : le
modèle cite `(3x-5)(3x+5)` là où `content` porte `(3x - 5)(3x + 5)`. Le
passage tel qu'il figure dans `content` est conservé à l'identique, seuls
les marqueurs sont ajoutés.

Pendant serveur de `ancrerIncertitudes` (frontend/src/lib/transcriptionHighlight.ts),
qui reste en place pour les transcriptions enregistrées avant ce module.
"""

from __future__ import annotations

import re

from src.models.domain import PageTranscription, TranscriptionResult

# Marqueurs déjà posés par le modèle (mêmes motifs que le frontend).
_MARQUEUR = re.compile(r"⟦[^⟦⟧]*⟧|\[ILLISIBLE\]")

_CITATIONS = [
    re.compile(r'"([^"]{3,200})"'),
    re.compile(r"«\s*([^«»]{3,200}?)\s*»"),
    re.compile(r"`([^`]{3,200})`"),
    re.compile(r"“([^”]{3,200})”"),
]

# Fragment sans espace qui ressemble à une écriture mathématique : au moins
# un chiffre ou une lettre ET au moins un opérateur / délimiteur.
_FRAGMENT = re.compile(r"[^\s]{4,}")
_OPERATEUR = re.compile(r"[()=+\-−–/²³√×÷<>≤≥\[\];]")
_ALNUM = re.compile(r"[0-9A-Za-z]")

_TIRETS = "-−–"


def _motif_souple(passage: str) -> re.Pattern[str]:
    """Motif qui retrouve `passage` en ignorant les espaces et les variantes de tiret."""
    morceaux: list[str] = []
    for car in passage:
        if car.isspace():
            continue
        morceaux.append(f"[{re.escape(_TIRETS)}]" if car in _TIRETS else re.escape(car))
    return re.compile(r"\s*".join(morceaux))


def _citations(phrase: str) -> list[str]:
    out: list[str] = []
    for motif in _CITATIONS:
        out.extend(m.group(1).strip() for m in motif.finditer(phrase))
    return [c for c in out if c]


def _fragments_maths(phrase: str) -> list[str]:
    out: list[str] = []
    for m in _FRAGMENT.finditer(phrase):
        frag = m.group(0).strip(".,:;!?'\"")
        # Parenthèse ouvrante orpheline laissée par la ponctuation de la phrase.
        if frag.count("(") > frag.count(")") and frag.startswith("("):
            frag = frag[1:]
        if frag.count(")") > frag.count("(") and frag.endswith(")"):
            frag = frag[:-1]
        if len(frag) >= 4 and _OPERATEUR.search(frag) and _ALNUM.search(frag):
            out.append(frag)
    return out


def _candidats(phrase: str) -> list[str]:
    cites = _citations(phrase)
    candidats = cites or _fragments_maths(phrase)
    retenus: list[str] = []
    for c in candidats:
        if "⟦" in c or "⟧" in c or "[ILLISIBLE]" in c:
            continue
        compact = re.sub(r"\s", "", c)
        # Un token court (« 25 », « BC ») risque de viser la mauvaise
        # occurrence — on le laisse au bandeau plutôt que de surligner à tort.
        if len(compact) < 4 or (not re.search(r"\s", c) and len(compact) < 5):
            continue
        retenus.append(c)
    return retenus


def ancrer_contenu(content: str, uncertainties: list[str]) -> str:
    """Renvoie `content` avec `⟦…⟧` autour de chaque passage cité par un doute."""
    if not content or not uncertainties:
        return content
    resultat = content
    for phrase in uncertainties:
        for cand in _candidats(phrase):
            occupes = [(m.start(), m.end()) for m in _MARQUEUR.finditer(resultat)]
            for m in _motif_souple(cand).finditer(resultat):
                debut, fin = m.start(), m.end()
                if any(debut < f and fin > d for d, f in occupes):
                    continue
                resultat = f"{resultat[:debut]}⟦{resultat[debut:fin]}⟧{resultat[fin:]}"
                break
    return resultat


def ancrer_incertitudes(transcription: TranscriptionResult) -> TranscriptionResult:
    """Applique `ancrer_contenu` à chaque page de la transcription."""
    pages: list[PageTranscription] = [
        page.model_copy(update={"content": ancrer_contenu(page.content, page.uncertainties)})
        for page in transcription.pages
    ]
    return transcription.model_copy(update={"pages": pages})
