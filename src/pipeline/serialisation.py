"""
Conversion `PipelineResult` ↔ JSON.

Pourquoi pas de pickle
----------------------
Un pickle stocké en base est fragile — il casse dès qu'un champ de dataclass ou de
modèle Pydantic change, et un pickle est du code exécutable : le désérialiser
revient à faire confiance au contenu de la base. Une correspondance explicite coûte
quelques dizaines de lignes et échoue lisiblement quand un champ manque, au lieu de
lever une erreur incompréhensible six mois plus tard.

Le pipeline sait déjà sérialiser ses objets (`model_dump()` de Pydantic, voir
l'export `result.json`) : on s'appuie dessus.

Les chemins de fichiers sont conservés en texte. Ils désignent des fichiers dans
`runs/` — conséquence à connaître pour le déploiement : ce dossier est du disque
local. Sur Railway ou Render, sans volume persistant, il disparaît au redéploiement.
Les documents durables (scan, rapport, remédiation) sont, eux, déjà écrits en base
par le pipeline, donc rien d'irremplaçable n'est perdu — seule une correction en
cours au moment du redéploiement serait à relancer.

Framework-indépendant (D-CEO-40/D-CEO-42) : vivait dans `correction_web/`
(app Django) alors que Django et FastAPI en dépendent tous les deux — déplacé
ici pour que FastAPI cesse d'importer un module rangé sous une app Django.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _chemin(valeur: Any) -> str | None:
    return str(valeur) if valeur else None


def serialiser(resultat) -> dict:
    """`PipelineResult` → dict JSON-compatible."""
    grade = resultat.grade
    return {
        "copy_id": resultat.copy_id,
        "student_name": resultat.student_name,
        "ingestion": {
            "copy_id": resultat.ingestion.copy_id,
            "total_pages": resultat.ingestion.total_pages,
            "pages": [str(p) for p in resultat.ingestion.pages],
            "output_dir": str(resultat.ingestion.output_dir),
        }
        if resultat.ingestion
        else None,
        "transcription": resultat.transcription.model_dump() if resultat.transcription else None,
        "grade": grade.model_dump() if grade else None,
        "diagnostic": resultat.diagnostic.model_dump() if resultat.diagnostic else None,
        "plan_remediation": (
            resultat.plan_remediation.model_dump()
            if resultat.plan_remediation
            else None
        ),
        "plan_erreur": resultat.plan_erreur,
        "rubric": resultat.rubric.model_dump() if resultat.rubric else None,
        "pdf_path": _chemin(resultat.pdf_path),
        "remediation_pdf_path": _chemin(resultat.remediation_pdf_path),
        "json_path": _chemin(resultat.json_path),
        "errors": list(resultat.errors or []),
        "model_routing": dict(resultat.model_routing or {}),
        "subject_text": resultat.subject_text,
        "bareme_id": resultat.bareme_id,
        "runs_dir": resultat.runs_dir,
        "expert_instructions": resultat.expert_instructions,
        "official_answers": resultat.official_answers,
    }


def deserialiser(donnees: dict):
    """dict → `PipelineResult`.

    `validation_issues` n'est pas restauré : ce sont des avertissements produits
    pendant une exécution, sans usage après coup, et les reconstituer demanderait de
    figer un schéma de plus.
    """
    from src.models.domain import (
        CopyGrade,
        DiagnosticResult,
        IngestionResult,
        PlanRemediation,
        Rubric,
        TranscriptionResult,
    )
    from src.pipeline.pipeline import PipelineResult

    ingestion_brut = donnees.get("ingestion") or {}
    ingestion = IngestionResult(
        copy_id=ingestion_brut.get("copy_id", donnees["copy_id"]),
        total_pages=ingestion_brut.get("total_pages", 0),
        pages=[Path(p) for p in ingestion_brut.get("pages", [])],
        output_dir=Path(ingestion_brut.get("output_dir", ".")),
    )

    def _modele(classe, cle):
        brut = donnees.get(cle)
        return classe.model_validate(brut) if brut else None

    return PipelineResult(
        copy_id=donnees["copy_id"],
        student_name=donnees.get("student_name", ""),
        ingestion=ingestion,
        transcription=_modele(TranscriptionResult, "transcription"),
        grade=_modele(CopyGrade, "grade"),
        diagnostic=_modele(DiagnosticResult, "diagnostic"),
        # Les résultats d'avant le plan unique portent `remediation_subject` :
        # ignoré, ces corrections sont terminées et leur PDF déjà produit.
        plan_remediation=_modele(PlanRemediation, "plan_remediation"),
        plan_erreur=donnees.get("plan_erreur", ""),
        rubric=_modele(Rubric, "rubric"),
        pdf_path=Path(donnees["pdf_path"]) if donnees.get("pdf_path") else None,
        remediation_pdf_path=(
            Path(donnees["remediation_pdf_path"])
            if donnees.get("remediation_pdf_path")
            else None
        ),
        json_path=Path(donnees["json_path"]) if donnees.get("json_path") else None,
        errors=list(donnees.get("errors") or []),
        model_routing=dict(donnees.get("model_routing") or {}),
        subject_text=donnees.get("subject_text", ""),
        bareme_id=donnees.get("bareme_id", ""),
        runs_dir=donnees.get("runs_dir", ""),
        expert_instructions=donnees.get("expert_instructions", ""),
        official_answers=donnees.get("official_answers", ""),
    )
