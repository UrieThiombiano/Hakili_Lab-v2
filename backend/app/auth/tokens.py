"""Jetons opaques signés — remplace `django.core.signing` (utilisé côté
Django par `suivi_web/jetons.py`). Même sel, même absence d'expiration, même
raison de ne pas afficher `identifiant_hakili` en clair dans une URL
(D-CEO-25) : voir `suivi_web/jetons.py` pour la justification complète.

Réutilise `DJANGO_SECRET_KEY` — pas une nouvelle variable d'environnement —
pour que la clé qui protège les jetons Django et celle qui protège les
jetons FastAPI restent une seule et même chose à faire tourner en cas de
compromission, même après la bascule (Phase 4 du plan).
"""
from __future__ import annotations

import os

from itsdangerous import BadSignature, URLSafeSerializer

_SECRET = os.environ.get("DJANGO_SECRET_KEY", "dev-uniquement-ne-jamais-utiliser-en-production")
_SEL = "hakili.eleve"

_serializer = URLSafeSerializer(_SECRET, salt=_SEL)


def jeton(valeur: str) -> str:
    """Jeton opaque et signé désignant une entité (élève, copie, session —
    même mécanisme générique réutilisé pour les trois côté Django, voir
    `suivi_web/jetons.py`)."""
    return _serializer.dumps(valeur)


def valeur_depuis_jeton(jeton_recu: str) -> str | None:
    """Valeur d'origine, ou `None` si le jeton est absent, forgé ou altéré.
    Pas de date d'expiration, délibérément — un lien reste valable tant que
    l'entité existe ; l'autorisation est revérifiée à chaque requête."""
    try:
        return _serializer.loads(jeton_recu)
    except BadSignature:
        return None
