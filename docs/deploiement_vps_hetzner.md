# Mise en service — VPS Hetzner
**2026-08-17** · remplace `docs/deploiement.md` (Render/Railway) comme cible de déploiement.

Contrairement à Render/Railway (PaaS géré), un VPS Hetzner est une machine nue :
rien n'est fourni automatiquement — ni HTTPS, ni redémarrage du process, ni
déploiement sur `git push`. Ce document couvre ce qu'il faut mettre en place
en plus. Tout ce qui concerne l'application elle-même (variables
d'environnement, migration `suivi 0007 --fake`, stockage des documents,
données personnelles) reste décrit dans `docs/deploiement.md` — le lire
d'abord, ce fichier ne répète que ce qui change avec un VPS.

Base de données : **Neon, inchangée**, comme avec Render/Railway. Neon héberge
la base, pas l'application — le choix de l'hébergeur applicatif ne la
concerne pas.

---

## Ce qui change par rapport à Render/Railway

| Sujet | Render/Railway | VPS Hetzner |
|---|---|---|
| HTTPS | fourni automatiquement | nginx + Let's Encrypt (certbot) à installer |
| Process web | géré par la plateforme (`Procfile`) | service systemd (`deploy/hakili.service`) |
| Port | `$PORT` fourni | socket Unix local, nginx fait le proxy |
| Déploiement | auto sur `git push` | script manuel (`deploy/deploy.sh`) ou CI/CD par SSH |
| Fichiers statiques | WhiteNoise sert tout | nginx sert `/static/`, WhiteNoise reste en secours |
| Système de fichiers | éphémère (redéploiement = perte de `runs/`) | **persistant** — ce point ouvert de `docs/deploiement.md` disparaît |
| Fichier secret Google | mécanisme "Secret Files" de la plateforme | déposé à la main sur le serveur (`scp`) |
| Domaine | sous-domaine `*.onrender.com` / `*.up.railway.app` | domaine propre à pointer vers l'IP du VPS |

Le `Procfile` devient inutile sur un VPS — `deploy/hakili.service` le
remplace. Il n'est pas nécessaire de le supprimer si Render/Railway reste une
option de repli.

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

Installe Python 3.12, nginx, certbot, git ; crée l'utilisateur système
`hakili` (sans shell de connexion) et configure le pare-feu UFW (SSH +
HTTP/HTTPS uniquement — le port de gunicorn n'est jamais exposé
publiquement, seul nginx l'est).

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
# éditer .env : DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS,
# DATABASE_URL, ANTHROPIC_API_KEY, etc. — voir la table de docs/deploiement.md
```

Déposer le compte de service Google (jamais versionné) :

```bash
# depuis votre poste, pas depuis le serveur :
scp credentials/service_account.json hakili@VOTRE_IP:/opt/hakili/Hakili_Lab/credentials/service_account.json
ssh hakili@VOTRE_IP chmod 600 /opt/hakili/Hakili_Lab/credentials/service_account.json
```

Générer la clé secrète Django et la coller dans `.env` :

```bash
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

⚠ Si la base Neon porte déjà les tables `copie`/`document` créées par
l'ancien Alembic (cas d'une base existante réutilisée depuis Render/Railway),
appliquer **une seule fois** l'étape décrite dans `docs/deploiement.md`
(section "Une étape manuelle") avant `migrate` :

```bash
.venv/bin/python manage.py migrate suivi 0007 --fake
```

Puis, normalement :

```bash
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py importer_referentiel
.venv/bin/python manage.py verifier_installation
exit  # retour en root
```

## Étape 3 — Service systemd

```bash
cp /opt/hakili/Hakili_Lab/deploy/hakili.service /etc/systemd/system/hakili.service
systemctl daemon-reload
systemctl enable --now hakili
systemctl status hakili
```

Le service écoute sur un socket Unix (`/run/hakili/gunicorn.sock`), jamais
directement exposé — seul nginx y accède. Les mêmes réglages gunicorn que le
`Procfile` (`--workers 2 --threads 4 --timeout 180`) sont repris, pour la même
raison : les corrections tournent dans un thread du process web, et un dépôt
de lot peut être long sur une connexion lente.

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

**Point d'attention propre au VPS** : `hakili/settings.py` active
`SECURE_SSL_REDIRECT` hors `DEBUG` et lit le protocole via l'en-tête
`X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`). `deploy/nginx_hakili.conf`
envoie bien cet en-tête (`proxy_set_header X-Forwarded-Proto $scheme`) — sans
lui, la redirection HTTPS de Django boucle indéfiniment. Sur Render/Railway
c'était géré par la plateforme ; sur un VPS c'est nginx qui doit le faire, il
n'y a personne d'autre.

Mettre à jour `.env` avec le domaine réel puis redémarrer le service :

```bash
# DJANGO_ALLOWED_HOSTS=votredomaine.example
# DJANGO_CSRF_TRUSTED_ORIGINS=https://votredomaine.example
systemctl restart hakili
```

## Étape 5 — Vérification

```bash
python manage.py verifier_installation --copie copie.pdf --test socle_3eme --eleve HAK-...
```

Comme documenté dans `docs/deploiement.md` : c'est le seul contrôle qui
prouve que la chaîne tient de bout en bout avec les vraies API, en conditions
de production.

---

## Mises à jour suivantes

```bash
ssh root@VOTRE_IP
bash /opt/hakili/Hakili_Lab/deploy/deploy.sh
```

Fait l'équivalent du `release:` + redémarrage `web:` de Render/Railway :
`git pull`, installation des dépendances, `collectstatic`, `migrate`,
redémarrage du service. Prend la branche `main` par défaut
(`deploy.sh nom-de-branche` pour une autre branche).

---

## Ce qui NE change pas par rapport à `docs/deploiement.md`

- La table des variables d'environnement obligatoires/recommandées.
- L'étape manuelle `migrate suivi 0007 --fake` (une seule fois, sur une base
  Neon déjà migrée par Alembic).
- Le point ouvert sur les données personnelles (CIL Burkina Faso, PIN en
  clair dans le Sheet, consentement parental) — indépendant de l'hébergeur.
- **Une seule instance** : le suivi de progression passe par la base, mais le
  thread qui travaille vit dans un processus donné. Cette contrainte
  s'applique identiquement sur un VPS — ne pas faire tourner deux
  `hakili.service` ou un load-balancer devant plusieurs instances tant
  qu'une file de tâches n'est pas mise en place.

## Ce qui disparaît

Le point ouvert "stockage des fichiers" de `docs/deploiement.md` (système de
fichiers éphémère, volume persistant à envisager) **ne s'applique plus** :
le disque d'un VPS Hetzner est persistant par nature. `runs/` survit à un
redémarrage du service comme à un reboot de la machine — aucun volume
supplémentaire à attacher.
