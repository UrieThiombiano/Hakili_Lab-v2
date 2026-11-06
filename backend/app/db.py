"""Moteur SQLAlchemy — synchrone (voir la Phase 0 du plan de migration : pas
d'async/await tant que `src/pipeline/` et les clients LLM restent bloquants).

Réutilise `src/core/config.py::settings.database_url` sans le dupliquer —
même variable d'environnement que Django (`DATABASE_URL`), déjà écrite dans
une convention compatible SQLAlchemy (`sqlite:///:memory:`, `postgresql://...
?sslmode=require`) : Django l'a toujours été, un `_config_base` maison la
retraduit pour Django, mais SQLAlchemy la consomme directement.
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as SQLASession
from sqlalchemy.orm import sessionmaker

# Le bootstrap du path vers `src/` vit dans `app/__init__.py` (exécuté avant
# tout sous-module de `app`, donc garanti ici quel que soit l'ordre d'import).
from src.core.config import settings


def _url() -> str:
    return settings.database_url or "sqlite:///:memory:"


def _make_engine() -> Engine:
    url = _url()
    kwargs: dict = {}
    if url.startswith("postgresql"):
        # Neon met la base en veille : mêmes réglages que Django
        # (`CONN_HEALTH_CHECKS`/`CONN_MAX_AGE=300`, D-CEO-19) pour tolérer un
        # réveil de connexion sans exposer l'erreur à l'appelant.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 300
    if url.startswith("sqlite"):
        # Une base en mémoire par défaut n'existe que le temps d'une
        # connexion : StaticPool garde la même connexion ouverte pour toute
        # la durée du process (utile en test, jamais en production Postgres).
        from sqlalchemy.pool import StaticPool

        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


engine: Engine = _make_engine()
SessionLocal: sessionmaker[SQLASession] = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[SQLASession]:
    """Dépendance FastAPI : une session par requête, fermée systématiquement."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
