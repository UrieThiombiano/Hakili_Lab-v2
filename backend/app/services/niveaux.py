"""Port intégral de `referentiel/niveaux.py` — copié plutôt qu'importé
depuis `referentiel.niveaux` : ce module ne dépend d'aucun framework en lui-
même, mais il vit dans un package Django (`referentiel/`) dont l'import
déclenche l'app registry. Contenu inchangé — voir le fichier d'origine."""
from __future__ import annotations

ORDRE_NIVEAUX: dict[str, int] = {
    "Primaire": 0,
    "6eme": 1,
    "5eme": 2,
    "4eme": 3,
    "3eme": 4,
    "2ndeC": 5,
    "1ereD": 6,
    "tleD": 7,
}


def deja_enseigne(niveau_intro: str, niveau_test: str) -> bool:
    rang_intro = ORDRE_NIVEAUX.get(niveau_intro)
    rang_test = ORDRE_NIVEAUX.get(niveau_test)
    if rang_intro is None or rang_test is None:
        return False
    return rang_intro < rang_test
