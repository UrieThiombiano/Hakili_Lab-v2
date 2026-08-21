#!/bin/sh
# Point d'entrée du conteneur — équivalent du `release:` + `web:` du Procfile
# (Render/Railway) pour un déploiement Docker sur VPS Hetzner.
#
# Ne fait PAS `migrate suivi 0007 --fake` (étape manuelle, une seule fois,
# uniquement si la base Neon vient d'un ancien déploiement Alembic — voir
# docs/deploiement.md, "Une étape manuelle"). L'exécuter à la main via
# `docker exec` avant le tout premier démarrage sur une base existante.
#
# Une commande passée après le nom de l'image (`docker run image <cmd>`)
# est exécutée telle quelle au lieu du démarrage normal — sans ça, un
# `docker run --rm image python -c "..."` finirait par lancer gunicorn
# quand même, en ignorant silencieusement la commande demandée.
set -e

if [ "$#" -eq 0 ]; then
    python manage.py migrate --noinput

    exec gunicorn hakili.wsgi:application \
        --bind "0.0.0.0:${PORT:-8010}" \
        --workers 2 \
        --threads 4 \
        --timeout 180 \
        --access-logfile - \
        --error-logfile -
else
    exec "$@"
fi
