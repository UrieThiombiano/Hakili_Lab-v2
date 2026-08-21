"""Squelette FastAPI — Phase 0 du plan de migration
(`C:\\Users\\Urie\\.claude\\plans\\majestic-nibbling-anchor.md`).

Ne touche ni à la base Neon de production ni au code Django, qui continue de
tourner sans interruption : `DATABASE_URL` pointe ici vers une base de dev
(ou `sqlite:///:memory:` par défaut). Voir ce fichier pour la suite prévue
(Phase 1 : le reste des routeurs, un par écran déjà inventorié).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.csrf import CSRFMiddleware
from app.db import SessionLocal, engine
from app.depot import DepotFastAPI
from app.models import Base
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import corrections as corrections_router
from app.routers import eleves as eleves_router
from app.routers import sessions as sessions_router
from app.security import SecuriteProductionMiddleware
from src.core.config import settings
from src.pipeline.depot import installer_depot


@asynccontextmanager
async def lifespan(app: FastAPI):
    # `create_all` est un confort de dev (base sqlite/postgres de dev vide) —
    # Alembic prend le relais dès qu'un schéma existe déjà (voir alembic/).
    Base.metadata.create_all(engine)
    installer_depot(DepotFastAPI(SessionLocal))
    yield


app = FastAPI(title="Hakili Lab API", lifespan=lifespan)
# Ordre délibéré : la sécurité production (redirection HTTPS/HSTS) avant le
# CSRF — une requête http en clair ne doit jamais atteindre la vérification
# CSRF, elle doit être redirigée avant. ASGI applique les middlewares dans
# l'ordre inverse de leur ajout (le dernier ajouté est le plus externe), donc
# `SecuriteProductionMiddleware` est ajouté en dernier.
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecuriteProductionMiddleware, actif=not settings.debug)
app.include_router(auth_router.router)
app.include_router(eleves_router.router)
app.include_router(sessions_router.router)
app.include_router(corrections_router.router)
app.include_router(admin_router.router)


@app.get("/api/sante")
def sante() -> dict:
    return {"ok": True}
