#!/bin/bash
# Provisionnement initial d'un VPS Hetzner neuf (Ubuntu 22.04/24.04), en root.
# Une seule fois par serveur. Reconstruit l'équivalent FastAPI + React de
# l'ancien `deploy/provision_serveur.sh` (Django, supprimé en D-CEO-42/43) :
# Python 3.12, Node.js (build du frontend), nginx, certbot, git, utilisateur
# système `hakili`, pare-feu UFW.
#
# Usage : scp ce fichier sur le VPS puis `bash provision_serveur.sh`.
set -euo pipefail

echo "== Paquets système =="
apt-get update
apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl ufw

echo "== Node.js 22 LTS (build du frontend) =="
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi

echo "== Utilisateur système hakili (pas de connexion SSH directe : aucune clé déposée pour lui, accès uniquement via 'su - hakili' depuis root) =="
if ! id hakili >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash hakili
fi
mkdir -p /opt/hakili
chown hakili:hakili /opt/hakili

echo "== Pare-feu UFW (SSH + HTTP/HTTPS uniquement) =="
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "== Fait =="
echo "Suite : su - hakili, puis suivre docs/deploiement_vps_hetzner.md (Étape 2)."
