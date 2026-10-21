"""
Génération PDF de la fiche de remédiation (module 7) via xhtml2pdf.

À la différence de `pdf_remediation_html.py` (un sujet d'exercices attaché à
UNE copie), cette fiche décrit le **plan** d'une session entière — quoi
travailler, dans quel ordre, combien d'heures — tel que produit par
`suivi/plan.py::construire()`. Elle n'est pas persistée comme les autres
documents : le plan change tant que des problèmes passent de confirmé à
résolu, un PDF figé irait vite périmé. Elle se régénère à la demande.
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


def _get_font_name() -> str:
    try:
        from src.pipeline.pdf_report_html import _register_unicode_font
        return _register_unicode_font()
    except Exception:
        return "Helvetica"


def _build_context(student_name: str, session: Any, plan: dict, provisoire: bool = False) -> dict[str, Any]:
    from src.pipeline.pdf_report_html import _cm

    etapes_ctx = []
    for etape in plan["etapes"]:
        etapes_ctx.append({
            "rang": etape.rang,
            "competence_libelle": _cm(etape.competence.libelle),
            "competence_code": etape.competence.code,
            "type_erreur_libelle": _cm(etape.type_erreur.libelle),
            "cout": etape.cout,
            "prerequis": [_cm(p.libelle) for p in etape.prerequis_aussi_en_difficulte],
            "signatures": [
                {
                    "production": _cm(s.production_eleve),
                    "interpretation": _cm(s.interpretation),
                }
                for s in etape.signatures
            ],
        })

    return {
        "STUDENT_NAME":  student_name,
        "DATE":          _today_fr(),
        "PALIER":        plan["palier"],
        "TOTAL_HEURES":  plan["total_heures"],
        "NB_PROBLEMES":  plan["nb_problemes"],
        "REPOSE_SUR_ESTIMATION": plan["repose_sur_estimation"],
        "etapes":        etapes_ctx,
        "INSCRIT":       session.inscrite,
        "DATE_INSCRIPTION": session.date_inscription,
        "PROVISOIRE":    provisoire,
    }


def generate_plan_pdf(
    output_path: Path,
    student_name: str,
    session: Any,
    plan: dict,
    provisoire: bool = False,
) -> None:
    """Génère la fiche de remédiation (le plan chiffré) en PDF via xhtml2pdf.

    `provisoire=True` : plan construit à partir d'hypothèses non confirmées
    (voir `GET /api/sessions/{jeton}/plan-provisoire`) — affiche un bandeau
    d'avertissement, reste sinon un rendu identique."""
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
    template = env.get_template("fiche_remediation_plan.html.j2")
    ctx = _build_context(student_name, session, plan, provisoire=provisoire)
    ctx["FONT_NAME"] = font_name
    html_content = template.render(**ctx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as pdf_file:
        result = pisa.CreatePDF(html_content, dest=pdf_file, encoding="utf-8")

    if result.err:
        raise RuntimeError(
            f"xhtml2pdf : {result.err} erreur(s) lors de la génération de {output_path.name}"
        )
    logger.info("Fiche de remédiation PDF générée → %s", output_path)
