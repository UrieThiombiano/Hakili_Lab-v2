# CLAUDE.md — Hakili Lab AI Assisted Correction

## Rôle de Claude Code

Tu es l'assistant d'ingénierie du projet Hakili Lab : outil de correction assistée par IA pour copies manuscrites de mathématiques, utilisé par les enseignants Hakili Lab au Burkina Faso.

**Objectif central actuel : remplacer le diagnostic en texte libre par un système de suivi structuré et traçable.** Le diagnostic n'est plus une phrase générée par un LLM — c'est une liste d'objets comptables (`compétence × type d'erreur`), avec un cycle de vie d'états daté, qui permet de mesurer une progression, de comparer des élèves, et de calculer un coût de remédiation. C'est le chantier "v2" (`guide-v2.md`, `protocole-v2.md`, 28 juillet 2026), décrit en détail plus bas.

Ce document a deux parties : l'état réel de l'infrastructure aujourd'hui, puis le chantier en cours.

---

## Partie 1 — État réel de l'infrastructure

`docs/decision_register.md` (D001 à D-CEO-43) est la **source de vérité datée** pour toute décision d'architecture. Lis-le avant de toucher à l'auth, à la persistance, ou aux Sheets — ce qui suit n'en est qu'un résumé, il peut avoir été complété depuis.

### FastAPI + React portent toute l'interface (D-CEO-42/43, Django retiré le 2026-08-21)

**Django est supprimé du dépôt** (commit `feat!: retire Django, FastAPI + React devient la seule interface`, 2026-08-21) — plus de coexistence, plus de `manage.py`, `hakili/`, `comptes/`, `correction_web/`, `suivi_web/`, `referentiel/`, `suivi/`. L'API **FastAPI** (`backend/`, SQLAlchemy 2.0 + Alembic) et l'interface **React + Vite + Tailwind** (`frontend/`) sont la seule interface, en développement comme en production. Détail de la décision : `docs/decision_register.md` D-CEO-42 (bascule) et D-CEO-43 (module 7, fiches de travail).

`src/api/`, `src/pipeline/`, `src/knowledge/`, `src/models/`, `src/core/`, `src/integrations/` restent **indépendants du framework** — ne pas y introduire de dépendance à FastAPI. Cette discipline a survécu à deux migrations de framework (Streamlit → Django → FastAPI) sans effet sur ces modules ni sur `tests/`.

⚠ **La bascule en production n'a pas eu lieu.** Le code tourne en dev contre une base séparée (121 tests `pytest backend/tests/`, 40 tests Vitest `frontend/`, 240 tests `pytest tests/`). Selon l'utilisateur (2026-08-22, à vérifier plutôt qu'à supposer), l'adoption du schéma Neon par Alembic (`alembic stamp head`) serait déjà faite — voir `deploy/bascule_neon.md`. La cible réelle est un **VPS Hetzner partagé** (`167.233.234.219`, plusieurs apps en service derrière Docker + Caddy déjà en place, pas un VPS dédié à provisionner). **Tout le déploiement est regroupé dans `deploy/`** (`Dockerfile`, `entrypoint.sh`, `deploy.sh`, `caddy_snippet.txt`, `bascule_neon.md`, et `deploy/README.md` comme guide de livraison — D-CEO-45, 2026-09-09) ; testé localement (image construite et lancée, API + frontend + SPA vérifiés) mais jamais exécuté contre le vrai serveur — ça demande les accès SSH de l'utilisateur.

**Perte assumée au retrait de Django, sans équivalent FastAPI construit à ce jour :** dix commandes `manage.py` de l'outillage v2 (`verifier_installation`, `rapprocher_remediation`, `corpus`, `diagnostiquer`, `donnees_demo`, `mesurer_plancher`, `recalculer_couts`, `taguer_corpus`), récupérables via `git show main:<chemin>` si besoin. Aucune n'est un écran de l'app. En particulier, **le contrôle qui exécute une correction complète sur une vraie copie de bout en bout** (`verifier_installation --copie … --test … --eleve …`) n'a pas d'équivalent — c'est le seul contrôle qui prouvait que la chaîne tenait avec les vraies API, et il n'a jamais été repassé depuis le retrait.

**Commandes :**
```bash
make setup && make run    # backend uvicorn (reload), :8000 — ou voir Makefile
cd frontend && npm install && npm run dev   # frontend Vite, proxy /api vers :8000
make test                 # pytest tests/ + pytest backend/tests/
cd frontend && npm test   # Vitest
python -m alembic -c backend/alembic.ini upgrade head   # migrations (base de dev)
python backend/scripts/importer_referentiel.py          # import du classeur (idempotent)
```
Note : `DATABASE_URL` garde la convention à **trois** barres (`sqlite:///:memory:`),
héritée de SQLAlchemy — `backend/app/db.py` et `src/core/config.py` la lisent tous
les deux, une seule variable pour toute la persistance applicative.

### Persistance : deux systèmes, un seul rôle chacun
- **Google Sheets** (`src/integrations/google_sheets.py`) — source de vérité pour l'**identité** : élèves (`get_eleves()`) et personnel (`get_personnel()`, un seul Sheet fusionné pour enseignants/responsables/admin, colonne `role`). Contrôlé par un tiers (le docteur), lecture seule côté app. **Ne jamais recréer une table `eleve` ou `utilisateur` en base** — ça a déjà été fait et démoli deux fois (D-CEO-20, D-CEO-21) parce que ça crée une deuxième source de vérité qui diverge.
- **Postgres/Neon** (SQLAlchemy, `backend/app/models/`) — `copie` (copy_id, `identifiant_hakili` texte — pas de FK vers une table élève —, classe, notes) et `document` (scan/rapport/remédiation en `bytea`), dans `backend/app/models/correction.py` avec le reste du suivi (`suivi.py`, `referentiel.py`, `auth.py`). Le pipeline y écrit en best-effort à 5 points d'injection (D-CEO-19), **par `src/pipeline/depot.py`** et sans connaître FastAPI (implémentation : `backend/app/depot.py::DepotFastAPI`) ; le seul point non best-effort est la vérification que l'élève existe dans le Sheet **avant** tout appel IA (D-CEO-20).
- `pool_pre_ping=True` / `pool_recycle=300` dans `backend/app/db.py` — Neon met la base en veille, ne pas retirer ça sans comprendre pourquoi c'est là (D-CEO-19, réglage porté depuis Django).

### Authentification et rôles
Connexion par **nom (liste déroulante recherchable) + PIN à 4 chiffres**, les deux lus dans le Sheet personnel à chaque connexion — pas de mot de passe, pas de table `credentials` en base (supprimée, D-CEO-25). Rôles : `administrateur`, `responsable`, `enseignant`, dérivés de la colonne `role` du Sheet. `src/services/auth_service.py` porte la logique ; `UserRole` (`src/core/roles.py`) n'est qu'un enum de confort, pas un type de colonne SQL.

Centres dérivés dynamiquement des Sheets (`src/core/centre_normalizer.py`, `deriver_centres()`) — plus de liste figée. Un centre vu une seule fois est signalé "suspect" sans jamais être bloqué.

### Périmètre : un centre d'encadrement, pas une école (D-CEO-32)
**Toute personne autorisée voit tous les élèves et peut corriger n'importe quelle copie.** Le cloisonnement par centre et par classe a été retiré : les enseignants tournent et reprennent les copies d'un collègue absent, le filtrage bloquait un travail légitime sans rien protéger. Une copie mal attribuée est empêchée par la **sélection explicite de l'élève** (D-CEO-20), pas par le périmètre. Le rôle ne commande plus qu'une chose : l'accès à l'administration. Les affectations (centre, classe) restent lues du Sheet, à titre informatif.

### Écrans (`frontend/src/routes/`, servis par `backend/app/routers/`)
- **Accueil** : liste des élèves avec pastille de tendance (vert/orange/rouge/gris, `src/core/tendance.py`, `SEUIL_TENDANCE = 1.0`), baisses en premier.
- **Profil élève** (`ProfilEleve.tsx`) : une seule vue pour tous les rôles — tendance, copies chronologiques, documents servis par jeton signé (`backend/app/auth/tokens.py`, jamais `identifiant_hakili` en clair dans une URL).
- **Détail de session** (`SessionDetail.tsx`) : plan de remédiation ordonné, volume, palier, inscription au programme, lien de fiche de travail par problème confirmé (module 7, D-CEO-43).
- **Admin** (`Administration.tsx`) : reste explicitement hors du périmètre `/api/admin/*` porté par ce chantier — pas de CRUD référentiel/suivi côté React à ce jour.

### Pipeline de correction (existant, réutilisable — chantier v2 vient s'y ajouter, pas le remplacer entièrement)
- Ingestion PDF/images 150 DPI (`src/pipeline/ingestion.py`)
- Transcription multimodale (Gemini 2.5 Flash / Claude Sonnet fallback)
- Correction binaire 0/1 proposée par IA, validée par l'enseignant dans un tableau (`TeacherDecision`, `src/models/domain.py` — **déjà implémenté**, `compute_final_score()` priorise la décision enseignant)
- Diagnostic + remédiation + export PDF/HTML (`src/pipeline/pdf_report_html.py`, `pdf_remediation_html.py`)
- Routing multi-provider par tâche, fallback Claude (table d'origine : `docs/decision_register.md` D-CEO-03). **Depuis D-CEO-44**, le fournisseur de chaque étape (transcription / correction / analyse) est choisi dans **Paramètres → Modèles IA** (admin) et vit dans `data/preferences_modeles.json` (`src/core/preferences_modeles.py`), qui **prime sur `.env`**. Restent Claude-only par sécurité : diagnostic contraint module 4, génération des sujets T1/T3/T4/T5, extraction énoncé/barème.

**Attention à un piège de doc :** `README.md` décrit encore `TeacherDecision` et le tableau de validation comme "à construire". **C'est fait.** Ne t'y fie pas pour l'état d'avancement — vérifie `docs/v2_roadmap.md` et `docs/decision_register.md`. (`AGENTS.md` portait la même erreur : supprimé au nettoyage du 2026-07-30.)

---

## Partie 2 — Chantier en cours : v2, le suivi structuré

### Documents de référence (à lire dans cet ordre, avant tout code de ce chantier)
1. `protocole-v2.md` (racine du dépôt de travail, hors `Hakili_Lab/`) — le vocabulaire et les règles métier
2. `guide-v2.md` — les 9 modules à construire, module par module
3. `Referentiel_Socle_v0.xlsx` — le classeur : 101 compétences, 7 types d'erreur, 1031 signatures d'erreur, 284 distracteurs QCM tagués, 444 coûts de remédiation précalculés

### Le principe : un problème = une compétence × un type d'erreur
L'unité de suivi n'est plus un score mais un **problème**, avec un cycle de vie d'états datés : `hypothese → confirme/ecarte → en_remediation → resolu/non_resolu → regresse → clos`. Sept types d'erreur, liste **fermée** : `PRQ` (prérequis manquant), `CPT` (conceptuelle), `MOD` (modélisation), `PRC` (procédurale), `CNS` (connaissance non disponible), `RED` (rédaction), `ATT` (inattention — ne donne jamais lieu à remédiation).

### Trois règles non négociables
1. **Aucun code de compétence ou de type d'erreur n'est inventé.** Tout vient du référentiel. Un code absent est un bug, pas une variante.
2. **Aucune sortie en texte libre côté diagnostic structuré.** Chaque module rend des objets structurés à champs fixes.
3. **Aucune tâche n'est automatisée avant d'avoir été faite à la main une fois** — sans point de comparaison (le corpus de référence, module 3), impossible de savoir si un module fonctionne.

### Décision d'architecture actée (ne pas suivre le guide littéralement ici)
Le guide (`guide-v2.md`) prescrit une base **SQLite séparée** à 11 tables. **Décision actée avec l'utilisateur : ces tables vivent dans la base Neon/Postgres existante**, pas dans une SQLite isolée — une seule base pour toute la persistance applicative, cohérent avec la discipline "une seule source de vérité" déjà appliquée au projet (D-CEO-20/21/25). Détail complet du schéma retenu : `C:\Users\Urie\.claude\plans\dynamic-wandering-duckling.md`.

Points clés de cette adaptation :
- `evaluation` référence `copie.copy_id` (nullable) au lieu de dupliquer le stockage des scans/documents — un `T0`/`T1`/etc. réutilise la `Copie` déjà persistée par le pipeline existant.
- L'identité élève reste `identifiant_hakili` (texte), jamais une FK vers une table `eleve` — cohérent avec D-CEO-20.
- Nommer la table de session `session_suivi` (pas `session`, ambigu avec la session HTTP).
- Import du classeur via un script idempotent (pattern `seed_users.py`), pas de saisie manuelle des tables référentiel/banque de questions.

Le diagnostic structuré (module 4) **remplace directement** l'actuel `DiagnosticResult`/`CompetencyGap` en texte libre — niveau par niveau, au fur et à mesure que le référentiel et la grille de diagnostic couvrent ce niveau. Pas de coexistence longue entre les deux systèmes.

### Les 9 modules — suivi détaillé dans `docs/v2_roadmap.md`

Ce chantier se déroule en 9 modules dépendants (0 → 9, chacun a besoin des précédents : appropriation du référentiel, socle de données, ~~lecture des copies par zones~~ (supprimé, D-CEO-38), corpus de référence, diagnostic contraint, composition du test de confirmation, palier et plan de remédiation, génération des fiches, interfaces de saisie, restitution et indicateurs).

**`docs/v2_roadmap.md` est la seule source de vérité sur l'avancement** — statut par module, sous-tâches, critères de fin, jalons de validation, et un journal de bord daté. **Lis-le en début de session, mets-le à jour en fin de session.** Ne pas recréer un deuxième tableau de suivi ici : ce serait reproduire l'erreur "deux sources de vérité" déjà corrigée deux fois sur ce projet (D-CEO-20, D-CEO-21).

**Jalon de validation obligatoire avant tout déploiement réel du module 4 :** cent sorties consécutives valides (aucun code hors référentiel), diagnostic comparé au tagage manuel du corpus de référence, écart mesuré et consigné.

### Protocole T0→T5 — cinq étapes, pas six (D-CEO-33)
T0 positionnement (1h30) → diagnostic machine → T1 confirmation (45min, discrimine chaque hypothèse) → **inscription au programme** (décision humaine, `Session.inscrire()`) → remédiation hors plateforme (8-20h) → T3 vérification en fin de volume horaire → T4/T5 rétention (45j, 3 mois). **T2 (mi-parcours) est retiré** — il ne correspond pas à la pratique du centre. **Un même type d'évaluation peut se répéter** (plusieurs T3 tant que les lacunes tiennent), distingué par un rang attribué automatiquement.

Palier selon coût total à T1 : A (<8h, ciblé) · B (8-20h, complet) · C (>20h, hors dispositif — le dire clairement plutôt que vendre un plan voué à l'échec ; `inscrire()` refuse le palier C sans motif explicite tracé).

Sept états de session (D-CEO-34), dont **trois sorties sans remédiation à ne pas confondre** : `sans_suite` (T1 n'a rien confirmé — c'est un **bon** résultat), `hors_dispositif` (palier C, orientation), `abandonnee` (retrait de la famille). Le détail fait foi dans `docs/cycle_de_suivi.md`.

---

## Contraintes actives (fusion existant + chantier v2)

- Python + **API FastAPI (`backend/`) + SPA React/Vite/Tailwind (`frontend/`)**, seule interface depuis le retrait de Django (D-CEO-42/43). `src/` reste sans dépendance de framework.
- Barème binaire 0/1 par question et sous-question (hors nouveau format QCM/court/rédigé du chantier v2).
- L'enseignant a toujours le dernier mot sur le score (`TeacherDecision`, déjà implémenté).
- **Aucun code de compétence ou de type d'erreur inventé — tout vient du référentiel.**
- **Aucun appel LLM pour interpréter un QCM** — la table `option_qcm` donne la réponse directement.
- Identité élève/personnel : Google Sheets, jamais recréée en base.
- Coût cible pipeline correction : ~$0.02/copie (avec Gemini actif).

---

## Style de travail

Avant de coder sur ce dépôt :
1. Lire `docs/decision_register.md` — décisions actives et datées.
2. Si la tâche touche le chantier v2 : lire aussi `protocole-v2.md`, `guide-v2.md`, et parcourir `Referentiel_Socle_v0.xlsx`.
3. Lire `src/models/domain.py` (schémas du pipeline) et `suivi/models.py` + `referentiel/models.py` (schéma Postgres) avant d'ajouter un champ ou une table.
4. Proposer un plan si la tâche touche plusieurs modules ou plusieurs fichiers.
5. Ne pas recréer ce qui existe — vérifier `src/knowledge/`, `src/pipeline/`, `src/api/`, `src/services/`, `src/integrations/` avant d'écrire une nouvelle fonction.
6. Ne jamais réintroduire une table `eleve` ou `utilisateur`/`credentials` en Postgres — l'identité vit dans les Sheets (D-CEO-20/21/25).

---

## Ce qu'il ne faut pas faire

- Ouvrir le chantier du site web en parallèle du chantier v2. Un seul chantier prioritaire à la fois.
- Ajouter une colonne, un état ou un type d'erreur au référentiel sans en parler.
- Laisser un LLM produire une phrase là où un code structuré est attendu (diagnostic module 4).
- Appeler un modèle de langage pour interpréter un QCM.
- Sauter le module 3 (corpus de référence) — c'est lui qui donne à tous les autres leur point de comparaison.
- Stocker un code local de matrice (`N-a`, `G-c`...) en base — seuls les codes canoniques de l'onglet `02_Competences` sont stables entre niveaux.

---

## Commandes

```powershell
# Windows — deux terminaux
.\.venv\Scripts\Activate.ps1
$env:DEBUG="true"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
cd frontend; npm install; npm run dev          # Vite :5173, proxy /api -> :8000

# Unix / make
make setup && make run          # API FastAPI (uvicorn --reload, :8000)
cd frontend && npm install && npm run dev
make test                       # pytest tests/ + pytest backend/tests/
cd frontend && npm test         # Vitest
make lint

# Migrations (Alembic, base de dev — Neon en prod via deploy/entrypoint.sh)
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini revision --autogenerate -m "…"
python backend/scripts/importer_referentiel.py   # import du classeur (idempotent)

# Déploiement : tout est dans deploy/ (voir deploy/README.md)
bash deploy/deploy.sh
```

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `src/pipeline/pipeline.py` | Pipeline de correction principal (Phase A/B, déjà scindé) |
| ~~`src/pipeline/zones.py`~~ | **Supprimé le 2026-08-05 (D-CEO-38).** Le module 2 découpait la copie par zones ; trois copies réelles imprimées et scannées l'ont mis en défaut, et il reconstituait par la géométrie une correspondance que la correction produit déjà. Ne pas le reconstruire sans lire D-CEO-38 |
| `src/models/domain.py` | Schémas Pydantic pipeline — `TeacherDecision`, `CopyGrade`, `DiagnosticResult` |
| `backend/app/db.py` | Moteur SQLAlchemy — base Neon, `pool_pre_ping`/`pool_recycle`, support SQLite pour les tests |
| `backend/app/models/referentiel.py` | 7 tables du référentiel et de la banque de questions (importées du classeur) |
| `backend/app/models/suivi.py` | Tables de suivi — `Probleme`, `Transition`, `Session`, `FicheRemediation` (module 7, D-CEO-43) |
| `backend/app/services/etats.py` | `changer_etat()` — cycle de vie d'un `Probleme`, cœur du dispositif |
| `backend/app/services/session_service.py` | `inscrire()` et `calculer_palier()` — inscription au programme, palier A/B/C |
| `backend/app/services/plan.py` | Plan de remédiation — tri topologique sur les prérequis, coût, palier (module 6) |
| `backend/app/services/fiche_remediation.py` | Fiche de travail — compétence × type d'erreur × niveau, catalogue versionné (module 7, D-CEO-43) |
| `backend/app/services/couts.py` | Formule de coût — arrondi 0,5 h, plancher 0,5, plafond 4, volume de repli lycée (D-CEO-29) |
| `backend/app/services/contexte.py` | Ancrage du diagnostic reconstruit depuis le référentiel (D-CEO-30) |
| `backend/app/services/diagnostic_referentiel.py` | **Diagnostic contraint (module 4)** — QCM court-circuités sans appel de modèle, codes admis par question, rejet et redemande. `reponses_depuis_correction()` est le point d'entrée en production : il reprend les réponses de la correction déjà faite (D-CEO-38) |
| `backend/app/services/diagnostic_suivi.py` | Écriture des problèmes du module 4 en `hypothese` — refuse d'écrire dans une évaluation du corpus |
| ~~`suivi/mesure.py`~~ | **Supprimé au retrait de Django (D-CEO-42/43), pas de commande FastAPI équivalente.** Écart module 4 ↔ corpus (exacts, compétence juste/type faux, manqués, en trop, écart de coût) — récupérable via `git show main:suivi/mesure.py` |
| `backend/app/services/niveaux.py` | Ordre des niveaux — une seule définition, partagée par le tagage du corpus et le diagnostic |
| `prompts/diagnostic_contraint_prompt.md` | Prompt du diagnostic contraint — aucun champ de prose dans la sortie |
| `backend/app/auth/deps.py` | Authentification nom+PIN adossée au Sheet — cookie de session (clé opaque en base), dépendances FastAPI (`connexion_requise`/équivalents) |
| `backend/app/routers/corrections.py` | Flux de correction — copie unique, lot, mode libre ; état en base, pas en session |
| `backend/app/auth/tokens.py` | Jetons signés dans les URL à la place de `identifiant_hakili` (D-CEO-25) |
| `backend/scripts/importer_referentiel.py` | Import idempotent du classeur (`make importer`) |
| `src/pipeline/depot.py` | Contrat de persistance du pipeline — 4 méthodes, aucun framework (D-CEO-40) |
| `backend/app/depot.py` | Son implémentation FastAPI (`DepotFastAPI`), installée dans `app/main.py::lifespan`. Opérations **rejouables** : le retry du pipeline en dépend |
| `src/integrations/google_sheets.py` | Source de vérité identité élèves/personnel |
| `src/services/auth_service.py` | Authentification nom+PIN par rôle |
| `src/core/tendance.py` | Calcul de tendance (pattern à réutiliser pour les indicateurs module 9) |
| `src/core/centre_normalizer.py` | Dérivation des centres depuis les Sheets |
| `docs/decision_register.md` | Toutes les décisions actives et datées — source de vérité |
| `docs/cycle_de_suivi.md` | **Le cycle T0→T5 en détail** — états d'un problème, règles de décision, ce que le cycle produit. Fait foi sur le déroulé |
| `docs/audit_donnees.md` | Audit de la base et de la connaissance — constats classés par gravité, plan en 9 étapes |
| `docs/v2_roadmap.md` | Chantier v2 — avancement détaillé, jalons, journal de bord — source de vérité sur "où en est-on" |
| `docs/harmonisation_donnees.md` | Écart ancien système ↔ référentiel v2 — arbitrages en attente, défauts constatés. **À lire avant le module 1** |
| `deploy/README.md` | **Guide de déploiement (livraison commanditaire)** — VPS Hetzner **partagé** (Docker + Caddy déjà en place) : pré-requis, premier déploiement, mises à jour, retour arrière, dépannage |
| `deploy/Dockerfile` · `deploy/entrypoint.sh` · `deploy/deploy.sh` · `deploy/caddy_snippet.txt` | Image (API + frontend buildé, un conteneur), démarrage (`alembic upgrade` + uvicorn), script git pull → build → conteneur, bloc reverse proxy Caddy |
| `deploy/bascule_neon.md` | Procédure unique d'adoption du schéma Neon existant par Alembic (`alembic stamp head`) — à faire avant le premier démarrage réel |
| `docs/deploiement.md` | **Historique** — mise en service Railway/Render (hébergeur précédent) ; conservé pour le raisonnement sur variables d'environnement et données de mineurs |
| `docs/architecture_cible.md` | Recommandation de sortie de Streamlit — **appliquée** (D-CEO-39), valeur historique |
| `docs/accents_a_corriger.md` | Généré — liste des accents à corriger dans le classeur, à remettre au docteur |
| `guide-v2.md` | Chantier v2 — les 9 modules, détaillés |
| `protocole-v2.md` | Chantier v2 — vocabulaire, taxonomie, protocole T0-T5 |
| `Referentiel_Socle_v0.xlsx` | Classeur référentiel — compétences, types d'erreur, grille de diagnostic, coûts |

---

## Dette documentaire connue

`README.md` décrit un état du produit antérieur à D-CEO-16 : tableau de validation "à construire", aucune mention de Postgres, des Sheets, de l'authentification ni de Django. C'est le dernier document périmé du projet — `AGENTS.md` et `docs/implementation_plan.md`, qui portaient la même erreur, ont été supprimés au nettoyage du 2026-07-30.
