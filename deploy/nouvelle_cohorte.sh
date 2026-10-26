#!/usr/bin/env bash
# Changement de cohorte en prod : sauvegarde → purge des données d'élèves
# (base + runs/) → bascule GOOGLE_SHEET_ELEVES_ID → recréation du conteneur.
# Garde le référentiel, les fiches de remédiation et le personnel.
#
#   bash deploy/nouvelle_cohorte.sh <NOUVEL_ID_SHEET>               # simulation (compte seulement)
#   bash deploy/nouvelle_cohorte.sh <NOUVEL_ID_SHEET> --confirmer   # exécution réelle
#
# À lancer depuis ~/hakili-lab, conteneur `hakili` en marche. purge_eleves.py
# est passé sur stdin : pas besoin qu'il soit dans l'image.
# Sauvegarde dans ~/hakili-sauvegardes/.
set -euo pipefail

NOUVEL_ID="${1:?Usage : bash deploy/nouvelle_cohorte.sh <NOUVEL_ID_SHEET> [--confirmer]}"
CONFIRMER="${2:-}"
CONTENEUR=hakili
IMAGE=hakili:latest
PORT="${HAKILI_PORT:-8017}"
cd "$(dirname "$0")/.."

echo "== Données d'élèves actuellement en base =="
docker exec -i "$CONTENEUR" python - compter < deploy/purge_eleves.py
echo "  runs/ : $(ls runs | wc -l) entrée(s), $(du -sh runs | cut -f1)"
echo "  Sheet élèves actuel : $(grep '^GOOGLE_SHEET_ELEVES_ID=' .env | cut -d= -f2)"
echo "  Nouveau Sheet       : $NOUVEL_ID"

if [ "$CONFIRMER" != "--confirmer" ]; then
    echo "== Simulation : rien n'a été modifié. Relancer avec --confirmer pour exécuter. =="
    exit 0
fi

SAUV="$HOME/hakili-sauvegardes/cohorte-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$SAUV"
echo "== 1/4  Sauvegarde dans $SAUV =="
cp .env "$SAUV/env"
docker exec -i "$CONTENEUR" python - sauvegarder < deploy/purge_eleves.py | gzip > "$SAUV/donnees_eleves.json.gz"
gzip -t "$SAUV/donnees_eleves.json.gz"
tar czf "$SAUV/runs.tar.gz" runs
ls -lh "$SAUV"

echo "== 2/4  Purge de la base (une transaction) =="
docker exec -i "$CONTENEUR" python - purger < deploy/purge_eleves.py

echo "== 3/4  Purge de runs/ (dans le conteneur : fichiers appartenant à uid 1000) =="
docker exec "$CONTENEUR" sh -c 'cd /app/runs && rm -rf copie-* verif-* && find . -type f -delete'
echo "  runs/ : $(find runs -type f | wc -l) fichier(s) restant(s)"

echo "== 4/4  Bascule du Sheet et recréation du conteneur =="
sed -i "s/^GOOGLE_SHEET_ELEVES_ID=.*/GOOGLE_SHEET_ELEVES_ID=$NOUVEL_ID/" .env
grep '^GOOGLE_SHEET_ELEVES_ID=' .env
docker stop "$CONTENEUR" >/dev/null
docker rm "$CONTENEUR" >/dev/null
docker run -d \
    --name "$CONTENEUR" \
    --env-file .env \
    -p "127.0.0.1:${PORT}:8011" \
    -v "$(pwd)/credentials:/app/credentials:ro" \
    -v "$(pwd)/runs:/app/runs" \
    -v "$(pwd)/logs:/app/logs" \
    --restart unless-stopped \
    "$IMAGE" >/dev/null

for i in $(seq 1 15); do
    if curl -sf -H 'X-Forwarded-Proto: https' "http://127.0.0.1:${PORT}/api/sante" >/dev/null; then
        echo "  API en ligne — OK"
        docker exec -i "$CONTENEUR" python - compter < deploy/purge_eleves.py
        echo "== Fait. Sauvegarde : $SAUV =="
        exit 0
    fi
    sleep 2
done
echo "!! L'API ne répond pas — voir : docker logs $CONTENEUR" >&2
exit 1
