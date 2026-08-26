"""API FastAPI — seule interface depuis le retrait de Django (D-CEO-42/43,
`docs/decision_register.md`). `DATABASE_URL` pointe vers une base de dev en
local (ou `sqlite:///:memory:` par défaut) ; en production, vers Neon —
la bascule (`alembic stamp head` contre Neon) reste à faire par vous, voir
`backend/docs/bascule_neon.md` et `docs/deploiement_vps_hetzner.md`.
"""
from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from starlette.types import Scope

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

# `backend/app/main.py` -> parents[2] = racine du dépôt (voir app/__init__.py,
# même calcul). Le serveur applicatif (Docker sur le VPS Hetzner partagé,
# docs/deploiement_vps_hetzner.md) sert l'API et le frontend buildé depuis un
# seul processus/port — un seul bloc Caddy par app sur ce serveur, pas deux.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"


def _configurer_logging() -> None:
    """Persiste les `logger.warning`/`logger.error` déjà écrits dans le
    pipeline (diagnostic IA, modules 4/5 best-effort) — jusqu'ici, ils ne
    vivaient que dans le terminal d'`uvicorn` et disparaissaient au premier
    redémarrage. `logs/` existe déjà mais ne contenait que des fichiers
    Django obsolètes (dernier retrait 2026-08-21) : aucun handler fichier
    n'était branché côté FastAPI."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    racine = logging.getLogger()
    racine.addHandler(handler)
    racine.setLevel(logging.INFO)


_configurer_logging()


class _SPAStaticFiles(StaticFiles):
    """`StaticFiles` qui retombe sur `index.html` pour toute route inconnue
    (react-router prend le relais côté client) — équivalent de `try_files
    $uri $uri/ /index.html` chez nginx, nécessaire ici car `html=True` seul
    ne sert `index.html` que pour un répertoire, pas pour une route SPA
    arbitraire (ex. `/profil/HAK-123` rechargée directement)."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return FileResponse(Path(self.directory) / "index.html")


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


# Monté en dernier : les routes `/api/*` ci-dessus sont enregistrées avant et
# priment. Absent en développement tant que `npm run build` n'a pas tourné
# (le frontend sert alors via `npm run dev` + le proxy Vite, pas ce mount) —
# obligatoire en production, où l'image Docker construit toujours le
# frontend (voir backend/Dockerfile).
if _FRONTEND_DIST.is_dir():
    app.mount("/", _SPAStaticFiles(directory=_FRONTEND_DIST), name="frontend")
