#!/bin/bash
# Mise à jour du déploiement — équivalent du release:+redémarrage web: d'un
# PaaS géré. À exécuter en root sur le VPS (fait les étapes privilégiées :
# redémarrage du service, pas de sudo requis pour le reste).
#
# Usage : bash deploy.sh [branche]     (défaut : main)
set -euo pipefail

BRANCHE="${1:-main}"
REPO=/opt/hakili/Hakili_Lab

echo "== Code (branche $BRANCHE) =="
su - hakili -c "cd $REPO && git fetch origin && git checkout $BRANCHE && git pull origin $BRANCHE"

echo "== Dépendances backend =="
su - hakili -c "cd $REPO && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"

echo "== Migrations (Alembic — sans effet si déjà à jour) =="
su - hakili -c "cd $REPO && .venv/bin/alembic -c backend/alembic.ini upgrade head"

echo "== Build frontend =="
su - hakili -c "cd $REPO/frontend && npm ci && npm run build"

echo "== Redémarrage du service =="
systemctl restart hakili
systemctl status hakili --no-pager

echo "== Vérification nginx =="
# nginx sert frontend/dist directement depuis le disque, aucun reload requis
# pour un nouveau build — seulement si deploy/nginx_hakili.conf a changé.
nginx -t

echo "== Fait =="
