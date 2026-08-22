# Mise en service — VPS Hetzner (FastAPI + React)

**2026-08-22** · réécrit pour la pile FastAPI + React (D-CEO-42/43, Django
retiré le 2026-08-21) — remplace la version précédente de ce document, qui
décrivait un déploiement Django (gunicorn, `manage.py`, WhiteNoise). Les
scripts `deploy/` qu'elle référençait ont été supprimés avec Django et sont
reconstruits ici pour la nouvelle pile.

Base de données : **Neon, inchangée**. Neon héberge la base, pas
l'application — le choix de l'hébergeur applicatif ne la concerne pas.
**Non exécuté à ce jour :** l'adoption du schéma Neon existant par Alembic
(`backend/docs/bascule_neon.md`) — étape manuelle, préalable au tout premier
démarrage du backend contre Neon, à faire par vous avec vos accès.

Deux process tournent derrière nginx sur le même domaine :
- **backend** (`hakili.service`, uvicorn, `127.0.0.1:8000`) sert l'API sous `/api/*`.
- **frontend** : pas de process — `frontend/dist/` (build Vite) est servi en
  statique directement par nginx. Le SPA React fait le reste côté client.

Un seul point de terminaison TLS (nginx), une seule origine pour le
navigateur — le frontend appelle `/api/...` en relatif (`frontend/src/lib/api.ts`),
donc aucun CORS à configurer.

---

## Étape 0 — Domaine et DNS

Créer un enregistrement `A` (et `AAAA` si IPv6) pointant le domaine choisi
vers l'IP publique du VPS. Attendre la propagation DNS avant l'étape certbot
(vérifier avec `dig votredomaine.example`).

## Étape 1 — Provisionnement du serveur (une fois)

Sur un VPS Hetzner neuf (Ubuntu 22.04 ou 24.04), en root :

```bash
scp deploy/provision_serveur.sh root@VOTRE_IP:/root/
ssh root@VOTRE_IP
bash provision_serveur.sh
```

Installe Python 3.12, Node.js 22 (build du frontend), nginx, certbot, git ;
crée l'utilisateur système `hakili` et configure le pare-feu UFW (SSH +
HTTP/HTTPS uniquement — le port d'uvicorn n'est jamais exposé publiquement,
seul nginx l'est, en écoute sur `127.0.0.1:8000`).

## Étape 2 — Déploiement du code (première fois)

```bash
su - hakili
git clone <url-du-depot> /opt/hakili/Hakili_Lab
cd /opt/hakili/Hakili_Lab

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cp .env.example .env
chmod 600 .env
# éditer .env : DATABASE_URL (Neon), ANTHROPIC_API_KEY, GOOGLE_API_KEY,
# DEEPSEEK_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY,
# GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_ELEVES_ID,
# GOOGLE_SHEET_PERSONNEL_ID — DEBUG=false en production.
```

Générer `SECRET_KEY` et la coller dans `.env` — **obligatoire hors DEBUG**,
`app/auth/tokens.py` refuse de signer un jeton d'URL sans elle :

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Déposer le compte de service Google (jamais versionné) :

```bash
# depuis votre poste, pas depuis le serveur :
scp credentials/service_account.json hakili@VOTRE_IP:/opt/hakili/Hakili_Lab/credentials/service_account.json
ssh hakili@VOTRE_IP chmod 600 /opt/hakili/Hakili_Lab/credentials/service_account.json
```

⚠ **Avant le tout premier `alembic upgrade head` contre Neon**, si la base
porte déjà le schéma créé par les migrations Django (`referentiel_*`,
`suivi_*`) : suivre `backend/docs/bascule_neon.md` (`alembic stamp head`,
vérification colonne à colonne sur une branche Neon dédiée) — sinon Alembic
tente de recréer des tables qui existent déjà et échoue bruyamment (rien
n'est perdu, mais rien ne démarre non plus).

Build initial et migration :

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
cd frontend && npm ci && npm run build && cd ..
exit  # retour en root
```

## Étape 3 — Service systemd (backend)

```bash
cp /opt/hakili/Hakili_Lab/deploy/hakili.service /etc/systemd/system/hakili.service
systemctl daemon-reload
systemctl enable --now hakili
systemctl status hakili
```

`hakili.service` exécute `alembic upgrade head` avant chaque démarrage
(sans effet si le schéma est déjà à jour), puis lance uvicorn en 2 workers
sur `127.0.0.1:8000` — jamais exposé directement, seul nginx y accède.

## Étape 4 — nginx et HTTPS

```bash
cp /opt/hakili/Hakili_Lab/deploy/nginx_hakili.conf /etc/nginx/sites-available/hakili
# remplacer VOTRE_DOMAINE.example par le vrai domaine dans ce fichier
ln -s /etc/nginx/sites-available/hakili /etc/nginx/sites-enabled/hakili
nginx -t && systemctl reload nginx

certbot --nginx -d votredomaine.example
```

`certbot --nginx` réécrit le fichier tout seul pour ajouter le bloc HTTPS, la
redirection 80→443, et programme le renouvellement automatique (timer
systemd `certbot.timer`, déjà activé par le paquet Debian/Ubuntu — vérifier
avec `systemctl list-timers | grep certbot`).

**Point d'attention** : `app/security.py::SecuriteProductionMiddleware`
force la redirection HTTPS et l'en-tête HSTS hors `DEBUG`, en lisant le
protocole via `X-Forwarded-Proto`. `deploy/nginx_hakili.conf` envoie bien
cet en-tête sur `/api/` — sans lui, la redirection HTTPS boucle
indéfiniment côté backend.

## Étape 5 — Vérification

```bash
curl -s https://votredomaine.example/api/sante
# {"ok": true}
```

Puis un aller-retour réel depuis un navigateur : connexion nom+PIN, dépôt
d'une copie, génération d'un plan et d'une fiche PDF — le contrôle
`manage.py verifier_installation` de l'ère Django n'a pas d'équivalent
FastAPI construit (perte assumée, voir le commit `feat!: retire Django`) ;
c'est ce parcours manuel qui en tient lieu tant qu'il n'est pas reconstruit.

---

## Mises à jour suivantes

```bash
ssh root@VOTRE_IP
bash /opt/hakili/Hakili_Lab/deploy/deploy.sh
```

`git pull`, dépendances backend, migration Alembic, build frontend,
redémarrage de `hakili.service`. Prend la branche `main` par défaut
(`deploy.sh nom-de-branche` pour une autre branche).

---

## Ce qui ne change pas par rapport à l'ancien déploiement Django

- Neon comme base, avec les mêmes réglages de tolérance au réveil de
  connexion (`pool_pre_ping`/`pool_recycle=300`, D-CEO-19 — portés dans
  `backend/app/db.py`).
- Le point ouvert sur les données personnelles (CIL Burkina Faso, PIN en
  clair dans le Sheet, consentement parental) — indépendant de la pile.
- **Une seule instance** : pas de file de tâches, ne pas faire tourner deux
  `hakili.service` ni un load-balancer devant plusieurs instances.
- Le disque du VPS est persistant par nature — `runs/` (fiches PDF
  générées) survit à un redémarrage du service comme à un reboot.

## Ce qui disparaît avec Django

- `collectstatic`/WhiteNoise — le frontend est un build statique servi par
  nginx. `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` n'existent plus
  (le cookie de session FastAPI est une clé opaque vérifiée en base, voir
  `backend/app/auth/deps.py`) ; `DJANGO_SECRET_KEY` devient `SECRET_KEY`
  (même obligation hors DEBUG, seulement pour les jetons d'URL signés —
  voir Étape 2 ci-dessus).
- Le `Procfile` (Render/Railway, `docs/deploiement.md`) et `manage.py
  verifier_installation` — sans équivalent FastAPI à ce jour.
