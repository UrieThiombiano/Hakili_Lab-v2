"""
Generation PDF via xhtml2pdf (HTML+CSS -> PDF, pur Python).
Dependance : xhtml2pdf (base sur reportlab, deja installe).
Unicode: Arial standard ne couvre pas tous les symboles mathematiques.
Les textes AI sont normalises avant rendu (_clean).
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from markupsafe import Markup

# Helpers de formatage mathématique partagés avec l'UI (src/pipeline/math_format.py).
# Alias soulignés conservés : usages internes et tests existants inchangés.
from src.pipeline.math_format import (
    humanize_ids_in_text as _humanize_ids_in_text,
    math_to_html as _math_to_html,
)
from src.pipeline.text_structuring import split_numbered_items as _split_steps

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_MONTHS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _today_fr() -> str:
    d = date.today()
    return f"{d.day} {_MONTHS_FR[d.month]} {d.year}"

# ── Police Unicode ─────────────────────────────────────────────────────────────
# Priorite : Arial Unicode MS (Office), Segoe UI Symbol (Win10+), Arial standard

_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arialuni.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    (r"C:\Windows\Fonts\seguisym.ttf", r"C:\Windows\Fonts\seguisym.ttf"),
    (r"C:\Windows\Fonts\arial.ttf",    r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
     "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
]

_font_ready = False
_font_css_name = "Helvetica"


def _register_unicode_font() -> str:
    """Enregistre une police TTF Unicode via ReportLab. Retourne son nom CSS."""
    global _font_ready, _font_css_name
    if _font_ready:
        return _font_css_name
    _font_ready = True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        from reportlab.pdfbase.ttfonts import TTFont

        for regular, bold in _FONT_CANDIDATES:
            if Path(regular).exists():
                pdfmetrics.registerFont(TTFont("HakFont", regular))
                bold_path = bold if Path(bold).exists() else regular
                pdfmetrics.registerFont(TTFont("HakFont-Bold", bold_path))
                registerFontFamily("HakFont", normal="HakFont", bold="HakFont-Bold")
                _font_css_name = "HakFont"
                logger.info("Police Unicode enregistree depuis %s", regular)
                break
    except Exception as exc:
        logger.warning("Police Unicode introuvable (%s) -- fallback Helvetica", exc)
    return _font_css_name


# ── Normalisation texte ────────────────────────────────────────────────────────

_ID_NUM = re.compile(r"^Q_NUM_0*(\d+[a-z]?)$", re.IGNORECASE)
_ID_GEO = re.compile(r"^Q_GEO_0*(\d+[a-z]?)$", re.IGNORECASE)

# Symboles Unicode hors répertoire WGL4 -- remplacement PDF-safe.
# WGL4 est le socle commun à TOUTES les polices candidates (Arial, Segoe,
# Arial Unicode, Liberation, DejaVu) : ≤ ≥ ≠ ≈ ± × ÷ − √ ∞ ° π → ← ≡ et le
# grec de base y figurent et sont donc CONSERVÉS tels quels (notation maths).
# Seuls les symboles absents de WGL4 sont remplacés — et en français lisible
# par un élève, jamais en jargon informatique.
_MATH_SAFE: dict[str, str] = {
    # Ensembles de nombres (Letterlike Symbols U+2100-U+214F, hors WGL4)
    "ℕ": "N",  # N (naturels)
    "ℤ": "Z",  # Z (entiers)
    "ℚ": "Q",  # Q (rationnels)
    "ℝ": "R",  # R (reels)
    "ℂ": "C",  # C (complexes)
    "ℙ": "P",  # P (premiers)
    # Vecteurs — flèches combinantes (U+20D0–U+20FF) non rendues par les polices PDF
    "⃗": "",   # COMBINING RIGHT ARROW ABOVE (vecteur AB⃗ → AB)
    "⃖": "",   # COMBINING LEFT ARROW ABOVE
    "⃡": "",   # COMBINING LEFT RIGHT ARROW ABOVE
    # Doubles flèches (hors WGL4) — la simple flèche → est dans WGL4
    "⇒": " → ",
    "⇔": " équivaut à ",
    # Operateurs ensemblistes (hors WGL4) — en français élève, pas en ASCII
    "∈": " appartient à ",
    "∉": " n'appartient pas à ",
    "⊂": " inclus dans ",
    "⊆": " inclus dans ",
    "∪": " U ",      # union — notation orale "U" standard au collège
    "∩": " inter ",  # intersection — notation orale standard
    # Multiplication par point (U+22C5 hors WGL4) → croix du collège
    "⋅": " × ",
    # Angles et geometrie (hors WGL4) — vocabulaire français
    "∠": "angle ",
    "⊥": " perpendiculaire à ",
    "∥": " // ",  # notation // écrite en classe
}


# Exposants (U+2070-U+209F) et indices (U+2080-U+2089) Unicode : traités par
# SÉQUENCE pour que "2⁻²" → "2^-2" et "2²¹" → "2^21" (un seul <sup> au rendu),
# et non caractère par caractère ("2^-^2").
_SUPER_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁺⁻", "0123456789n+-")
_SUBSC_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPER_RUN = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁺⁻]+")
_SUBSC_RUN = re.compile("[₀₁₂₃₄₅₆₇₈₉]+")


def _safe_text(s: str) -> str:
    """Remplace les symboles Unicode que la police PDF ne peut pas rendre."""
    s = _SUPER_RUN.sub(lambda m: "^" + m.group(0).translate(_SUPER_MAP), s)
    s = _SUBSC_RUN.sub(lambda m: "_" + m.group(0).translate(_SUBSC_MAP), s)
    for char, repl in _MATH_SAFE.items():
        s = s.replace(char, repl)
    # Les remplacements français (" appartient à ") peuvent doubler les espaces
    return re.sub(r" {2,}", " ", s)


def _clean(s: str) -> str:
    """Normalise un texte AI : IDs lisibles + symboles PDF-safe."""
    return _safe_text(_humanize_ids_in_text(s))


def _cm(s: str) -> str:
    """_clean + _math_to_html, marqué Markup (HTML sûr pour Jinja2 autoescape)."""
    return Markup(_math_to_html(_clean(s)))


# ── Mise en forme des textes IA denses (diagnostic, remédiation) ──────────────
# Les textes générés par l'IA (causes cachées, plans de remédiation) sont de longs
# paragraphes bruts. Sans découpage, ils s'affichent comme un bloc unique illisible.

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ])')

# Le découpage des listes numérotées ("… : 1) … ; 2) …", "…:\n1. …\n2. …",
# formats hybrides mélangés par les LLM) est centralisé dans
# text_structuring.split_numbered_items : marqueurs = frontières
# positionnelles, numéros sources ignorés et supprimés, numérotation
# régénérée par le template. Les références "(Num. 4)" / "(Geo. 7)" issues
# de _humanize_ids_in_text sont protégées par la garde anti-référence.


def _numbered_list_html(intro: str, steps: list[str]) -> Markup:
    """Rend (intro, items) en <p> + <ol> — l'unique numérotation visible."""
    parts = []
    if intro.strip():
        parts.append(f"<p>{_math_to_html(intro.strip())}</p>")
    parts.append("<ol class='step-list'>")
    parts.extend(f"<li>{_math_to_html(step)}</li>" for step in steps)
    parts.append("</ol>")
    return Markup("".join(parts))


def _paragraphs(s: str) -> Markup:
    """Découpe un texte dense en paragraphes ; si le texte contient une liste
    numérotée (même hybride), elle est rendue en <ol> — jamais en marqueurs bruts."""
    cleaned = _clean(s)
    intro, steps = _split_steps(cleaned)
    if steps:
        return _numbered_list_html(intro, steps)
    sentences = [p.strip() for p in _SENT_SPLIT.split(cleaned) if p.strip()]
    if len(sentences) <= 1:
        return Markup(_math_to_html(cleaned))
    return Markup("".join(f"<p>{_math_to_html(p)}</p>" for p in sentences))


def _action_html(s: str) -> Markup:
    """Rend un plan d'action : liste numérotée <ol> si détectée, sinon paragraphes."""
    cleaned = _clean(s)
    intro, steps = _split_steps(cleaned)
    if not steps:
        return _paragraphs(s)
    return _numbered_list_html(intro, steps)


def _display_id(rid: str) -> str:
    """Q_NUM_04 -> 'Num. 4', Q_GEO_03a -> 'Geo. 3a', autres -> inchanges."""
    m = _ID_NUM.match(rid)
    if m:
        return f"Num. {m.group(1)}"
    m = _ID_GEO.match(rid)
    if m:
        return f"Geo. {m.group(1)}"
    return rid


# ── Formatage ──────────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Formate un score -- virgule decimale francaise."""
    s = str(int(v)) if v == int(v) else f"{v:g}"
    return s.replace(".", ",")


def _effective_score(q: Any) -> float:
    try:
        if q.teacher_decision.value == "refused" and q.teacher_score is not None:
            return float(q.teacher_score)
    except AttributeError:
        pass
    return float(q.score)


# ── Contexte Jinja2 ────────────────────────────────────────────────────────────

def _build_context(
    copy_id: str,
    grade: Any,
    diagnostic: Any,
    student_name: str,
    rubric: Any = None,
) -> dict[str, Any]:
    """Construit le contexte de rendu -- valeurs brutes, HTML-echappees par Jinja2."""
    questions = grade.questions
    avg_conf = (sum(q.confidence for q in questions) / len(questions)) if questions else 0.0
    n_review = sum(1 for q in questions if q.requires_review)

    final_score    = grade.final_score    if grade.final_score    is not None else grade.total_score
    final_score_20 = grade.final_score_on_20
    _denom = grade.total_possible
    pct = (final_score / _denom) if _denom else 0.0

    rubric_pts: dict[str, float] = {}
    points_corrige: dict[str, float] = {}
    if rubric:
        rubric_pts = {item.id: item.max_score for item in (rubric.items or [])}
        points_corrige = {
            item.id: item.points_corrige for item in (rubric.items or []) if getattr(item, "points_corrige", None)
        }
    # Tests du référentiel : points affichés comme sur le corrigé papier
    # (« 1 / 2 »), et non sur l'échelle /20 (« 0,333333 / 0,666667 »).
    en_points_corrige = bool(points_corrige)

    good_qs: list[dict] = []
    partial_qs: list[dict] = []
    bad_qs:  list[dict] = []
    for q in questions:
        ms  = rubric_pts.get(q.rubric_item_id, 1.0)
        eff = _effective_score(q)
        pts = points_corrige.get(q.rubric_item_id)
        affiche, maximum = (eff / ms * pts, pts) if pts and ms else (eff, ms)
        entry = {
            "id":        _display_id(q.rubric_item_id),
            "score_fmt": _fmt(round(affiche, 2)),
            "max_fmt":   _fmt(round(maximum, 2)),
            "conf_pct":  round(q.confidence * 100),
            "comment":   _cm(q.comment or ""),
            "observed":  _cm(q.observed_answer or "--"),
            "correct":   _cm(q.correct_answer  or "--"),
            "review":    q.requires_review,
        }
        if eff <= 0:
            bad_qs.append(entry)
        elif eff >= ms - 1e-6:
            good_qs.append(entry)
        else:
            partial_qs.append(entry)

    skills: list[dict] = []
    if diagnostic and diagnostic.skills:
        for sk in diagnostic.skills:
            skills.append({
                "name":     _cm(sk.name),
                "level":    sk.level,
                "evidence": _cm(sk.evidence),
            })

    root_causes: list[dict] = []
    if diagnostic and diagnostic.root_causes:
        for rc in diagnostic.root_causes:
            root_causes.append({
                "visible": _paragraphs(rc.visible_error),
                "hidden":  _paragraphs(rc.hidden_cause),
                "qs":      ", ".join(_display_id(q) for q in rc.linked_questions) or "--",
            })

    remediation: list[dict] = []
    if diagnostic and diagnostic.remediation_plan:
        for item in sorted(diagnostic.remediation_plan, key=lambda x: x.priority):
            remediation.append({
                "priority": item.priority,
                "topic":    _cm(item.topic),
                "action":   _action_html(item.action),
            })

    is_perfect = (final_score_20 or 0) >= 20.0

    return {
        "STUDENT_NAME":      student_name or copy_id,
        "COPY_ID":           copy_id,
        "DATE":              _today_fr(),
        "FINAL_SCORE":       _fmt(final_score),
        "FINAL_SCORE_20":    _fmt(final_score_20) if final_score_20 is not None else "--",
        "TOTAL_POSSIBLE":    _fmt(grade.total_possible),
        "AI_CONFIDENCE_PCT": round(avg_conf * 100),
        "REVIEW_COUNT":      n_review,
        "SCORE_PCT":         pct,
        "good_questions":    good_qs,
        "partial_questions": partial_qs,
        "bad_questions":     bad_qs,
        "POINTS_CORRIGE":    en_points_corrige,
        "TOTAL_CORRIGE":     _fmt(round(sum(points_corrige.values()), 2)) if en_points_corrige else "",
        "strengths":         [_cm(s) for s in (diagnostic.strengths  if diagnostic else [])],
        "weaknesses":        [_cm(s) for s in (diagnostic.weaknesses if diagnostic else [])],
        "skills":            skills,
        "root_causes":       root_causes,
        "remediation":       remediation,
        "has_diagnostic":    bool(diagnostic),
        "is_perfect_score":  is_perfect,
    }


# ── API publique ───────────────────────────────────────────────────────────────

def generate_copy_report(
    output_path: Path,
    copy_id: str,
    grade: Any,
    diagnostic: Any,
    student_name: str = "",
    remediation_subject: Any = None,
    rubric: Any = None,
) -> None:
    """Genere le rapport PDF via xhtml2pdf (HTML+CSS -> PDF)."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        raise RuntimeError(
            "xhtml2pdf non installe. Lancez : pip install xhtml2pdf>=0.2.14"
        )
    from jinja2 import Environment, FileSystemLoader

    font_name = _register_unicode_font()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("rapport_correction.html.j2")
    ctx = _build_context(copy_id, grade, diagnostic, student_name, rubric)
    ctx["FONT_NAME"] = font_name
    html_content = template.render(**ctx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as pdf_file:
        result = pisa.CreatePDF(html_content, dest=pdf_file, encoding="utf-8")

    if result.err:
        raise RuntimeError(
            f"xhtml2pdf : {result.err} erreur(s) lors de la generation de {output_path.name}"
        )
    logger.info("[%s] Rapport PDF genere -> %s", copy_id, output_path)
