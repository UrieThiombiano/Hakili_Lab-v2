# Hakili Lab — image Docker de l'app complète (D-CEO-42/43, seule interface
# depuis le retrait de Django — voir docs/decision_register.md et
# backend/docs/bascule_neon.md).
#
# Cible réelle : le VPS Hetzner PARTAGÉ (167.233.234.219, plusieurs apps déjà
# en service — voir docs/deploiement_vps_hetzner.md). Docker + Caddy y sont
# déjà en place pour toutes les apps ; chaque app est UN conteneur sur UN
# port interne, un bloc Caddy par app fait le reverse proxy + HTTPS. D'où le
# choix ci-dessous : un seul conteneur sert l'API **et** le frontend buildé
# (`fastapi.staticfiles`, voir `backend/app/main.py`) plutôt que deux
# conteneurs + nginx — un seul port à demander à l'administrateur du
# serveur, un seul bloc Caddy à ajouter au Caddyfile partagé.
#
# Contexte de build = LA RACINE DU DÉPÔT, pas `backend/`. `frontend/dist/`
# doit exister AVANT ce build (`deploy/deploy.sh` le fait) — pas de stage
# Node ici : `npm run build` tourne sur l'hôte, Docker ne fait que copier le
# résultat. Choix délibéré, pas une simplification de confort : un stage
# Node dans ce Dockerfile s'est montré peu fiable en local (npm plante en
# root sous certaines configurations Docker Desktop/WSL2, indépendamment du
# Dockerfile) — construire hors conteneur évite la dépendance à ce
# comportement, aussi bien en local que sur le VPS.
#   cd frontend && npm ci && npm run build && cd ..
#   docker build -f backend/Dockerfile -t hakili .
#
# Principes : utilisateur non-root, secrets montés en volume jamais copiés
# dans l'image, port interne (8011, libre sur ce serveur au 2026-08-22)
# derrière Caddy — jamais exposé directement à Internet.

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
RUN chmod +x backend/entrypoint.sh

# Frontend buildé sur l'hôte avant ce `docker build` (voir en-tête) — servi
# par `app/main.py` (StaticFiles, fallback SPA sur index.html) à la racine,
# à côté des routes `/api/*`.
COPY --chown=hakili frontend/dist /app/frontend/dist

# runs/ (fiches PDF générées) et credentials/ (compte de service Google,
# monté en volume au démarrage, jamais copié dans l'image — voir
# .dockerignore) : répertoires que l'app doit pouvoir écrire.
RUN mkdir -p runs credentials

ENV PORT=8011
EXPOSE 8011

ENTRYPOINT ["./backend/entrypoint.sh"]
