"""L'image de production contient tout ce que le code lit à l'exécution.

Recette prod du 2026-10-16 : `templates/` n'était pas copié par
deploy/Dockerfile, et aucun PDF ne pouvait être produit en production."""
from __future__ import annotations

import re
from pathlib import Path

_RACINE = Path(__file__).parent.parent


def _dossiers_copies() -> set[str]:
    dockerfile = (_RACINE / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    return set(re.findall(r"^COPY\s+(?:--\S+\s+)*([A-Za-z_]+)/", dockerfile, re.M))


def test_dossiers_lus_a_l_execution_copies_dans_l_image():
    copies = _dossiers_copies()
    for dossier in ("src", "backend", "prompts", "templates", "data"):
        assert dossier in copies, f"{dossier}/ absent de deploy/Dockerfile"


def test_gabarits_pdf_presents():
    for gabarit in (
        "rapport_correction.html.j2",
        "remediation_exercises.html.j2",
        "plan_remediation/plan_remediation.html.j2",
        "plan_remediation/plan_remediation.css",
        "plan_remediation/vendor/tex-svg.js",
        "plan_remediation/vendor/fonts.css",
    ):
        assert (_RACINE / "templates" / gabarit).exists()


def test_chromium_installe_dans_l_image():
    """Le plan de remédiation est imprimé par Chromium : sans lui, aucun plan
    en production."""
    dockerfile = (_RACINE / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in dockerfile
    exigences = (_RACINE / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^playwright==\d", exigences, re.M)
