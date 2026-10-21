"""
RemediationRetriever — récupération du contenu de `remediation/` par
compétence canonique.

Fonctionnement
--------------
1. Charge au démarrage `data/knowledge/remediation_<niveau>.yaml` (produits
   par `scripts/generer_remediation_yaml.py`) et `remediation_competences_map
   .yaml` (produit par `manage.py rapprocher_remediation`).
2. `get_by_competence(code, niveau)` rend, si le rapprochement en a trouvé
   une, la leçon de remédiation la plus proche de cette compétence **dans le
   livret du niveau demandé**.
3. `RemediationChunk.to_context_text()` rend un texte compact pour un prompt
   — méthode, erreurs fréquentes typées, un seul exemple travaillé.

Ce que ça résout
-----------------
Résout Arbitrage C (`docs/harmonisation_donnees.md` §7, D-CEO-41) : le
diagnostic (module 4), le sujet de confirmation T1 (module 5) et les sujets
de vérification T3/T4/T5 généraient jusqu'ici leurs items sans savoir ce qui
est réellement enseigné à un niveau donné, ni disposer d'un exemple calibré à
imiter — voir `referentiel/contexte.py::contexte_diagnostic()`, dont le
docstring appelait explicitement cet enrichissement.

Ce que ce module ne fait jamais
---------------------------------
`to_context_text()` n'expose ni le numéro ni le corrigé d'un exercice noté de
la banque (`exercices` dans le YAML) : ce serait fournir au LLM l'antisèche
d'un item qu'il doit inventer lui-même, à l'encontre de la règle déjà écrite
dans `prompts/confirmation_subject_prompt.md` (« aucune indication qui
donnerait la réponse »). Seuls le rappel de méthode, les erreurs fréquentes
typées et **un** exemple résolu (le modèle travaillé, pas un item à recopier)
sont injectés.

`RemediationChunk.exercices_gradues()` est la seule exception délibérée à
cette règle : il rend des exercices corrigés en clair, mais seulement pour le
générateur de fiches de travail (module 7, `app/services/fiche_remediation.py`)
qui assemble un document lu par un tuteur humain, jamais par un prompt LLM.
Ne jamais faire transiter le résultat de cette méthode par un prompt.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent.parent.parent / "data" / "knowledge"

# `NiveauTest` (referentiel.models) -> nom de dossier `remediation/<...>`.
# Seule divergence : le dossier source `TleD` correspond à la valeur
# `NiveauTest` `tleD` (minuscule) — à normaliser explicitement plutôt que de
# la découvrir en prod.
_NIVEAU_TEST_VERS_DOSSIER = {
    "6eme": "6eme", "5eme": "5eme", "4eme": "4eme", "3eme": "3eme",
    "2ndeC": "2ndeC", "1ereD": "1ereD", "tleD": "TleD",
}

_MAX_ERREURS_INJECTEES = 2


class RemediationChunk:
    """Une leçon de remédiation, prête à être injectée dans un prompt."""

    def __init__(self, lecon: dict, module: dict) -> None:
        self.id: str = lecon["id"]
        self.niveau: str = module["niveau"]
        self.module: int = module["module"]
        self.module_titre: str = module["module_titre"]
        self.titre: str = lecon["titre"]
        self.retenir: list[str] = lecon.get("retenir") or []
        self.methode: dict | None = lecon.get("methode")
        self.exemple_resolu: str | None = lecon.get("exemple_resolu")
        self.erreurs_frequentes: list[dict] = lecon.get("erreurs_frequentes") or []
        self.declic: str | None = lecon.get("declic")
        #: Pool d'exercices du *module* (pas de la leçon seule — le YAML ne
        #: tague pas un exercice par leçon, voir docstring de tête) : numero,
        #: etoiles (1-3), enonce, correction. Réservé à `exercices_gradues()`.
        self._exercices_module: list[dict] = module.get("exercices") or []

    def exercices_gradues(self, repartition: dict[int, int]) -> list[dict]:
        """Sélectionne, dans le pool d'exercices du module, jusqu'à
        `repartition[etoiles]` exercices par niveau d'étoiles (1 à 3), triés
        par numéro. Rend moins que demandé si le pool n'en contient pas assez
        à un niveau donné — jamais d'erreur, jamais d'invention.

        Ne fait jamais le lien exercice → leçon précise : le YAML ne le porte
        pas (les exercices sont groupés par module, ~4 leçons). C'est la
        meilleure granularité disponible aujourd'hui — voir D-CEO-41."""
        par_etoile: dict[int, list[dict]] = {}
        for exercice in sorted(self._exercices_module, key=lambda e: e["numero"]):
            par_etoile.setdefault(exercice["etoiles"], []).append(exercice)

        selection: list[dict] = []
        for etoiles in sorted(repartition):
            selection.extend(par_etoile.get(etoiles, [])[: repartition[etoiles]])
        return selection

    def to_context_text(self) -> str:
        lignes = [
            f"Repère de remédiation ({self.niveau}, module « {self.module_titre} », "
            f"leçon « {self.titre} ») — matière de référence, pas un énoncé à recopier :"
        ]
        if self.retenir:
            lignes.append("- Ce qu'il faut retenir : " + " ".join(self.retenir))
        if self.methode and self.methode.get("etapes"):
            lignes.append(
                f"- Méthode ({self.methode.get('titre', '')}) : "
                + " ".join(self.methode["etapes"])
            )
        if self.exemple_resolu:
            lignes.append(
                "- Exemple travaillé, gabarit de difficulté uniquement (ne jamais le "
                f"recopier) : {self.exemple_resolu}"
            )
        for erreur in self.erreurs_frequentes[:_MAX_ERREURS_INJECTEES]:
            lignes.append(
                f"- Erreur fréquente à ce niveau : {erreur['erreur']} "
                f"→ correction attendue : {erreur['correction']}"
            )
        if self.declic:
            lignes.append(f"- Point de blocage habituel : {self.declic}")
        return "\n".join(lignes)


class RemediationRetriever:
    def __init__(self) -> None:
        self._lecons_par_id: dict[str, tuple[dict, dict]] = {}
        self._carte: dict[str, dict[str, dict]] = {}
        self._charger()

    def _charger(self) -> None:
        for dossier in set(_NIVEAU_TEST_VERS_DOSSIER.values()):
            fichier = _KB_DIR / f"remediation_{dossier}.yaml"
            if not fichier.exists():
                logger.warning("RemediationRetriever : %s introuvable", fichier)
                continue
            modules = yaml.safe_load(fichier.read_text(encoding="utf-8")) or []
            for module in modules:
                for lecon in module["lecons"]:
                    self._lecons_par_id[lecon["id"]] = (lecon, module)

        fichier_carte = _KB_DIR / "remediation_competences_map.yaml"
        if fichier_carte.exists():
            self._carte = yaml.safe_load(fichier_carte.read_text(encoding="utf-8")) or {}
        else:
            logger.warning(
                "RemediationRetriever : %s introuvable — "
                "lancer `manage.py rapprocher_remediation`.", fichier_carte
            )

    def get_by_competence(self, code: str, niveau: str) -> RemediationChunk | None:
        """`niveau` est une valeur `NiveauTest` (ex. `2ndeC`, `tleD`).

        Cherche d'abord dans le livret du niveau demandé. Sans correspondance
        — carte incomplète, ou compétence hors couverture actuelle du
        rapprochement — retourne `None` sans jamais lever d'exception, comme
        `contexte_diagnostic()` retourne `""` : un ancrage absent doit
        dégrader la qualité du prompt, jamais faire échouer la génération.
        """
        entree = self._carte.get(niveau, {}).get(code)
        if not entree:
            return None
        paire = self._lecons_par_id.get(entree["lecon_id"])
        if not paire:
            logger.warning(
                "RemediationRetriever : lecon_id '%s' absent des YAML chargés "
                "(carte désynchronisée — relancer generer_remediation_yaml.py "
                "puis rapprocher_remediation).", entree["lecon_id"],
            )
            return None
        lecon, module = paire
        return RemediationChunk(lecon, module)


# Singleton — chargement unique par processus. Plusieurs points d'appel
# (contexte.py, correction_web/taches.py, suivi/generation.py) partagent le
# même retriever plutôt que de recharger ~2 Mo de YAML par requête.
_retriever: RemediationRetriever | None = None


def get_remediation_retriever() -> RemediationRetriever:
    global _retriever
    if _retriever is None:
        _retriever = RemediationRetriever()
    return _retriever
