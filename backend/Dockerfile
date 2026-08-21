# Hakili Lab — image Docker du backend FastAPI (D-CEO-42, chantier de
# bascule vers FastAPI + React — voir docs/decision_register.md D-CEO-42 et
# backend/docs/bascule_neon.md).
#
# ⚠️ Livrable de préparation, pas encore déployé : ce fichier n'a jamais été
# construit ni poussé contre un registre ni exécuté sur le VPS Hetzner. La
# bascule reste une décision et une action de l'utilisateur.
#
# ⚠️ Contexte de build = LA RACINE DU DÉPÔT, pas `backend/` : `backend/app`
# importe `src/` par chemin relatif au dépôt (bootstrap dans
# `backend/app/__init__.py`), à l'identique de ce que fait Django avec le
# même `src/`. Construire avec :
#   docker build -f backend/Dockerfile -t hakili-backend .
#
# Mirroir volontaire du `Dockerfile` racine (Django) : mêmes principes
# (utilisateur non-root, secrets montés en volume jamais copiés dans
# l'image, port interne derrière un reverse proxy) — uvicorn à la place de
# gunicorn+wsgi, `PORT` par défaut différent (8011) pour pouvoir tourner
# à côté de l'instance Django (8010) le temps de la bascule.

FROM python:3.12-slim

RUN useradd -m -u 1000 hakili
USER hakili
ENV PATH="/home/hakili/.local/bin:$PATH"

WORKDIR /app

COPY --chown=hakili requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# `src/`, `prompts/`, `data/` (référentiel/connaissance packagée, pas les
# données de copies/élèves — exclues par .dockerignore) et `backend/` : le
# strict nécessaire à l'exécution de l'API, pas tout le dépôt Django.
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
