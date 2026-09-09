# Hakili Lab — image Docker de l'app complète (API FastAPI + frontend React
# buildé, servis par un seul processus). FastAPI est la seule interface depuis
# le retrait de Django (D-CEO-42/43, voir docs/decision_register.md).
#
# Tout le déploiement est regroupé dans ce dossier `deploy/` — voir
# `deploy/README.md` (livraison), `deploy/bascule_neon.md` (base Neon),
# `deploy/deploy.sh` (script de mise à jour), `deploy/caddy_snippet.txt`.
#
# Cible réelle : le VPS Hetzner PARTAGÉ (167.233.234.219, plusieurs apps déjà
# en service). Docker + Caddy y sont déjà en place ; chaque app est UN
# conteneur sur UN port interne, un bloc Caddy par app fait le reverse proxy
# + HTTPS. D'où le choix : un seul conteneur sert l'API **et** le frontend
# buildé (`fastapi.staticfiles`, voir `backend/app/main.py`) plutôt que deux
# conteneurs + nginx — un seul port à demander à l'administrateur, un seul
# bloc Caddy à ajouter au Caddyfile partagé.
#
# ── Build ────────────────────────────────────────────────────────────────────
# Contexte de build = LA RACINE DU DÉPÔT, pas `deploy/`. `frontend/dist/` doit
# exister AVANT ce build (`deploy/deploy.sh` le fait) — pas de stage Node ici :
# `npm run build` tourne sur l'hôte, Docker ne fait que copier le résultat.
# Choix délibéré : un stage Node dans ce Dockerfile s'est montré peu fiable en
# local (npm plante en root sous certaines configs Docker Desktop/WSL2).
#
#   cd frontend && npm ci && npm run build && cd ..
#   docker build -f deploy/Dockerfile -t hakili .
#
# `.dockerignore` reste à la racine du dépôt (emplacement lu par Docker pour
# le contexte de build) — il exclut .venv/, node_modules/, .git/, les bases
# locales, les secrets et les données d'élèves.
#
# Principes : utilisateur non-root, secrets montés en volume jamais copiés
# dans l'image, port interne (8011, libre au 2026-08-22) derrière Caddy —
# jamais exposé directement à Internet.

FROM python:3.12-slim

RUN useradd -m -u 1000 hakili
USER hakili
ENV PATH="/home/hakili/.local/bin:$PATH"

WORKDIR /app

COPY --chown=hakili requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# `src/`, `prompts/`, `data/` (référentiel/connaissance packagée, pas les
# données de copies/élèves — exclues par .dockerignore) et `backend/` : le
# strict nécessaire à l'exécution de l'API.
COPY --chown=hakili src/ /app/src/
COPY --chown=hakili prompts/ /app/prompts/
COPY --chown=hakili data/ /app/data/
COPY --chown=hakili backend/ /app/backend/

# Point d'entrée du conteneur (regroupé dans deploy/ avec le reste).
COPY --chown=hakili deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Frontend buildé sur l'hôte avant ce `docker build` (voir en-tête) — servi
# par `app/main.py` (StaticFiles, fallback SPA sur index.html) à la racine,
# à côté des routes `/api/*`.
COPY --chown=hakili frontend/dist /app/frontend/dist

# runs/ (fiches PDF générées) et credentials/ (compte de service Google,
# monté en volume au démarrage, jamais copié dans l'image — voir
# .dockerignore) : répertoires que l'app doit pouvoir écrire.
RUN mkdir -p runs credentials logs

ENV PORT=8011
EXPOSE 8011

ENTRYPOINT ["./entrypoint.sh"]
