"""
Plan de remédiation (cahier élève) : HTML Jinja2 → PDF par Chromium headless.

Pourquoi Chromium et pas xhtml2pdf comme le rapport de correction : le cahier
reproduit à l'identique l'exemplaire validé (NIKIEMA K. Amale), qui repose sur
des grilles CSS, des polices web et des formules LaTeX rendues par MathJax —
trois choses que xhtml2pdf ne sait pas faire.

Rien ne sort sur le réseau : la page est servie depuis une origine fictive
(`_ORIGINE`) dont Playwright intercepte chaque requête, et MathJax comme les
polices sont embarqués dans templates/plan_remediation/vendor/.
"""
from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from src.models.domain import PlanRemediation

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "plan_remediation"
_ORIGINE = "https://plan.hakili.invalid/"


def _duree(h: float) -> str:
    """1.0 → « 1 h », 1.5 → « 1 h 30 »."""
    entieres, minutes = int(h), round((h - int(h)) * 60)
    return f"{entieres} h {minutes:02d}" if minutes else f"{entieres} h"


def _plage(bornes: tuple[int, int]) -> str:
    debut, fin = bornes
    return str(debut) if debut == fin else f"{debut} à {fin}"


def _liste_et(nombres: list[int]) -> str:
    """[3] → « 3 », [3, 14] → « 3 et 14 », [1, 2, 3] → « 1, 2 et 3 »."""
    textes = [str(n) for n in nombres]
    return textes[0] if len(textes) == 1 else f"{', '.join(textes[:-1])} et {textes[-1]}"


def _paragraphes(texte: str) -> list[str]:
    return [p.strip() for p in texte.split("\n\n") if p.strip()]


def _capitalize_first(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


_FORMULE_CENTREE = re.compile(r"^\\\[.*\\\]$", re.S)
# Formules en ligne ou centrées : jamais d'italique à l'intérieur (\(a*b\)).
_SEGMENTS_MATH = re.compile(r"(\\\(.*?\\\)|\\\[.*?\\\])", re.S)
_ITALIQUE = re.compile(r"\*([^*\n]+)\*")


def _formule_centree(texte: str) -> bool:
    return bool(_FORMULE_CENTREE.match(texte.strip()))


def _emphase(texte: str) -> Markup:
    """Échappe le texte, puis *mot* → <em>mot</em> hors des formules."""
    morceaux = _SEGMENTS_MATH.split(texte)
    return Markup("").join(
        escape(m) if i % 2 else Markup(_ITALIQUE.sub(r"<em>\1</em>", str(escape(m))))
        for i, m in enumerate(morceaux)
    )


def _environnement() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.filters.update(
        duree=_duree, plage=_plage, liste_et=_liste_et,
        paragraphes=_paragraphes, capitalize_first=_capitalize_first, emphase=_emphase,
    )
    env.tests["formule_centree"] = _formule_centree
    return env


def render_plan_html(plan: PlanRemediation) -> str:
    """HTML du cahier. Ses ressources (CSS, polices, MathJax) sont en chemins
    relatifs au dossier du gabarit."""
    return _environnement().get_template("plan_remediation.html.j2").render(
        plan=plan, seances=plan.seances()
    )


def generate_plan_remediation_pdf(output_path: Path, plan: PlanRemediation) -> int:
    """Écrit le PDF du cahier. Renvoie le nombre de formules que MathJax n'a
    pas pu composer (0 attendu) : une formule fautive s'affiche en rouge dans
    le PDF au lieu de faire échouer toute la génération."""
    from playwright.sync_api import sync_playwright

    html = render_plan_html(plan).encode("utf-8")

    def _servir(route) -> None:
        chemin = route.request.url[len(_ORIGINE):].split("?")[0]
        if chemin in ("", "index.html"):
            route.fulfill(body=html, content_type="text/html; charset=utf-8")
            return
        fichier = (_TEMPLATE_DIR / chemin).resolve()
        if _TEMPLATE_DIR not in fichier.parents or not fichier.is_file():
            route.fulfill(status=404)
            return
        type_mime = mimetypes.guess_type(fichier.name)[0] or "application/octet-stream"
        route.fulfill(body=fichier.read_bytes(), content_type=type_mime)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        try:
            page = navigateur.new_page(color_scheme="light")
            # Tout ce qui n'est pas notre origine est refusé : aucune fuite réseau.
            page.route("**/*", lambda r: _servir(r) if r.request.url.startswith(_ORIGINE) else r.abort())
            page.goto(_ORIGINE + "index.html", wait_until="load")
            page.evaluate("() => MathJax.startup.promise.then(() => document.fonts.ready).then(() => true)")
            erreurs_math = page.evaluate("() => document.querySelectorAll('mjx-merror').length")
            page.emulate_media(media="print")
            page.pdf(path=str(output_path), format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            navigateur.close()

    if erreurs_math:
        logger.warning("[%s] Plan de remédiation : %d formule(s) non composée(s) par MathJax",
                       plan.copy_id, erreurs_math)
    logger.info("Plan de remédiation écrit : %s", output_path)
    return erreurs_math
