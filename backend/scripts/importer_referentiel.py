#!/usr/bin/env python
"""CLI — importe `Referentiel_Socle_v0.xlsx` dans la base du nouveau
backend. Port de `manage.py importer_referentiel` (Django), même options :

    python scripts/importer_referentiel.py
    python scripts/importer_referentiel.py --classeur /chemin/Referentiel.xlsx
    python scripts/importer_referentiel.py --a-blanc     # rapport sans écriture
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.services.import_referentiel import ErreurImport, importer  # noqa: E402

# Le classeur vit à la racine du dépôt de travail (au-dessus de `Hakili_Lab/`),
# même convention que `referentiel/management/commands/importer_referentiel.py`.
_CANDIDATS = [
    Path(__file__).resolve().parents[3] / "Referentiel_Socle_v0.xlsx",
    Path(__file__).resolve().parents[2] / "Referentiel_Socle_v0.xlsx",
]


def _resoudre_classeur(fourni: str) -> Path:
    if fourni:
        chemin = Path(fourni).expanduser().resolve()
        if not chemin.exists():
            raise SystemExit(f"Classeur introuvable : {chemin}")
        return chemin
    for candidat in _CANDIDATS:
        if candidat.exists():
            return candidat
    raise SystemExit(
        "Referentiel_Socle_v0.xlsx introuvable. Cherché dans :\n  "
        + "\n  ".join(str(c) for c in _CANDIDATS)
        + "\nPréciser le chemin avec --classeur."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe le référentiel (compétences, types d'erreur, questions, coûts).")
    parser.add_argument("--classeur", type=str, default="", help="Chemin du .xlsx")
    parser.add_argument("--a-blanc", action="store_true", help="Analyse et rapporte sans rien écrire en base.")
    args = parser.parse_args()

    chemin = _resoudre_classeur(args.classeur)
    print(f"Classeur : {chemin}\n")

    db = SessionLocal()
    try:
        try:
            rapport = importer(db, chemin, a_blanc=args.a_blanc)
        except ErreurImport as exc:
            raise SystemExit(str(exc)) from exc

        if rapport.a_blanc:
            print("  Marche à blanc — aucune écriture en base.")
            for nom, n in rapport.lignes_lues.items():
                print(f"    {nom:24s} {n:5d} lignes lues")
            return

        print("")
        for libelle, n in [
            ("Types d'erreur", rapport.n_types),
            ("Compétences", rapport.n_competences),
            ("Liens de prérequis", rapport.n_prerequis),
            ("Coûts de remédiation", rapport.n_couts),
            ("  dont estimés (lycée)", rapport.n_couts_estimes),
            ("Questions", rapport.n_questions),
            ("Signatures d'erreur", rapport.n_signatures),
            ("Options de QCM", rapport.n_options),
        ]:
            print(f"  {libelle:24s} {n:5d}")

        print("")
        print(f"  Import terminé. {rapport.n_qcm_avec_reponse} QCM avec bonne réponse.")
        if rapport.n_sans_corrige:
            print(
                f"  {rapport.n_sans_corrige} questions sans corrigé — le classeur n'en "
                "contient pas pour les formats autres que QCM (arbitrage B de "
                "docs/harmonisation_donnees.md)."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
