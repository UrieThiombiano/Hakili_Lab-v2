#!/bin/sh
# Point d'entrée du conteneur FastAPI (deploy/Dockerfile). Contexte de build à
# la racine du dépôt : `backend/app` importe `src/` par chemin relatif au
# dépôt (`app/__init__.py`), et les chemins ci-dessous sont relatifs à /app.
#
# Ne fait PAS `alembic stamp head` — étape manuelle, une seule fois, décrite
# dans deploy/bascule_neon.md, à exécuter par vous avant le tout premier
# démarrage contre la base Neon existante.
#
# Une commande passée après le nom de l'image (`docker run image <cmd>`) est
# exécutée telle quelle au lieu du démarrage normal, pour éviter qu'une
# commande de debug ne finisse par lancer le serveur quand même.
set -e

if [ "$#" -eq 0 ]; then
    alembic -c backend/alembic.ini upgrade head

    exec uvicorn app.main:app \
        --app-dir backend \
        --host "0.0.0.0" \
        --port "${PORT:-8011}" \
        --workers 2
else
    exec "$@"
fi
