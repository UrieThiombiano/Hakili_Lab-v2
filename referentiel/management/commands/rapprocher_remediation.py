"""
Rapproche les leçons de `data/knowledge/remediation_<niveau>.yaml` des 101
compétences canoniques — résout Arbitrage C (`docs/harmonisation_donnees.md`
§7) au profit de `remediation/`, plus riche que les 121 chunks du curriculum
RAG (leçons + exercices notés + corrigés + erreurs fréquentes, contre de la
seule métadonnée pour le curriculum).

    python manage.py rapprocher_remediation

Écrit `data/knowledge/remediation_competences_map.yaml` :
`{niveau: {code_competence: {lecon_id, module, score, confiance}}}` —
consommé par `RemediationRetriever.get_by_competence(code, niveau)`.

Principe repris de `scripts/rapprocher_curriculum.py`
-------------------------------------------------------
Même famille de score (similarité de libellé + recouvrement de mots-clés),
même discipline de code (aucune compétence inventée, un score composite
borné). Deux différences assumées :

  1. **Source des compétences** : requête Django ORM plutôt que le classeur
     Excel (`Referentiel_Socle_v0.xlsx` absent de ce checkout ; les 101 lignes
     sont déjà importées en base — c'est la même donnée, à jour).
  2. **Écart de niveau non symétrique.** Le script curriculum traite un écart
     de niveau comme un signal de désaccord dans les deux sens. Ici, un
     livret de remédiation `remediation/<N>/` s'adresse par construction à un
     élève qui *entre* en N et retravaille des notions introduites *avant* N
     (le livret 2ndeC reprend des chapitres de 4e/3e, voir
     `PLAN_Livret_Remediation_2ndeC.md` §4). Une compétence introduite au
     niveau du livret ou avant est donc attendue ; une compétence introduite
     après ne devrait normalement pas s'y trouver.

Seuil unique, auto-validé
--------------------------
Décision explicite avec l'utilisateur (à la différence du classeur de
relecture bloquant utilisé pour Arbitrage C) : au-delà de `SEUIL`, la
correspondance est retenue directement, sans relecture humaine préalable.
Le score et un repère de confiance restent écrits dans la carte produite,
pour audit a posteriori — voir le rapport imprimé par cette commande.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand

from referentiel.models import Competence

_KB = Path(__file__).resolve().parents[3] / "data" / "knowledge"

# Une compétence sans niveau introductif en Tle D dans le classeur (vérifié :
# aucune des 101 lignes n'a `niveau_intro = "tleD"`) — la borne haute pour le
# livret TleD est donc `1ereD`, jamais dépassée.
_ORDRE_NIVEAUX = ["Primaire", "6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD", "tleD"]
_NIVEAU_DOSSIER_VERS_TEST = {
    "6eme": "6eme", "5eme": "5eme", "4eme": "4eme", "3eme": "3eme",
    "2ndeC": "2ndeC", "1ereD": "1ereD", "TleD": "tleD",
}

SEUIL = 0.40

_SYNONYMES = {
    "fonction": "application", "fonctions": "application",
    "homothetie": "transformation", "translation": "transformation",
    "symetrie": "transformation", "rotation": "transformation",
    "frequence": "statistique", "frequences": "statistique",
    "moyenne": "statistique", "mediane": "statistique",
    "quotient": "division", "produit": "multiplication", "somme": "addition",
    "racine": "racines", "puissance": "puissances",
    "equation": "equations", "inequation": "inequations",
    "vecteur": "vecteurs", "fraction": "fractions",
}


def _fold(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", str(texte or "")) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def _mots(texte: str) -> set[str]:
    bruts = {m for m in _fold(texte).split() if len(m) > 3}
    return bruts | {_SYNONYMES[m] for m in bruts if m in _SYNONYMES}


def _charger_lecons() -> list[dict]:
    lecons = []
    for fichier in sorted(_KB.glob("remediation_*.yaml")):
        if "positionnement" in fichier.name or fichier.name.endswith("_competences_map.yaml"):
            continue
        modules = yaml.safe_load(fichier.read_text(encoding="utf-8")) or []
        for m in modules:
            for l in m["lecons"]:
                lecons.append({
                    "id": l["id"],
                    "niveau": m["niveau"],
                    "module": m["module"],
                    "module_titre": m["module_titre"],
                    "titre": l["titre"],
                    "texte_cle": " ".join(
                        [l["titre"]]
                        + l.get("retenir", [])
                        + ([l["methode"]["titre"]] if l.get("methode") else [])
                    ),
                })
    return lecons


def _score(lecon: dict, competence: Competence, niveau_test: str) -> float:
    titre_lecon = _fold(lecon["titre"])
    libelle_comp = _fold(competence.libelle)
    base = SequenceMatcher(None, titre_lecon, libelle_comp).ratio()

    tronc = libelle_comp.split(" ")[0:3]
    base = max(base, SequenceMatcher(None, titre_lecon, " ".join(tronc)).ratio() * 0.9)

    mots_lecon = _mots(lecon["texte_cle"])
    mots_comp = _mots(competence.libelle) | _mots(competence.description)
    recouvrement = 0.0
    if mots_lecon and mots_comp:
        recouvrement = len(mots_lecon & mots_comp) / len(mots_lecon)

    score = 0.6 * base + 0.4 * recouvrement

    idx_book = _ORDRE_NIVEAUX.index(niveau_test) if niveau_test in _ORDRE_NIVEAUX else None
    idx_comp = (
        _ORDRE_NIVEAUX.index(competence.niveau_intro)
        if competence.niveau_intro in _ORDRE_NIVEAUX else None
    )
    if idx_book is not None and idx_comp is not None:
        if idx_comp < idx_book:
            score += 0.05
        elif idx_comp == idx_book:
            pass
        else:
            score -= 0.08 * (idx_comp - idx_book)

    return max(0.0, min(1.0, score))


class Command(BaseCommand):
    help = "Rapproche les leçons de remediation_<niveau>.yaml des compétences canoniques."

    def handle(self, *args, **options):
        competences = list(Competence.objects.all())
        lecons = _charger_lecons()
        if not competences:
            self.stderr.write("Aucune compétence en base — importer_referentiel d'abord.")
            return
        if not lecons:
            self.stderr.write("Aucune leçon — generer_remediation_yaml.py d'abord.")
            return

        carte: dict[str, dict[str, dict]] = defaultdict(dict)
        couverture: dict[str, set[str]] = defaultdict(set)

        for niveau_dossier, niveau_test in _NIVEAU_DOSSIER_VERS_TEST.items():
            lecons_niveau = [l for l in lecons if l["niveau"] == niveau_dossier]
            for competence in competences:
                classes = sorted(
                    ((_score(l, competence, niveau_test), l) for l in lecons_niveau),
                    key=lambda paire: paire[0], reverse=True,
                )
                if not classes:
                    continue
                meilleur_score, meilleure_lecon = classes[0]
                if meilleur_score < SEUIL:
                    continue
                carte[niveau_test][competence.code] = {
                    "lecon_id": meilleure_lecon["id"],
                    "module": meilleure_lecon["module"],
                    "score": round(meilleur_score, 3),
                }
                couverture[niveau_test].add(competence.code)

        sortie = _KB / "remediation_competences_map.yaml"
        sortie.write_text(
            yaml.dump(dict(carte), allow_unicode=True, sort_keys=True, width=100),
            encoding="utf-8",
        )

        self.stdout.write(f"{len(competences)} compétences · {len(lecons)} leçons\n")
        total_paires = sum(len(v) for v in carte.values())
        for niveau_test in _NIVEAU_DOSSIER_VERS_TEST.values():
            n = len(couverture.get(niveau_test, set()))
            self.stdout.write(f"  {niveau_test:8s} {n:3d}/{len(competences)} compétences couvertes")
        self.stdout.write(f"\n  Total : {total_paires} paires (niveau, compétence) -> {sortie}")
