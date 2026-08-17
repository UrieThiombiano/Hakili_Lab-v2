# Hakili Lab — image Docker (déploiement VPS Hetzner par conteneur)
#
# Alternative conteneurisée au déploiement systemd décrit dans
# docs/deploiement_vps_hetzner.md (deploy/hakili.service). Les deux
# approches sont valides ; celle-ci convient si le VPS fait tourner
# plusieurs apps derrière Docker/Traefik/nginx plutôt qu'un service natif.
#
# ⚠️ Port interne : EXPOSE 8010 par défaut (exemple donné par
# l'administrateur). Redéfinir via `-e PORT=xxxx` si un autre port
# libre est imposé sur le serveur — ne jamais l'exposer publiquement
# directement, un reverse proxy (nginx/Traefik) doit rester devant.

FROM python:3.12-slim

RUN useradd -m -u 1000 hakili
USER hakili
ENV PATH="/home/hakili/.local/bin:$PATH"

WORKDIR /app

COPY --chown=hakili requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=hakili . /app
RUN chmod +x entrypoint.sh

# Répertoires que l'app doit pouvoir écrire (runs/, logs/, staticfiles/) —
# recréés ici car exclus du build context par .dockerignore (données de
# copies/élèves, jamais dans une image). credentials/ reste vide : le
# compte de service Google se monte en volume au démarrage, jamais copié
# dans l'image (voir .dockerignore).
RUN mkdir -p runs logs staticfiles credentials

# collectstatic ne touche pas la base — DEBUG=true ici contourne
# uniquement l'obligation de DJANGO_SECRET_KEY à la construction
# (hakili/settings.py). La vraie clé est fournie au démarrage du
# conteneur, jamais gravée dans l'image.
RUN DEBUG=true python manage.py collectstatic --noinput

ENV PORT=8010
EXPOSE 8010

ENTRYPOINT ["./entrypoint.sh"]
