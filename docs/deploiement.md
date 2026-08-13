# Mise en service — Railway ou Render
**2026-07-30** · décisions : [architecture_cible.md](architecture_cible.md), D-CEO-28

L'application tournait jusqu'ici **en local**, sur le poste de l'utilisateur. Elle
devient multi-utilisateurs : tuteurs sur téléphone, responsables, administrateur.
Elle a donc besoin d'une adresse joignable.

Base de données : **Neon, inchangée**. Neon héberge la base, pas l'application.

---

## Avant de déployer

```bash
python manage.py verifier_installation
```

Contrôle la configuration, la base, les migrations, les Sheets, les clés d'API, le
référentiel et le stockage — sans appeler aucune API ni rien écrire. Chaque point
manquant est nommé avec sa conséquence.

Pour un essai de correction réel, sur une vraie copie :

```bash
python manage.py verifier_installation --copie copie.pdf --test socle_3eme --eleve HAK-...
```

C'est **le seul contrôle qui prouve que la chaîne tient de bout en bout** —
transcription, correction, diagnostic, rapport, avec les vraies API. Il
conditionnait le retrait de Streamlit ; le retrait a eu lieu sans lui
(D-CEO-39), et **il reste donc à passer**. Aucun filet ne le remplace : les
tests simulent le pipeline.

---

## 🔴 Une étape manuelle, une seule fois, avant la prochaine mise en ligne

`copie` et `document` sont passées de SQLAlchemy à Django le 2026-08-05
(D-CEO-40). **Sur la base Neon, ces deux tables existent déjà** — elles ont été
créées par les migrations Alembic. La migration Django qui les adopte n'a donc
rien à créer là-bas, seulement à être enregistrée :

```bash
python manage.py migrate suivi 0007 --fake      # UNE SEULE FOIS, sur Neon
python manage.py migrate                        # le reste normalement
```

**Si on l'oublie, le déploiement échoue bruyamment** — `relation "copie" existe
déjà` — la transaction est annulée et aucune donnée n'est touchée. Le `release:`
du Procfile s'arrête, la mise en ligne ne se fait pas. C'est le comportement
voulu : mieux vaut un déploiement bloqué qu'une base à moitié migrée.

Sur une base neuve (poste de développement, tests, nouvel environnement), il n'y
a rien à faire : `migrate` crée les deux tables comme les autres.

**Alembic n'existe plus.** `alembic.ini`, `migrations/` et `src/db/` ont été
supprimés ; il n'y a plus qu'un ORM et qu'un système de migrations. Les anciennes
révisions restent dans l'historique Git si une archéologie était nécessaire.

## Variables d'environnement

| Variable | Obligatoire | Rôle |
|---|---|---|
| `DJANGO_SECRET_KEY` | **oui** hors DEBUG | Signe les sessions et les jetons d'URL. L'application **refuse de démarrer** sans : une clé de repli rendrait les sessions falsifiables. |
| `DJANGO_ALLOWED_HOSTS` | **oui** hors DEBUG | Domaines servis, séparés par des virgules. Vide = toutes les requêtes refusées. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | **oui** derrière HTTPS | Origines avec schéma (`https://…`). Sans elles, tous les formulaires échouent. |
| `DATABASE_URL` | oui | Chaîne Neon. Partagée avec le pipeline. |
| `DEBUG` | non | Absent ou `false` en production. |
| `ANTHROPIC_API_KEY` | oui | Filet de secours de toutes les étapes et seul provider de l'extraction de barème. Sans elle, aucune correction ne démarre. |
| `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY` | recommandées | Leur absence bascule le pipeline sur Claude — dix fois plus cher sur la transcription. |
| `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_SHEET_ELEVES_ID`, `GOOGLE_SHEET_PERSONNEL_ID` | oui | Identité des élèves et du personnel. Sans elles, personne ne peut se connecter. |

Générer la clé secrète :

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

---

## Déploiement

Le `Procfile` convient à Railway comme à Render :

```
release: python manage.py collectstatic --noinput && python manage.py migrate --noinput
web: gunicorn hakili.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 180
```

`release` applique les migrations avant chaque mise en ligne. Les fichiers
statiques sont servis par WhiteNoise, sans serveur web séparé — ni Railway ni
Render n'en fournissent. Hors `DEBUG`, `STORAGES["staticfiles"]` utilise
`CompressedManifestStaticFilesStorage` (`hakili/settings.py`), qui exige un
manifeste : sans `collectstatic` avant `migrate`, la première page utilisant
`{% static %}` lève `ValueError: Missing staticfiles manifest entry`.

**Compte de service Google (`GOOGLE_SERVICE_ACCOUNT_FILE`) :** le fichier JSON
n'est jamais versionné (`credentials/` est gitignoré). Sur Railway comme sur
Render, le déposer via leur mécanisme de **fichier secret** (Render : *Secret
Files* ; Railway : *volume* ou variable de build) à l'emplacement pointé par
la variable, par exemple `credentials/service_account.json` — pas de
changement de code nécessaire, `google_sheets.py` lit un chemin de fichier.

**Pourquoi `--threads 4` :** les corrections tournent dans un thread du processus
web. Des workers uniquement synchrones bloqueraient une requête pendant toute la
durée d'une correction.

**Pourquoi `--timeout 180` :** le dépôt d'un lot de copies peut représenter
plusieurs dizaines de mégaoctets sur une connexion lente.

Après le premier déploiement :

```bash
python manage.py importer_referentiel   # 101 compétences, 280 questions, 444 coûts
```

---

## Le point qui demande une décision : le stockage des fichiers

Le pipeline écrit ses fichiers intermédiaires — images de pages, résultat JSON —
dans `runs/`, **sur le disque local**. Railway et Render fournissent un système de
fichiers **éphémère** : il disparaît à chaque redéploiement et n'est pas partagé
entre instances.

Ce que cela implique concrètement :

- Les documents durables — scan, rapport, remédiation — sont déjà écrits **en base**
  par le pipeline. Rien d'irremplaçable n'est perdu.
- En revanche, une correction **en cours** au moment d'un redéploiement perd ses
  fichiers de travail. Elle est détectée comme abandonnée au bout de quinze minutes
  et signalée à l'enseignant, qui doit la relancer.

Deux réponses possibles :

1. **Attacher un volume persistant** monté sur `runs/` (Railway et Render le
   proposent tous les deux). Une correction survit alors à un redéploiement.
2. **L'accepter** : redéployer en dehors des heures de correction, et relancer les
   rares copies interrompues.

L'option 1 est recommandée dès qu'il y a plus d'un enseignant qui corrige.

**Une seule instance.** Le suivi de progression passe par la base, mais le thread
qui travaille vit dans un processus donné. Avec plusieurs instances, une correction
lancée sur l'une reste invisible aux autres — elles verraient un état figé jusqu'au
délai d'abandon. Tant qu'une file de tâches n'est pas mise en place, rester à une
instance.

---

## Données personnelles — point ouvert #4

Dès que l'application quitte le poste local, des données scolaires nominatives
d'**élèves mineurs** transitent sur le réseau et deviennent accessibles depuis
l'extérieur. Trois conséquences :

- **HTTPS n'est plus optionnel.** Les réglages sont en place (`SECURE_SSL_REDIRECT`,
  cookies sécurisés, HSTS un an) et s'activent automatiquement hors DEBUG.
- Le **code PIN** vit toujours en clair dans le Sheet du personnel (D-CEO-25). C'était
  défendable pour un outil local ; ça l'est moins pour une application publique.
  À réexaminer.
- Les obligations auprès de la **CIL du Burkina Faso** et le **consentement parental**
  restent à traiter — ils conditionnent toute perspective commerciale
  institutionnelle (`v2_roadmap.md`, point ouvert #4).
