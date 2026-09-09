# Déploiement — Hakili Lab

Tout ce qui sert à mettre Hakili Lab en ligne est dans ce dossier. La cible est
le **VPS Hetzner partagé `167.233.234.219`** : Docker et Caddy y tournent déjà
pour plusieurs applications (`guichet-entrepreneur`, `api-sylviane`, …). Hakili
Lab s'y ajoute comme **une application de plus** — un conteneur, un port interne,
un bloc dans le Caddyfile partagé. Rien à provisionner.

L'API FastAPI et le frontend React sont servis par **un seul processus, un seul
port** : le conteneur build inclut `frontend/dist/` et FastAPI le sert en
statique (`backend/app/main.py`), les appels `/api/*` sont relatifs — pas de
CORS, pas de second conteneur, pas de nginx.

> **État au moment de la livraison :** `deploy/` est prêt et testé en local
> (image construite et lancée, API + frontend + SPA vérifiés). Il n'a **jamais
> été exécuté contre le vrai serveur** — cela demande les accès SSH du
> commanditaire. La bascule de la base (voir étape 0) n'a pas non plus été
> faite.

---

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `README.md` | Ce guide (explications). |
| `CHECKLIST.md` | Runbook linéaire à cocher pour la session SSH — sans explications. |
| `Dockerfile` | Image de l'app complète (API + frontend buildé). Contexte de build = racine du dépôt. |
| `entrypoint.sh` | Démarrage du conteneur : `alembic upgrade head` puis `uvicorn` (2 workers). |
| `deploy.sh` | Script de déploiement / mise à jour : `git pull` → build frontend → build image → relance du conteneur → contrôle santé. |
| `caddy_snippet.txt` | Bloc à coller dans le Caddyfile partagé (reverse proxy + HTTPS). |
| `bascule_neon.md` | Procédure unique d'adoption du schéma Neon existant par Alembic (étape 0). |

Deux fichiers restent **à la racine du dépôt**, à leur emplacement imposé :

- **`.dockerignore`** — Docker le lit à la racine du contexte de build. Il
  exclut `.venv/`, `frontend/node_modules/`, `.git/`, les bases locales
  (`*.db`), les secrets (`.env`, `credentials/`) et les données d'élèves
  (`runs/`, `logs/`, `data/copies/`).
- **`.env.example`** — gabarit de configuration, commun au développement et à
  la production. Les valeurs à changer pour la production sont listées plus bas.

---

## Ce que le serveur partagé impose (à ne pas casser)

- **Un port interne par app, jamais exposé à Internet.** Caddy y accède en
  `localhost`. Ports pris (`Tuto deploiement Heztner.txt`) : `7860`
  (guichet-entrepreneur), `8001` (api-sylviane) ; libres : `8010`, `8011`,
  `8012`. On utilise **`8011`** — c'est celui câblé dans `Dockerfile` et
  `deploy.sh`. **Vérifier auprès de l'administrateur (`HakiliLab`)** qu'il
  l'est toujours avant le premier déploiement.
- **Le Caddyfile `/etc/caddy/Caddyfile` est partagé.** N'y ajouter que le bloc
  de `caddy_snippet.txt`. Ne jamais modifier ni retirer le bloc d'une autre app.
- **Une app = un conteneur = un port = un bloc Caddy.** Ne pas scinder en deux
  conteneurs (API + statique) : ça demanderait un deuxième port.
- Pas de `ufw` (contrairement aux étapes 7/12 du tuto, prévues pour un test en
  IP:port d'une app Shiny — ici le conteneur n'écoute que sur `127.0.0.1:8011`),
  pas de `systemctl restart caddy` (reload seulement), aucune commande à
  l'échelle du serveur sans avoir vérifié qu'elle n'affecte que cette app.

---

## Référence serveur — `Tuto deploiement Heztner.txt`

Le fichier `Tuto deploiement Heztner.txt` (racine du dossier de travail, **hors
dépôt** — il contient le mot de passe SSH) est le tutoriel générique du serveur.
Il décrit une app Shiny, mais **le contexte serveur qu'il donne s'applique tel
quel** à Hakili Lab :

| Ce que le tuto donne | Pour Hakili Lab |
|---|---|
| `ssh …@167.233.234.219` + mot de passe (dans le fichier) | Le nom de compte y est un placeholder — le demander à l'admin (`HakiliLab`) |
| Docker + Caddy déjà installés, Caddyfile partagé `/etc/caddy/Caddyfile` | Idem — on ajoute un conteneur + un bloc Caddy, rien à installer |
| Ports pris : `7860` (guichet-entrepreneur), `8001` (api-sylviane) ; **libres : `8010`, `8011`, `8012`** | On utilise **`8011`** (câblé dans `Dockerfile`/`deploy.sh`) |
| Admin serveur : **HakiliLab** | À contacter pour le port et l'accès `sudo` au Caddyfile |
| Étapes 6-7 : `docker run -p 8010:7860` puis `sudo ufw allow 8010/tcp` pour tester en IP:port | **Non applicable** : `deploy.sh` publie sur `127.0.0.1:8011` seulement — Caddy y accède en local, aucun port à ouvrir dans `ufw` |
| Étape 5 : Dockerfile à la Shiny | Remplacé par `deploy/Dockerfile` (API FastAPI + frontend React buildé) |

La suite de ce guide reprend les étapes du tuto avec les spécificités Hakili Lab.

---

## Pré-requis

- **Accès SSH** au serveur (`ssh <compte>@167.233.234.219` — mot de passe et
  contexte dans `Tuto deploiement Heztner.txt`, hors dépôt ; le nom de compte
  est à demander à l'admin `HakiliLab`).
- **Dépôt GitHub** accessible depuis le serveur (token si privé).
- **Base Neon** : URL de connexion (`postgresql://…?sslmode=require`) + accès au
  projet Neon pour l'étape 0.
- **Clés API** : Anthropic (obligatoire), Google AI, DeepSeek, Mistral, OpenAI.
- **Compte de service Google** (`service_account.json`) avec accès lecture aux
  deux Sheets (élèves, personnel).
- **Un sous-domaine** (ex. `correction.hakililab.com`) avec un enregistrement
  DNS `A` vers `167.233.234.219`.
- **node / npm** sur le serveur (build du frontend hors conteneur) :
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
  sudo apt-get install -y nodejs
  ```

---

## Étape 0 — Adopter le schéma Neon (une seule fois)

La base Neon de production porte déjà le schéma (hérité des migrations Django
retirées). Avant le premier démarrage, Alembic doit l'**adopter** sans le
recréer — sinon `alembic upgrade head` (lancé à chaque démarrage du conteneur)
échoue sur « table déjà existante ».

Procédure complète, vérification comprise (branche Neon de test, comparaison
colonne à colonne, sauvegarde) : **`deploy/bascule_neon.md`**. En résumé, une
fois la vérification faite :

```bash
cd backend
DATABASE_URL="<url Neon réelle>" alembic stamp head
```

À faire par le commanditaire, avec ses accès Neon.

---

## Étape 1 — Premier déploiement

```bash
ssh <compte>@167.233.234.219
git clone <url-du-depot> ~/hakili-lab
cd ~/hakili-lab
git checkout fastapi-react            # branche déployée (voir note en bas)

cp .env.example .env
chmod 600 .env
nano .env
```

Renseigner dans `.env` :

| Variable | Valeur en production |
|---|---|
| `DEBUG` | `false` |
| `SECRET_KEY` | une clé générée (voir ci-dessous) — **obligatoire hors DEBUG** |
| `HAKILI_ACCES_LIBRE` | `false` |
| `DATABASE_URL` | `postgresql://…@…neon.tech/…?sslmode=require` |
| `ANTHROPIC_API_KEY` | la clé |
| `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `OPENAI_API_KEY` | les clés |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `credentials/service_account.json` |
| `GOOGLE_SHEET_ELEVES_ID`, `GOOGLE_SHEET_PERSONNEL_ID` | les IDs réels |

Générer `SECRET_KEY` :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Déposer le compte de service Google (jamais versionné), **depuis votre poste** :

```bash
scp credentials/service_account.json <compte>@167.233.234.219:~/hakili-lab/credentials/
ssh <compte>@167.233.234.219 chmod 600 ~/hakili-lab/credentials/service_account.json
```

Déployer :

```bash
bash deploy/deploy.sh
```

Le script build le frontend, build l'image, démarre le conteneur `hakili` sur
`127.0.0.1:8011`, et attend que `/api/sante` réponde.

---

## Étape 2 — Bloc Caddy (première fois seulement)

Un enregistrement DNS `A` doit déjà pointer le domaine vers `167.233.234.219`
(`dig correction.hakililab.com`).

```bash
sudo nano /etc/caddy/Caddyfile
# coller le contenu de deploy/caddy_snippet.txt, domaine remplacé
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtient et renouvelle seul le certificat HTTPS (Let's Encrypt).

---

## Étape 3 — Vérification

```bash
curl -s https://correction.hakililab.com/api/sante
# {"ok": true}
```

Puis un aller-retour réel depuis un navigateur : connexion nom + PIN, dépôt
d'une copie, relecture de la transcription, validation des notes, génération
d'un plan et d'une fiche PDF. C'est ce parcours manuel qui tient lieu de
contrôle de bout en bout (l'ancienne commande `verifier_installation` de l'ère
Django n'a pas d'équivalent FastAPI).

---

## Mises à jour suivantes

```bash
ssh <compte>@167.233.234.219
cd ~/hakili-lab
bash deploy/deploy.sh            # branche fastapi-react par défaut
```

`git pull`, rebuild frontend, rebuild image, remplace le conteneur. Le bloc
Caddy n'est à retoucher que si le domaine ou le port changent.

---

## Retour arrière

Le conteneur est éphémère, l'image précédente reste en cache tant qu'un nouveau
build ne l'a pas écrasée.

```bash
git checkout <commit-precedent>
bash deploy/deploy.sh
```

Aucune migration destructive n'est jouée automatiquement (`entrypoint.sh` ne
fait qu'`upgrade head`). Un retour arrière de schéma se fait à la main avec
`alembic downgrade`.

---

## Volumes et persistance

`deploy.sh` monte trois volumes sur le conteneur :

| Volume | Contenu |
|---|---|
| `credentials/` (lecture seule) | compte de service Google, jamais dans l'image |
| `runs/` | fiches PDF et rapports générés |
| `logs/` | `app.log` (rotation 5 Mo × 3) — peut contenir des noms d'élèves |

Le disque du VPS est persistant ; seul le conteneur est recréé à chaque
déploiement. La base (élèves, personnel, suivi) est sur **Neon**, hors serveur.

---

## Dépannage

| Symptôme | Piste |
|---|---|
| `deploy.sh` : « l'API ne répond pas » | `docker logs hakili --tail 50`. Souvent : `.env` incomplet, `SECRET_KEY` absente, `DATABASE_URL` invalide. |
| `alembic upgrade head` échoue sur « relation existe déjà » | L'étape 0 (`bascule_neon.md`) n'a pas été faite. |
| `502 Bad Gateway` sur le domaine | Le conteneur ne tourne pas (`docker ps`) ou n'écoute pas sur `127.0.0.1:8011`. |
| Certificat HTTPS invalide | `sudo journalctl -u caddy -f` ; vérifier que le DNS `A` est propagé. |
| Connexion impossible (nom + PIN) | Clé Google Sheets absente / Sheet non partagé avec le compte de service. |

---

## Note — branche déployée

`fastapi-react` est la branche livrée (FastAPI + React, D-CEO-42 → 45). Sa
fusion dans `main` est proposée dans la **PR #1** ; tant qu'elle n'est pas
mergée, `deploy.sh` déploie `fastapi-react` (son défaut). Une fois la PR
mergée et la mise en service confirmée, changer le défaut de `deploy.sh`
(`BRANCHE="${1:-main}"`) et déployer depuis `main`.
