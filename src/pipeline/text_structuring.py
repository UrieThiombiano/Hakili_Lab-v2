"""
Découpage structurel des textes LLM en (intro, items numérotés).

Problème résolu ici, une fois pour toutes
─────────────────────────────────────────
Les textes libres produits par les LLM (énoncés d'exercices, plans de
remédiation) mélangent fréquemment DEUX systèmes de numérotation dans une
même chaîne : "(1) … (2) … (3) …" inline ET "\n1. … \n2. …" — avec
redémarrages, sauts et entrelacements. Toute approche qui exige une séquence
1, 2, 3, … parfaite échoue sur ces hybrides, et toute approche qui préserve
le texte verbatim laisse les marqueurs sources entrer en collision avec la
numérotation régénérée par le template.

Principe de ce module — deux invariants :

1. **Les numéros écrits par le LLM ne sont pas fiables ; seule la POSITION
   des marqueurs fait foi.** Chaque marqueur ouvre un nouvel item, dans
   l'ordre de lecture, quel que soit le numéro qu'il prétend porter.

2. **Une seule numérotation doit survivre dans le PDF : celle du template.**
   Aucun marqueur source ("(1)", "2.", "3)") ne subsiste dans l'intro ni
   dans les items retournés — le template numérote via <ol>/loop.index.

Ce module est volontairement le SEUL endroit où vivent la détection et la
suppression des marqueurs : pdf_report_html et pdf_remediation_html
l'utilisent tous les deux.
"""
from __future__ import annotations

import re

# Marqueur de numérotation : "(n)", "n." ou "n)" —
#   - à une frontière de phrase/ligne ([.!?;:] ou \n ou début de texte),
#     jamais en pleine phrase ("mesure 40" ne doit pas matcher) ;
#   - 1 ou 2 chiffres maximum (élimine les années : "En 2020. ") ;
#   - suivi d'un blanc puis de tout sauf un nombre nu (élimine "3. 5" décimal
#     anglais) — "1. 5/8" ou "1. -7" restent des marqueurs (liste de valeurs,
#     sujet T1 du 2026-10-17) ;
#   - "(1 m = 1000 mm)" ne matche pas : il faut ")" ou "." collé au nombre.
_MARKER = re.compile(
    r"(?:\A|(?<=[.!?;:])|(?<=\n))"      # frontière
    r"[ \t]*"
    r"(?:\((\d{1,2})\)|(\d{1,2})[.)])"  # (n) | n. | n)
    r"\s+(?![0-9]+(?:[.,][0-9]+)?(?:\s|$))"
)

# Marqueur collé en pleine ligne, sans frontière de phrase : "1. -7 2. 9/4".
# Accepté seulement s'il porte le numéro qui suit immédiatement celui de
# l'item courant, et pas juste après un opérateur ("3x + 2. 5 est-il…") —
# garde contre une valeur numérique en pleine phrase.
_INLINE_SUIVANT = r"(?<=[^\s+\-×÷=*/<>(]\s)(?:\({n}\)|{n}[.)])\s+(?=\S)"

# Garde anti-référence : "Num. 4", "Geo. 7" (produits par _humanize_ids_in_text)
# sont des RÉFÉRENCES à une question — leur point est intrinsèque à
# l'abréviation et fournirait une fausse frontière au marqueur suivant
# ("… la question Num. 4. Ensuite …"). Les références en toutes lettres
# ("question 2", "exercice 3") ne peuvent pas matcher _MARKER : aucune
# frontière de phrase ne précède leur nombre — pas besoin de les garder ici,
# et les inclure rejetterait à tort les vraies listes après une phrase se
# terminant par ces mots ("Contexte du problème. 1. Fais …").
_REF_BEFORE = re.compile(r"(?:\bNum|\bG[ée]o)\.?\s*$", re.IGNORECASE)

# Marqueur résiduel collé en tête d'un item ("(1) 1. Justifie…") — supprimé
# itérativement pour garantir l'invariant n°2.
_LEADING_RESIDUAL = re.compile(r"^\(?\d{1,2}[.)][ \t]+(?![0-9])")


def _marker_number(m: re.Match) -> int:
    return int(m.group(1) or m.group(2))


def _eclater_inline(numero: int, seg: str) -> list[str]:
    """Sépare "-7 2. 9/4" (item n°1) en ["-7", "9/4"] : chaque marqueur
    inline doit porter le numéro suivant, sinon le segment reste entier."""
    morceaux: list[str] = []
    while True:
        m = re.search(_INLINE_SUIVANT.format(n=numero + 1), seg)
        if m is None or not seg[: m.start()].strip():
            morceaux.append(seg)
            return morceaux
        morceaux.append(seg[: m.start()].strip())
        numero, seg = numero + 1, seg[m.end():]


def _is_reference(text: str, m: re.Match) -> bool:
    avant = text[: m.start()]
    # "P(-3 ; 1) et Q(2 ; -4)" : le "1)" ferme une parenthèse de coordonnées,
    # ce n'est pas un marqueur (sujet T1 du 2026-10-17).
    if m.group(2) and m.group(0).rstrip().endswith(")") and avant.count("(") > avant.count(")"):
        return True
    return bool(_REF_BEFORE.search(avant))


def split_numbered_items(text: str) -> tuple[str, list[str]]:
    """
    Découpe un texte LLM en (intro, [item1, item2, …]) sur ses marqueurs de
    numérotation, dans l'ordre de lecture, en ignorant les numéros portés.

    Retourne (text, []) si aucune liste n'est détectée. L'intro peut être ""
    si le texte démarre directement sur un marqueur. Les items retournés ne
    contiennent plus aucun marqueur en tête — la numérotation visible doit
    être régénérée par l'appelant (template <ol> / loop.index).
    """
    matches = [m for m in _MARKER.finditer(text) if not _is_reference(text, m)]
    if not matches:
        return text, []

    # Un marqueur isolé n'est une liste que s'il annonce un début ("1"/"(1)").
    # Un "(3)" seul est plus probablement une scorie — on ne découpe pas.
    if len(matches) == 1 and _marker_number(matches[0]) != 1:
        return text, []

    intro = text[: matches[0].start()].strip()

    items: list[str] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        brut = text[m.end(): end].strip().rstrip(";").strip()
        for seg in _eclater_inline(_marker_number(m), brut):
            # Invariant n°2 : aucun marqueur résiduel en tête d'item
            while True:
                stripped = _LEADING_RESIDUAL.sub("", seg).strip()
                if stripped == seg:
                    break
                seg = stripped
            if seg:
                items.append(seg)

    if not items:
        return text, []
    return intro, items


# ── Découpage des questions en énoncé + tâches numérotées ────────────────────

# Séparation sur ". " suivi d'une majuscule (ponctuation de fin de phrase)
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-ZÁÉÈÊËÀÂÙÛÎÏÙÛÜ])')

# Verbes d'action français (infinitif) qui introduisent une tâche
_TASK_VERBS = re.compile(
    r'^(Puis\s+|Ensuite[\s,]+)?(Calculer|Simplifier|R[eé]soudre|Identifier|'
    r'Pr[eé]senter|V[eé]rifier|[EÉé]crire|Montrer|Factoriser|D[eé]composer|'
    r'D[eé]velopper|Trouver|Poser|Exprimer|Justifier|Repr[eé]senter|'
    r'D[eé]terminer|Comparer|Classer|Lister|Conclure|Indiquer|Expliquer|'
    r'D[eé]montrer|Appliquer|D[eé]duire|Utiliser|Dresser|Effectuer|'
    r'R[eé]duire|Donner|Mod[eé]liser|Construire|Tracer|[EÉ]valuer|'
    r'Prouver|[EÉ]tablir|Partager|D[eé]finir|Repr[eé]senter|Calculez|'
    r'Résolvez|Vérifiez|Montrez|Trouvez)\b',
    re.IGNORECASE,
)


def split_question(text: str) -> tuple[str, list[str]]:
    """
    Découpe le texte d'un exercice en (énoncé_contexte, [tâche1, tâche2, …]).

    Priorité 1 : marqueurs de numérotation ("(1)", "2.", "3)") traités comme
    des frontières positionnelles par split_numbered_items — les numéros émis
    par le LLM sont ignorés, la numérotation visible est régénérée par le
    template. L'énoncé peut être vide si le texte démarre sur un marqueur
    (le template n'affiche alors pas de bloc contexte).
    Priorité 2 : phrases débutant par un verbe d'action → tâches numérotées.
    Les phrases contextuelles (ex: "Un père a 3 fois…") → énoncé.
    Si aucun marqueur détecté, première phrase = énoncé, reste = tâches.
    """
    text = text.strip()

    intro, tasks = split_numbered_items(text)
    if tasks:
        return intro, tasks

    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if len(sentences) <= 1:
        return text, []

    enonce_parts: list[str] = []
    tasks = []

    for sent in sentences:
        if _TASK_VERBS.match(sent):
            tasks.append(sent)
        elif tasks:
            # Phrase non-tâche après des tâches → rattacher à la dernière tâche
            tasks[-1] = tasks[-1].rstrip('.') + '. ' + sent
        else:
            enonce_parts.append(sent)

    if not tasks:
        # Aucun verbe d'action → première phrase = énoncé, reste = tâches
        return enonce_parts[0], enonce_parts[1:]

    return ' '.join(enonce_parts), tasks


# ── Titre de série élève ──────────────────────────────────────────────────────
# Les topics sont les libellés `weaknesses` du diagnostic, au format
# "Compétence : symptôme observé sur la copie — Num. X". Le symptôme et la
# référence de question sont du vocabulaire de diagnostic destiné à
# l'enseignant — sur le sujet remis à l'élève, seul l'intitulé de compétence
# fait un titre de série cohérent.

# Références de questions en fin de libellé : "— Num. 4a", "— Geo. 2, Geo. 4", "— Q_NUM_07"
_TRAILING_QREFS = re.compile(
    r"\s*[—–-]\s*(?:(?:Num|G[ée]o)\.\s*\w+|Q_\w+)(?:\s*(?:,|et)\s*(?:(?:Num|G[ée]o)\.\s*\w+|Q_\w+))*\s*$",
    re.IGNORECASE,
)


def series_title(topic: str) -> str:
    """Extrait un titre de série présentable pour l'élève depuis un libellé
    de faiblesse diagnostic. Ne modifie jamais `topic` lui-même (clé de
    regroupement des séries et contrat de validation orchestrateur)."""
    t = _TRAILING_QREFS.sub("", topic.strip())
    # Sujet T1 : topic "compétence × type d'erreur" — le type d'erreur est une
    # hypothèse destinée à l'enseignant, pas un titre pour l'élève.
    t = t.split(" × ", 1)[0]
    # L'intitulé de compétence est la proposition avant le premier " : "
    head = t.split(" : ", 1)[0].strip()
    if len(head) >= 8:
        t = head
    t = t.strip(" .;:—–-")
    if not t:
        t = topic.strip()
    if len(t) > 90:
        t = t[:90].rsplit(" ", 1)[0] + "…"
    return t[:1].upper() + t[1:] if t else t
