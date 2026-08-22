#!/bin/bash
# Déploiement/mise à jour sur le VPS Hetzner PARTAGÉ (167.233.234.219,
# plusieurs apps déjà en service — Docker + Caddy déjà en place pour toutes,
# voir docs/deploiement_vps_hetzner.md). Pas de provisionnement ici : rien
# à installer sur le serveur, une seule app de plus dans le Docker déjà là.
#
# Usage, depuis ~/hakili-lab (ou le dossier choisi au premier clonage) :
#   bash deploy/deploy.sh [branche]     (défaut : fastapi-react)
#
# Première exécution : le dossier doit déjà être un clone du dépôt, avec un
# `.env` rempli (copié depuis .env.example, SECRET_KEY générée) et
# `credentials/` déposé (scp depuis votre poste, jamais versionné). Voir
# docs/deploiement_vps_hetzner.md Étape 2.
set -euo pipefail

BRANCHE="${1:-fastapi-react}"
PORT="${HAKILI_PORT:-8011}"
CONTENEUR="hakili"

echo "== Code (branche $BRANCHE) =="
git fetch origin
git checkout "$BRANCHE"
git pull origin "$BRANCHE"

echo "== Build frontend (npm, hors Docker — voir en-tête de backend/Dockerfile) =="
(cd frontend && npm ci && npm run build)

echo "== Build image Docker =="
docker build -f backend/Dockerfile -t hakili:latest .

echo "== Redémarrage du conteneur =="
docker stop "$CONTENEUR" 2>/dev/null || true
docker rm "$CONTENEUR" 2>/dev/null || true
docker run -d \
    --name "$CONTENEUR" \
    --env-file .env \
    -p "127.0.0.1:${PORT}:8011" \
    -v "$(pwd)/credentials:/app/credentials:ro" \
    -v "$(pwd)/runs:/app/runs" \
    --restart unless-stopped \
    hakili:latest

echo "== Vérification =="
sleep 5
docker logs "$CONTENEUR" --tail 20
curl -sf "http://127.0.0.1:${PORT}/api/sante" && echo " -- OK" || echo "ÉCHEC : voir 'docker logs $CONTENEUR'"

echo "== Fait =="
echo "Premier déploiement seulement : ajouter le bloc Caddy (deploy/caddy_snippet.txt)"
echo "au Caddyfile partagé si ce n'est pas déjà fait, puis 'sudo systemctl reload caddy'."
