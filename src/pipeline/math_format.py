"""
Formatage mathématique des textes IA — helpers PURS (regex uniquement).

Utilisés par le rendu PDF (pdf_report_html) et par l'affichage des écrans.
Module volontairement sans dépendance (stdlib `re` seulement) : importable
n'importe où sans coût de démarrage.
"""
from __future__ import annotations

import re

# ── IDs de questions dans du texte libre ──────────────────────────────────────

_ID_IN_TEXT = re.compile(r"Q_(?:NUM|GEO)_0*(\d+[a-z]?)", re.IGNORECASE)


def humanize_ids_in_text(s: str) -> str:
    """Remplace Q_NUM_04, Q_GEO_07 par 'Num. 4', 'Geo. 7' dans du texte libre."""
    def _repl(m: re.Match) -> str:
        full = m.group(0).upper()
        num = m.group(1)
        return f"Num. {num}" if "NUM" in full else f"Geo. {num}"
    return _ID_IN_TEXT.sub(_repl, s)


# ── Conversion notation mathématique ASCII → HTML ─────────────────────────────
# Deux passes :
#   A. ascii_math_upgrade : les notations INFORMATIQUES produites par les LLM
#      malgré les consignes ("<=", ">=", "=>", "->", "**", "!=", "* " espacé,
#      commandes LaTeX résiduelles) sont promues en symboles mathématiques
#      WGL4 (≤ ≥ → ≠ × ≈), AVANT échappement HTML — elles contiennent < et >.
#   B. conversions structurelles (après échappement HTML) :
#      sqrt(expr) → √expr | (a/b) et a/b → fraction <sup>a</sup>⁄<sub>b</sub>
#      x^2, x^-2, x^(n+1) → <sup> | u_1, x_A → <sub> | pi → π

_SUP  = re.compile(r'\^(\{[^{}]*\}|\([^()]*\)|[+-]?[A-Za-z0-9]+|[+-])')
_SQRT = re.compile(r'sqrt\(((?:[^()]*|\([^()]*\))*)\)', re.IGNORECASE)
_FRAC = re.compile(r'\((\d+)/(\d+)\)')
# Fraction nue "7/12" : 1-3 chiffres / 1-4 chiffres, jamais adjacente à un
# autre chiffre, un slash, un point ou une virgule (protège les dates
# "06/07/2026", les couples d'années "2025/2026" et les décimaux).
_FRAC_BARE = re.compile(r'(?<![\d/.,_])(\d{1,3})/(\d{1,4})(?![\d/])')
# Indice : lettre isolée + underscore + 1-2 alphanumériques ("u_1", "x_A").
# La lettre doit être un mot d'une lettre (\b) — "copy_id" ne matche pas.
_SUB = re.compile(r'\b([A-Za-z])_([A-Za-z0-9]{1,2})\b')

# Exposants écrits sans caret par l'IA malgré la consigne "a^n" -- l'IA écrit parfois
# "cm2"/"R2" au lieu de "cm^2"/"R^2". Ces deux familles sont sans ambiguïté dans ce
# domaine (unités d'aire/volume, rayon/diamètre au carré) contrairement à un exposant
# générique sur une lettre isolée (ex: u2 pourrait être un indice de suite u_n).
_UNIT_POW = re.compile(r'\b([cdk]?m)(2|3)\b')
# Pas de « R » ni de « D » seuls : D1 à D4 sont des codes de question
# (organisation de données) dans tous les tests du référentiel — « En D2, … »
# devenait « En D², … » dans les rapports (recette du 2026-10-16).
_GEOM_POW = re.compile(r'\b(Rayon|rayon|Diam[eè]tre|diam[eè]tre)(2|3)\b')
_SUP_DIGIT = {"2": "²", "3": "³"}

# Commandes LaTeX résiduelles (défense en profondeur — les prompts imposent
# l'ASCII mais un provider peut fuiter du LaTeX, et le contenu de
# `remediation/` — module 7 — est du LaTeX plus riche, écrit à la main)
_LATEX_FRAC = re.compile(r'\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}')
_LATEX_SQRT = re.compile(r'\\sqrt\{([^{}]+)\}')
_LATEX_WIDEHAT = re.compile(r'\\widehat\{([^{}]+)\}')
_LATEX_SIMPLE = [
    (r'\times', '×'), (r'\cdot', '×'), (r'\div', '÷'), (r'\pi', 'π'),
    (r'\leq', '≤'), (r'\geq', '≥'), (r'\neq', '≠'),
    (r'\le', '≤'), (r'\ge', '≥'), (r'\ne', '≠'), (r'\infty', '∞'),
    (r'\circ', '°'),
    # Délimiteurs de taille — purement visuels en LaTeX, sans équivalent HTML
    # utile ici : la parenthèse/le crochet qui suit porte déjà le sens.
    (r'\left', ''), (r'\right', ''),
]
# `re.escape(cmd)` + lookahead "pas une lettre juste après" : sans ça,
# `str.replace('\le', '≤')` mangeait `\left` en `≤ft` (`\le` est un préfixe
# de `\left`) — découvert sur du contenu `remediation/` réel (D-CEO-43).
_LATEX_CMD_RE = [(re.compile(re.escape(cmd) + r'(?![a-zA-Z])'), sym) for cmd, sym in _LATEX_SIMPLE]


def ascii_math_upgrade(s: str) -> str:
    """Notations informatiques → symboles mathématiques (avant échappement)."""
    # LaTeX résiduel → formes ASCII/Unicode gérées en aval
    s = _LATEX_FRAC.sub(r'(\1/\2)', s)
    s = _LATEX_SQRT.sub(r'sqrt(\1)', s)
    s = _LATEX_WIDEHAT.sub(r'angle \1', s)
    for pattern, sym in _LATEX_CMD_RE:
        s = pattern.sub(sym, s)
    # Comparaisons et flèches — l'ordre compte : <=> avant <= et =>
    s = re.sub(r'\s*<=>\s*', ' équivaut à ', s)
    s = re.sub(r'\s*<=\s*', ' ≤ ', s)
    s = re.sub(r'\s*>=\s*', ' ≥ ', s)
    s = re.sub(r'\s*(?:=>|->)\s*', ' → ', s)
    s = re.sub(r'\s*(?:=/=|!=)\s*', ' ≠ ', s)
    # Gras markdown résiduel "**texte**" → texte (avant la règle puissance)
    s = re.sub(r'\*\*([^*\n]{1,80})\*\*', r'\1', s)
    # Puissance Python "2**3" → "2^3" (rendue en <sup> ensuite)
    s = s.replace('**', '^')
    # "~" d'approximation entre deux valeurs → ≈
    s = re.sub(r'(?<=[\s\d])~(?=\s?\d)', '≈', s)
    # Multiplication : "*" adjacent ou espacé entre termes → ×
    s = re.sub(r'(?<=[A-Za-z0-9)])\*(?=[A-Za-z0-9(])', '×', s)
    s = re.sub(r'(?<=[A-Za-z0-9)])\s+\*\s+(?=[A-Za-z0-9(])', ' × ', s)
    return s


def math_to_html(s: str) -> str:
    """Convertit les notations mathématiques en HTML lisible.

    Échappe systématiquement & < > AVANT d'insérer les balises <sup>/<sub> :
    le résultat est marqué Markup par les appelants, tout caractère HTML
    brut résiduel du texte LLM casserait le rendu xhtml2pdf.
    """
    s = ascii_math_upgrade(s)
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # 0. Exposants sans caret sur unités/rayon/diamètre → notation en exposant
    s = _UNIT_POW.sub(lambda m: m.group(1) + _SUP_DIGIT[m.group(2)], s)
    s = _GEOM_POW.sub(lambda m: m.group(1) + _SUP_DIGIT[m.group(2)], s)

    def _sup_repl(m: re.Match) -> str:
        inner = m.group(1)
        if (inner.startswith('{') and inner.endswith('}')) or \
           (inner.startswith('(') and inner.endswith(')')):
            inner = inner[1:-1]
        inner = inner.replace('*', '×')
        return f'<sup>{inner}</sup>'

    # 1. sqrt(expr) → √expr  ou  √(expr) si l'expression est composée
    def _repl_sqrt(m: re.Match) -> str:
        inner = m.group(1).strip()
        inner = re.sub(r'(?<=[A-Za-z0-9])\*(?=[A-Za-z0-9])', '×', inner)
        inner = _SUP.sub(_sup_repl, inner)
        if re.match(r'^[A-Za-z0-9]+$', inner):
            return f'√{inner}'
        return f'√({inner})'

    s = _SQRT.sub(_repl_sqrt, s)

    # 2. Exposants x^2, x^-2, x^{n+1}, x^(n+1) → <sup>…</sup>
    #    (avant les fractions : dans "2^3/2^5", le "3/2" ne doit pas devenir
    #    une fraction — une fois les <sup> posés, il n'y a plus d'ambiguïté)
    s = _SUP.sub(_sup_repl, s)

    # 3. Fractions : "(a/b)" puis fractions nues "a/b"
    def frac_html(m):
        return f'<sup>{m.group(1)}</sup>&frasl;<sub>{m.group(2)}</sub>'

    s = _FRAC.sub(frac_html, s)
    s = _FRAC_BARE.sub(frac_html, s)

    # 4. Indices u_1, x_A → <sub>
    s = _SUB.sub(r'\1<sub>\2</sub>', s)

    # 5. pi isolé → π
    s = re.sub(r'\bpi\b', 'π', s)

    return s
