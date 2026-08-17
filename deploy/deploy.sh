#!/usr/bin/env bash
# Script de mise à jour — Hakili Lab sur VPS Hetzner.
#
# À exécuter à chaque nouvelle version, en root (il bascule lui-même sur
# l'utilisateur applicatif pour les étapes qui n'en ont pas besoin) :
#   ssh root@VOTRE_IP
#   bash /opt/hakili/Hakili_Lab/deploy/deploy.sh
#
# Équivalent du `release:` + `web:` du Procfile (Render/Railway), mais fait à
# la main puisqu'un VPS n'a pas de mécanisme de déploiement intégré.

set -euo pipefail

APP_USER="hakili"
APP_DIR="/opt/hakili/Hakili_Lab"
SERVICE_NAME="hakili"
BRANCH="${1:-main}"

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être exécuté en root (sudo)." >&2
    exit 1
fi

run_as_app() {
    sudo -u "${APP_USER}" -H bash -c "cd '${APP_DIR}' && $1"
}

echo "==> git pull (branche ${BRANCH})"
run_as_app "git fetch origin && git checkout ${BRANCH} && git pull origin ${BRANCH}"

echo "==> Installation des dépendances"
run_as_app ".venv/bin/pip install --upgrade pip"
run_as_app ".venv/bin/pip install -r requirements.txt"

echo "==> collectstatic"
run_as_app ".venv/bin/python manage.py collectstatic --noinput"

echo "==> migrate"
run_as_app ".venv/bin/python manage.py migrate --noinput"

echo "==> Redémarrage du service ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl --no-pager --lines=15 status "${SERVICE_NAME}"

echo ""
echo "==> Déploiement terminé."
