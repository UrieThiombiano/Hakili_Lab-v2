# Hakili Lab — image Docker du backend FastAPI (D-CEO-42/43, seule interface
# depuis le retrait de Django — voir docs/decision_register.md et
# backend/docs/bascule_neon.md).
#
# ⚠️ Livrable de préparation, pas encore déployé : ce fichier n'a jamais été
# construit ni poussé contre un registre ni exécuté en production. Chemin de
# déploiement retenu pour le VPS Hetzner : systemd + nginx natifs, sans
# conteneur — voir docs/deploiement_vps_hetzner.md et deploy/. Cette image
# reste une alternative disponible (registre, autre hébergeur), pas le
# chemin documenté pas à pas.
#
# ⚠️ Contexte de build = LA RACINE DU DÉPÔT, pas `backend/` : `backend/app`
# importe `src/` par chemin relatif au dépôt (bootstrap dans
# `backend/app/__init__.py`). Construire avec :
#   docker build -f backend/Dockerfile -t hakili-backend .
#
# Principes : utilisateur non-root, secrets montés en volume jamais copiés
# dans l'image, port interne (8011) derrière un reverse proxy — jamais
# exposé directement.

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

# runs/ (fiches PDF générées) et credentials/ (compte de service Google,
# monté en volume au démarrage, jamais copié dans l'image — voir
# .dockerignore) : répertoires que l'app doit pouvoir écrire.
RUN mkdir -p runs credentials

ENV PORT=8011
EXPOSE 8011

ENTRYPOINT ["./backend/entrypoint.sh"]
