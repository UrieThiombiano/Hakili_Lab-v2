"""
Génération PDF du rapport diagnostique des lacunes (module 9) via xhtml2pdf.

À la différence de `pdf_plan_html.py` (le plan de travail, restreint aux
problèmes confirmés/en remédiation), ce rapport montre l'état des lieux
complet d'une session — hypothèses non tranchées comprises — groupé par
état. Pas persisté comme document (même raison que le plan : la session
évolue), régénéré à la demande.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_MONTHS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _today_fr() -> str:
    d = date.today()
    return f"{d.day} {_MONTHS_FR[d.month]} {d.year}"


def _date_fr(d: Any) -> str:
    if d is None:
        return ""
    return f"{d.day} {_MONTHS_FR[d.month]} {d.year}"


def _get_font_name() -> str:
    try:
        from src.pipeline.pdf_report_html import _register_unicode_font
        return _register_unicode_font()
    except Exception:
        return "Helvetica"


def _build_context(student_name: str, rapport: dict) -> dict[str, Any]:
    from src.pipeline.pdf_report_html import _cm

    groupes_ctx = []
    for groupe in rapport["groupes"]:
        lignes_ctx = []
        for ligne in groupe.lignes:
            lignes_ctx.append({
                "competence_libelle": _cm(ligne.competence.libelle),
                "competence_code": ligne.competence.code,
                "type_erreur_libelle": _cm(ligne.type_erreur.libelle),
                "cout": ligne.probleme.cout_estime,
                "interpretation": _cm(ligne.interpretation),
                "justification": _cm(ligne.probleme.justification),
                "date_detection": _date_fr(ligne.date_detection),
                "date_dernier_changement": _date_fr(ligne.date_dernier_changement),
            })
        groupes_ctx.append({"libelle": groupe.libelle, "etat": groupe.etat, "lignes": lignes_ctx})

    return {
        "STUDENT_NAME": student_name,
        "DATE": _today_fr(),
        "NB_PROBLEMES": rapport["nb_problemes"],
        "COUT_CONFIRME": rapport["cout_confirme"],
        "COUT_HYPOTHESE": rapport["cout_hypothese"],
        "groupes": groupes_ctx,
    }


def generate_diagnostic_pdf(
    output_path: Path,
    student_name: str,
    rapport: dict,
) -> None:
    """Génère le rapport diagnostique des lacunes en PDF via xhtml2pdf."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        raise RuntimeError(
            "xhtml2pdf non installé. Lancez : pip install xhtml2pdf>=0.2.14"
        )
    from jinja2 import Environment, FileSystemLoader

    font_name = _get_font_name()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("rapport_diagnostique.html.j2")
    ctx = _build_context(student_name, rapport)
    ctx["FONT_NAME"] = font_name
    html_content = template.render(**ctx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as pdf_file:
        result = pisa.CreatePDF(html_content, dest=pdf_file, encoding="utf-8")

    if result.err:
        raise RuntimeError(
            f"xhtml2pdf : {result.err} erreur(s) lors de la génération de {output_path.name}"
        )
    logger.info("Rapport diagnostique PDF généré → %s", output_path)
