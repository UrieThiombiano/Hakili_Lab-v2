# Adoption du schéma Neon existant par Alembic

**Statut : non exécuté.** Ce document décrit la procédure prévue pour faire
adopter par Alembic (backend FastAPI) le schéma déjà présent sur la base Neon
de production — schéma actuellement possédé par les migrations **Django**
(`referentiel/`, `suivi/`, D-CEO-40). C'est la dernière étape avant de pouvoir
démarrer le backend FastAPI contre la base réelle. **À exécuter par vous**,
avec vos accès Neon, pas par un agent automatisé — voir "Ce qui ne sera pas
fait à votre place" plus bas.

Contexte de la décision : `docs/decision_register.md` D-CEO-42 (racine du
dépôt). Chantier suivi dans `C:\Users\Urie\.claude\plans\majestic-nibbling-anchor.md`.

## Précédent direct dans ce projet

Ce geste n'est pas nouveau ici : quand `copie`/`document` sont passées de
SQLAlchemy à Django (D-CEO-40), les deux tables existaient déjà sur Neon
(créées par l'ancien Alembic). La migration Django qui les adoptait ne
créait rien — elle s'enregistrait seulement :

```bash
python manage.py migrate suivi 0007 --fake      # une seule fois, sur Neon
```

`alembic stamp head` ci-dessous est le geste symétrique dans l'autre sens :
Alembic (FastAPI) adopte un schéma que Django possède déjà, sans le
recréer.

## Pré-requis avant d'exécuter quoi que ce soit contre Neon

1. **Vérification colonne à colonne, pas seulement table par table.** Les
   modèles SQLAlchemy (`backend/app/models/`) ont été écrits pour répliquer
   les noms de table/colonne/contrainte Django exactement (`UniqueConstraint`,
   `CheckConstraint` inclus) — mais ils n'ont jamais été comparés au schéma
   Neon réel, seulement à une base de dev vide créée par
   `Base.metadata.create_all()`. Avant de stamper :
   ```bash
   # Depuis backend/, DATABASE_URL pointée sur une COPIE de Neon (pg_dump
   # restauré ailleurs, ou une branche Neon dédiée) — jamais Neon prod pour
   # ce test.
   alembic upgrade head --sql > /tmp/attendu.sql   # DDL que nos modèles produiraient
   pg_dump --schema-only "$NEON_URL" > /tmp/reel.sql
   # Comparaison manuelle : les deux DDL doivent décrire le même schéma
   # pour les 13 tables héritées de Django (referentiel_*, suivi_*).
   ```
   Un écart trouvé ici (type de colonne, contrainte manquante, index en
   plus/en moins) doit être corrigé dans les modèles SQLAlchemy **avant**
   de stamper — après le stamp, Alembic considère le schéma comme sien et
   ne le comparera plus.

2. **Neon Branching, pas la base prod, pour toute la vérification.** Neon
   permet de créer une branche à partir de la prod en quelques secondes —
   c'est l'environnement recommandé pour l'étape 1, jamais la base de
   production elle-même.

3. **Sauvegarde avant l'exécution finale**, même si `stamp` n'écrit aucune
   donnée (il écrit seulement une ligne dans `alembic_version`) — précaution
   standard avant toute opération sur la base de production.

## Procédure (une seule fois, sur Neon, une fois la vérification faite)

```bash
cd backend
DATABASE_URL="<url Neon réelle>" alembic stamp head
```

Ceci enregistre la révision `head` actuelle (les deux migrations existantes,
`25993fea0675` puis `cab106d96cf9`) comme déjà appliquée, sans exécuter leur
DDL — exactement le même principe que `migrate suivi 0007 --fake`.

Après cette commande, les démarrages suivants du backend FastAPI (voir
`backend/entrypoint.sh`) exécutent `alembic upgrade head` normalement : sur
un schéma déjà stampé, cette commande ne fait rien (déjà à `head`) ; une
future migration créée après la bascule s'appliquera normalement.

## Ce qui ne sera pas fait à votre place

- Exécuter `alembic stamp head` contre la vraie base Neon — nécessite vos
  identifiants de production.
- Créer la branche Neon de vérification (étape 1) — nécessite votre accès
  au projet Neon.
- Déployer l'image `backend/Dockerfile` sur le VPS Hetzner — nécessite un
  accès SSH que cet agent n'a pas. Voir `docs/deploiement_vps_hetzner.md`
  pour le pattern de déploiement Django déjà en place ; le backend FastAPI
  suit le même schéma (service systemd ou conteneur Docker derrière nginx),
  sur un port différent (8011, voir `backend/Dockerfile`) le temps de faire
  tourner les deux stacks en parallèle avant la coupure finale.
- Retirer Django — prématuré tant que la bascule n'a pas été validée en
  production réelle.

## Frontend : build et service statique

`frontend/npm run build` produit `frontend/dist/` (assets statiques,
découpés en chunks par route — voir Partie F du plan, `React.lazy()`).
Deux options pour le servir, aucune choisie à ce stade :

- **nginx** (recommandé, cohérent avec `deploy/nginx_hakili_docker.conf`
  déjà en place pour Django) : `frontend/dist/` servi en statique par nginx,
  qui proxy les requêtes `/api/*` vers le backend FastAPI (port 8011).
  Avantage : même reverse proxy que Django aujourd'hui, un seul point de
  terminaison TLS à gérer.
- **`StaticFiles` de FastAPI** (`from fastapi.staticfiles import StaticFiles`) :
  le backend sert directement `dist/` en plus de l'API. Plus simple à
  déployer (un seul processus), mais mélange le rôle "API" et "serveur de
  fichiers statiques" que nginx sépare proprement.

Aucun de ces deux chemins n'a été construit ni testé — décision à prendre
au moment de la bascule, pas avant.
