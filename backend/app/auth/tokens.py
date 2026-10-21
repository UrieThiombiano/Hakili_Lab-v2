"""Jetons opaques signés — élève/copie/session jamais en clair dans une URL
(D-CEO-25). Même mécanisme générique réutilisé pour les trois entités.

`SECRET_KEY` (`src/core/config.py::settings.secret_key`) est OBLIGATOIRE hors
DEBUG — l'application refuse de signer un jeton plutôt que de tourner avec la
clé de repli de développement, publique dans ce dépôt. En DEBUG, la clé de
repli suffit : forcer une vraie clé en développement local casserait
`DEBUG=true` sans bénéfice, personne d'autre n'accède à cette instance.
"""
from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer

from src.core.config import settings

_SECRET_DEV = "dev-uniquement-ne-jamais-utiliser-en-production"
_SEL = "hakili.eleve"


def _secret() -> str:
    if settings.secret_key:
        return settings.secret_key
    if settings.debug:
        return _SECRET_DEV
    raise RuntimeError(
        "SECRET_KEY manquante hors DEBUG — voir .env.example. "
        "Générer une clé : python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )


_serializer = URLSafeSerializer(_secret(), salt=_SEL)


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
