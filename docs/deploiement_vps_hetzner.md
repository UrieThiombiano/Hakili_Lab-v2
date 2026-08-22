# Mise en service — VPS Hetzner (serveur partagé, Docker + Caddy)

**2026-08-22, réécrit une deuxième fois le même jour.** La première version
de ce document (retrait de Django, D-CEO-42/43) décrivait le provisionnement
d'un VPS dédié neuf — systemd, nginx, certbot, UFW installés de zéro. C'était
faux pour le serveur réel : `167.233.234.219` est un **serveur Hetzner
partagé**, déjà provisionné, qui héberge plusieurs apps (`guichet-entrepreneur`,
`api-sylviane`, …) derrière **Docker** (déjà installé) et **Caddy** (reverse
proxy + HTTPS automatique pour toutes les apps, déjà en service — voir
`Tuto deploiement Heztner.txt` à la racine du dossier de travail). `deploy/`
a été reconstruit pour cette réalité : un conteneur Docker de plus, un bloc
Caddy de plus, rien à provisionner.

Base de données : **Neon**. Selon l'utilisateur (2026-08-22, à vérifier au
premier démarrage réel plutôt qu'à supposer) : l'adoption du schéma Neon par
Alembic (`backend/docs/bascule_neon.md`, `alembic stamp head`) serait déjà
faite. Si `alembic upgrade head` (dans `backend/entrypoint.sh`, à chaque
démarrage du conteneur) échoue en tentant de recréer une table déjà
existante, c'est que ce n'est pas le cas — repasser par
`backend/docs/bascule_neon.md` avant de relancer.

---

## Ce que ce serveur impose (à ne pas casser)

- **Un port interne par app**, jamais exposé directement — Caddy y accède en
  `localhost`. Ports déjà pris au 2026-08-22 : `7860` (guichet-entrepreneur),
  `8001` (api-sylviane). **`8011` est libre** — c'est celui déjà câblé dans
  `backend/Dockerfile`/`deploy/deploy.sh`. Vérifier auprès de l'administrateur
  (`HakiliLab`) qu'il l'est toujours avant le premier déploiement : un autre
  chantier a pu le prendre entre-temps.
- **Le Caddyfile est partagé entre toutes les apps** (`/etc/caddy/Caddyfile`)
  — n'y ajouter que le bloc de `deploy/caddy_snippet.txt`, ne jamais modifier
  ou retirer un bloc d'une autre app.
- **Une app = un conteneur Docker = un port = un bloc Caddy.** D'où le choix
  fait dans `backend/Dockerfile` : un seul conteneur sert l'API **et** le
  frontend React buildé (`fastapi.staticfiles`, `backend/app/main.py`) —
  jamais deux conteneurs (API + nginx statique) pour cette app, ça
  demanderait deux ports et compliquerait le Caddyfile partagé pour rien.
- Ne jamais lancer `ufw`, `systemctl restart caddy` (reload seulement, voir
  plus bas), ou toute commande à l'échelle du serveur sans avoir vérifié
  qu'elle n'affecte que le bloc/conteneur de cette app.

---

## Étape 1 — Premier déploiement

Depuis le serveur (`ssh <compte>@167.233.234.219`, voir `Tuto deploiement
Heztner.txt` pour les identifiants) :

```bash
git clone <url-du-depot> ~/hakili-lab
cd ~/hakili-lab
git checkout fastapi-react

cp .env.example .env
chmod 600 .env
# éditer .env : DATABASE_URL (Neon), ANTHROPIC_API_KEY, GOOGLE_API_KEY,
# DEEPSEEK_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY,
# GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_ELEVES_ID,
# GOOGLE_SHEET_PERSONNEL_ID, DEBUG=false.
```

Générer `SECRET_KEY` et la coller dans `.env` — **obligatoire hors DEBUG**,
`app/auth/tokens.py` refuse de signer un jeton d'URL sans elle :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Déposer le compte de service Google (jamais versionné), depuis votre poste,
pas depuis le serveur :

```bash
scp credentials/service_account.json <compte>@167.233.234.219:~/hakili-lab/credentials/service_account.json
ssh <compte>@167.233.234.219 chmod 600 ~/hakili-lab/credentials/service_account.json
```

`node`/`npm` doivent être disponibles sur le serveur pour l'étape de build du
frontend (voir en-tête de `backend/Dockerfile` — construit hors conteneur,
un stage Node dans l'image s'est montré peu fiable en test). Installer une
fois si absent :

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs
```

Puis :

```bash
bash deploy/deploy.sh fastapi-react
```

Construit le frontend, l'image Docker, et démarre le conteneur `hakili` sur
`127.0.0.1:8011` (voir `deploy/deploy.sh` — `alembic upgrade head` tourne à
chaque démarrage du conteneur, dans `backend/entrypoint.sh`, sans effet si
le schéma est déjà à jour).

## Étape 2 — Bloc Caddy (première fois seulement)

```bash
sudo nano /etc/caddy/Caddyfile
# coller le contenu de deploy/caddy_snippet.txt, domaine remplacé
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtient et renouvelle seul le certificat HTTPS (Let's Encrypt) dès que
le bloc est actif — pas d'étape certbot séparée, Caddy le fait pour toutes
les apps de ce serveur de la même façon.

**Avant le bloc Caddy**, un enregistrement DNS `A` doit pointer le domaine
choisi vers `167.233.234.219` (propagation : `dig votredomaine.hakililab.com`).

## Étape 3 — Vérification

```bash
curl -s https://votredomaine.hakililab.com/api/sante
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
ssh <compte>@167.233.234.219
cd ~/hakili-lab
bash deploy/deploy.sh          # branche fastapi-react par défaut
```

`git pull`, build frontend, build image, remplace le conteneur. Le bloc
Caddy n'a besoin d'être touché que si le domaine ou le port changent — un
nouveau build ne le concerne pas.

---

## Volumes et persistance

`deploy/deploy.sh` monte deux volumes sur le conteneur :
- `credentials/` (lecture seule) — le compte de service Google, jamais
  copié dans l'image (`.dockerignore`).
- `runs/` — fiches PDF générées, persistantes entre redémarrages du
  conteneur (le disque du VPS est persistant par nature ; seul le conteneur
  est éphémère à chaque `docker run`).

## Ce qui ne change pas par rapport à l'ancien déploiement Django

- Neon comme base, avec les mêmes réglages de tolérance au réveil de
  connexion (`pool_pre_ping`/`pool_recycle=300`, D-CEO-19 — portés dans
  `backend/app/db.py`).
- Le point ouvert sur les données personnelles (CIL Burkina Faso, PIN en
  clair dans le Sheet, consentement parental) — indépendant de la pile.
- **Une seule instance** : pas de file de tâches, un seul conteneur `hakili`
  à la fois.

## Ce qui disparaît avec Django

- `collectstatic`/WhiteNoise — le frontend est un build statique servi par
  le même processus FastAPI (`fastapi.staticfiles`). `DJANGO_ALLOWED_HOSTS`/
  `DJANGO_CSRF_TRUSTED_ORIGINS` n'existent plus (le cookie de session
  FastAPI est une clé opaque vérifiée en base, voir
  `backend/app/auth/deps.py`) ; `DJANGO_SECRET_KEY` devient `SECRET_KEY`
  (même obligation hors DEBUG, seulement pour les jetons d'URL signés).
- Le `Procfile` (Render/Railway, `docs/deploiement.md`) et `manage.py
  verifier_installation` — sans équivalent FastAPI à ce jour.
