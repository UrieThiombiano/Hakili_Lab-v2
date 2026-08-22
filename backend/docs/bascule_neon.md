# Adoption du schéma Neon existant par Alembic

**Statut : non exécuté.** Ce document décrit la procédure pour faire adopter
par Alembic (backend FastAPI, seule interface depuis le retrait de Django —
D-CEO-42/43) le schéma présent sur la base Neon de production — schéma
possédé jusqu'ici par les migrations **Django**, retirées du dépôt le
2026-08-21 mais dont l'empreinte reste sur Neon (`referentiel_*`,
`suivi_*`, D-CEO-40) tant que cette procédure n'a pas été exécutée. C'est la
dernière étape avant de démarrer le backend FastAPI en production contre la
base réelle. **À exécuter par vous**, avec vos accès Neon, pas par un agent
automatisé — voir "Ce qui ne sera pas fait à votre place" plus bas.

Contexte de la décision : `docs/decision_register.md` D-CEO-42/D-CEO-43
(racine du dépôt). Déploiement applicatif : `docs/deploiement_vps_hetzner.md`.

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
- Provisionner le VPS et déployer réellement — nécessite un accès SSH que
  cet agent n'a pas. `docs/deploiement_vps_hetzner.md` et `deploy/`
  (`provision_serveur.sh`, `hakili.service`, `nginx_hakili.conf`,
  `deploy.sh`) sont prêts et documentés (2026-08-22), jamais exécutés
  contre un vrai serveur.

## Frontend : build et service statique

**Tranché (2026-08-22, voir `docs/deploiement_vps_hetzner.md`) : nginx.**
`frontend/dist/` (produit par `npm run build`) est servi en statique par
nginx, qui proxy `/api/*` vers le backend FastAPI (`127.0.0.1:8000`) — un
seul point de terminaison TLS, aucun CORS à gérer puisque le frontend
appelle l'API en relatif. L'option alternative (`StaticFiles` de FastAPI,
un seul processus) n'a pas été retenue pour garder le rôle "API" et
"serveur de fichiers statiques" séparés, comme le faisait déjà nginx côté
Django.
