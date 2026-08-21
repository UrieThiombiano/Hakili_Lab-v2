#!/bin/sh
# Point d'entrée du conteneur FastAPI — mirroir de `entrypoint.sh` (racine,
# Django) pour le nouveau backend (D-CEO-42). Construit avec le contexte de
# build à la racine du dépôt (voir backend/Dockerfile) : `backend/app`
# importe `src/` par chemin relatif au dépôt (`app/__init__.py`).
#
# Ne fait PAS `alembic stamp head` — étape manuelle, une seule fois, décrite
# dans backend/docs/bascule_neon.md, à exécuter par vous avant le tout
# premier démarrage contre la base Neon existante.
#
# Une commande passée après le nom de l'image (`docker run image <cmd>`)
# est exécutée telle quelle au lieu du démarrage normal — même garde que
# l'entrypoint Django, pour la même raison (éviter qu'une commande de debug
# ne finisse par lancer le serveur quand même).
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
