"""Génération PDF de la fiche de travail (module 7) via xhtml2pdf.

À la différence de `pdf_plan_html.py` (module 6 — le plan chiffré d'une
session entière : quoi, dans quel ordre, combien d'heures), cette fiche
décrit **comment** travailler UN problème (compétence × type d'erreur) :
méthode, exemple résolu, exercices gradués corrigés, critère de réussite.
Voir `app/services/fiche_remediation.py` pour l'assemblage du contenu et
D-CEO-43 (`docs/decision_register.md`) pour l'historique de la confusion de
nommage entre les deux documents.

Contrairement au plan, cette fiche est **persistée** (`FicheRemediation`,
catalogue par compétence × type d'erreur × niveau) : elle ne change pas tant
qu'un tuteur ne la corrige pas explicitement, deux élèves avec le même
problème doivent voir le même document.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from markupsafe import Markup

logger = logging.getLogger(__name__)

#: `exemple_resolu` (contenu `remediation/`, écrit à la main) contient parfois
#: un tableau markdown pipe (« Ce qu'on fait / Ce qu'on écrit ») — laissé tel
#: quel par `_cm()` (pensé pour de la prose IA), il s'affichait en texte brut
#: avec des `|` et des lignes de tirets. Rendu en `<table>` ici plutôt que
#: dans `math_format.py` (partagé, pas le bon endroit pour une règle propre
#: à un seul champ d'un seul module).
_MD_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")


def _est_ligne_separatrice(cellules: list[str]) -> bool:
    return all(set(c.strip()) <= {"-", ":"} and c.strip() for c in cellules)


def _table_html(lignes_brutes: list[str]) -> str:
    """Rend un tableau markdown en lignes « cellule 1 → cellule 2 », pas en
    `<table>` HTML : le moteur de tables de xhtml2pdf calcule des largeurs de
    colonne inexploitables (une lettre par ligne observé en pratique) sans
    qu'aucune règle CSS testée (`table-layout: fixed`, largeurs explicites)
    ne s'en sorte mieux — plus simple et plus sûr de s'en passer (D-CEO-43)."""
    from src.pipeline.pdf_report_html import _cm

    lignes = [l.strip("|").split("|") for l in lignes_brutes]
    if len(lignes) >= 2 and _est_ligne_separatrice(lignes[1]):
        lignes = [lignes[0]] + lignes[2:]

    items = []
    for ligne in lignes:
        cellules = [c.strip() for c in ligne if c.strip()]
        if not cellules:
            continue
        contenu = " → ".join(str(_cm(c)) for c in cellules)
        items.append(f"<li>{contenu}</li>")
    return f'<ul class="exemple-tableau">{"".join(items)}</ul>' if items else ""


def _render_avec_tableaux(texte: str) -> Markup:
    """Convertit un texte pouvant contenir des tableaux markdown en HTML —
    paragraphes passés par `_cm` (nettoyage + math), tableaux rendus tels
    quels. Utilisé pour `exemple_resolu`, seul champ de remédiation observé
    avec des tableaux (D-CEO-43)."""
    from src.pipeline.pdf_report_html import _cm

    parts: list[str] = []
    para_buf: list[str] = []
    table_buf: list[str] = []

    def _flush_para() -> None:
        if para_buf:
            joined = " ".join(para_buf).strip()
            if joined:
                parts.append(f"<p>{_cm(joined)}</p>")
            para_buf.clear()

    def _flush_table() -> None:
        if table_buf:
            parts.append(_table_html(table_buf))
            table_buf.clear()

    for ligne in texte.split("\n"):
        s = ligne.strip()
        if _MD_TABLE_ROW.match(s):
            _flush_para()
            table_buf.append(s)
        elif not s:
            _flush_para()
            _flush_table()
        else:
            _flush_table()
            para_buf.append(s)
    _flush_para()
    _flush_table()
    return Markup("".join(parts))

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_MONTHS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

_LIBELLES_DEROULE = {
    "verification_prerequis": "Vérification des prérequis",
    "rappel_methode": "Rappel de la méthode",
    "exemple_commente": "Exemple travaillé, commenté",
    "exercices_gradues": "Exercices gradués",
    "bilan": "Bilan et critère de réussite",
}


def _today_fr() -> str:
    d = date.today()
    return f"{d.day} {_MONTHS_FR[d.month]} {d.year}"


def _get_font_name() -> str:
    try:
        from src.pipeline.pdf_report_html import _register_unicode_font
        return _register_unicode_font()
    except Exception:
        return "Helvetica"


def _build_context(fiche: Any) -> dict[str, Any]:
    from src.pipeline.pdf_report_html import _cm

    contenu = fiche.contenu

    deroule = [
        {"libelle": _LIBELLES_DEROULE.get(cle, cle), "minutes": minutes}
        for cle, minutes in contenu.get("deroule_minutes", {}).items()
    ]

    return {
        "COMPETENCE_CODE": contenu["competence_code"],
        "COMPETENCE_LIBELLE": _cm(contenu["competence_libelle"]),
        "TYPE_ERREUR_LIBELLE": _cm(contenu["type_erreur_libelle"]),
        "NIVEAU": contenu["niveau"],
        "DATE": _today_fr(),
        "VERSION": fiche.version,
        "CORRIGEE_PAR": fiche.corrigee_par,
        "DATE_CORRECTION": fiche.date_correction.strftime("%d/%m/%Y") if fiche.date_correction else "",
        "OBJECTIF": _cm(contenu["objectif"]),
        "PREREQUIS": contenu.get("prerequis_a_verifier") or [],
        "METHODE": (
            {
                "titre": _cm(contenu["methode"].get("titre", "")),
                "etapes": [_cm(e) for e in contenu["methode"].get("etapes", [])],
            }
            if contenu.get("methode")
            else None
        ),
        "RETENIR": [_cm(r) for r in (contenu.get("retenir") or [])],
        "EXEMPLE_RESOLU": _render_avec_tableaux(contenu["exemple_resolu"]) if contenu.get("exemple_resolu") else None,
        "ERREURS_FREQUENTES": [
            {"erreur": _cm(e["erreur"]), "correction": _cm(e["correction"])}
            for e in (contenu.get("erreurs_frequentes") or [])
        ],
        "DECLIC": _cm(contenu["declic"]) if contenu.get("declic") else None,
        "DEROULE": deroule,
        "EXERCICES": [
            {
                "numero": ex["numero"],
                "etoiles": ex["etoiles"],
                "enonce": _cm(ex["enonce"]),
                "correction": _cm(ex["correction"]),
            }
            for ex in (contenu.get("exercices") or [])
        ],
        "CRITERE_REUSSITE": _cm(contenu["critere_reussite"]),
    }


def generate_fiche_travail_pdf(output_path: Path, fiche: Any) -> None:
    """Génère la fiche de travail (module 7) en PDF via xhtml2pdf, à partir
    d'une `FicheRemediation` déjà cataloguée (voir
    `app/services/fiche_remediation.py::obtenir_ou_generer`)."""
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
    template = env.get_template("fiche_travail.html.j2")
    ctx = _build_context(fiche)
    ctx["FONT_NAME"] = font_name
    html_content = template.render(**ctx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as pdf_file:
        result = pisa.CreatePDF(html_content, dest=pdf_file, encoding="utf-8")

    if result.err:
        raise RuntimeError(
            f"xhtml2pdf : {result.err} erreur(s) lors de la génération de {output_path.name}"
        )
    logger.info("Fiche de travail PDF générée → %s", output_path)
