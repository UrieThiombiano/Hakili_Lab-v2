"""Store de session côté serveur — remplace `django.contrib.sessions` (backend
base de données par défaut de Django : un cookie porte une clé opaque et
aléatoire, la donnée réelle vit en base). Django n'expose pas ce mécanisme via
un modèle applicatif — cette table est donc nouvelle, pas un port d'un modèle
Django existant, contrairement à `referentiel.py`/`suivi.py`.

Pourquoi une table plutôt qu'un JWT : la "casquette" (rôle actif d'une
personne à double rôle, `comptes/session.py::changer_casquette`) doit pouvoir
changer **sans reconnexion**. Un JWT signé côté client redeviendrait invalide
dès qu'on voudrait en changer le contenu ; il faudrait de toute façon un état
mutable côté serveur pour ça, donc autant garder le modèle Django au plus
près (voir le plan de migration, section « Auth »).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .suivi import JSONType


class AppSession(Base):
    """Une session ouverte. `id` est la clé opaque posée dans le cookie —
    aléatoire (`secrets.token_urlsafe`), jamais devinable, jamais elle-même
    porteuse de données (contrairement aux jetons d'URL de `app/auth/tokens.py`,
    qui eux encodent et signent une valeur)."""

    __tablename__ = "app_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    personne: Mapped[dict] = mapped_column(JSONType)
    casquette: Mapped[str] = mapped_column(String(30), default="", server_default="")
    expire_at: Mapped[datetime] = mapped_column(DateTime)
