#!/usr/bin/env bash
# Provisionnement initial d'un VPS Hetzner neuf (Ubuntu 22.04/24.04) — Hakili Lab.
#
# À exécuter UNE SEULE FOIS, en root, sur le serveur neuf :
#   scp deploy/provision_serveur.sh root@VOTRE_IP:/root/
#   ssh root@VOTRE_IP
#   bash provision_serveur.sh
#
# Ce script installe les paquets système, crée l'utilisateur applicatif et le
# pare-feu. Il NE clone PAS le dépôt et NE configure PAS .env ni les clés
# Google : ces étapes touchent des secrets, elles restent manuelles
# (voir docs/deploiement_vps_hetzner.md).

set -euo pipefail

APP_USER="hakili"
APP_DIR="/opt/hakili"

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être exécuté en root (sudo)." >&2
    exit 1
fi

echo "==> Mise à jour du système"
apt-get update
apt-get upgrade -y

echo "==> Installation des paquets (Python 3.12, nginx, certbot, git, pare-feu)"
apt-get install -y \
    software-properties-common \
    git \
    curl \
    nginx \
    ufw \
    certbot \
    python3-certbot-nginx

# Python 3.12 (requis par .python-version) — présent nativement sur Ubuntu
# 24.04 ; ajout du PPA deadsnakes sinon (ex. Ubuntu 22.04).
if ! command -v python3.12 >/dev/null 2>&1; then
    echo "==> Python 3.12 absent, ajout du PPA deadsnakes"
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    apt-get install -y python3.12 python3.12-venv
else
    apt-get install -y python3.12-venv
fi

echo "==> Création de l'utilisateur applicatif ${APP_USER} (sans shell de connexion)"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
else
    echo "    ${APP_USER} existe déjà, ignoré."
fi

mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Pare-feu (UFW) : SSH + HTTP/HTTPS uniquement"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo ""
echo "==> Provisionnement terminé."
echo ""
echo "Prochaines étapes (voir docs/deploiement_vps_hetzner.md) :"
echo "  1. su - ${APP_USER}"
echo "     git clone <url-du-depot> ${APP_DIR}/Hakili_Lab"
echo "  2. cd ${APP_DIR}/Hakili_Lab && python3.12 -m venv .venv"
echo "     .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"
echo "  3. cp .env.example .env  # puis remplir les valeurs (jamais commité)"
echo "     chmod 600 .env"
echo "  4. Déposer credentials/service_account.json (compte de service Google), chmod 600"
echo "  5. .venv/bin/python manage.py collectstatic --noinput"
echo "     .venv/bin/python manage.py migrate --noinput"
echo "  6. exit  # retour en root"
echo "     cp deploy/hakili.service /etc/systemd/system/hakili.service"
echo "     systemctl daemon-reload && systemctl enable --now hakili"
echo "  7. cp deploy/nginx_hakili.conf /etc/nginx/sites-available/hakili"
echo "     # éditer VOTRE_DOMAINE.example dans ce fichier"
echo "     ln -s /etc/nginx/sites-available/hakili /etc/nginx/sites-enabled/hakili"
echo "     nginx -t && systemctl reload nginx"
echo "  8. certbot --nginx -d VOTRE_DOMAINE.example"
