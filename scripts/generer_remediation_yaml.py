#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transforme `remediation/<niveau>/modules_c/M*.md` en YAML structuré.

    python scripts/generer_remediation_yaml.py

Produit, pour chacun des 7 niveaux, `data/knowledge/remediation_<niveau>.yaml`
(modules → leçons → retenir/méthode/exemple/attention/déclic, exercices notés
et corrigés, fiche de révision, trouve l'erreur) et
`data/knowledge/remediation_positionnement_<niveau>.yaml` (grille
question de positionnement → module prioritaire, quand elle existe).

Rejoue en écrasant (idempotent) — la source (`remediation/`) fait foi, ce
fichier n'est jamais retouché à la main.

Échoue fort plutôt que de produire un niveau silencieusement vide : un module
qui ne respecte pas les invariants du gabarit (numéro/titre, au moins une
leçon, au moins un exercice — voir `remediation_parser.py`) est un vrai
défaut de source, pas un cas limite à absorber.
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.knowledge.remediation_parser import (
    NIVEAUX,
    parse_niveau,
    parse_plan_livret,
    parse_positionnement,
)

_KB = Path(__file__).resolve().parent.parent / "data" / "knowledge"


def _module_to_dict(m) -> dict:
    return {
        "niveau": m.niveau,
        "module": m.numero,
        "module_titre": m.titre,
        "pourquoi": m.pourquoi,
        "diagnostic": [{"question": q, "reponse": r} for q, r in m.diagnostic],
        "lecons": [
            {
                "id": f"{m.niveau}_M{m.numero:02d}_L{l.numero.split('.')[-1]}",
                "numero": l.numero,
                "titre": l.titre,
                "retenir": l.retenir,
                "methode": (
                    {"titre": l.methode_titre, "etapes": l.methode_etapes}
                    if l.methode_titre or l.methode_etapes
                    else None
                ),
                "exemple_resolu": l.exemple_resolu,
                "erreurs_frequentes": [asdict(e) for e in l.erreurs_frequentes],
                "declic": l.declic,
                "figures": l.figures,
            }
            for l in m.lecons
        ],
        "exercices": [asdict(e) for e in m.exercices],
        "fiche_revision": m.fiche_revision,
        "trouve_erreur": [{"faux": f, "correction": c} for f, c in m.trouve_erreur],
        "cartographie_lacunes": [],  # rempli plus bas si un PLAN_Livret existe
        "source_path": m.source_path,
    }


def generer() -> int:
    _KB.mkdir(parents=True, exist_ok=True)
    total_modules = total_lecons = total_exercices = 0

    for niveau in NIVEAUX:
        modules = parse_niveau(niveau)
        if not modules:
            raise SystemExit(f"{niveau} : aucun module parsé — arrêt.")

        cartographie = parse_plan_livret(niveau)
        carto_par_module: dict[str, list[dict]] = {}
        for lac in cartographie:
            carto_par_module.setdefault(lac.module.strip(), []).append(
                {"lacune": lac.lacune, "bloque_en": lac.bloque_en}
            )

        sortie = []
        n_lecons = n_exercices = 0
        for m in modules:
            d = _module_to_dict(m)
            d["cartographie_lacunes"] = carto_par_module.get(f"M{m.numero}", [])
            sortie.append(d)
            n_lecons += len(d["lecons"])
            n_exercices += len(d["exercices"])

        if n_lecons == 0 or n_exercices == 0:
            raise SystemExit(f"{niveau} : {n_lecons} leçons, {n_exercices} exercices — arrêt.")

        chemin = _KB / f"remediation_{niveau}.yaml"
        chemin.write_text(
            yaml.dump(sortie, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )

        positionnement = parse_positionnement(niveau)
        chemin_pos = _KB / f"remediation_positionnement_{niveau}.yaml"
        chemin_pos.write_text(
            yaml.dump(
                [{"question": p.numero, "module": p.module} for p in positionnement],
                allow_unicode=True, sort_keys=False, width=100,
            ),
            encoding="utf-8",
        )

        total_modules += len(modules)
        total_lecons += n_lecons
        total_exercices += n_exercices
        print(f"{niveau:8s} {len(modules):2d} modules · {n_lecons:3d} leçons · "
              f"{n_exercices:3d} exercices · {len(cartographie):2d} lacunes cartographiées · "
              f"{len(positionnement):2d} questions de positionnement -> {chemin.name}")

    print(f"\nTotal : {total_modules} modules, {total_lecons} leçons, "
          f"{total_exercices} exercices, sur {len(NIVEAUX)} niveaux.")
    return 0


if __name__ == "__main__":
    sys.exit(generer())
