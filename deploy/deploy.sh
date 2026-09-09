#!/bin/bash
# Déploiement / mise à jour de Hakili Lab sur le VPS Hetzner PARTAGÉ
# (167.233.234.219 — Docker + Caddy déjà en place pour plusieurs apps, voir
# deploy/README.md). Aucun provisionnement : une app de plus dans le Docker
# déjà présent, un conteneur, un port interne, un bloc Caddy.
#
# Usage, depuis le dossier du clone (ex. ~/hakili-lab) :
#   bash deploy/deploy.sh [branche]        (défaut : fastapi-react)
#
# Pré-requis, une seule fois (voir deploy/README.md, étape 1) :
#   - dossier = clone du dépôt, `.env` rempli (cp .env.example .env, SECRET_KEY
#     générée, DEBUG=false), `credentials/service_account.json` déposé par scp
#   - node/npm disponibles sur l'hôte (build du frontend hors conteneur)
#   - schéma Neon adopté par Alembic une fois (deploy/bascule_neon.md)

set -euo pipefail

BRANCHE="${1:-fastapi-react}"
PORT="${HAKILI_PORT:-8011}"          # port interne, doit rester libre sur le VPS
CONTENEUR="hakili"
IMAGE="hakili:latest"

cd "$(git rev-parse --show-toplevel)"

echo "== 1/5  Code (branche $BRANCHE) =="
git fetch origin
git checkout "$BRANCHE"
git pull --ff-only origin "$BRANCHE"

echo "== 2/5  Build du frontend (npm, hors Docker — voir deploy/Dockerfile) =="
( cd frontend && npm ci && npm run build )

echo "== 3/5  Build de l'image Docker =="
docker build -f deploy/Dockerfile -t "$IMAGE" .

echo "== 4/5  Redémarrage du conteneur =="
docker stop "$CONTENEUR" 2>/dev/null || true
docker rm   "$CONTENEUR" 2>/dev/null || true
docker run -d \
    --name "$CONTENEUR" \
    --env-file .env \
    -p "127.0.0.1:${PORT}:8011" \
    -v "$(pwd)/credentials:/app/credentials:ro" \
    -v "$(pwd)/runs:/app/runs" \
    -v "$(pwd)/logs:/app/logs" \
    --restart unless-stopped \
    "$IMAGE"

echo "== 5/5  Vérification santé =="
for i in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:${PORT}/api/sante" >/dev/null; then
        echo "  API en ligne sur 127.0.0.1:${PORT} — OK"
        echo "== Fait =="
        echo "Premier déploiement seulement : ajouter le bloc Caddy"
        echo "(deploy/caddy_snippet.txt) au Caddyfile partagé, puis"
        echo "  sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy"
        exit 0
    fi
    sleep 2
done

echo "  ÉCHEC : l'API ne répond pas. Journaux :" >&2
docker logs "$CONTENEUR" --tail 40 >&2
exit 1
