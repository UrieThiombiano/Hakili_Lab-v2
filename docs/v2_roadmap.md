# Feuille de route — Chantier v2 (suivi structuré)
**Document de pilotage — fait foi pour l'avancement.** `CLAUDE.md` renvoie ici pour le détail ; ce fichier est la seule source de vérité sur "où en est-on" — ne pas dupliquer le suivi ailleurs.

**Dernière mise à jour :** 2026-08-13 (arbitrage H clos — les 7 `bareme_socle_*.yaml` (6eme à tleD) reconstruits à la main sur la structure à 3 parties, sans attendre la mise à jour du classeur)

⚠ **Ce document n'a pas suivi D-CEO-42/D-CEO-43** (2026-08-20/22) : Django est **retiré** depuis le 2026-08-21 (FastAPI + React seule interface, commit "retire Django"), et le module 7 (ci-dessous) est construit. Tout ce qui suit qui mentionne `manage.py`, Django ou "interface migrée sur Django" décrit un état antérieur — se fier à `git log` et à D-CEO-42/43 (`docs/decision_register.md`) pour l'état réel, pas à cette ligne de résumé, non retouchée pour rester un historique daté.
**Où en est-on (résumé en une ligne) :** Modules 0, **1 et 3 ✅ faits** · **Module 2 ⛔ supprimé le 2026-08-05** — trois copies 5e réelles imprimées et scannées l'ont mis en défaut (les trois refusées, dérive jusqu'à 3 cm), et il reconstituait par la géométrie une correspondance que la correction produit déjà ; au passage le risque du tramage est levé, l'imprimante n'imprime pas les bandes de guidage du tout · **Module 4 🟨 le moteur tourne et il est branché** — `manage.py diagnostiquer --correction <id>` reprend une copie déjà corrigée, sans lecture ni appel de modèle supplémentaire, QCM court-circuités, décision enseignant prioritaire · **Module 5 🟨 amorcé le 2026-08-07** — génération du sujet T1 et confirmation automatique (dépôt de copie → correction → confirmé/écarté) branchées de bout en bout, jamais essayées en conditions réelles · **Module 6 🟨 le plan et le palier tournent** · **interface migrée sur Django**. **Arbitrage B fermé le 2026-08-12 : les 7 corrigés sont relus et validés par un enseignant de mathématiques** (`data/Documents/corriges/`) — c'est la relecture que `00_Notice` exigeait avant de figer le référentiel. **Arbitrage H fermé le 2026-08-13 : les 7 `bareme_socle_*.yaml` (6eme à tleD) reconstruits à la main** sur la structure à 3 parties des sujets recomposés — le classeur `Referentiel_Socle_v0.xlsx` reste non modifié, ces 7 fichiers font foi en avance sur lui (détail `docs/harmonisation_donnees.md`). **Les 3 copies réelles 5e ont été corrigées et diagnostiquées** (`manage.py verifier_installation --copie … --eleve …`, le contrôle qui n'avait jamais été passé) — mais la **mesure juste** du module 4 reste à faire : ces 3 copies n'ont pas de tagage manuel, il n'y a donc rien à comparer pour l'instant. Les seuils de palier A/B/C **n'ont toujours pas été rejugés** après la hausse de ~33 % des coûts.

**État vérifié le 2026-08-05 : 275 tests Django + 239 pytest = 514 tests passent.** ⚠ Avant la prochaine mise en ligne : `migrate suivi 0007 --fake` une fois sur Neon (D-CEO-40, `docs/deploiement.md`).

✅ **Le fichier de clé JSON du compte de service Google a été déposé** dans
`Hakili_Lab/credentials/` — `verifier_installation` confirme les Sheets
joignables (85 élèves, 87 personnes) le 2026-08-06. Le point qui bloquait
l'usage de l'interface est levé.

**Pour reprendre le travail sur Django :**
```bash
DEBUG=true DATABASE_URL="sqlite:///:memory:" python manage.py test         # les 253 tests Django
DEBUG=true python manage.py importer_referentiel --a-blanc                 # contrôle sans écriture
DEBUG=true python manage.py runserver                                      # admin sur /admin/
DEBUG=true python manage.py verifier_installation                          # contrôle avant mise en service
```
Note : `DATABASE_URL` suit la convention SQLAlchemy — `sqlite:///:memory:`, **trois** barres.

> ✅ **Le manque qui pesait — détail dans `docs/harmonisation_donnees.md`.** Le référentiel ne contenait **aucune bonne réponse** pour 209 questions non-QCM, ce qui bloquait les modules 3 à 9. **Corrigés relus et validés par un enseignant de mathématiques le 2026-08-12** — 7 PDF complets dans `data/Documents/corriges/`, c'est la validation `00_Notice` qui manquait. Arbitrage B ✅ fermé.
>
> ⚠️ **Mais cette livraison a révélé un nouveau problème (arbitrage H, 2026-08-12) : les 7 sujets recomposés (structure Automatismes/Savoir-faire/Raisonnement) ne correspondent plus à `bareme_socle_*.yaml`** (généré le 2026-08-07, resté sur l'ancienne structure à 2 parties — le classeur `Referentiel_Socle_v0.xlsx` n'a pas changé). 11 à 14 items par niveau reclassés/repondérés, 4 à 6 nouveaux problèmes de synthèse sans `RubricItem`. Tranché avec l'utilisateur : régénérer depuis le classeur mis à jour — **mise à jour du classeur et relance de `scripts/generer_baremes_socle.py` restent à faire.** Détail chiffré : `docs/harmonisation_donnees.md`, arbitrage H.
>
> Arbitrages rendus : **A** (archivage), **D** (barème /20), **G** (source = le classeur), **B** (corrigés validés, 2026-08-12), **H** (les 7 niveaux `socle_6eme` à `socle_tleD` reconstruits à la main, 2026-08-12/13 — clos ; le classeur lui-même n'est plus dans le chemin critique, décision utilisateur). En attente : **C** (curriculum RAG), **E** (volumes lycée), **F** (format `construction`).

---

## Comment reprendre le travail (lire ceci en premier, à chaque session)

1. Lire la ligne "Où en est-on" ci-dessus.
2. Lire les 3 dernières entrées du **Journal de bord** (fin de ce document) — elles disent ce qui a été fait, ce qui a été décidé, et ce qui bloquait à la fin de la dernière session.
3. Ouvrir le module marqué 🟨 (en cours) dans le tableau ci-dessous, ou le premier ⬜ si aucun n'est en cours. Reprendre à la première sous-tâche non cochée.
4. Avant de coder quoi que ce soit sur ce chantier : relire `protocole-v2.md`, `guide-v2.md`, et la section "Chantier en cours" de `CLAUDE.md`.
5. **À la fin de la session** (même partielle) : cocher les sous-tâches faites, mettre à jour le statut du module concerné, mettre à jour la ligne "Où en est-on", et ajouter une entrée au Journal de bord. Un module qui progresse sans que ce fichier soit mis à jour est une session perdue pour la suivante.

---

## Vue d'ensemble

| # | Module | Statut | Bloqué par |
|---|---|---|---|
| 0 | Appropriation du référentiel | ✅ Fait (2026-07-30) | — |
| 1 | Socle de données (Neon, Django) | ✅ Fait (2026-07-30) | — |
| 2 | ~~Lecture des copies par zones~~ | ⛔ **Supprimé (2026-08-05, D-CEO-38)** — remplacé par la reprise de la correction | — |
| 3 | Corpus de référence | ✅ Fait (2026-07-31) — 5 copies, 66 problèmes | — (PRQ et RED non couverts, voir la fiche) |
| 4 | Diagnostic contraint | 🟨 En cours (2026-08-05) — moteur fait, **branché sur la correction** | La mesure juste : reste à corriger les 3 copies 5e puis à comparer |
| 5 | Composition du test de confirmation (T1) | 🟨 En cours (2026-08-13) — génération du sujet et confirmation automatique branchées, désormais ancrées sur `remediation/` (D-CEO-41, `reference_pedagogique`), toujours jamais essayées en conditions réelles | Module 4 |
| 6 | Palier et plan de remédiation | 🟨 En cours (2026-07-30) — moteur fait, séances à planifier | Module 4 pour l'alimenter en vrais problèmes |
| 7 | Génération des fiches | ⬜ À faire — matière première désormais disponible (D-CEO-41 : `RemediationRetriever`, 79 modules, 2 838 exercices corrigés), le générateur lui-même reste à construire | Module 6 |
| 8 | Interfaces de saisie | 🟨 Amorcé — admin sur les 11 tables + écran de parcours/inscription | Module 1 (peut démarrer en parallèle dès que le socle existe) |
| 9 | Restitution et indicateurs | ⬜ À faire | Module 1, 6, 7, 8 |

Légende : ⬜ à faire · 🟨 en cours · ✅ fait · 🔴 bloqué (voir colonne "Bloqué par" ou Journal)

---

## Jalons de validation (go/no-go — ne pas franchir sans eux)

- **Avant le Module 4 en conditions réelles :** Module 3 doit avoir produit au moins 5 copies entièrement taguées et marquées corpus de référence.
- **Avant tout déploiement du Module 4 auprès d'un enseignant :** 100 sorties consécutives valides (aucun code hors référentiel) + écart mesuré et consigné entre le diagnostic automatique et le tagage manuel du corpus.
- **Avant de couper l'ancien diagnostic texte libre pour un niveau donné :** le Module 4 doit être validé sur ce niveau précis (le remplacement se fait niveau par niveau, pas globalement — voir `CLAUDE.md`).
- **Avant toute perspective commerciale institutionnelle :** point ouvert #4 ci-dessous (données personnelles de mineurs) doit être traité, pas seulement noté.

---

## Détail par module

### Module 0 — Appropriation du référentiel ✅ **FAIT (2026-07-30)**
**Objectif :** savoir lire le classeur avant d'écrire la moindre ligne de code qui s'en sert.

- [x] Parcourir les 9 onglets de `Referentiel_Socle_v0.xlsx` dans l'ordre, en commençant par `00_Notice`.
- [x] Prendre le test d'entrée en 3ème, choisir 3 questions (dont ≥1 QCM) → **L5** (QCM), **L7** (court), **G13** (rédigé, partie B).
- [x] Pour chacune, retrouver : compétence canonique, signatures d'erreur, types d'erreur des distracteurs, coût de remédiation.
- [x] Répondre à la question de contrôle.

**Réponse à la question de contrôle** — *un élève coche l'option a) à la question L5 du test de 3ème :*
> L5 = « Développer (2x−3)² », format QCM, compétence canonique **`L.IDR`** (Identités remarquables : développement, introduite en 4ème, volume officiel 2 h).
> Option a) = `4x² + 9` → `06_Distracteurs` la tague **`CPT`** (« oubli complet du double produit : (a−b)² traité comme a²+b² »).
> **Problème à créer : `L.IDR × CPT`**, en état `hypothese`, avec sa ligne dans `transition`.
> **Coût : 0,5 h** (`08_Cout_remediation` : 2 h × 0,35 = 0,7 h → arrondi à la demi-heure = 0,5 h).
> Aucun appel LLM n'est nécessaire : la lettre cochée suffit.

**Vérifications d'intégrité effectuées sur le classeur (utiles au module 1 — l'import peut compter dessus) :**
- 280 questions = 7 tests × 40, toutes rattachées à une compétence existante (0 code inconnu).
- 1031 signatures, 280/280 questions couvertes, 3 à 4 signatures par question ; 0 type d'erreur inconnu, 0 compétence inconnue.
- 284 options QCM, 0 type d'erreur inconnu.
- `07_Couverture` : 116 lignes, **écart = 0 partout**.
- Règle du protocole « RED uniquement en partie B » : **respectée** (68/68 signatures RED en partie B).
- Répartition des signatures : CPT 345 · PRC 233 · CNS 134 · ATT 101 · PRQ 92 · RED 68 · MOD 58.
- Le piège des codes locaux est réel et vérifié : `N-a` désigne **7 compétences canoniques différentes** selon le test (N.NUM en 6ème, N.DIVIS en 4ème, N.ENS en 3ème, N.RAC/N.PUI/N.VAB en 1ereD/tleD…). Un code local peut aussi pointer vers **plusieurs** codes canoniques (`L-a → L.DEV1 ; L.IDR`).

**Trois points remontés (à trancher par l'utilisateur / le docteur, pas par l'implémentation) :**
1. **`08_Cout_remediation` contient 444 = 74 × 6 lignes, pas 101 × 7.** Deux exclusions structurelles, toutes deux légitimes mais qui doivent être gérées explicitement dans le code : `ATT` n'a **aucune** ligne de coût (non remédiable, coefficient 0) — le module 6 doit traiter `ATT` comme coût 0, **pas** comme « ligne manquante = erreur » ; et les **27 compétences du lycée** (15 en 2ndeC, 12 en 1ereD) ont un volume horaire `"non disponible"` et donc aucun coût — un problème diagnostiqué sur une compétence de lycée **ne peut pas être chiffré aujourd'hui**, ce qui bloque le calcul de palier (module 6) pour ces niveaux. C'est le point ouvert #2 ci-dessous, mais son impact concret est plus large qu'annoncé : il ne dégrade pas seulement la précision, il empêche le palier A/B/C d'être calculé pour un élève de 2ndeC ou 1ereD.
2. **Un 4ème format de question existe : `construction` (7 questions).** `guide-v2.md` (module 2) ne décrit que 3 formats de cadre (QCM 1 ligne, court 2 lignes, rédigé 8 lignes). Les 7 questions `construction` (toutes en partie B, barème 3, une par niveau de la 6ème à la 3ème) attendent un **tracé géométrique** (règle/compas), pas du texte. Le module 2 doit prévoir ce cas, et le module 4 ne pourra vraisemblablement pas le diagnostiquer automatiquement — à orienter vers la saisie humaine (module 8).
3. **`ATT` apparaît 2 fois en partie B** alors que le protocole présente l'inattention comme un phénomène de partie A (99 des 101 signatures ATT y sont). Anomalie mineure, sans doute volontaire — signalée pour mémoire, ne bloque rien.

**Critère de fin :** ✅ atteint — la question de contrôle a une réponse immédiate et tracée jusqu'au classeur.
**Fichiers concernés :** aucun (exercice manuel, aucun code produit).

---

### Module 1 — Socle de données (Neon/Postgres) ✅ **FAIT (2026-07-30)**
**Objectif :** les 11 tables du guide, greffées sur la base Postgres existante — pas de SQLite séparée (décision actée, voir `CLAUDE.md`).

> ⚠ **Écart avec le plan initial : le module a été fait en Django, pas en SQLAlchemy.** Cette fiche prescrivait des modèles dans `src/db/models.py` et une révision Alembic ; la décision de migrer l'interface vers Django (D-CEO-28) a été prise le même jour, et les 11 tables ont été créées comme apps Django (`referentiel/`, `suivi/`) avec les migrations Django. `src/db/models.py` **n'a pas été touché** et garde ses deux seules tables, `copie` et `document`, sous SQLAlchemy/Alembic. Les deux ORM cohabitent sur la même base Neon sans recouvrement d'écriture. C'est la raison pour laquelle `Evaluation.copy_id` est un champ texte et non une FK.

- [x] **Barème sur 20** (décision D) : `question.bareme` en `DecimalField(max_digits=8, decimal_places=6)`, converti à l'import par `bareme_classeur / 3` (partie A → 0,3333 ; partie B → 1,0). `bareme_classeur` conserve la valeur d'origine entière.
- [x] **Règle de calcul du score, à appliquer partout :** la note se calcule contre la **somme réelle des `max_score`**, jamais contre un total déclaré en métadonnée. C'est la condition pour qu'une copie parfaite vaille exactement 20/20 malgré les tiers de point — et c'est aussi le correctif du bug §5.1 de `harmonisation_donnees.md`.
- [x] Les 4 tables référentiel : `Competence`, `Prerequis`, `TypeErreur`, `CoutRemediation` — dans `referentiel/models.py`.
- [x] Les 3 tables banque de questions : `Question`, `SignatureErreur`, `OptionQcm`. Les colonnes `question.reponse_attendue` et `question.solution` ont été prévues **dès la première version, même vides** — l'arbitrage B est toujours en attente, mais aucune migration corrective ne sera nécessaire quand les 209 corrigés arriveront.
- [x] Les tables suivi : `SessionSuivi` (nom retenu pour éviter l'ambiguïté avec la session Streamlit), `Evaluation` (lien souple vers `Copie.copy_id`), `Reponse`, `Probleme`, `Transition`, `Seance` — soit 6 tables. `eleve` est *exclue*, l'identité restant dans les Sheets (D-CEO-20).
- [x] Contraintes en base : `evaluation.type` ∈ {T0..T5}, `probleme.etat` ∈ {hypothese, confirme, ecarte, en_remediation, resolu, non_resolu, regresse, clos}, `session_suivi.palier` ∈ {A, B, C} — par `TextChoices` + `CheckConstraint` Django, pas par `Enum` Postgres natif (ce qui évite du même coup le piège du `DROP TYPE` au `downgrade`, rencontré en D-CEO-20/21).
- [x] Cycle descente/remontée des migrations testé, comme sur les migrations Alembic précédentes du projet.
- [x] **`Transition` protégée par le code, pas par la discipline** : `Probleme.changer_etat()` refuse un enchaînement non prévu et écrit la transition dans la même opération atomique ; `Transition.save()` refuse toute modification après création ; l'admin met `etat` en lecture seule pour qu'on ne puisse pas contourner la méthode.
- [x] Import idempotent : `manage.py importer_referentiel` (pattern de `seed_users.py`, option `--a-blanc`), lit les 9 onglets via `openpyxl`, upsert par code. Contrôle d'intégrité **avant** toute écriture — un code inconnu fait échouer l'import avec un message précis, plutôt que d'écrire à moitié.
- [x] Import passé contre le classeur réel, compteurs vérifiés : **7 types · 101 compétences · 136 prérequis · 280 questions · 1031 signatures · 284 options QCM · 71 QCM corrigés · 209 sans corrigé**. Chiffres identiques au module 0. *(Les coûts étaient 444 à cette date ; ils sont passés à **606** depuis — 444 officiels + 162 estimés par le repli lycée, D-CEO-29.)*
- [x] **Support SQLite ajouté** à `DATABASE_URL` pour que tests et intégration continue tournent sans Neon ; la production reste sur Neon. Réglages Neon repris de D-CEO-19 : `CONN_HEALTH_CHECKS` (= `pool_pre_ping`) et `CONN_MAX_AGE=300` (= `pool_recycle`).

**Critère de fin :** ✅ atteint — l'import remplit les 7 tables référentiel/banque de questions sans erreur, et **le parcours complet T0→T5 d'un élève fictif avec toutes ses transitions** est couvert par les tests. Vérifié en base : `L5` du test de 3ème redonne exactement la réponse du module 0 (`L.IDR × CPT`, bonne réponse `d`, distracteurs tagués CPT/PRC/PRC).
**Fichiers concernés :** `referentiel/models.py`, `suivi/models.py`, `referentiel/migrations/`, `suivi/migrations/`, `referentiel/management/commands/importer_referentiel.py`, `hakili/settings.py`. **Pas** `src/db/models.py`.

**Deux décisions de conception prises en cours de route, à ne pas défaire par mégarde :**
1. **Les settings Django ne lisent pas `src/core/config.py`** — `Settings()` exige `anthropic_api_key` sans défaut, ce qui ferait échouer `manage.py migrate` sur une machine sans clé LLM, alors qu'une migration n'appelle aucun modèle.
2. **`Evaluation.copy_id` est un champ texte, pas une clé étrangère.** Tentée d'abord en FK vers une `Copie` non gérée : Django ne crée pas les tables non gérées en base de test, donc toute insertion échouait, et le contournement ne marche pas non plus (les migrations figent `managed: False`). Le lien souple est de toute façon le bon choix — c'est le précédent de `identifiant_hakili` (D-CEO-20). Deviendra une vraie FK si `copie` passe un jour sous Django.

---

### Module 2 — Lecture des copies par zones ⛔ **SUPPRIMÉ (2026-08-05, D-CEO-38)**
**Ce module n'existe plus. Ne pas le reconstruire sans lire D-CEO-38 en entier.**

**Ce qu'il devait faire :** transformer un sujet rempli et scanné en une liste
`(code_question, image_de_la_réponse)`, pour que le module 4 dispose de la
réponse à *une* question isolée.

**Pourquoi il a été retiré.** Trois copies réelles de 5ème — imprimées,
composées, scannées à 200 DPI — sont passées dans la chaîne le 2026-08-05.
**Les trois ont été refusées, aucune n'était découpable.** La cause a été
mesurée et elle n'est pas réparable par un réglage : après impression laser et
numérisation, le bord d'un cadre ne subsiste qu'entre 243 et 248 contre un
papier à 251,6, alors qu'il est à 121–156 dans le PDF. Le seuil d'encre du
recalage (140) ne le voyait jamais et s'accrochait au texte imprimé — échelle
fausse jusqu'à −10 %, soit **85 pt (3 cm) de dérive** en bas de page, et **4
pages sur 10 acceptées** avec 20 à 35 pt de décalage. Une zone découpée
attrapait l'énoncé imprimé et perdait le bas de la réponse ; ailleurs les cadres
tombaient une question plus bas, chacun contenant de l'écriture — donc sans que
rien n'ait l'air anormal.

Le fond du problème n'est pas ce seuil : c'est que ce module faisait dépendre le
diagnostic de la **géométrie d'un objet physique** qu'on ne maîtrise pas.
Impression sans réduction, scan droit, bon nombre de pages dans le bon ordre,
cadres survivant au toner. En production de masse, aucune de ces conditions
n'est tenable, et chacune était un refus de copie.

**Ce qui le remplace était déjà en service.** La correction lit la copie page
entière et rend, pour chaque question du barème, ce que l'élève a écrit
(`observed_answer`) et si c'est juste. L'identifiant d'item du barème **est** le
code de question du référentiel : la correspondance existait déjà, sans
géométrie et sans appel de modèle supplémentaire. Voir
`referentiel.diagnostic.reponses_depuis_correction()`.

**✅ Le risque du tramage est levé, dans l'autre sens.** C'était la question
ouverte depuis le 1er août. Mesuré : à l'intérieur d'un cadre, le scan est
uniformément blanc (moyenne 251,6, écart-type 1,1, **0,00 % de pixels sous
200**) là où le PDF porte des gris à 191–246. L'imprimante n'a pas tramé les
bandes de guidage — elle ne les a pas imprimées. Il n'y avait rien à filtrer.

**Supprimé :** `src/pipeline/zones.py` (893 lignes), `tests/test_zones.py`
(578), `_lire_zones` et `PipelineResult.zones`. **Conservé :**
`HakiliTest.formats` — le format d'une question décide de ce que le diagnostic
peut en faire.

**Ce que ça change pour les sujets :** rien à l'impression. Les cadres et les
codes restent utiles à l'élève et à la lecture, mais ils ne sont plus une
dépendance du diagnostic.


---

### Module 3 — Corpus de référence ✅ **FAIT (2026-07-31)** — avec une limite à connaître
**Objectif :** un jeu de copies taguées à la main pour mesurer objectivement le Module 4.

- [x] **Marquer les copies du corpus** — `Evaluation.corpus_reference`, avec `tague_par` et `date_tagage`. Une contrainte en base refuse un marquage sans auteur ni date : on ne saurait ni qui interroger sur un tagage discutable, ni à quelle version du référentiel il se rapporte. *(Le module 1 avait laissé ce point « à définir ».)*
- [x] **Deux champs ajoutés à `Probleme`**, dont le module 4 a besoin autant que le module 3 : `evaluation_origine` (la passation qui a révélé le problème) et `justification` (ce qu'on a lu sur la copie). La justification est ce qui rend un désaccord entre le corpus et le module 4 **arbitrable**, au lieu d'un simple écart de comptage.
- [x] **Outil de saisie : `manage.py taguer_corpus --fichier …`** (arbitrage rendu : un fichier YAML plutôt qu'un écran — le tagage est lent et discutable, un fichier se relit, se compare et se reprend le lendemain ; un formulaire perd tout à la première fermeture d'onglet). Options `--a-blanc` et `--remplacer`.
- [x] **Validation complète avant toute écriture** : aucun code inventé, justification obligatoire, `ATT` non confirmable, couple en double refusé. Un corpus à moitié écrit serait pire que pas de corpus — il aurait l'air complet.
- [x] Rassembler ≥5 anciennes copies d'élèves Hakili Lab — **5 réunies** (2 en 3ème, 2 en 5ème, 1 en 6ème).
- [x] Taguer les 5 copies — **fait**. 66 problèmes, 70 h de remédiation cumulées.

| copie | niveau | problèmes | coût | profil dominant |
|---|---|---|---|---|
| `CORPUS-3E-01` | 3ème | 22 | 34,5 h | CPT — effondrement conceptuel |
| `CORPUS-3E-02` | 3ème | 10 | 8,5 h | PRC / ATT — gestes ratés |
| `CORPUS-5E-03` | 5ème | 14 | 12,5 h | CNS — connaissances absentes |
| `CORPUS-5E-04` | 5ème | 9 | 7,0 h | PRC — exécution |
| `CORPUS-6E-05` | 6ème | 11 | 7,5 h | CNS (8/11) — vocabulaire et formules |

**⚠ Deux types d'erreur ne sont pas couverts : `PRQ` et `RED`.** Le module 4 ne pourra pas être mesuré sur eux, et ce n'est pas un défaut de tagage :
- **`RED`** est réservé par le référentiel à la partie B, « où la consigne précise que la démarche est évaluée autant que le résultat ». Les tests de l'ancien format ne posent jamais cette consigne. Il faudra des copies du **nouveau format**.
- **`PRQ`** demande un échec corrélé sur des compétences partageant un prérequis *nommable*. Sur les cinq copies, les échecs ne convergent vers aucun ancêtre commun : le graphe des prérequis est trop maigre. C'est un défaut du référentiel, pas des copies.
- [x] **Outil durci après trois copies** (voir le journal du 2026-07-31) : consultation du référentiel pendant le tagage, libellés rappelés au compte rendu, codes proches suggérés, contrôle de niveau, étanchéité avec le suivi réel, `manage.py corpus` pour relire l'étalon, rapport d'hésitations.
- [x] Pour chaque copie : relever chaque réponse fausse, chercher la signature correspondante dans `05_Grille_diagnostic`, noter le problème (`code_competence` + `code_type_erreur`) — fait sur les 5 copies, 66 problèmes.
- [x] Enregistrer chaque problème taggé dans les tables du Module 1 (`probleme` + `transition`) — fait, en état `hypothese` puis `confirme`, chaque transition écrite.
- [x] Noter chaque cas d'hésitation et pourquoi — fait : rapport d'hésitations produit par l'outil de tagage, ce sont des défauts potentiels du référentiel à remonter à l'utilisateur (pas à corriger seul, cf. `CLAUDE.md` "ce qui n'est pas de ton ressort").
- [x] Marquer explicitement ces copies comme « corpus de référence » — fait, voir ci-dessus.
- [ ] ⚠ **`PRQ` et `RED` resteront non couverts par ce corpus** — signalé par `manage.py corpus`. Ce **n'est pas une tâche de tagage à reprendre** : les deux manques sont structurels (détail deux paragraphes plus haut), `RED` demande des copies du **nouveau format** et `PRQ` un graphe de prérequis plus fourni. La case reste ouverte parce que la limite tient toujours, pas parce qu'il resterait des copies à taguer.

**Critère de fin :** au moins 5 copies entièrement taguées en base et marquées comme corpus de référence.
**Fichiers concernés :** `suivi/models.py` (marqueur + `evaluation_origine`, `justification`), `suivi/management/commands/taguer_corpus.py`, `referentiel/couts.py` (`cout_precalcule`), `data/corpus/exemple.yaml`.
**Tests :** `suivi/tests_corpus.py` (16).

**⚠ Une règle à ne pas enfreindre plus tard :** le module 4 **ne doit jamais écrire** dans les problèmes d'une évaluation marquée `corpus_reference`. La mesure se fait en comparant sa sortie à ces problèmes, pas en les mettant à jour — un étalon qu'on corrige au fur et à mesure ne mesure plus rien.

**⚠ Ce que le corpus ne peut pas porter pour une copie de l'ancien format.** `Reponse` exige une clé étrangère vers les 280 questions v2 : une copie de l'ancien format n'en a aucune, donc **aucune `Reponse` n'est enregistrable** pour elle. Seuls les `Probleme` le sont — et c'est suffisant, puisque le problème est précisément l'unité que le module 4 produit et contre laquelle il sera mesuré.

---

### Module 4 — Diagnostic contraint 🟨 **EN COURS (2026-08-01) — le moteur tourne**
**Objectif :** remplacer le rapport en texte libre par une liste de problèmes structurés.

- [x] **Format de sortie strict** : `(code_question, code_competence, code_type_erreur, citation)`, rien d'autre. Aucun champ de prose n'existe dans le schéma — c'est ce qui empêche le texte libre de revenir par la fenêtre.
- [x] **Les signatures d'erreur de la question sont fournies** au modèle (`signature_erreur`, 3 à 4 par question). Il reconnaît, il ne devine pas.
- [x] **Rejet et redemande.** Une sortie refusée n'est **jamais réparée à sa place** : les motifs lui sont rendus et on redemande une fois. Ce qui reste invalide est **écarté** — un problème inventé oriente une remédiation vers la mauvaise notion, une absence se rattrape.
- [x] **QCM entièrement court-circuités** — lettre cochée → `option_qcm` → type d'erreur. Un test échoue si le client est seulement *touché* pour un QCM. 71 des 280 questions ne coûtent donc rien et ne peuvent pas se tromper.
- [x] **Écriture dans `probleme`** en état `hypothese`, jamais `confirme` : c'est T1 qui tranche, pas un modèle de langage. Deux questions révélant la même lacune fusionnent en un problème (contrainte d'unicité par session) en conservant les deux citations.
- [x] **Le module 4 ne peut pas écrire dans une évaluation du corpus** — refus explicite, écriture atomique. Un étalon qu'on corrige au fur et à mesure ne mesure plus rien, et le défaut serait invisible : les chiffres s'amélioreraient tout seuls.
- [x] **Ce qui n'est pas diagnostiqué est nommé** (`questions_ecartees`) : construction géométrique, réponse illisible, QCM sans case cochée, modèle indisponible. Une question écartée en silence se lirait comme une réussite.
- [x] **Outil de mesure écrit** (`suivi/mesure.py`, option `--comparer`) : exacts / compétence juste mais type faux / manqués / en trop, précision, rappel, et **écart de coût en heures** — c'est le coût qui décide du palier, donc de ce qu'une famille paie.
- [x] **Mesure plancher écrite** (`manage.py mesurer_plancher`, `diagnostiquer_sans_ancrage`) — arbitrage rendu le 2026-08-01 : puisque le corpus ne peut pas alimenter le mode ancré, le modèle est mis à la tâche **plus dure** (production brute + catalogue du niveau, aucune signature). Comparaison loyale avec le tagage manuel, et plancher : le mode ancré ne peut que faire mieux.
- [x] **Transcription des 5 copies du corpus** (`data/productions/corpus_*.yaml`) — lue sur les scans, sans lire le tagage des copies 1 à 4. Les 5 fichiers passent la validation de format **et** le contrôle anti-recopie.
- [x] **Mesure plancher exécutée sur les 5 copies (2026-08-01)** — **rappel compétence 85 %, couple exact 65 %, précision 61 %** sur 66 problèmes. Tableau par copie et analyse au journal. **Le point dur est le type d'erreur, pas la compétence**, et `ATT` n'est jamais retrouvé — ce qui surfacture, puisque c'est le seul type à coût nul.
- [ ] 🔴 **Mesure en configuration de production** — attend des copies au nouveau format, voir ci-dessous.
- [x] **Point d'entrée en production — fait le 2026-08-05** (D-CEO-38) : `reponses_depuis_correction()` reprend les réponses de la **correction déjà faite**, et `manage.py diagnostiquer --correction <id>` les diagnostique. Aucune lecture supplémentaire de la copie, aucun appel de modèle en plus, et la décision de l'enseignant prime sur celle de l'IA pour dire ce qui est réussi. C'est ce qui a remplacé le module 2.
- [ ] **Déclenchement automatique** — toujours différé, et le motif n'a pas changé : tant que la mesure juste n'existe pas, rien ne s'approche d'un enseignant. Ce qui reste à trancher est plus étroit qu'avant, puisqu'il n'y a plus de surcoût d'appel : à quel moment du flux de correction le diagnostic part, et ce que devient le rapport en texte libre.
- [ ] Atteindre 100 sorties consécutives valides. Demande des clés d'API, et des copies au nouveau format.

**Critère de fin :** 100 sorties consécutives valides + écart diagnostic automatique / tagage manuel mesuré et consigné.
**Fichiers concernés :** `prompts/diagnostic_contraint_prompt.md`, `src/models/domain.py` (`ProblemeDetecte`, `DiagnosticContraint`), `src/api/claude_client.py` (`diagnose_constrained`, outil à `enum`), `referentiel/diagnostic.py` (moteur), `suivi/diagnostic.py` (écriture), `suivi/mesure.py` (écart), `suivi/management/commands/diagnostiquer.py`, `data/reponses/exemple.yaml`.
**Tests :** `referentiel/tests_diagnostic.py` (31) + `suivi/tests_diagnostic.py` (9) + `tests/test_diagnostic_contraint.py` (6).

#### Les trois barrières contre un code inventé
Aucune ne suffit seule, et c'est pour ça qu'il y en a trois :

1. **Le schéma de l'outil** déclare les codes admis en `enum` — un code hors référentiel devient très difficile à produire, au lieu d'être rattrapé après coup.
2. **La validation par question.** L'`enum` ne peut porter qu'**une** liste pour tout le tableau, alors que chaque question a la sienne (sa compétence et ses prérequis) ; il n'empêche donc pas d'attribuer à `L5` une compétence admissible pour `G13`. **C'est le seul contrôle qui attrape le cas réellement dangereux** — un code valide mais mal placé, qui passerait toute autre validation sans un mot.
3. **La redemande**, puis la mise à l'écart de ce qui reste invalide.

⚠ **Conséquence sur le jalon « 100 sorties consécutives valides » : il est en grande partie garanti par construction.** L'`enum` rend un code hors référentiel presque impossible à produire. Ce jalon ne prouvera donc pas grand-chose ; **c'est l'écart contre le corpus qui mesure quelque chose**, et lui seul.

#### 🔴 Le corpus ne peut pas mesurer ce module — cette feuille de route disait le contraire
La fiche du module 2 promettait que le module 4 « se mesurera d'abord sur le corpus de référence, qui est constitué de copies de l'ancien format ». **Ça ne tient pas, et il vaut mieux le savoir maintenant.**

Le diagnostic contraint travaille **par question** : il reçoit l'énoncé, la compétence évaluée, ses prérequis et ses signatures d'erreur, tous tirés des 280 questions v2. Une copie de l'ancien format n'en porte **aucune** — il n'y a rien à quoi rattacher ses réponses. C'est déjà pour cette raison que le module 3 ne peut enregistrer aucune `Reponse` pour ces copies ; la conséquence sur la mesure n'avait simplement pas été tirée.

**Arbitrage rendu le 2026-08-01 : les deux, en parallèle.** La mesure plancher est écrite et donne un signal sans attendre ; la mesure juste attend le sujet imprimé, qui est de toute façon nécessaire au module 2. L'option écartée : rapprocher les questions des anciens tests des compétences du référentiel — un travail du même ordre que l'arbitrage C, qui aurait introduit sa propre marge d'erreur **dans l'instrument de mesure lui-même**.

##### La mesure plancher, et le piège qu'elle désamorce
`manage.py mesurer_plancher --productions … --contre <évaluation>` donne au modèle la production brute de l'élève et le catalogue des compétences déjà enseignées à ce niveau (17 en 6ème, 63 en 3ème), **sans aucune signature d'erreur**. Le résultat se compare aux problèmes tagués à la main.

⚠ **Le piège, et il est facile à tendre :** alimenter la mesure avec `Probleme.justification`, déjà en base pour les 66 problèmes du corpus. Ces justifications sont écrites par le tagueur et portent le diagnostic en toutes lettres (« la formule est juste, seul le produit est faux ») — les donner en entrée revient à fournir la réponse avec la question. **Le score serait excellent et ne voudrait rien dire**, ce qui est le pire des cas : personne ne met en doute un bon chiffre. La commande compare donc chaque production aux justifications de l'étalon et **refuse de tourner** au-delà de 75 % de ressemblance. Vérifié : une justification recopiée est rejetée à 100 %.

**Ce qu'il reste à faire pour obtenir le chiffre :** ~~transcrire les 5 copies~~ — **fait le 2026-08-01** (`data/productions/corpus_3e_01`, `corpus_3e_02`, `corpus_5e_03`, `corpus_5e_04`, `corpus_6e_05`). Reste à installer les dépendances (`anthropic` n'est pas présent dans l'interpréteur courant) et à renseigner `ANTHROPIC_API_KEY`, puis à lancer les 5 commandes et à consigner l'écart ici.

##### Ce que la transcription a demandé de trancher, et qui n'était pas prévu
- **Les copies portent trois encres, pas une.** Bleu = l'élève, rouge = le correcteur, gris = les tracés au crayon. Seuls le bleu et le crayon sont transcrits. La consigne « recopier ce qui est écrit » ne suffisait pas : recopier le rouge aurait donné au modèle la correction en même temps que la production — le même piège que les justifications, par une autre porte.
- **`exemple.yaml` demande de ne pas faire figurer les questions réussies.** C'est appliqué, mais il faut savoir que ça durcit encore la tâche : le tagueur humain, lui, avait la copie entière et raisonne explicitement par contraste (« laissé vide *alors que* la question précédente est juste »). Le plancher est donc plus bas que le protocole ne le laisse croire. Le critère retenu pour inclure une question : réponse vide, ou réponse dont la fausseté se lit sans diagnostic (résultat faux, mot absent du sujet). Pas de jugement de compétence.
- **Deux passages n'ont pas été transcrits faute de lecture sûre** et c'est dit dans les fichiers : l'annotation de l'angle au rapporteur de `CORPUS-6E-05` (se lit « 40 » ou « 60 »), et deux des quatre égalités vectorielles de `CORPUS-3E-01`. Inventer une lecture pour compléter aurait mis une erreur dans l'instrument de mesure.
- **La copie 5 a été transcrite après lecture de son tagage** (sa fiche avait été ouverte plus tôt dans la session) ; les copies 1 à 4 l'ont été à l'aveugle. Si l'écart mesuré sur la copie 5 se détache nettement des quatre autres, cette asymétrie est la première explication à envisager.

#### Point d'entrée en production — **fait le 2026-08-05 (D-CEO-38)**
`manage.py diagnostiquer --correction <id>` part d'une copie **déjà corrigée** :
la correction a lu la page entière et relevé, pour chaque question du barème, ce
que l'élève a écrit (`observed_answer`) et si c'est juste. L'identifiant d'item
du barème **est** le code de question du référentiel (`D1`, `L5`…) — la
correspondance est directe.

**Le coût qui bloquait n'existe plus.** L'arbitrage du 2026-08-01 opposait
« en parallèle » (deux appels de modèle par copie, contre une cible de
~$0,02/copie) et « en remplacement » (couper un livrable qui marche). Reprendre
la correction ne coûte **aucun appel supplémentaire** : la lecture de la copie a
déjà eu lieu. Sur les QCM, il n'y a même aucun appel du tout — 71 questions sur
280.

Trois règles ont été posées en chemin, et elles valent d'être connues :
- **Les questions réussies ne sont pas soumises.** Le diagnostic cherche des
  lacunes ; une réussite n'en porte pas.
- **La décision de l'enseignant prime sur celle de l'IA** pour dire ce qui est
  réussi. Diagnostiquer une question que l'enseignant vient de valider
  produirait une lacune que personne ne constate.
- **« Illisible » n'est pas « rien écrit ».** Une lecture ratée est un trou : la
  question part en écartée, avec un motif qui dit à l'enseignant qu'il y a là une
  réponse à relire. Une zone vierge, elle, est un signal de diagnostic.

Ce qui reste à trancher est plus étroit : **à quel moment du flux** le
diagnostic se déclenche tout seul, et **ce que devient le rapport en texte
libre** — les modules 7 (fiches) et 9 (rapport) doivent arriver d'abord, sans
quoi on retirerait à l'enseignant un livrable qui marche pour une liste de codes
que rien ne met en forme. Le jalon go/no-go tient : rien ne s'approche d'un
enseignant avant l'écart mesuré.

---

### Module 5 — Composition du test de confirmation (T1)
**Objectif :** générer automatiquement un T1 qui départage les hypothèses, pas un T0 raccourci.

- [x] **Ancrage pédagogique (D-CEO-41, 2026-08-13)** — `ConfirmationHypothesis`/`VerificationItem` portent désormais `competence_code`, `niveau` et `reference_pedagogique` (méthode, erreurs fréquentes typées, un exemple travaillé, tirés de `remediation/` via `RemediationRetriever.get_by_competence()`), peuplés dans `correction_web/taches.py` (T1) et `suivi/generation.py` (T3/T4/T5). Avant cet ajout, le LLM ne recevait qu'un libellé de compétence et un libellé de type d'erreur — sans niveau ni exemple calibré, cause structurelle des sujets hors programme ou mal calibrés. Dégradé sans erreur si le rapprochement ne couvre pas la compétence (`reference_pedagogique = None`).
- [ ] Pour chaque problème en état `hypothese`, générer une question qui sépare deux causes possibles du même échec (ex. exécution simple vs lourde pour distinguer `CPT` de `PRC`).
- [ ] Rejeter toute question qui ne discrimine rien.
- [ ] Produire le sujet T1 au même format PDF que les tests d'entrée (cadres de réponse ancrés par code), pour que le Module 2 puisse le relire.
- [ ] À l'issue de T1, faire passer chaque problème à `confirme` ou `ecarte`, avec sa transition enregistrée.

**Critère de fin :** à partir d'une liste de problèmes en hypothèse, le module génère un sujet T1 imprimable dont chaque question est reliée à l'hypothèse qu'elle tranche.
**Fichiers concernés :** nouveau générateur (`src/pipeline/` ou module dédié), réutilise le moteur de génération PDF existant (`pdf_report_html.py` / équivalent).

---

### Module 6 — Palier et plan de remédiation 🟨 **EN COURS (2026-07-30) — moteur fait**
**Objectif :** passer des problèmes confirmés à un plan de travail chiffré.

- [x] Additionner les coûts (`cout_remediation`) des problèmes en état `confirme` pour une session donnée — `Session.cout_total_confirme`.
- [x] Traiter `ATT` comme coût **0**, pas comme une ligne manquante : `08_Cout_remediation` ne contient aucune ligne `ATT` par construction (non remédiable). `Probleme.cout_estime` vaut 0 par défaut, et le modèle refuse par ailleurs qu'un `ATT` soit confirmé ou remédié.
- [x] Gérer l'absence de coût pour les 27 compétences de lycée — **résolu par D-CEO-29** : volume de repli de 4 h, marqué `volume_estime` / `estime` pour qu'une valeur dérivée ne passe jamais pour un chiffre officiel. `CoutRemediation` passe de 444 à 606 lignes, le palier redevient calculable en 2ndeC/1ereD.
- [x] Déterminer le palier : A (<8h), B (8-20h), C (>20h — le dire clairement, ne pas proposer de plan voué à l'échec) — `Session.calculer_palier()`, et `inscrire()` **refuse** le palier C sans dérogation motivée et tracée (D-CEO-34).
- [x] Ordonner le plan selon le graphe des prérequis (`prerequis`) — tri topologique par couches dans `suivi/plan.py`, départagé à égalité par le niveau d'introduction (le plus fondamental d'abord). Un cycle dans le graphe ne fait pas boucler.
- [x] Écran de restitution : `/parcours/<jeton>/` affiche le plan ordonné, le volume, le palier, les hypothèses restantes et le bouton d'inscription (POST seulement).
- [ ] **Reste :** dérouler le plan en **séances** (`Seance` existe en base et dans l'admin, rien ne la remplit encore) — c'est ce qui manque au critère de fin.
- [ ] **Reste :** validation sur des données réelles — le moteur n'a encore tourné que sur des problèmes créés à la main, faute de Module 4.

**Critère de fin :** pour une session donnée, le module produit un plan ordonné, un coût total, un palier, et une séquence de séances respectant l'ordre des prérequis.
**Fichiers concernés :** `suivi/plan.py` (calcul), `suivi/models.py` (`calculer_palier`, `inscrire`), `suivi_web/views.py` + `templates/suivi_web/session_detail.html` (restitution), `referentiel/couts.py` (formule de coût).
**Tests :** `suivi/tests_plan.py` (12) + les tests de parcours de `suivi_web/tests.py`.

---

### Module 7 — Génération des fiches ✅ **CONSTRUIT (D-CEO-43, 2026-08-22)**
**Objectif :** une séance prête à l'emploi pour le tuteur, pas de la matière première.

- [x] **Matière première disponible (D-CEO-41, 2026-08-13)** — `RemediationRetriever.get_by_competence(code, niveau)` (`src/knowledge/remediation_retriever.py`) rend, par compétence canonique, une leçon de remédiation complète : méthode, erreurs fréquentes, exemple travaillé, et référence à un module de `remediation/` qui porte lui-même son propre pool d'exercices notés ★/★★/★★★ corrigés (`data/knowledge/remediation_<niveau>.yaml`).
- [x] Unité de fiche = compétence × type d'erreur (pas le chapitre) — `app/services/fiche_remediation.py::construire_contenu()`, cataloguée par couple compétence × type d'erreur × **niveau** (`FicheRemediation`, `suivi_fiche_remediation`), pas par élève : le même problème chez deux élèves rend la même fiche.
- [x] Contenu obligatoire : objectif, prérequis à vérifier (`referentiel_prerequis`, tous les prérequis directs — pas seulement ceux aussi en difficulté), méthode + exemple résolu, erreurs fréquentes, déroulé minuté (5 étapes fixes), exercices gradués (répartition 2 faciles/2 moyens/1 difficile via le nouvel accesseur `RemediationChunk.exercices_gradues()`, corrigés en clair — document lu par un tuteur), critère de réussite déterministe.
- [x] Génération à la demande, pour les problèmes `confirme`/`en_remediation` — `GET /api/sessions/{jeton}/problemes/{probleme_id}/fiche`, lien par étape dans `SessionDetail.tsx`. Refuse avec un message explicite (pas de fiche creuse) si le rapprochement ne couvre pas le couple compétence × niveau.
- [x] Versionnement : `PATCH` sur le même endpoint enregistre une correction tuteur (`version: generee → corrigee`) ; jamais régénérée automatiquement une fois cataloguée. Aucun écran dédié (hors périmètre des deux écrans du Module 8) — API seulement pour l'instant.

**Au passage (D-CEO-43) :** confusion de nommage corrigée — le PDF du plan (module 6) s'appelait « fiche de remédiation » (`pdf_plan_html.py`, endpoint `/fiche`), renommé « plan de remédiation » (`pdf_plan_html.py` inchangé de nom de fichier mais docstring/gabarit/endpoint `/plan` corrigés) pour ne plus se confondre avec la vraie fiche du module 7. Deux bugs de rendu/parsing réels trouvés et corrigés en testant sur données réelles : substitution LaTeX naïve dans `math_format.py` (`\le` mangeait `\left`) et chevauchement DÉCLIC/ATTENTION dans `remediation_parser.py` (YAML régénérés, mêmes totaux : 79 modules, 2838 exercices).

**Critère de fin :** une fiche générée est utilisable en séance sans retouche par un tuteur qui découvre le dossier — **atteint pour les couples couverts par le rapprochement** (encore partiel, voir D-CEO-41 : ~162/707 paires niveau × compétence).
**Fichiers concernés :** `app/services/fiche_remediation.py`, `src/pipeline/pdf_fiche_travail_html.py`, `templates/fiche_travail.html.j2`, `backend/app/models/suivi.py::FicheRemediation`, migration `a1b2c3d4e5f6`.
**Tests :** `backend/tests/test_fiche_remediation.py` (service), `backend/tests/test_routers_sessions.py` (endpoints).

---

### Module 8 — Interfaces de saisie 🟨 **AMORCÉ**
**Objectif :** deux écrans, pas davantage, intégrés à l'app existante.

- [ ] Écran 1 : saisie/correction des réponses d'une évaluation, copie découpée affichée à côté du champ. *(dépend du Module 2 pour la découpe ; le tableau de validation du pipeline existant en couvre déjà la moitié)*
- [ ] Écran 2 : fiche de séance tuteur, 5 champs (problèmes travaillés, blocage, déblocage, travail donné, appréciation), utilisable au téléphone en moins de 2 minutes.
- [x] Réutiliser l'auth déjà en place plutôt que créer un nouveau système d'accès — fait côté Django (`comptes/`, décorateurs `connexion_requise` / `admin_requis`).
- [x] Acquis en chemin, à ne pas refaire : l'**admin Django sur les 11 tables** couvre la consultation et la correction ponctuelle, et l'écran `/parcours/<jeton>/` porte déjà l'inscription au programme.
- [x] Acquis les 2-3 août, **hors de ce module** : un **système visuel unifié** dans `templates_django/base.html` (composants nommés, gamme de couleurs, échelles typographique et d'espacement) sur lequel les onze écrans existants ont été repris, et un **jeu d'identités factices** (D-CEO-37) qui rend les écrans travaillables sans les Sheets. Les deux écrans à construire ci-dessus s'appuieront dessus — ils n'en sont pas plus avancés pour autant.

> ⚠ **Ne pas confondre.** Le travail de présentation des 2-3 août ne coche aucune des deux premières cases : elles demandent des écrans qui **n'existent pas**, pas une meilleure mise en page de ceux qui existent. Le module reste amorcé, au même point qu'au 30 juillet.

**Critère de fin :** un tuteur remplit une fiche de séance depuis son téléphone en moins de 2 minutes ; une évaluation complète peut être corrigée à l'écran sans manipuler de fichier.
**Fichiers concernés :** `suivi_web/` et `correction_web/` (nouvelles vues et gabarits), sur le système visuel de `templates_django/base.html`.

---

### Module 9 — Restitution et indicateurs
**Objectif :** les deux documents qui donnent sa valeur au produit.

- [ ] Rapport de fin de remédiation (parents) : 2 pages, problèmes ouverts/résolus/restants, travail effectué.
- [ ] Tableau de bord interne, 5 indicateurs calculés depuis `transition` :
  - [ ] Taux de résolution à T3 (résolus / confirmés)
  - [ ] Taux de rétention à 45 jours (T4)
  - [ ] Taux de rétention à long terme (T5)
  - [ ] Taux de confirmation à T1 (confirmés / hypothèses) — sain entre 60 et 80%
  - [ ] Écart durée estimée / durée réelle par type d'erreur (recalibrage futur des coefficients)
- [ ] Réutiliser le moteur PDF existant (`pdf_report_html.py`) pour le rapport parents.
- [ ] Réutiliser le pattern de tableau de bord déjà validé (`src/core/tendance.py`, D-CEO-23) pour l'affichage des indicateurs.

**Critère de fin :** les deux documents se génèrent depuis la base sans aucune retouche manuelle.
**Fichiers concernés :** `src/pipeline/pdf_report_html.py` (nouveau template), `suivi_web/` (écran d'indicateurs).

---

## Points ouverts (hérités de `protocole-v2.md` §12 — à ne pas perdre de vue)

1. **Extension au-delà des maths** — quelles matières, dans quel ordre, taxonomie transposable ou non. Non tranché.
2. **Volumes horaires du lycée manquants** — ✅ **traité par D-CEO-29 (repli de 4 h), reste à confirmer par le terrain.** 74/101 compétences ont un volume officiel ; les 27 compétences de lycée (15 en 2ndeC, 12 en 1ereD) reçoivent 4 h — la médiane des volumes réels du collège — ce qui rend le palier de nouveau calculable sur ces niveaux (`CoutRemediation` : 444 officiels + 162 estimés = 606). **C'est une estimation et elle est marquée comme telle** (`volume_estime`, `estime`, mention orange dans l'admin, signalement `repose_sur_estimation` dans le plan) ; le classeur source continue d'indiquer « non disponible ». Reste à obtenir les vrais volumes — le remplacement sera trivial, et la feuille `04_Volumes_lycee` du lot à compléter le demande (arbitrage E).
3. **Tarification** — à poser avant toute mise à l'échelle. Non tranché, pas du ressort technique.
4. **Données personnelles de mineurs** — obligations à vérifier auprès de la CIL du Burkina Faso, consentement parental à prévoir dès le premier élève suivi dans ce dispositif. **Bloquant pour toute perspective commerciale institutionnelle.**
5. **Validation pédagogique** — le référentiel doit être relu par un enseignant de mathématiques avant d'être figé (`00_Notice` du classeur le dit déjà : "A VALIDER").
6. **Recalibration** — réviser les coefficients de coût après 20 sessions closes (dépend du Module 9, indicateur écart durée estimée/réelle).

---

## Lot à faire compléter par le relecteur pédagogique

Quatre manques du référentiel demandent tous un enseignant de mathématiques — et tombent dans le même passage que la validation pédagogique déjà exigée par `00_Notice` (« À VALIDER »). Ils ont été rassemblés en **un seul classeur pré-rempli**.

```bash
python scripts/generer_lot_a_completer.py       # produit Lot_a_completer_<date>.xlsx
# … le relecteur remplit les colonnes sur fond crème …
python scripts/integrer_corriges.py --lot ../Lot_a_completer_<date>.xlsx
python scripts/generer_baremes_socle.py          # les corrigés sont repris
```

| Feuille | Contenu | Arbitrage |
|---|---|---|
| `01_Corriges` | **209 questions sans réponse attendue** — le plus important | B |
| `02_Accents` | 150 mots à réaccentuer | — |
| `03_Accents_a_arbitrer` | 16 mots ambigus (« calcule » ou « calculé » ?) | — |
| `04_Volumes_lycee` | 27 compétences sans volume horaire | E |
| `05_Questions_construction` | 7 questions attendant un tracé : que vérifier ? | F |

**Le point de conception qui compte :** les corrigés saisis vont dans `data/knowledge/corriges_socle.yaml`, **séparé des barèmes**. `generer_baremes_socle.py` régénère les barèmes depuis le classeur source et les écraserait s'ils y étaient stockés — plusieurs heures de travail d'enseignant perdues au premier `git pull` suivi d'une régénération. Le générateur fusionne ce fichier séparé à chaque exécution.

**Vérifié** par un aller-retour complet avec un lot d'essai : saisie → réintégration → régénération, les corrigés survivent. L'anomalie « démarche saisie sans réponse attendue » est détectée et signalée (c'est la réponse qui sert à corriger, pas la démarche). Données d'essai supprimées après vérification.

Les feuilles 02 à 05 ne sont **pas** réinjectées automatiquement : elles corrigent le classeur source, qui appartient au docteur. Le script rapporte ce qui a été rempli pour qu'on sache quoi reporter.

---

## Rapprochement curriculum ↔ compétences (arbitrage C)

```bash
python scripts/rapprocher_curriculum.py --lot     # analyse + classeur à valider
python scripts/integrer_rapprochement.py --lot ../Lot_rapprochement_curriculum_<date>.xlsx
```

Écrit un `code_competence` dans chaque leçon des `curriculum_*.yaml` : le module 7 pourra alors retrouver le contenu pédagogique d'un problème `compétence × type d'erreur` sans jointure supplémentaire.

| Feuille | Lignes | Ce qu'on attend |
|---|---|---|
| `01_A_confirmer` | 31 | Proposition nette — un coup d'œil, O ou N |
| `02_A_trancher` | 85 | Ambigu — à décider une par une |
| `03_Sans_proposition` | 5 | Code, **ou « AUCUNE »** si le référentiel ne couvre pas la notion |
| `04_Competences_sans_lecon` | 76 | Pour information (dont 27 de lycée, hors couverture du curriculum) |
| `05_Notions_non_couvertes` | 5 | Lacunes constatées du référentiel — décision de fond |

### Trois constats qui valent plus que le rapprochement lui-même

**1. Quatre notions enseignées n'ont aucune compétence.** Vérifié par recherche exhaustive dans les libellés **et** les descriptions des 101 compétences : `probabilité`, `angle inscrit`, `similitude / figures semblables`, `variance / écart-type` sont absents. Un élève échouant sur ces notions **ne peut pas être diagnostiqué** aujourd'hui. Ce ne sont pas des échecs de rapprochement : il n'y a rien à rapprocher.

**2. Un décalage de niveau sur l'homothétie.** Le curriculum l'enseigne en 3e ; le référentiel place `G.HOM` (« Transformations du plan ») en 2nde C. L'un des deux se trompe, ou il s'agit de deux notions différentes.

**3. Deux signaux de rapprochement se sont révélés inutilisables**, et c'est documenté dans le script pour qu'on ne les réessaie pas : les **numéros de chapitre** (le curriculum écrit `Ch4` là où le classeur écrit `ch15` pour la même notion — les deux découpages ne coïncident pas) et les **domaines** (2 côté curriculum, 8 côté classeur). Seuls le libellé de leçon et la classe portent de l'information.

### Ce que l'outil fait, et ne fait pas
Il **propose**, il ne décide pas — le rapprochement est un jugement pédagogique. Un premier réglage ne donnait que 17 propositions nettes ; l'examen des cas rejetés a montré qu'ils étaient majoritairement corrects et que le vocabulaire différait systématiquement entre les deux sources (« fonction » contre « application », « fréquence » contre « statistique »). Une table d'équivalences relevée sur pièces — non devinée — a porté les propositions nettes à 31 et réduit les leçons sans candidat de 35 à 5.

Limite structurelle assumée : certaines compétences ont un libellé volontairement large (« Statistique du college », « Transformations du plan ») qui recouvre plusieurs leçons. Aucune ressemblance textuelle ne peut les reconnaître — elles sont signalées comme génériques pour que le relecteur sache qu'un rapprochement large est attendu, plutôt que de conclure à une lacune.

**Vérifié** par un aller-retour complet : acceptation, correction, réponse « AUCUNE », refus sans code de remplacement et code inexistant — les deux anomalies sont détectées et signalées, les curricula restaurés après essai.

---

## Journal de bord

### 2026-08-29 (suite) — Le sujet T1 n'était plus généré à la réanalyse d'une copie

Signalé par l'utilisateur : « les exos de confirmation de lacunes ne sont plus
générés après analyse ». Cause trouvée dans `app/services/taches.py::_ecrire_hypotheses_module4` :
le sujet T1 n'était généré que si le diagnostic du T0 **créait** au moins une hypothèse
(`ecriture.crees` non vide). Or réanalyser la copie d'un élève qui a déjà une session
ouverte (cas courant en test, et en production quand un collègue a déjà lancé un T0)
ne crée rien de neuf — tous les couples compétence × type d'erreur sont « déjà suivis » —
donc `_generer_sujet_confirmation` n'était jamais appelé, même quand aucun sujet n'existait.
Confirmé sur `dev.db` : session 16, évaluations T0 nº 12 et 13 du 2026-08-29,
« 0 problème(s) écrits, 14 déjà suivis », aucun sujet.

Correctif : on génère désormais dès qu'un T0 laisse des hypothèses ouvertes **et**
qu'aucun T0 de la session ne porte encore de `sujet_confirmation` persisté
(`_session_a_un_sujet_t1`, même critère que `sessions.py::session_detail` pour le lien
« Sujet T1 »). Un sujet déjà présent → pas de second appel modèle. Trois tests neufs
(`backend/tests/test_taches.py`). 155 tests backend OK.

### 2026-08-29 — Choix des fournisseurs IA sorti dans Paramètres (D-CEO-44)

Demande de l'utilisateur : que le choix du modèle par étape ne soit plus figé dans `.env`.
Fait — **Paramètres → Modèles IA**, config globale, éditable par l'administrateur seul,
lecture seule pour les autres casquettes. Trois familles : transcription
(Claude / Gemini / ChatGPT), correction (DeepSeek / Claude / Gemini), analyse —
diagnostic texte libre du rapport de copie — (Gemini / Claude / ChatGPT / DeepSeek),
plus une variante Sonnet / Opus quand Claude est choisi.

Mécanique : `src/core/preferences_modeles.py` (magasin fichier `data/preferences_modeles.json`,
rechargé à chaud, sans dépendance de framework), qui **prime sur `.env`** — ce dernier
devient le repli. Les fabriques de clients du pipeline (`_make_*_client`) le consultent ;
`GET`/`PUT /api/admin/preferences-modeles` l'exposent. `GeminiClient` a gagné `grade()` et
`diagnose()` ; `ClaudeClient` accepte un modèle au constructeur / par appel. Modèles Claude
passés à la famille 5 (`claude-sonnet-5` / `claude-opus-5`).

**Restent Claude-only, volontairement :** le diagnostic contraint du module 4
(`diagnose_constrained`, outil `enum` = 1re barrière anti-code hors référentiel — changer
son fournisseur ré-ouvrirait le jalon « 100 sorties valides »), la génération des sujets
T1/T3/T4/T5, l'extraction énoncé/barème. Aucun autre client ne porte ces méthodes.

**Vérifié :** 152 `backend/tests/`, 246 `tests/`, 47 Vitest — verts (dont 12 + 4 + 6 + 3
nouveaux tests ciblés). Aller-retour réel `claude-in-chrome` non repassé.

### 2026-08-13 (suite 4) — `bareme_socle_tleD.yaml` reconstruit — dernier niveau, arbitrage H clos

66 items (20 A + 14 B + 32 sous-items C, 6 problèmes). Ce corrigé est le plus favorable des 7 : sa grille
de fin donne directement le barème officiel par domaine (N 4 / L 11 / F 30 / S 11 / T 8 / D 4 / G 12 =
80 pts) **et** la clé de répartition exacte des points de chaque problème de partie C entre domaines
(« P1 donne 4 pts à S et 1 à D »…) — recoupement **exact** sur les 7 domaines, sans qu'aucune lecture
visuelle n'ait été nécessaire pour déterminer la clé elle-même (contrairement aux niveaux précédents, où
seuls les totaux par domaine étaient parfois donnés, jamais la clé par problème).

Deux nouveautés propres à ce niveau :
- 7 domaines actifs au lieu de 5 au collège/2ndeC/1ereD : `S` (suites et récurrence) et `T` (trigonométrie)
  apparaissent comme domaines à part entière (déjà présents avant mais absorbés ailleurs).
- Le corrigé lui-même classe les fonctions rationnelles tantôt domaine `L` (résolution algébrique isolée,
  ex. `L3`, `L5`) tantôt domaine `F` (étude de variation d'une fonction rationnelle, ex. `F10`, `F11`,
  partie C de `P5`) — suivi à l'identique, ce n'est pas une incohérence du corrigé mais une distinction
  volontaire entre calcul et étude de fonction.

Trois sous-items isolés (`P4a`/`P4b`, `P6d`) n'ont pas de code canonique dédié à leur contenu très précis
(répartition entre calcul de distance et conversion d'échelle ; signalement d'une donnée manquante en
géométrie dans l'espace) — affectés par approximation raisonnée, sans effet sur les totaux par domaine
qui restent exacts.

**Tests :** `tests/test_baremes_socle.py` 59/59 (+4 tests devenus vides, `_NIVEAUX_HERITES` est maintenant
une liste vide — les 7 niveaux sont recomposés), suite pipeline complète 240 passent + 4 vides, `manage.py
check` propre.

**Arbitrage H clos.** Les 7 niveaux (`6eme` à `tleD`) sont désormais reconstruits à la main sur la structure
à 3 parties (Automatismes/Savoir-faire/Raisonnement), en avance sur `Referentiel_Socle_v0.xlsx` qui reste
non modifié — ces 7 fichiers YAML font foi jusqu'à ce que le classeur soit repris (décision actée le
2026-08-12 : « le classeur n'est pas la priorité, la plateforme si »). Détail : `docs/harmonisation_donnees.md`.

### 2026-08-13 (suite 3) — `bareme_socle_1ereD.yaml` reconstruit — deuxième niveau lycée, recoupement exact

59 items (20 A + 14 B + 25 sous-items C, 6 problèmes). Même méthode que 2ndeC (lecture visuelle du sujet
et du corrigé PDF rendus en image, échelle 80 pts ÷4). Ce corrigé revient au motif précis de 5e/4e/2ndeC :
le tableau « profil par domaine » donne les totaux par domaine (N 12,5 / L 16,5 / F 22 / G 22,5 / D 6,5
= 80 pts) et une clé explicite de répartition des points de chaque problème de partie C entre domaines
(« P1 donne 3,5 pts à L et 1,5 pt à G »…) — recoupement **exact** sur les 5 domaines, aucune approximation
sur les totaux.

Seule nuance : deux sous-items isolés (`P5d`, `P6e`) n'ont pas de code canonique qui colle exactement à
leur contenu précis (comparaison numérique de deux carrés pour `P5d` ; signalement d'une donnée manquante
pour `P6e`) — rattachés par approximation à `N.RAC` et `N.PROB` respectivement, sans effet sur les totaux
par domaine puisque ceux-ci restent exacts. Deux nouveaux domaines apparaissent pour la première fois
dans la progression : `F.CIRC`/`F.VAR`/`F.DEF`/`F.PAR`/`F.REF`/`F.APP` (fonctions, développés depuis la
4e mais mobilisés en bloc ici) et `L.EQ2`/`L.TRI`/`L.INEQ2`/`L.SYSL`/`N.MAJ` (second degré, système linéaire
et inéquations produit/quotient, propres au lycée).

**Tests :** `tests/test_baremes_socle.py` 60/60 (`1ereD` déplacé de `_NIVEAUX_HERITES` vers `_NIVEAUX_RECOMPOSES`),
suite pipeline complète 241/241, `manage.py check` propre.

**Reste à faire :** tleD, dernier niveau.

### 2026-08-13 (suite 2) — `bareme_socle_2ndeC.yaml` reconstruit — premier niveau lycée, échelle ÷4

66 items (20 A + 14 B + 32 sous-items C, 6 problèmes P1-P6). Premier niveau lycée : barème classeur **80 pts**, converti /20 par **division par 4** (collège : 60 pts, ÷3) — `tests/test_baremes_socle.py` distingue maintenant `_NIVEAUX_LYCEE`, avec une nuance : seuls les niveaux lycée **déjà reconstruits** utilisent la nouvelle échelle 80/÷4 dans les tests — `1ereD`/`tleD`, pas encore repris, restent testés sur l'ancienne échelle 60/÷3 jusqu'à leur tour.

Ce corrigé revient au motif précis de 5e/4e (répartition exacte par domaine et par problème, recoupement exact avec le tableau officiel, aucune approximation) — contrairement à 3e. Aucun item hybride calcul/construction (pas de constructions géométriques au programme de ce niveau).

**Tests :** `tests/test_baremes_socle.py` 61/61, suite pipeline complète 242/242, `manage.py check` propre.

**Reste à faire :** 1ereD, tleD.

### 2026-08-13 (suite) — `bareme_socle_3eme.yaml` reconstruit (4e niveau) — la vérification exacte par domaine s'arrête ici

50 items (16 A + 12 B + 22 sous-items C). **Ce corrigé rompt avec le motif des deux précédents :** il ne détaille pas le domaine de chaque terme de barème en partie C, seulement un domaine dominant par problème entier (P1/P2→G, P3→L, P4→F, « les quatre problèmes croisent plusieurs domaines, chacun est rattaché à son domaine dominant »). La décomposition fine en sous-items (une compétence par sous-item) a été maintenue par cohérence avec la logique du module 4, mais **sans le recoupement exact qui validait fortement 5e et 4e** — plusieurs sous-items de partie C sont marqués « confiance basse » directement dans leur `objet`, code disponible le plus proche du référentiel actuel, à confirmer par l'enseignant.

Nouveautés : domaines **G.VEC** (vecteurs, Chasles) et **F** (applications/fonctions, image/antécédent) apparaissent pour la première fois dans la progression. `G7` décomposé en construction + déduction (même motif que G5 en 4e, G7/G9 en 5e).

**Tests :** `tests/test_baremes_socle.py` 62/62, suite pipeline complète 243/243, `manage.py check` propre.

**Reste à faire :** 2ndeC, 1ereD, tleD (lycée — structure à 80 pts/÷4, à vérifier si le motif de vérification par domaine y est aussi coarse ou fin).

### 2026-08-13 — `bareme_socle_4eme.yaml` reconstruit (3e niveau) — la décomposition de la partie C n'est plus fixée à 4

48 items (16 A + 12 B + 20 sous-items C). Ce corrigé donne, en plus du domaine par terme de barème, une phrase récapitulative par problème (« P1 donne 2 points à M et 3 à N… ») — recoupement **exact** avec le tableau « profil par domaine », comme en 5e.

Deux nouveautés propres à ce niveau, qui touchent la méthode elle-même :
- Apparition d'un nouveau domaine, **L (calcul littéral et équations)**, en plus de N/M/G/D.
- Certains problèmes de partie C ont **5 ou 6 sous-questions** (pas toujours 4) — le nombre de sous-items suit le nombre exact de termes du barème imprimé, pas un compte fixe. `test_sous_items_partie_c_rattaches_a_un_probleme` généralisé (3 à 6 sous-items acceptés, la somme du barème reste la contrainte forte).
- Un seul item mixte calcul/construction (`G5` → `G5a`/`G5b`), contre deux en 5e.

Point signalé sans solution : `N6` (PPCM) rattaché à `N.PGCD`, faute de code dédié.

**Tests :** `tests/test_baremes_socle.py` 63/63, suite pipeline complète 244/244, `manage.py check` propre.

**Reste à faire :** 3e, 2ndeC, 1ereD, tleD.

### 2026-08-12 (suite 2) — `bareme_socle_5eme.yaml` reconstruit (2e niveau, même méthode)

45 items (16 A + 13 B + 16 sous-items C). Même méthode que la 6e (lecture visuelle du corrigé PDF, décomposition de la partie C en 4 sous-items par problème), avec deux différences propres à ce niveau :

- Le corrigé 5e indique le domaine de chaque terme de barème directement entre parenthèses (`1 pt (G)`) et la grille finale donne la répartition par domaine pour chaque problème — la vérification contre le tableau officiel « profil par domaine » tombe donc **exactement juste** (G 2 / M 4 / N 10 / D 6 = 22 pts en partie C, zéro écart), contrairement à la 6e où il restait 1 point d'approximation.
- Deux items de partie B (`G7`, `G9`) mélangent calcul et construction au compas dans un seul item à 2 points. Décomposés en `G7a`/`G7b` et `G9a`/`G9b` (1 pt chacun, l'un `redige`, l'autre `construction`) — la partie B passe de 11 à 13 items, 22 points inchangés. `test_structure_a_3_parties` généralisé en conséquence (somme des points plutôt qu'un compte fixe de 11).

Un point signalé sans solution : `G3`/`G6` (angles supplémentaires) n'ont pas de code canonique dédié dans le référentiel actuel ; `G.ANG2` (angles complémentaires) retenu par approximation.

**Tests :** `tests/test_baremes_socle.py` 64/64, suite pipeline complète 245/245, `manage.py check` propre.

**Reste à faire :** 4e, 3e, 2ndeC, 1ereD, tleD.

### 2026-08-12 (suite) — `bareme_socle_6eme.yaml` reconstruit à la main (pilote arbitrage H), sans attendre le classeur

**Décision de l'utilisateur :** ne pas attendre la mise à jour de `Referentiel_Socle_v0.xlsx` pour corriger le désalignement trouvé dans l'entrée précédente — « la mise à jour du fichier n'est pas importante, mais la plateforme si ». `data/knowledge/bareme_socle_6eme.yaml` a donc été reconstruit directement depuis le sujet et le corrigé PDF recomposés, en pilote sur un seul niveau avant réplication.

**Méthode :** lecture visuelle des 8 pages du corrigé (rendues en image via PyMuPDF — les valeurs numériques du sujet et du corrigé sont vectorielles, invisibles à l'extraction texte, mais les consignes et le texte diagnostique « Si l'élève échoue » sont en texte brut). Chaque problème de partie C (`P1`–`P4`) est décomposé en 4 `RubricItem` (`Pxa`–`Pxd`), un par terme du barème imprimé (`Barème. 1 + 2 + 1 + 1`), chacun avec une seule compétence canonique — pas de nouveau champ de schéma. La compétence de chaque sous-item a été déduite du texte puis recoupée avec le tableau officiel « profil par domaine » du corrigé (N 10 / M 6 / G 1 / D 5 pts) ; l'allocation obtenue tombe à N 11 / M 5, écart d'1 point sur un seul item (`P3b`, deux savoir-faire dans un même terme de barème) — signalé, non bloquant.

**Correction méthodologique en cours de route :** les codes de question (`N1`, `D2`…) ne sont pas des identifiants stables entre l'ancien classeur et le nouveau sujet — simples étiquettes de position. La réconciliation précédente (entrée ci-dessous) comparait par code ; celle-ci compare par contenu, ce qui a permis de corriger deux erreurs : `G5`/`G6` sont des tracés au compas/équerre, retagués `format: construction` (pas `redige`), `reponse_attendue` laissée vide comme pour les autres questions `construction` (arbitrage F).

**Résultat :** 43 items (16 A + 11 B + 16 sous-items de partie C), 60/60 pts classeur, 20,0/20 exact. `tests/test_baremes_socle.py` mis à jour — nouvelles assertions pour les niveaux « recomposés », anciennes conservées pour les 6 niveaux pas encore repris (paramétrage par liste, pas de duplication de fichier). 65/65 passent. Suite pipeline complète : 246/246. `manage.py test` : mêmes échecs préexistants `exige_une_connexion`/`personnel` que d'habitude, aucun nouveau, rien lié au contenu du barème.

**Reste à faire :** répliquer aux 6 autres niveaux (5e, 4e, 3e, 2ndeC, 1ereD, tleD), chaque table de correspondance soumise à l'utilisateur avant régénération, comme pour la 6e.

### 2026-08-12 — Corrigés enseignant validés pour les 7 tests (arbitrage B débloqué), et une nouvelle divergence trouvée (arbitrage H)

**Livraison `data/New-docs/`** (15 fichiers) : 7 sujets PDF recomposés + 7 corrigés enseignant PDF complets, relus et validés par un enseignant de mathématiques — c'est la relecture `00_Notice` qui manquait depuis le 2026-08-06 (arbitrage B, désormais ✅). Un `Referentiel_Urie_v0.xlsx` accompagnait la livraison mais s'est révélé être un doublon binaire exact de `Referentiel_Socle_v0.xlsx` (hash MD5 identique) — aucun changement de classeur.

**Intégré :**
- Les 7 anciens sujets PDF (structure 2 parties, 20 pts) déplacés vers `data/Documents/archive/` — conservés pour l'historique des copies déjà corrigées avec cette composition.
- Les 7 nouveaux sujets copiés dans `data/Documents/`, les 7 corrigés dans `data/Documents/corriges/`.
- `src/knowledge/test_registry.py` : nouveau champ `corrige_pdf` sur `HakiliTest`, résolu pour les 7 tests `socle_*`.
- `correction_web` : nouvelle vue `corrige()` + route `sujets/<bareme_id>/corrige/`, lien « Corrigé » ajouté à `sujets.html` à côté d'Ouvrir/Télécharger. Réservé aux personnes connectées, même logique que `sujet()`.
- `manage.py check` propre ; rechargement du registre vérifié en shell — les 7 `corrige_pdf` se résolvent sans avertissement.

**Découverte en réconciliant les corrigés contre `bareme_socle_*.yaml`** (grille de report extraite au texte, PyMuPDF, comparée code par code) : les 7 sujets recomposés ne correspondent plus au barème généré le 2026-08-07. Motif identique sur les 7 niveaux — passage d'une structure à 2 parties (30×1pt + 10×3pt, celle encore dans le YAML) à une structure à 3 parties (Automatismes/Savoir-faire/Raisonnement, avec des problèmes de synthèse croisant plusieurs compétences). Chiffres et détail complet : `docs/harmonisation_donnees.md`, arbitrage H (nouveau). Tranché avec l'utilisateur le jour même : **c'est une recomposition délibérée et finale**, à faire remonter dans `Referentiel_Socle_v0.xlsx` puis régénérer via `scripts/generer_baremes_socle.py` — **pas encore fait**, c'est un travail pédagogique (codes de compétence pour les nouveaux problèmes croisés) qui reste sur la feuille de route.

**Bloque tant que ce n'est pas fait :** un import strict du module 1 pour ces 7 tests, le diagnostic contraint (module 4) sur les problèmes de la nouvelle partie C (aucun `RubricItem`, donc pas notables), et la fiabilité de la notation automatique sur les 11 à 14 items reclassés par niveau entre partie A et B.

**Tests :** aucun test automatisé nouveau (changement de données + une route de téléchargement calquée sur `sujet()` déjà couverte par `TestSujetsImprimables`) ; `manage.py check` rejoué, propre.

### 2026-08-07 (suite) — Volume horaire des hypothèses affiché, et T1 confirme/écarte automatiquement après correction

**Deux changements, décidés avec l'utilisateur.**

**1. Volume estimé dès l'hypothèse.** `Session.cout_total_hypothese` (nouvelle propriété, `suivi/models.py`) somme `cout_estime` des problèmes encore en `hypothese` — jusqu'ici seul `suivi/plan.py::construire()` calculait un total, et seulement pour les problèmes confirmés, donc rien ne s'affichait avant T1. Affiché sur `session_detail.html` (section « Lacunes à confirmer ») et sur `eleve_detail.html` (à côté du nombre de lacunes présumées).

**2. T1 corrige et tranche automatiquement, sans saisie manuelle.** Jusqu'ici, `Correction.type_evaluation` documentait déjà l'intention (« confirme/écarte des hypothèses existantes (T1) ») mais `_ecrire_hypotheses_module4` traitait toute copie T1 comme une copie hors référentiel et ne faisait rien — la confirmation restait entièrement à la main (`confirmer_hypotheses`, toujours en service en filet). Le circuit ajouté :
- `_generer_sujet_confirmation` (module 5) persiste maintenant le sujet T1 généré (`Evaluation.sujet_confirmation`, nouveau champ JSON) et, pour chaque hypothèse, les numéros d'exercice qui la ciblent (`Probleme.exercices_confirmation`) — appariés par le `topic` que le prompt impose textuellement identique à `"<compétence> × <type d'erreur>"`, jamais par position (une correspondance qui se devinerait après coup, le défaut qui a fait retirer le module 2).
- Nouvel écran `suivi_web` → `correction_web:soumettre_confirmation` : l'enseignant dépose seulement le scan des réponses (élève et barème déjà connus) ; le barème de correction est construit directement depuis `sujet_confirmation`, sans extraction ni auto-résolution.
- Le pipeline de correction (transcription, relecture, **tableau de validation des notes** — inchangé, D-CEO-16) tourne à l'identique. À la phase diagnostic, `_ecrire_hypotheses_module4` bascule vers `_confirmer_hypotheses_module4` → `suivi.diagnostic.confirmer_depuis_correction` : règle binaire simple (une question ratée sur celles qui ciblent l'hypothèse → `confirme`, tout réussi → `ecarte`), `ATT` toujours écarté (contrainte déjà posée par `Probleme.clean()`).
- Bouton « Soumettre la copie pour le test de confirmation (T1) » sur `session_detail.html`, visible seulement si un sujet a été généré — sinon la saisie manuelle reste seule proposée.

**Non fait, à garder en tête :** la nuance conceptuel/procédural que les deux questions par hypothèse sont censées départager (protocole §3) n'entre pas encore dans la décision — c'est une règle binaire pour démarrer, décidée avec l'utilisateur. Jamais essayé sur une vraie copie T1 (pas de client IA disponible en environnement de dev) — le module reste 🟨, pas ✅, tant que ce n'est pas fait une fois à la main comme l'exige la discipline du projet.

**Tests :** `suivi/tests_diagnostic.py::TestConfirmationAutomatique` (7), `correction_web/tests.py::TestSoumissionConfirmationT1` (5) et `TestConfirmationAutomatiqueT1` (2), `suivi_web/tests.py` (2 nouveaux, boutons). Suite complète rejouée : 238 tests sur `suivi`/`suivi_web`/`correction_web`, 13 échecs — tous de la même famille préexistante `exige_une_connexion`/`personnel` (vérifiée à nouveau reproductible sur du code non touché, ex. `TestCloisonnement`/`TestSujetsImprimables` isolés).

### 2026-08-07 — La fiche de l'élève affiche désormais les lacunes présumées, non confirmées

**Suite du constat ci-dessous, implémentée le même jour.** `eleve_detail` (`suivi_web/views.py`) attache maintenant à chaque session de `parcours` la liste de ses `Probleme` en état `hypothese` (`select_related` compétence/type d'erreur) ; le template affiche, sous chaque carte de session, le nombre de lacunes présumées et leur libellé (compétence + pastille type d'erreur), avec la mention « à confirmer par le second test (T1) ». Rien de plus : la confirmation elle-même reste sur `/parcours/<jeton>/` (`confirmer_hypotheses`, déjà en service) — cet écran ne fait qu'annoncer qu'il y a quelque chose à trancher là-bas, il ne duplique pas le formulaire.

**Ce que ça couvre, et ce que ça ne couvre pas :** ça répond au manque n°2 ci-dessous (l'affichage). Le manque n°1 (déclenchement automatique du diagnostic après une correction en ligne) reste ouvert — aujourd'hui il faut toujours `manage.py diagnostiquer --correction <id>` à la main pour que des `hypothese` existent à afficher. Le module 5 (composition automatique du T1) reste également ⬜, sans lien avec ce changement.

**Tests :** `suivi_web/tests.py::TestFicheEleveHypotheses` (2) — la lacune apparaît tant qu'elle est en `hypothese`, disparaît une fois tranchée (`ecarte`). Suite complète rejouée : 323 tests, 22 échecs — **les mêmes 22, préexistants et sans rapport** (vérifié par `git stash` : identiques sur le code non modifié, tous des tests `exige_une_connexion`/`personnel` qui semblent fuir une session Django entre méthodes de test, à investiguer séparément).

### 2026-08-07 — Constat : la fiche de l'élève n'affiche pas les lacunes présumées

**Constat remonté par l'utilisateur** après une correction en ligne (11,25/20, 26 réussies, 14 ratées) : la fiche de l'élève (`suivi_web/templates/suivi_web/eleve_detail.html`) ne montre nulle part les lacunes présumées (`Probleme` en état `hypothese`) que le module 4 a pu écrire, à confirmer par le second test T1. Aucun code n'a été touché — constat consigné pour ne pas le perdre.

**Deux manques distincts derrière ce constat, tous deux déjà connus de cette feuille de route :**
1. Le **déclenchement automatique** du diagnostic après une correction en ligne n'existe pas (module 4, case toujours ouverte) — aujourd'hui il faut lancer `manage.py diagnostiquer --correction <id>` à la main.
2. Même une fois des `Probleme` en `hypothese` en base, **rien ne les affiche** sur la fiche élève — `/parcours/<jeton>/` (`session_detail.html`) montre "les hypothèses restantes" mais seulement une fois qu'une `SessionSuivi` existe ; `eleve_detail.html` n'en montre aucune trace en dehors des sessions déjà ouvertes.

**Non fait ici, à trancher/planifier séparément :** où afficher ces hypothèses avant toute session ouverte, comment les relier à la génération du T1 (module 5, toujours ⬜), et à quel moment du flux de correction déclencher le diagnostic (question déjà ouverte au module 4).

### 2026-08-06 — Arbitrage B débloqué (202/209 corrigés) et les 3 copies réelles 5e corrigées

**Contexte :** le lot de saisie (`Lot_a_completer_2026-07-30.xlsx`) était généré depuis une semaine et resté à 0/209 rempli — personne n'avait encore répondu côté relecteur pédagogique. Décision prise avec l'utilisateur de ne plus attendre : un brouillon calculé (lecture de l'objet du barème + des 7 sujets PDF, résolution directe des 209 questions), relu et validé par l'utilisateur **sujet par sujet** avant chaque intégration (`integrer_corriges.py` → `generer_baremes_socle.py`), avec les tests `referentiel` + `suivi.tests_diagnostic/tests_corpus/tests_plan` (132/132) rejoués après chaque sujet.

**Résultat :** 202/209 corrigés produits sur les 7 sujets — 6e : 28, 5e : 27, 4e : 29, 3e : 29, 2ndeC : 30, 1ereD : 30, tleD : 29. Les 7 restants sont exactement les 7 questions de format `construction` (2 en 6e, 3 en 5e, 1 en 4e, 1 en 3e) : non traitées comme réponse texte, car l'arbitrage F (diagnostic auto ou saisie humaine sur un tracé) reste ouvert. Leurs critères de vérification de tracé ont été renseignés dans la feuille `05_Questions_construction` du lot, à reporter par le docteur dans le classeur source.

⚠ **Ce n'est pas la validation pédagogique attendue par `00_Notice`** (« À VALIDER » par un enseignant de mathématiques) — c'est un brouillon calculé et relu une fois par l'utilisateur, pas une relecture par un enseignant. Signalé pour mémoire ; ne bloque plus le développement, mais à faire relire avant tout usage à grande échelle avec de vrais élèves.

**`manage.py verifier_installation --copie … --test socle_5eme --eleve …` — le contrôle qui n'avait jamais été passé (CLAUDE.md) a été fait, trois fois**, sur les 3 copies réelles de 5e en attente (`KOANDA-SAIBATA-5E`, `NABALOUM-MADJID-5E`, `OUATTARA-FADEL_5E`, identités retrouvées dans le Sheet élèves). Notes IA : 8,0 / 9,25 / 11,75 sur 20. Diagnostic contraint (module 4) exécuté sur les 3 en repartant du `result.json` produit par `verifier_installation` (pas de ligne `Correction` persistée par ce chemin, donc `manage.py diagnostiquer --correction <id>` ne s'y applique pas directement — contourné par un script qui recharge `CopyGrade` depuis le JSON et appelle `reponses_depuis_correction()` + `diagnostiquer()`) : 13, 15, 8 problèmes structurés respectivement, sortie valide sur les 3.

⚠ **Ce n'est toujours pas la « mesure juste » du module 4.** Ces 3 copies n'ont pas de tagage manuel (elles ne sont pas dans le corpus de référence) : rien à comparer. La mesure juste demanderait de les tagger à la main comme le corpus — travail distinct, non fait ici, à décider avec l'utilisateur.

**Le fichier de clé JSON du compte de service Google a été retrouvé et déposé** dans `credentials/` — les Sheets sont joignables (85 élèves, 87 personnes), le point qui bloquait l'usage de l'interface est levé.

**Deux défauts pré-existants repérés en cours de route, non corrigés (hors scope de cette session) :**
- Le correcteur DeepSeek transcrit parfois une réponse QCM en phrase (« Le b est la bonne réponse ») au lieu de la seule lettre — le comparateur QCM du diagnostic contraint ne la reconnaît pas et écarte la question. Sous-compte les problèmes QCM.
- Les `Copie` déjà en base sous `verif-KOANDA-SAIBATA-5E` et `verif-OUATTARA-FADEL_5E` portaient un `identifiant_hakili` factice (`kabore_salif_…`) d'une tentative antérieure — `creer_copie()` fait un `get_or_create` par `copy_id` qui ne met pas à jour l'élève si la ligne existe déjà.

**`tests/test_baremes_socle.py::test_corriges_manquants_uniquement_hors_qcm` mis à jour** — son propre commentaire prévoyait qu'il faudrait le faire dès le premier corrigé ajouté. Vérifie désormais 7 manquants, tous de format `construction`, au lieu de 209.

**Outillage utilisé sans aucune modification :** `scripts/generer_lot_a_completer.py`, `scripts/integrer_corriges.py`, `scripts/generer_baremes_socle.py` — tous déjà prêts depuis le module 0/3, ce qui a rendu le travail purement pédagogique plutôt que technique.

### 2026-08-05 (suite 3) — Un seul ORM : SQLAlchemy et Alembic retirés

Troisième poste de la simplification. `copie` et `document` passent sous Django,
et le second ORM disparaît : `src/db/`, `src/services/copie_service.py`,
`migrations/` (4 révisions Alembic), `alembic.ini`, plus les deux dépendances.
**24 paquets au lieu de 26.**

Cette cohabitation n'avait jamais été un choix : elle datait de Streamlit, qui
écrivait ces deux tables. Il n'en restait qu'un coût, dont un piège permanent —
`Evaluation.copy_id` est un champ texte **parce que** Django ne pouvait pas
poser de clé étrangère vers une table qu'il ne gérait pas.

**La difficulté était le pipeline**, qui écrit en base à cinq points d'injection
alors que `src/` ne doit dépendre d'aucun framework. La couture est
`src/pipeline/depot.py` : un contrat de quatre méthodes, un dépôt courant que
`CorrectionWebConfig.ready()` installe au démarrage, et un dépôt neutre par
défaut pour que la correction tourne sans base. Le pipeline dépose, il ne sait
pas dans quoi — et il y **perd** des lignes, toute la mécanique
`SessionLocal()` / `try` / `finally: db.close()` ayant disparu.

On aurait pu abandonner la règle, Django étant seul appelant depuis D-CEO-39.
Elle est gardée sur deux constats : le retrait de Streamlit n'a touché aucun
test précisément parce que `src/` ignorait l'interface, et les 239 tests de
`tests/` importent le pipeline **sans configurer Django**.

**🔴 Un défaut trouvé en chemin, invisible jusque-là.** Le pipeline enveloppe
chaque écriture dans un retry, pour les refus de première connexion d'une base
serverless. **Ce retry ne rattrapait rien** : la seconde tentative rappelait
`create_copie`, qui échouait sur la clé primaire, ou `add_document_to_copie`,
qui ajoutait un *second* document du même type — et `get_document_by_type`
prenait « le premier trouvé », sans ordre garanti. Une copie recorrigée pouvait
donc servir l'ancien rapport. Les quatre opérations du dépôt sont maintenant
rejouables ; le retry fonctionne enfin.

**⚠ Une étape manuelle avant la prochaine mise en ligne.** Sur Neon, `copie` et
`document` existent déjà : la migration `suivi/0007` s'y applique **une fois
avec `--fake`** (`docs/deploiement.md`). Sans ça le déploiement échoue sur
« relation existe déjà », transaction annulée, rien de perdu — bruyant plutôt
que silencieux. Écrite à la main, parce que Django ne sait pas convertir un
modèle `managed = False` en modèle géré : il produit un `AlterModelOptions` qui
ne crée aucune table, et on ne s'en aperçoit qu'à la première base neuve.

**275 tests Django + 239 pytest passent** (514 au total). Sept tests neufs
couvrent le dépôt. Les tests des vues de suivi ont **cessé de simuler la base** :
ils créent de vraies lignes, ce qui teste davantage avec moins de code — c'était
la contrepartie du `managed = False`, elle tombe avec lui.

**Ce qui n'a pas bougé, et ne doit pas :** `identifiant_hakili` reste un champ
texte, jamais une clé étrangère. Le passage sous Django rend une table `eleve`
techniquement possible ; elle a déjà été démolie deux fois (D-CEO-20/21).

**Reste de la liste de simplification :** les trois clients IA non retenus
(1 671 lignes, arbitrage coût), la mesure plancher (276), le module 5 tel qu'il
est spécifié, et le principe **dégrader plutôt que refuser**.


### 2026-08-05 (suite 2) — Streamlit retiré, et deux dépendances de moins que prévu

Deuxième poste de la simplification décidée avec l'utilisateur. `src/ui/`
supprimé : **3 106 lignes**, dont `app.py` qui était le plus gros fichier du
projet (2 778). Avec lui partent `streamlit`, `pandas`, la configuration
`.streamlit/` et la cible `make run-streamlit`.

**Et `numpy` aussi**, ce qui n'était pas prévu : il ne servait pas à Streamlit
mais à `src/pipeline/zones.py`, supprimé le matin même (D-CEO-38). Plus rien ne
l'utilise. Le commentaire qui le déclarait dans `requirements.txt` disait
d'ailleurs exactement ça — « numpy sert à la découpe des zones de réponse » —
il aurait survécu sans être relu.

`hakili_logo.png` est **déplacé** dans `static/` plutôt que supprimé : c'était
le seul exemplaire de la marque dans le dépôt, et Django le sert désormais
(`STATICFILES_DIRS` prend `static/` s'il existe).

**Le filet ne rattrapait plus rien.** Django porte les onze écrans depuis le
30 juillet et Streamlit n'a plus servi depuis. Surtout, il ne pouvait pas
dépanner : sans la clé du compte de service Google, **aucune des deux
interfaces** ne permet de se connecter. Le point de panne est commun ; le
second exemplaire ne le contourne pas, il double seulement l'entretien.

**🔴 Ce que ce retrait emporte, et qu'il ne faut pas laisser filer.** La fiche
« Retrait de Streamlit » de ce document posait **un** point bloquant :
`verifier_installation --copie … --test … --eleve …`, une correction complète
sur une vraie copie. **Il n'a jamais tourné.** Le retrait a eu lieu sans lui —
c'est un choix, pas un oubli, et il est consigné comme tel en D-CEO-39. Les 268
tests Django ne le remplacent pas : ils simulent le pipeline. Ce contrôle reste
le seul qui prouve que la chaîne tient de bout en bout, et il est maintenant
**découplé** au lieu d'être bloquant — ce qui le rend plus facile à oublier, pas
moins nécessaire.

**Ce que ça débloque.** `copie` et `document` vivent sous SQLAlchemy/Alembic
parce que Streamlit les écrivait, et c'est la raison pour laquelle
`Evaluation.copy_id` est un champ texte plutôt qu'une clé étrangère. La
condition est levée : ces deux tables peuvent passer sous Django, ce qui retire
un second ORM et un second système de migrations. C'est le chantier suivant
(point 4 de la liste de simplification), pas un effet de bord de celui-ci.

**268 tests Django + 239 pytest passent, inchangés** — rien ne dépendait de
`src/ui`. C'est la discipline « `src/` sans dépendance de framework », tenue
depuis le début, qui rend ce retrait sans effet : les fonctions métier avaient
déjà été extraites vers `src/services/`.

**Reste de la liste de simplification :** les trois clients IA non retenus
(1 671 lignes), la double persistance (450), la mesure plancher (276), le module
5 tel qu'il est spécifié, et le principe **dégrader plutôt que refuser**.


### 2026-08-05 (suite) — ⛔ Le module 2 est supprimé, et le module 4 est branché

Le levier attendu depuis le 1er août est arrivé : **trois copies de 5ème,
imprimées, composées par des élèves et scannées** (200 DPI couleur, 10/9/10
pages). Elles devaient trancher le tramage et débloquer la mesure juste. Elles
ont fait les deux, et un peu plus.

**Ce que le papier a dit.**

1. **Le tramage n'existe pas.** À l'intérieur d'un cadre, le scan est
   uniformément blanc — moyenne 251,6, écart-type 1,1, **0,00 % de pixels sous
   200** — là où le PDF porte des gris à 191, 208, 212, 229, 246. L'imprimante
   n'a pas tramé les bandes de guidage : elle ne les a pas imprimées. Le risque
   ouvert de D-CEO-36 se referme sans qu'une ligne ait été écrite contre lui.
2. **Mais le même délavage a emporté le bord des cadres, qui était l'ancre du
   recalage.** Dans le PDF, un bord est une rangée dont 100 % des pixels sont à
   121–156 ; dans le scan, plus rien sous 235, et les bords ne réapparaissent
   qu'entre 243 et 248 contre un papier à 251,6. `SEUIL_ENCRE_DEFAUT = 140` ne
   les voyait **jamais** : le recalage s'accrochait au texte imprimé.
3. **Conséquence mesurée** contre une vérité terrain obtenue par corrélation
   avec le sujet rendu : échelle fausse jusqu'à −10 %, soit **85 pt (3 cm) de
   dérive** en bas de page. Sur les 10 pages d'une copie, 2 refusées à juste
   titre, 4 correctes… et **4 acceptées (score 50 %) avec 20 à 35 pt de
   décalage**. Le score ne discriminait pas : la plupart des pages n'ont que 2
   cadres, donc 4 bords, donc un score qui ne peut valoir que 0/25/50/75/100 %.
4. **Vérifié à l'œil**, parce qu'un chiffre de dérive ne dit pas ce qu'on perd :
   sur une page, le cadre découpé attrapait l'énoncé imprimé et perdait le bas
   de la réponse ; sur une autre, les trois cadres tombaient **une question plus
   bas**, chacun contenant de l'écriture — donc sans que rien n'ait l'air
   anormal. C'est exactement le mode de panne que ce module devait empêcher.

**Les trois copies ont été refusées par la chaîne. Aucune n'était découpable.**
Pour l'une des trois, le refus était d'ailleurs légitime et sans rapport : 9
pages scannées pour un sujet qui en compte 10.

**Une correction était possible, elle a été écartée.** Chercher les repères
juste sous le niveau du papier (papier − 6) ramène 8 pages sur 10 à moins de
7 pt de dérive, et fait passer les pages fautives de 5/5/8 à 1/1/3 sur les trois
copies. Mais elle échoue encore sur une page par copie **en annonçant 100 % de
confiance**, ce qui est le pire des cas. Et surtout elle ne touche pas au fond :
ce module faisait dépendre le diagnostic de la **géométrie d'un objet physique**
qu'on ne maîtrise pas — impression sans réduction, scan droit, bon nombre de
pages dans le bon ordre, cadres survivant au toner. En production de masse,
chacune de ces conditions est un refus de copie.

**Ce qui le remplace était déjà en service, et le pipeline le disait.** On lit
dans `pipeline.py` : « le module 4 n'existe pas encore : **personne ne consomme
les zones** ». Pendant ce temps la correction lit la page entière et rend, pour
chaque question du barème, `observed_answer` et le score — et le code d'item du
barème **est** le code de question du référentiel. La correspondance que 893
lignes de géométrie reconstituaient existait déjà, produite par une étape en
service, sans un appel de modèle de plus.

**Fait :**
- Supprimé : `src/pipeline/zones.py` (893 lignes), `tests/test_zones.py` (578),
  `_lire_zones`, `PipelineResult.zones`. Conservé : `HakiliTest.formats`, qui
  décide de ce que le diagnostic peut faire d'une réponse.
- Ajouté : `referentiel.diagnostic.reponses_depuis_correction()` et
  `manage.py diagnostiquer --correction <id>`, qui repart d'une copie corrigée.
- Trois règles posées au passage : les questions réussies ne sont pas soumises ;
  **la décision de l'enseignant prime sur celle de l'IA** pour dire ce qui est
  réussi ; et « illisible » cesse d'être confondu avec « rien écrit » — le
  moteur annonçait « réponse illisible » parmi ses cas écartés sans avoir de
  quoi le distinguer.
- Consigné en **D-CEO-38**. **D-CEO-35 et D-CEO-36 sont marquées caduques**,
  conservées pour mémoire.

**268 tests Django + 239 pytest passent.** Le total descend de 535 à 507 : les
43 tests du module 2 sont partis avec lui, 15 tests neufs couvrent le
branchement (correspondance des codes, réussite non diagnostiquée, priorité de
l'enseignant dans les deux sens, absence vs illisible, QCM sans appel, et les
refus de la commande sur un mode libre ou une correction non notée).

**⚠ Ce que ce travail ne fait pas.** Il ne donne toujours pas le chiffre du
module 4. Le branchement rend la mesure juste **possible** ; elle demande
maintenant de **corriger les trois copies 5e** dans l'application, puis de
comparer. C'est la prochaine étape, et elle ne dépend plus d'aucune calibration.

**Le contexte de la décision, à ne pas perdre.** Elle a été prise après un
constat de l'utilisateur : le projet s'était trop complexifié, et en production
de masse on ne peut pas exiger que toutes les copies respectent un format
strict. Le module 2 était le premier poste de cette dérive. D'autres ont été
identifiés et attendent leur tour : Streamlit (3 106 lignes), les trois clients
IA non retenus (1 671), la double persistance SQLAlchemy/Alembic à côté de
l'ORM Django (450), la mesure plancher (276), et le module 5 tel qu'il est
spécifié. Ainsi que le principe général : **dégrader plutôt que refuser** — une
page manquante ou un scan bancal doivent marquer la copie « à revoir », jamais
la jeter.


### 2026-08-05 — Quatre jours de travail remis dans le suivi, et la règle qui a sauté

Session de rattrapage. Le travail des **2 et 3 août n'était ni commité ni
documenté** : ni journal, ni registre de décisions, ni fiche de module. Il est
maintenant dans l'historique, en trois commits, et cette entrée dit ce qu'il
contient — c'est le rôle de ce fichier.

**Ce qui avait été fait hors du suivi :**

1. **Un système visuel unifié** (`templates_django/base.html`, +667 lignes, et
   les onze templates repris dessus). Les écrans avaient été écrits pour
   fonctionner, pas pour être lus : six couleurs pour tout, tailles au jugé,
   `style="..."` posés au cas par cas. Le rendu change, les vues ne changent
   pas — les 253 tests Django passent sans une retouche.
2. **Un jeu d'identités factices** (`src/integrations/sheets_factices.py`) et
   **trois parcours de démonstration** (`manage.py donnees_demo`). Sans
   identifiants de Sheet, cinq écrans sur sept affichaient « momentanément
   indisponible » : la mise en page était intravaillable. Décision consignée
   en **D-CEO-37**, parce que ça touche à la discipline d'identité
   (D-CEO-20/21/25) et que ça méritait mieux qu'un commit muet.
3. **Des corrections réelles ont tourné** les 2 et 3 août (`runs/`, rapports
   PDF produits). Rien n'en a été consigné — aucun enseignement n'en a été
   tiré, et c'est autant de perdu.

**🔴 La règle qui a sauté, et il faut la nommer.** `CLAUDE.md` dit : « Ne pas
ouvrir le chantier du site web en parallèle du chantier v2. Un seul
chantier prioritaire à la fois. » C'est exactement ce qui s'est passé, quatre
jours durant, pendant que le module 4 attendait sa mesure juste. Le travail
livré est bon et il servira ; ce n'est pas lui qui est en cause, c'est le fait
qu'il ait déplacé la priorité sans que la décision soit prise ni écrite.

**⚠ Et ce travail ne fait pas avancer le module 8.** La tentation serait de
cocher des cases : il n'y a rien à cocher. Le module 8 demande **deux écrans**
— saisie/correction des réponses d'une évaluation, et fiche de séance tuteur —
et **aucun des deux n'existe**. Ce qui a été fait, c'est la présentation des
écrans déjà là. Utile, pas comptable ici.

**Configuration.** Les clés du projet étaient éparpillées entre `../.env` (non
lu par le code) et `Hakili_Lab/.env`. Tout est consolidé dans le second, seul
fichier lu (`hakili/settings.py` et `src/core/config.py`), et le premier est
neutralisé — deux copies de secrets ne peuvent que diverger en silence. Les six
clés ont été vérifiées valides auprès de leur fournisseur le 2026-08-05.
Gemini, DeepSeek et Mistral sont réactivés sur leurs étapes respectives : la
condition posée le 01/08 (« tant que ces clés sont vides, rester sur Claude »)
n'a plus lieu d'être, et `VISION_PROVIDER=claude` coûtait plus cher pour le
même travail. `DIAGNOSTIC_PROVIDER` **reste sur Claude** — `diagnose_constrained`
est le seul client à porter l'outil à `enum`, première des trois barrières du
module 4.

**🔴 Un manque bloquant, découvert en consolidant :** le fichier de clé JSON du
compte de service Google est **introuvable sur la machine**. `verifier_installation`
le signale comme seul point à corriger. Sans lui, les Sheets sont injoignables
et **personne ne peut se connecter à l'interface** — le jeu factice masque le
problème en développement, il ne le résout pas. À retélécharger depuis la
console Google Cloud, à déposer dans `Hakili_Lab/credentials/`.

**Une scorie à traiter un jour :** `sheets_factices.comptes_demonstration()`
n'est appelée nulle part. Sa raison d'être est d'afficher les PIN de
démonstration sur l'écran de connexion — sans quoi le jeu factice est
inutilisable, puisqu'on ne devine pas un PIN. Soit on la branche, soit on la
retire.

**Vérifié le 2026-08-05 : 253 tests Django + 282 pytest = 535 tests passent.**

**Prochaine étape : inchangée depuis le 1er août, et c'est bien le problème.**
Le levier reste le **sujet socle imprimé et scanné** — une manipulation, qui
débloque le tramage (module 2) *et* la mesure juste du module 4.

### 2026-08-01 (suite 5) — État des lieux, et trois écarts de doc corrigés

Session sans code : relecture de l'avancement, tests relancés, feuille de route
remise d'aplomb sur trois points où elle ne disait plus la vérité.

- **Compteurs de tests.** L'en-tête annonçait « 251 Django + 267 pytest = 518 »
  alors que le journal de la même journée disait 524. Mesuré :
  **253 Django + 271 pytest = 524, tout passe.** L'en-tête et la commande de
  reprise (qui parlait encore de « 170 tests Django ») sont corrigés.
- **🔴 La fiche du module 1 décrivait un module qui n'a pas été construit ainsi.**
  Elle était marquée ✅ dans le tableau d'ensemble, mais ses 11 sous-tâches
  étaient toutes vides et prescrivaient des **modèles SQLAlchemy dans
  `src/db/models.py` + une révision Alembic**. Le module a été fait en **Django**
  (`referentiel/`, `suivi/`, migrations Django), la bascule D-CEO-28 ayant été
  décidée le même jour. C'était l'écart le plus coûteux des trois : quelqu'un
  reprenant le chantier par cette fiche serait allé ajouter les 11 tables dans
  `src/db/models.py`, **où elles existent déjà sous Django** — soit exactement le
  doublon de source de vérité que ce projet a déjà démoli deux fois
  (D-CEO-20/21). Fiche réécrite sur ce qui existe, avec l'écart signalé en tête
  et les deux décisions de conception (settings sans `config.py`,
  `copy_id` en texte) conservées.
- **Quatre cases du module 3** restaient vides alors que le module est ✅ et que
  le travail est fait (66 problèmes tagués, transitions écrites, hésitations
  rapportées) — cochées. La cinquième, `PRQ`/`RED`, **reste ouverte à dessein**
  mais était formulée comme une tâche de tagage à reprendre (« à chercher dans
  les deux dernières copies », alors que les 5 sont taguées) : reformulée en
  limite structurelle, ce qu'elle est.

**Rien n'a été touché dans le code.** Les compteurs de coûts de la fiche du
module 1 portent la mention du passage de 444 à 606 lignes (D-CEO-29), pour
qu'on ne prenne pas le chiffre d'époque pour l'état courant.

**Prochaine étape :** inchangée. Le levier hors code est le **sujet socle imprimé
et scanné** — une seule manipulation débloque le tramage (module 2) *et* la
mesure juste du module 4. Côté code, le point dur reste le **type d'erreur**,
`ATT` en tête. Et les **seuils A/B/C** n'ont toujours pas été rejugés après la
hausse de ~33 % des coûts.

### 2026-08-01 (suite 4) — Coûts en heures entières, Sonnet 5, et un bug qui rendait « 0 problème » pour une panne de format

Trois demandes utilisateur, et un défaut sérieux découvert en les traitant.

#### 1. Les écarts de coût négatifs — ce n'est pas un bug de calcul

`ecart_cout = cout_produit − cout_etalon`. Un écart négatif dit que le module 4
**sous-estime** : il chiffre moins d'heures que le tagage manuel. Ce n'est pas une
erreur d'arithmétique, c'est le résultat de la mesure — et c'est le sens le plus
inquiétant des deux. Une surestimation facture des heures inutiles et se voit sur
la facture ; une sous-estimation inscrit un élève sur un volume qui ne suffira
pas, et **ressemble à un devis raisonnable**. Le compte rendu de
`mesurer_plancher` lit désormais le signe à voix haute plutôt que de laisser
interpréter un `+` ou un `−`.

⚠ **Ne pas agréger les écarts.** Sur la première série, +3,5 h de somme cachaient
des écarts par copie de −4 h à +5,5 h qui se compensaient. Ce que paie une
famille n'est pas la moyenne du centre.

#### 2. 🔴 Le défaut que la question a fait remonter : la règle d'arrondi ne s'appliquait qu'à 27 % de la grille

En allant régler l'arrondi, constat : **les 444 coûts officiels étaient lus tels
quels dans le classeur** (`importer_referentiel.py`, `cout_heures=_decimal(r[6])`).
Seules les 162 lignes de lycée passaient par `cout_remediation()`. Autrement dit
la formule documentée dans `referentiel/couts.py` — « arrondi, plancher,
plafond » — **ne voyait jamais passer 73 % de la grille**. Changer la formule
seule n'aurait donc corrigé que 162 lignes sur 606, en silence, et le classeur
aurait continué d'imposer ses demi-heures.

Corrigé par un point de passage unique, `arrondir_heures()`, appliqué **aux deux
voies** à l'import. Mesuré au passage : sur les 444 officiels, 389 coïncident
avec la formule et **55 divergent** — tous des cas où le classeur avait arrondi
vers le bas (`G.MED × CPT` : 9 h × 0,35 = 3,15 → classeur 3 h). La valeur du
classeur reste la source (arbitrage G) ; c'est son arrondi qui est normalisé.

#### 3. Arrondi à l'heure entière supérieure (décision utilisateur)

Plus de demi-heures, toujours au-dessus : 1,5 → 2. `COUT_PLANCHER` passe de 0,5 h
à 1 h ; le plafond reste 4 h. Grille régénérée : **1 h × 394 · 2 h × 144 ·
3 h × 34 · 4 h × 34**, zéro valeur fractionnaire sur 606 lignes.

Deux conséquences à ne pas découvrir plus tard :
- **L'échelle se resserre.** Quatre valeurs au lieu de huit. Sur le lycée
  (volume de repli 4 h), quatre des six types remédiables tombent tous sur 1 h :
  le type d'erreur n'y départage presque plus rien. C'est la dégénérescence que
  le choix de 4 h évitait par le haut, revenue par le bas. Le test
  `test_le_repli_lycee_ne_departage_plus_que_deux_types` la consigne — **c'est
  un constat gardé sous les yeux, pas un objectif atteint.**
- **Les coûts montent de ~33 %,** donc les paliers glissent. L'étalon du corpus
  passe de 70 h à 93 h. Des élèves classés A (< 8 h) passeront en B. Le seuil
  A/B/C n'a pas été rejugé — à surveiller sur les premières sessions réelles.

Les coûts déjà **stockés** sur les problèmes (`Probleme.cout_estime` est copié à
la création, pas relu) restaient à l'ancienne échelle : nouvelle commande
`manage.py recalculer_couts` (avec `--a-blanc`). 46 problèmes réalignés,
45 h → 68 h. Elle **refuse de toucher** aux problèmes d'une session déjà
inscrite — un palier annoncé à une famille ne se réécrit pas dans son dos — et
les liste pour reprise à la main (2 cas, session `DEMO`).

#### 4. Sonnet 5 pour le diagnostic — et ce que ça coûte

`CLAUDE_MODEL_OPUS=claude-sonnet-5` (le champ garde son nom, qui ne désigne plus
un Opus — noté dans `.env`).

**🔴 Deux copies sur cinq rendaient « produit 0 ».** Pas une baisse de qualité :
une panne de format. Sonnet 5 emballe par intermittence sa sortie autrement que
le schéma ne le demande — soit `{"problemes": {…}}` (objet seul au lieu d'une
liste), soit, plus surprenant, **tout le JSON réemballé dans une chaîne à
l'intérieur du champ qu'il devait remplir** : `{"problemes": "{\"problemes\":
[…]}"}`. Pydantic refusait, la copie entière était perdue, et le compte rendu
affichait « produit 0 · rappel 0 % » — **un échec de format qui a l'apparence
d'un diagnostic vide.** C'est le symptôme le plus dangereux du lot : il ne
ressemble pas à une panne.

Traité par `ClaudeClient._normaliser_problemes`, qui déballe sans rien ajouter.
**Ce n'est pas une entorse à la règle « une sortie refusée n'est jamais réparée
à sa place »** : cette règle porte sur le contenu — on n'invente pas un code, on
ne déplace pas une compétence. Ici on ouvre une enveloppe. Les codes obtenus
repassent inchangés par la validation par question. Quatre tests verrouillent
les deux formes, le cas normal, et le refus de deviner sur une chaîne non-JSON.

**Le chiffre, une fois la panne levée :**

| copie | étalon | produit | exacts | type faux | manqués | en trop | rappel compétence | écart de coût |
|---|---|---|---|---|---|---|---|---|
| `3E-01` | 22 | 22 | 11 | 6 | 5 | 5 | 77 % | −13 h |
| `3E-02` | 10 | 7 | 1 | 4 | 5 | 2 | 50 % | −1 h |
| `5E-03` | 14 | 12 | 8 | 1 | 5 | 3 | 64 % | −6 h |
| `5E-04` | 9 | 9 | 5 | 0 | 4 | 4 | 56 % | −1 h |
| `6E-05` | 11 | 14 | 6 | 4 | 1 | 4 | 91 % | +8 h |
| **total** | **66** | **64** | **31** | **15** | **20** | **18** | **70 %** | **−13 h** |

**Sonnet 5 est nettement moins bon qu'Opus 4.7 sur cette tâche**, et il faut le
dire : rappel sur le couple **47 % contre 65 %**, rappel sur la compétence seule
**70 % contre 85 %**, précision **48 % contre 61 %**. Les 18 points de rappel
perdus ne sont pas du bruit sur 66 problèmes. Et **quatre copies sur cinq
sous-estiment** désormais le coût, là où la série Opus se partageait
équitablement entre sur- et sous-estimation.

Le basculement est fait comme demandé — c'est « en attendant ». Mais le prix est
réel, et le jalon du module 4 ne sera pas franchi sur ce modèle.

**Vérifié :** 253 tests Django + 271 pytest = **524 tests passent**.

**Prochaine étape :** inchangée sur le fond — le type d'erreur reste le point
dur, `ATT` en tête. S'y ajoute une question ouverte : **rejuger les seuils
A/B/C** après la hausse de ~33 % des coûts.

### 2026-08-01 (suite 3) — 🔢 Le module 4 a un chiffre : 85 % sur la compétence, 65 % sur le couple

Les cinq mesures plancher ont tourné contre les 66 problèmes du corpus.
**Le module 4 trouve la bonne compétence 85 % du temps, et le bon couple
`compétence × type d'erreur` 65 % du temps.**

| copie | étalon | produit | exacts | type faux | manqués | en trop | précision | rappel | rappel compétence | écart de coût |
|---|---|---|---|---|---|---|---|---|---|---|
| `CORPUS-3E-01` | 22 | 27 | 17 | 4 | 1 | 6 | 63 % | 77 % | 95 % | −4,0 h |
| `CORPUS-3E-02` | 10 | 9 | 4 | 4 | 2 | 1 | 44 % | 40 % | 80 % | **+5,5 h** |
| `CORPUS-5E-03` | 14 | 15 | 9 | 3 | 2 | 3 | 60 % | 64 % | 86 % | −1,5 h |
| `CORPUS-5E-04` | 9 | 8 | 5 | 0 | 4 | 3 | 62 % | 56 % | 56 % | +1,0 h |
| `CORPUS-6E-05` | 11 | 12 | 8 | 2 | 1 | 2 | 67 % | 73 % | 91 % | +2,5 h |
| **total** | **66** | **71** | **43** | **13** | **10** | **15** | **61 %** | **65 %** | **85 %** | **+3,5 h** |

**Ce que ces chiffres disent, et c'est le résultat de la session.** L'écart de
20 points entre 85 % et 65 % n'est pas du bruit : **le module 4 voit *où* ça
casse, et se trompe sur *pourquoi*.** C'est exactement le mode d'échec que la
fiche du module 4 désignait comme le plus coûteux — une compétence juste avec un
type d'erreur faux envoie le tuteur travailler la mauvaise chose pendant des
heures facturées, et aucune validation ne peut l'attraper puisque les deux codes
existent.

**Le défaut le plus net, et il a une conséquence financière directe : `ATT`.**
Le corpus porte 4 problèmes d'inattention ; le module 4 en produit **1**, et pas
au bon endroit — aucun des 4 n'est retrouvé. Ils reviennent en `CPT` ou en
`PRC`. Or `ATT` est **le seul type qui ne coûte rien** (non remédiable, D-CEO
module 6). Transformer une inattention en lacune conceptuelle **facture des
heures qui n'ont pas lieu d'être** : c'est la copie 2, dont l'étalon porte 3 des
4 `ATT` du corpus, qui affiche le pire écart de coût du lot — +5,5 h sur 8,5 h,
soit **+65 %**. Le palier de cet élève passerait de A à B sur cette seule
erreur de type.

**L'écart de coût agrégé est trompeur et il ne faut pas s'en servir.** +3,5 h
sur 70 h = +5 %, ce qui semble excellent. Mais les écarts par copie vont de
−4,0 h à +5,5 h : les surestimations et les sous-estimations se compensent en
agrégat alors qu'aucun élève n'est bien chiffré. **C'est l'écart absolu par
copie qui compte** — ce que paie une famille, ce n'est pas la moyenne du centre.

**Ce que ça ne dit pas.** C'est un plancher, et il est plus bas que le protocole
ne le laissait croire : le modèle a travaillé sans aucune signature d'erreur, et
sans les questions réussies (voir l'entrée précédente) alors que le tagueur
humain raisonnait explicitement par contraste. Le mode ancré du module 4 reçoit
3 à 4 signatures par question — il ne peut que faire mieux sur le type d'erreur,
qui est précisément ce que les signatures décrivent. **Ce chiffre n'atteste donc
pas le jalon**, il donne une base de comparaison pour le jour où le sujet
imprimé existera.

**Deux défauts d'exploitation corrigés en route, tous deux invisibles jusqu'à
l'exécution.**
1. **TLS.** Avast inspecte le HTTPS et signe les certificats avec sa propre
   racine, présente dans le magasin de Windows mais absente du bundle `certifi`
   qu'embarquent les SDK. Tout appel de modèle échouait sur
   `CERTIFICATE_VERIFY_FAILED` sur une machine dont le réseau marche par
   ailleurs. `manage.py` délègue désormais la vérification au magasin du système
   (`truststore`, ajouté aux dépendances) — rien n'est désactivé : ce que Windows
   refuse reste refusé.
2. **`temperature` sur Opus 4.7.** Le paramètre n'est plus accepté depuis
   Opus 4.7 et rend un 400 ; `claude_client.py` l'envoyait dans ses **onze**
   appels. Le filtrage se fait maintenant sur le nom du modèle, dans un passage
   obligé unique (`_creer_message`), plutôt qu'en retirant `temperature` de
   chaque appel : le même client sert Sonnet 4.6, qui l'accepte encore, et un
   changement de `CLAUDE_MODEL_HEAVY` dans `.env` aurait suffi à casser un appel
   resté correct par ailleurs. Le retrait est journalisé — un `temperature=0` qui
   disparaît en silence donnerait l'illusion d'un déterminisme qu'on n'a plus.

**Un défaut de la doc constaté au passage :** `.env.example` propose encore
`IMAGE_MIN_RESOLUTION` et `IMAGE_BLUR_THRESHOLD`, que `src/core/config.py` ne
déclare plus. `Settings` refuse les variables inconnues, donc **copier
`.env.example` en `.env` comme son en-tête le demande fait échouer toute commande
du pipeline.** Non corrigé ici (fichier versionné) — à retirer.

**Vérifié :** 251 tests Django + 267 pytest = **518 tests passent** après la
modification du client.

**Prochaine étape :** le chiffre existe, le point dur est désigné — le type
d'erreur, et `ATT` en particulier. Deux pistes, à trancher : (1) décrire `ATT`
explicitement dans `prompts/diagnostic_plancher_prompt.md` et re-mesurer, ce qui
coûte quelques centimes et dit tout de suite si le défaut est de prompt ou de
fond ; (2) attendre le mode ancré, dont les signatures portent justement la
distinction de type. La (1) ne dispense pas de la (2) mais l'éclaire. Reste
inchangé : imprimer, faire passer et scanner un sujet socle.

### 2026-08-01 (suite 2) — Les 5 copies sont transcrites ; la mesure plancher n'attend plus que la clé

Le travail manuel identifié comme prochaine étape par l'entrée précédente est fait :
les 5 copies du corpus sont transcrites en fichiers de productions
(`data/productions/corpus_3e_01`, `_3e_02`, `_5e_03`, `_5e_04`, `_6e_05`).
**Les 5 passent la validation de format et le contrôle anti-recopie** —
`mesurer_plancher` ne s'arrête plus que sur l'absence de modèle, ce qui est le
comportement attendu.

**Ce que la transcription a appris, et qui n'était pas dans le protocole**

1. **La consigne « recopier ce qui est écrit » était incomplète.** Les copies
   portent **trois encres** : le bleu de l'élève, le rouge du correcteur, le gris
   des tracés au crayon. Le module 2 avait déjà mesuré cette séparation sur un
   scan réel (2,3 % de pixels rouges) mais la conséquence n'avait pas été tirée
   ici : transcrire le rouge, c'est fournir la correction avec la production —
   exactement le piège que la commande interdit du côté des justifications, par
   une autre porte, et que rien n'aurait détecté. Consigné dans chaque fichier.
2. **Ne pas transcrire les questions réussies durcit la tâche plus que prévu.**
   C'est la règle de `exemple.yaml` et elle est appliquée. Mais le tagueur humain
   avait la copie entière et raisonne explicitement par contraste — la moitié des
   66 justifications du corpus dit « laissé vide *alors que* telle autre question
   est juste ». Le plancher mesuré sera donc plus bas que le protocole ne le
   laisse entendre : à interpréter comme tel, pas comme un mauvais résultat.
3. **Deux passages n'ont pas été transcrits, et c'est écrit dans les fichiers.**
   L'annotation de l'angle au rapporteur de `CORPUS-6E-05` se lit « 40 » ou
   « 60 » ; deux des quatre égalités vectorielles de `CORPUS-3E-01` ne se
   distinguent pas nettement du texte imprimé. Le module 3 avait déjà refusé de
   taguer ce même angle pour la même raison. Une lecture inventée pour compléter
   un fichier met l'erreur **dans l'instrument de mesure**.
4. **Une asymétrie assumée, à garder en tête au dépouillement.** La copie 5 a été
   transcrite après que sa fiche de tagage a été lue ; les copies 1 à 4 l'ont été
   à l'aveugle. Si son écart se détache des quatre autres, c'est la première
   explication à examiner.

**Ce qui bloque, et ce n'est plus du travail :** `anthropic` n'est pas installé
dans l'interpréteur courant (`pip install -r requirements.txt`) et il n'y a pas
de fichier `.env` ni de `ANTHROPIC_API_KEY` dans l'environnement.

**Vérifié :** 251 tests Django + 267 pytest = 518 tests passent (exécutés en début
de session, avant toute modification). Les 5 commandes `mesurer_plancher` ont été
lancées : les 5 franchissent validation et contrôle anti-circularité.

**Prochaine étape :** installer les dépendances, renseigner la clé, lancer les 5
mesures, consigner l'écart ici (exacts / type faux / manqués / en trop, et écart
de coût en heures). En parallèle, toujours : imprimer, faire passer et scanner un
sujet socle — il débloque le tramage du module 2 et la mesure juste du module 4.

### 2026-08-01 (suite) — 🟨 Module 4 : le moteur tourne, et il n'a rien contre quoi se mesurer

Le diagnostic contraint est écrit, testé et exécutable de bout en bout
(`manage.py diagnostiquer`). **La moitié mécanique tourne sans aucune clé d'API** :
vérifié sur le référentiel réel, un QCM coché `d` à la question `D2` du test de
3ème rend `M.ECH × CPT` sans qu'aucun modèle soit appelé, et une question de
construction est orientée vers la saisie humaine. 71 des 280 questions sont dans
ce cas — c'est un quart du diagnostic gratuit et infaillible.

**Trois choix de conception, et ce qu'ils évitent**

1. **Les compétences admises pour une question sont sa compétence *et ses
   prérequis*.** Restreindre à la seule compétence de la question rendrait `PRQ`
   inexprimable — ce type d'erreur signifie précisément que la lacune est en
   amont (« il ne rate pas les identités remarquables, il ne sait pas additionner
   deux relatifs »). C'est aussi ce qui donne un usage au graphe des prérequis
   côté diagnostic, et non plus seulement côté plan.
2. **Rien n'est deviné, et ce qui n'est pas jugé est nommé.** Un QCM sans case
   cochée n'est pas rattaché à `CNS` : aucune option ne décrit une case vide, et
   lui en attribuer une inventerait une lacune, avec un coût, dans le palier d'un
   élève. « b et c » n'est pas lu comme « b ». Ces cas partent dans
   `questions_ecartees`, qui est rendue au compte rendu — sans ça, leur absence
   de problème se lirait comme une réussite.
3. **Une sortie refusée n'est jamais réparée à la place du modèle.** On lui rend
   les motifs, on redemande une fois, et ce qui reste invalide est abandonné. Une
   lacune manquée se rattrape au test suivant ; une lacune inventée envoie un
   tuteur travailler la mauvaise notion pendant des heures facturées.

**Ce que l'`enum` du schéma change au jalon — et il faut le dire.** Les codes
admis sont déclarés en `enum` dans l'outil : un code hors référentiel devient
presque impossible à produire. Le jalon « 100 sorties consécutives valides » est
donc **en grande partie garanti par construction** et ne prouvera pas grand-chose.
Le contrôle qui compte est ailleurs : la validation **par question**, seule à
attraper un code valide mais mal placé — celui qui passerait tout le reste sans
un mot. C'est le même piège que le module 3 avait rencontré au tagage (`G.VOC`
existait, le tagage l'avait cru absent) : ce n'est jamais le code inventé qui fait
mal, c'est le code plausible.

**🔴 Le constat qui pèse le plus, et il contredit cette feuille de route.** La
fiche du module 2 annonçait que le module 4 se mesurerait « d'abord sur le corpus
de référence ». **Ce n'est pas possible.** Le diagnostic contraint travaille par
question — énoncé, compétence, prérequis, signatures, tous tirés des 280 questions
v2. Les 5 copies du corpus sont de l'**ancien format** et n'en portent aucune.
Le module 3 avait déjà constaté qu'aucune `Reponse` n'y était enregistrable ; la
conséquence sur la mesure n'avait pas été tirée. **Le module 4 est donc écrit,
mais aveugle** — trois issues sont posées dans sa fiche, aucune n'est gratuite.

**Le branchement au pipeline n'est pas fait, et c'est délibéré.** Il est
mécaniquement trivial (pour les 7 tests v2, l'identifiant d'item du barème *est*
le code de question). Mais le brancher en parallèle double le coût par copie face
à une cible de $0,02, et le brancher en remplacement retire à l'enseignant le
rapport PDF et le sujet de remédiation, qui se nourrissent du texte libre et n'ont
pas encore d'équivalent structuré — ce sont les modules 7 et 9. Trois options
posées dans la fiche, à trancher.

**Une décision de schéma prise en passant.** `guide-v2.md` demande « une ligne
dans `transition` » à la création d'un problème. Ce n'est pas faisable —
`Transition` interdit `etat_avant == etat_apres` — et surtout le corpus de
référence n'en écrit pas : en écrire ici rendrait les deux jeux non comparables et
fausserait le taux de confirmation du module 9. La date de l'hypothèse est portée
par `evaluation_origine.date`, ce qui est plus juste qu'une date d'écriture en base.

**Un défaut d'exploitation corrigé au passage.** Le compte rendu emploie `└`,
absent de cp1252 — l'encodage par défaut d'une console Windows. La commande
s'interrompait sur une trace d'encodage **au milieu** de la liste des problèmes,
ce qui donne l'illusion d'un diagnostic en échec alors qu'il a abouti. Le flux est
désormais dégradé plutôt qu'interrompu. `taguer_corpus` et `corpus` portent le
même caractère et donc le même risque latent — non traité ici.

**Deux arbitrages rendus dans la foulée.**
- **Mesure : les deux à la fois.** La mesure plancher est écrite (`mesurer_plancher`) et donne un signal sans rien attendre ; la mesure juste attend le sujet imprimé, nécessaire de toute façon au module 2. Écarté : rapprocher les questions des anciens tests du référentiel, qui aurait mis la marge d'erreur d'un rapprochement **dans l'instrument de mesure**.
- **Pipeline : différé.** Rien ne s'approche d'un enseignant avant l'écart mesuré — c'est le jalon go/no-go de ce document. Le module s'alimente à la main en attendant.

**Le piège de la mesure plancher, désamorcé avant d'avoir été tendu.** Alimenter
la mesure avec `Probleme.justification` (déjà en base pour les 66 problèmes) était
la voie facile : ces justifications portent le diagnostic en toutes lettres, donc
le score aurait été excellent et vide de sens. **C'est le pire cas de figure —
personne ne met en doute un bon chiffre.** La commande compare chaque production
aux justifications de l'étalon et refuse de tourner au-delà de 75 % de
ressemblance ; vérifié en lui soumettant une justification recopiée, rejetée à
100 %. `ORDRE_NIVEAUX`, dupliqué dans le tagage du corpus, a été ramené à une
seule définition (`referentiel/niveaux.py`) — les deux modules posent la même
question sur l'ordre des niveaux.

**Vérifié :** 50 tests nouveaux (35 sur le moteur, 9 sur l'écriture et la mesure,
6 sur les schémas), dont « aucun appel de modèle pour un QCM » qui échoue si le
client est seulement touché. **251 tests Django + 267 pytest = 518 tests passent.**
Les deux commandes ont été exécutées sur le référentiel réel (101 compétences, 280
questions) : `diagnostiquer` rend `M.ECH × CPT` sur un QCM sans aucun appel de
modèle, `mesurer_plancher` s'arrête proprement faute de clé d'API.

**Prochaine étape, dans l'ordre :** transcrire les 5 copies du corpus en fichiers
de productions (aucun jugement, seulement recopier ce qui est écrit), lancer la
mesure plancher avec une clé, consigner l'écart ici. En parallèle : imprimer,
faire passer et scanner un sujet socle — il débloque à la fois le tramage du
module 2 et la mesure juste du module 4.

### 2026-07-30 (suite) — Nettoyage, et un bug sérieux qu'il a révélé
- **Nettoyage** : 22 fichiers supprimés (docs périmées, schémas JSON morts, orphelins), 3 bibliothèques retirées. Détail et faux positifs écartés : D-CEO-31.
- **Bug découvert en inventoriant : le RAG était mort sur les 7 nouveaux tests.** `socle_3eme` recevait 0 caractère de contexte programme, contre 2 048 pour un ancien test. Cause : l'ancrage passait par `chunk_ids`, champ que les barèmes générés depuis le classeur n'ont pas. Le pipeline n'échouait pas — il produisait un diagnostic générique, exactement ce que D-CEO-12 qualifie d'inutilisable.
- **Réparé sans attendre l'arbitrage C** : le contexte est reconstruit depuis le référentiel (compétence, chaîne de prérequis sur deux niveaux, signatures propres à la question). Mesuré : 3 490 caractères et 3 lacunes pour trois questions de 3ème. Voir D-CEO-30.
- **Un diagnostic sans ancrage est désormais journalisé en avertissement** — c'est ce silence qui avait laissé le défaut vivre.
- **Vérifié :** 112 tests Django + 218 pytest = **330 tests passent**, et `src/` ne contient toujours aucun import Django.

### 2026-07-30 (suite) — Sujets intégrés au projet
Les 7 PDF ont été déposés dans `data/Documents/`, et les anciens DOCX retirés. Deux conséquences traitées :

- **Les avertissements « DOCX introuvable » sur les tests archivés étaient trompeurs** : leurs sujets ont été refaits, l'absence est normale. Passés en information pour les tests archivés, l'avertissement restant réservé aux cas réellement anormaux. Vérifié que les tests archivés gardent leurs `niveaux` — c'est ce dont dépend la résolution de classe des copies historiques.
- **Les sujets deviennent imprimables depuis l'application** (`/sujets/`). L'élève compose **sur le sujet** : l'enseignant doit pouvoir l'imprimer autant de fois qu'il a d'élèves, sans aller chercher le bon fichier ailleurs — avec le risque de distribuer la mauvaise version. Réservé aux personnes connectées : un sujet d'évaluation diffusé à l'avance perd sa valeur diagnostique. Les tests archivés n'ont pas de sujet et ne sont donc pas distribuables.
- La page rappelle les consignes d'impression qui conditionnent la lecture automatique : noir et blanc, recto seul, **sans réduction** — les cadres doivent garder leur taille, c'est ce qui permettra au module 2 de les détecter.

**Vérifié :** 87 tests Django + 218 pytest = **305 tests passent**.

*Ajouter une entrée à chaque session de travail sur ce chantier — même courte, même si rien n'a été codé. Format : date, ce qui a été fait, décisions prises, ce qui bloque, prochaine étape.*

### 2026-07-30
- Lu `guide-v2.md`, `protocole-v2.md`, exploré `Referentiel_Socle_v0.xlsx` (9 onglets confirmés : 101 compétences, 7 types d'erreur, 280 questions, 1031 signatures, 284 distracteurs, 444 coûts), vérifié le format des nouveaux sujets sur `Test_diagnostique_entree_6eme.pdf` (cadres ancrés confirmés).
- Constaté que `docs/decision_register.md` est à jour et fiable, mais que `CLAUDE.md`/`AGENTS.md`/`README.md` sont périmés (décrivent le tableau de validation enseignant comme "à construire" alors qu'il est implémenté ; ignorent totalement Postgres/Neon, Google Sheets, l'auth par rôle).
- **Décisions actées avec l'utilisateur :** (1) les 11 tables du guide vivent dans Postgres/Neon existant, pas une SQLite séparée ; (2) le diagnostic structuré remplace directement le diagnostic texte libre, niveau par niveau ; (3) `CLAUDE.md` réécrit en place plutôt qu'un nouveau document séparé.
- `Hakili_Lab/CLAUDE.md` réécrit : état réel de l'infra + chantier v2 comme priorité active.
- Ce document (`docs/v2_roadmap.md`) créé comme source de vérité unique pour l'avancement, avec détail des 9 modules, jalons de validation, et ce journal.
- **Bloqué par :** rien techniquement — le Module 0 (appropriation manuelle du référentiel) peut démarrer immédiatement.
- **Prochaine étape :** Module 0, puis Module 1 (migration Alembic).

### 2026-07-30 (suite) — Module 0 terminé
- Parcouru les 9 onglets du classeur. Tracé 3 questions du test de 3ème (L5 QCM, L7 court, G13 rédigé) de bout en bout : `04_Questions` → `05_Grille_diagnostic` → `06_Distracteurs` → `08_Cout_remediation`.
- Question de contrôle répondue : **L5 option a) → problème `L.IDR × CPT` → 0,5 h** (détail et dérivation dans la fiche Module 0 ci-dessus).
- **Intégrité du classeur vérifiée par script : 0 violation.** Aucune question sans compétence, aucune signature avec type/compétence inconnu, aucun distracteur avec type inconnu, `07_Couverture` à écart 0 sur ses 116 lignes, 280/280 questions couvertes par 3-4 signatures. Le module 1 peut écrire un import strict (échec sur code inconnu) sans craindre de faux positifs.
- Piège des codes locaux confirmé empiriquement : `N-a` = 7 compétences canoniques différentes selon le test ; un code local peut aussi pointer vers plusieurs codes canoniques.
- **3 anomalies remontées** (détail dans la fiche Module 0) : (1) `08_Cout_remediation` = 74 × 6, pas 101 × 7 — `ATT` sans ligne de coût par construction, et 27 compétences lycée sans coût, ce qui **rend le palier du module 6 incalculable en 2ndeC/1ereD** ; (2) un **4ème format de question, `construction` (7 questions)**, absent de `guide-v2.md` module 2 — attend un tracé, pas du texte ; (3) `ATT` apparaît 2 fois en partie B, mineur.
- Fiches Module 2 et Module 6 et point ouvert #2 mis à jour en conséquence.
- **Bloqué par :** rien. Les anomalies 1 et 2 demandent un arbitrage utilisateur/docteur mais ne bloquent pas le Module 1.
- **Prochaine étape :** Module 1 — modèles SQLAlchemy, migration Alembic, script `import_referentiel.py`.

### 2026-07-30 (suite) — Investigation harmonisation des données
- Investigation demandée sur l'écart entre les données de test existantes (`Hakili_Lab/data/knowledge/`) et le référentiel v2. Résultat complet : **`docs/harmonisation_donnees.md`**.
- **Résultat central :** les 7 nouveaux PDF et le classeur sont **parfaitement alignés** (280/280 codes de question identiques, intitulés correspondant mot à mot). L'ancien système n'est aligné avec rien : aucun identifiant commun, vocabulaire de compétences en texte libre, ancrage par `chunk_ids` disjoint des codes canoniques, nombre de questions variable (26 à 54 contre 40 systématiques).
- **Manque bloquant découvert, non signalé par `guide-v2.md` :** le référentiel ne contient de bonne réponse que pour les 71 QCM. **209 questions sur 280 (75 %) n'ont aucun corrigé** — la Phase A est impossible dessus, ce qui bloque les modules 3 à 9. L'ancien système, lui, a des corrigés complets et de bonne qualité (format `reponse` + `solution`), transposable comme modèle.
- **Divergence de barème :** classeur sur 60 pts (30 A + 30 B), PDF sur 20 pts. Rapport exactement 3, poids relatifs identiques — conversion mécanique, mais l'échelle de stockage doit être tranchée avant la migration.
- **4 défauts actifs constatés dans l'ancien système** (documentés, non corrigés) : (1) **bug de notation en production** — une copie parfaite donne 20,5/20 au test 3e v1, 18,5/20 au 3e v2, 19,5/20 au tle, à cause du dénominateur `total_possible` divergent de la somme réelle des `max_score` ; (2) `meta.total_questions` faux dans 4 barèmes sur 6 ; (3) `bareme_test_3e.yaml` utilise `score_max` alors que le loader ne lit que `points_originaux` — champ silencieusement ignoré ; (4) **RAG dégradé en silence** : 16 `chunk_ids` cassés, 69/121 chunks jamais utilisés, 38 questions sans ancrage, le tout journalisé en `logger.debug` donc invisible en exploitation.
- **6 arbitrages formulés** (§9 du document) : A archivage des anciens tests · **B production des 209 corrigés — chemin critique** · C sort du curriculum RAG · D échelle de barème · E volumes lycée · F traitement du format `construction`.
- **Bloqué par :** arbitrages B et D à rendre avant d'écrire la migration du Module 1 (le schéma de la table `question` en dépend).
- **Prochaine étape :** décision utilisateur sur les arbitrages, puis Module 1.

### 2026-07-30 (suite) — Arbitrages A et D rendus et appliqués
- **Décision A → A1 : les 6 anciens tests sont archivés.** Appliqué dans `src/knowledge/test_registry.py` : champ `archive: True` sur les 6 entrées du catalogue, nouveau champ `HakiliTest.archive`, `available_tests()` filtre les archivés, `all_tests()` ajouté pour l'historique.
- **Archivage fait sans casser l'historique** — point vérifié avant de coder : `get_test()` continue de résoudre les tests archivés, car `pipeline.py:375` s'en sert pour déterminer la classe d'une copie déjà corrigée (`_apply_extracted_classe`). Les retirer du catalogue aurait dégradé silencieusement la relecture des copies existantes. Seul `available_tests()` (menu de sélection UI) les masque.
- **Conséquence visible assumée :** l'interface ne propose plus aucun test Hakili tant que les 7 nouveaux ne sont pas intégrés — le menu ne contient que « Test personnalisé ». Comportement attendu de A1, signalé à l'utilisateur.
- **Décision D : barème stocké sur 20.** Conversion `bareme_classeur / 3` à l'import. Le tiers de point (partie A) n'étant pas représentable exactement, la décision s'accompagne d'une règle : **la note se calcule toujours contre la somme réelle des `max_score`, jamais contre un total déclaré.** Cette règle rend l'imprécision inoffensive (copie parfaite = 20,00 exactement) et corrige du même coup le bug §5.1 constaté en production. Elle donne enfin un usage au champ `rubric_actual_max` déjà présent mais inutilisé dans `CopyGrade`.
- **Vérifié :** `available_tests()` vide, `all_tests()`/`ids` complets, `get_test('hakili_3e_v1')` résout toujours (archive=True, niveaux intacts). Suite de tests : **102 passent**. Les 2 erreurs de collecte (`test_google_sheets.py`, `test_ui_math.py`) sont pré-existantes et sans rapport — absence de `.env` local, `ANTHROPIC_API_KEY` manquante à l'import de `config.py`.
- **Bloqué par :** rien pour le Module 1. Arbitrages B, C, E, F toujours en attente (B est le chemin critique pour les modules 3 à 9).
- **Prochaine étape :** Module 1 — modèles SQLAlchemy, migration Alembic, `import_referentiel.py`.

### 2026-07-30 (suite) — Les 7 nouveaux tests générés et opérationnels
- **Découverte qui a changé l'approche : les énoncés ne sont pas extractibles des PDF.** Les 7 sujets sont produits par WeasyPrint et **toutes les mathématiques sont dessinées en vectoriel** (211 tracés sur une page, aucun span de texte). L'extraction rend la prose sans les formules : `N5` → « Recopier et compléter avec le symbole  ou le symbole  :  et  . ». Tous les modes d'extraction testés, aucune source HTML ni script générateur trouvé sur le disque.
- **Nuance importante : les codes de cadre s'extraient parfaitement** — c'est ce qui avait permis la vérification 280/280, et c'est tout ce dont le module 2 a besoin. Le problème ne touche que les énoncés littéraux.
- **Point qui débloque tout :** dans ce format l'élève compose **sur le sujet**, donc la copie scannée porte l'énoncé imprimé que l'IA transcrit. `subject_text` devient non critique, alors qu'il aurait été bloquant dans l'ancien format à copie séparée.
- **Décision G (nouvelle) : le classeur est la source des données de test**, pas les PDF. `04_Questions` donne code/partie/format/barème/compétence/intitulé, `06_Distracteurs` donne les options QCM avec la bonne réponse.
- **Livré :** `scripts/generer_baremes_socle.py` (idempotent, vérifié par hachage) génère les 7 `data/knowledge/bareme_socle_*.yaml`. **280 questions, 71 QCM avec bonne réponse, 209 champs `reponse_attendue`/`solution` vides** prêts pour l'arbitrage B — aucune migration corrective ne sera nécessaire.
- **Format YAML plat** (`questions`) et non l'ancien découpage `questions_numeriques`/`questions_geometriques` : les 7 domaines du référentiel (N, L, G, D, F, M, S, T) n'y rentrent pas. `_build_rubric_from_yaml` accepte désormais les deux formats — l'ancien reste lu pour les tests archivés.
- **Les 7 tests déclarent une classe canonique unique** (`6e`…`Tle`) au lieu des niveaux évalués. Vérifié au passage que `normalize_classe` ne reconnaît **pas** `2ndeC`/`1ereD`/`TleD` (retourne `None`) — d'où l'emploi des formes canoniques. Bénéfice : `resolve_classe` a un garde-fou exact et un repli fiable si l'extraction d'en-tête échoue, ce que les anciens tests n'offraient pas.
- **Propriété centrale vérifiée : une copie parfaite vaut exactement 20,0/20 sur les 7 tests**, malgré les tiers de point de la partie A (somme réelle 19,99999, absorbée par l'arrondi au quart). Verrouillé par test de régression.
- **Vérifié :** `tests/test_baremes_socle.py` — 40 questions/test, structure 30 A + 10 B, barème /20 = classeur/3, classe reconnue par le normaliseur, codes uniques, QCM avec bonne réponse unique, distracteurs tagués par un type de la liste fermée, 209 sans corrigé = exactement les non-QCM, copie parfaite = 20/20, copie nulle = 0/20, archivés masqués mais résolus. **168 tests passent** (102 avant, 66 nouveaux).
- **Limite cosmétique connue :** les intitulés du classeur sont en ASCII replié (254/280 sans accents) et apparaissent tels quels comme libellés dans l'interface. Sans effet sur la correction ni le diagnostic ; corrigeable plus tard sans changement de schéma.
- **Bloqué par :** rien. **Prochaine étape : Module 1.**

### 2026-07-30 (suite) — Accents traités, architecture cible recommandée
- **Accents : ce n'est pas un problème d'encodage mais de saisie dans le classeur**, qui se contredit lui-même (« apres » 34× vs « après » 36×, « carre » 29× vs « carré » 10×). L'auteur a bien tapé des accents (204 mots distincts en portent) — les formes nues sont des oublis.
- **Mesuré : 150 mots à corriger, 16 à arbitrer** sur 2 314 mots distincts des colonnes lisibles.
- **Correction automatique écartée délibérément :** pour 16 mots, la forme sans accent est aussi un mot français valide — « calcule » (je calcule) ou « calculé » ? « eleve » (l'élève) ou « élevé » (au carré) ? « cote » a 4 lectures. Un remplacement à l'aveugle écrirait un contresens pédagogique dans un libellé lu par un parent. Même règle que partout : ne jamais deviner une donnée.
- **Livré :** `scripts/verifier_accents.py --rapport` → `docs/accents_a_corriger.md`, document remettable tel quel au docteur (mot, correction, occurrences, onglets, et les 16 ambigus séparés avec leur piège explicité). La correction se fait dans le classeur, pendant la relecture pédagogique déjà requise par `00_Notice`.
- **Verrou :** `tests/test_accents_referentiel.py` fixe les plafonds (150 / 16) et échoue si le classeur régresse — **et aussi s'il s'améliore**, pour forcer l'abaissement du plafond, sinon le garde-fou se relâcherait. C'est ce qui répond au « une bonne fois » : le défaut ne peut plus revenir sans être vu, contrairement aux `chunk_ids` cassés restés invisibles en `logger.debug`.
- **172 tests passent** (168 avant).
- **Architecture : recommandation écrite dans `docs/architecture_cible.md`** — sortir de Streamlit pour **Django + HTMX**. Mesures à l'appui : `app.py` fait 2 876 lignes (26 % du projet, 342 appels `st.*`, 71 `session_state`, 30 blocs HTML en chaînes), mais **70 % du code est déjà indépendant du framework** (pipeline, clients IA, RAG, PDF, Sheets migrent intacts). Les deux arguments décisifs pour Django : l'auth/permissions intégrées (données nominatives de mineurs sur 7 mois, point ouvert #4 / CIL Burkina Faso — le PIN est aujourd'hui en clair dans un Sheet, sans jeton de session ni autorisation par requête) et l'`admin` qui couvre presque gratuitement les écrans du module 8 sur 11 tables relationnelles.
- **Le moment est critique :** les 11 tables ne sont pas encore écrites. Décider du framework **avant** le Module 1, sinon 11 modèles SQLAlchemy + une migration Alembic seront à jeter.
- **Bloqué par :** décision framework, et une question qui la conditionne — **les centres ont-ils une connexion fiable ?** Si le tuteur doit remplir sa fiche hors ligne, il faut une PWA avec file d'attente locale, ce qui change la conception.
- **Prochaine étape :** trancher l'architecture, puis Module 1 dans la cible retenue.

### 2026-07-30 (suite) — Contraintes d'architecture tranchées
- **Décidé : pas de hors ligne** (connexion Internet requise), **pas de PWA**, **base sur Neon inchangée**.
- **Effet :** ces trois réponses lèvent la seule réserve qui pesait sur la recommandation. Sans besoin hors ligne, aucune API explicite n'est nécessaire et Django REST Framework devient inutile — **Django + HTMX en rendu serveur est la réponse, sans nuance.** Le module 8 (fiche tuteur sur téléphone) devient une page HTML responsive à 5 champs, pas une application installable.
- **Simplification obtenue :** pas de service worker, pas de file d'attente locale, pas de synchronisation ni de résolution de conflits.
- **Seul point pratique encore ouvert : où héberger l'application.** Vérifié que l'app tourne aujourd'hui **en local** (`streamlit run`, aucun `Procfile`, `runtime.txt` seul vestige d'un déploiement envisagé) — Neon ne fournit que la base. Une app Django multi-utilisateurs (tuteurs sur téléphone, responsables, admin) suppose une adresse joignable : hébergeur, domaine, HTTPS, sauvegardes.
- **Conséquence à ne pas manquer sur le point ouvert #4 :** dès que l'application quitte le poste local, les données nominatives de mineurs transitent sur le réseau. HTTPS devient obligatoire et le remplacement du PIN en clair par une vraie authentification devient urgent — c'est exactement ce que Django apporte.
- **Bloqué par :** choix de l'hébergement, et feu vert sur la migration (plusieurs semaines d'interface).
- **Prochaine étape :** feu vert → squelette Django + les 11 tables (= Module 1 fait directement dans la cible).

### 2026-07-30 (suite) — ✅ Module 1 fait, en Django
- **Décidé :** hébergement **Railway ou Render** ; feu vert pour Django. Django 5.2 installé, ajouté à `requirements.txt`.
- **Livré :** projet `hakili/` (settings, urls, wsgi, asgi) + apps `referentiel` et `suivi` + `manage.py`. `src/` n'a pas été touché — pipeline, clients IA, RAG, PDF et Sheets restent intacts, et Streamlit continue de tourner.
- **11 tables migrées** : `referentiel` (Competence, Prerequis, TypeErreur, CoutRemediation, Question, SignatureErreur, OptionQcm) et `suivi` (Session→`session_suivi`, Evaluation, Reponse, Probleme, Transition, Seance). Cycle descente/remontée testé, comme sur les migrations Alembic précédentes.
- **Import du référentiel** (`manage.py importer_referentiel`, idempotent, vérifié sur deux passages) : **7 types · 101 compétences · 136 prérequis · 444 coûts · 280 questions · 1031 signatures · 284 options · 71 QCM corrigés · 209 sans corrigé**. Chiffres identiques au module 0. Contrôle d'intégrité **avant** toute écriture : un code inconnu fait échouer l'import avec un message précis, plutôt que d'écrire à moitié.
- **Vérifié en base : L5 du test de 3ème redonne exactement la réponse du module 0** — `L.IDR × CPT`, coût 0,50 h, bonne réponse `d`, distracteurs tagués CPT/PRC/PRC.
- **Admin configuré** sur les 11 tables : compétences filtrables par domaine et niveau (volume manquant signalé en rouge), questions par test/format avec leurs signatures et options en ligne, problèmes avec état coloré et historique des transitions. C'est ce qui remplace une bonne part des écrans du module 8.
- **`Transition` est protégée par le code, pas par la discipline** : `Probleme.changer_etat()` refuse un enchaînement non prévu, écrit la transition dans la même opération atomique, et `Transition.save()` refuse toute modification après création. L'admin met `etat` en lecture seule pour qu'on ne puisse pas contourner la méthode.
- **Deux décisions de conception prises en cours de route, motivées :**
  1. **Les settings Django ne lisent pas `src/core/config.py`** — `Settings()` exige `anthropic_api_key` sans défaut, ce qui ferait échouer `manage.py migrate` sur une machine sans clé LLM, alors qu'une migration n'appelle aucun modèle.
  2. **`Evaluation.copy_id` est un champ texte, pas une clé étrangère.** Tentée d'abord en FK vers une `Copie` non gérée : les tests ont révélé que Django ne crée pas les tables non gérées en base de test, donc toute insertion échouait. Le contournement (lanceur de tests flexant `managed`) ne marche pas non plus, les migrations figeant `managed: False`. Le lien souple est de toute façon le bon choix — c'est exactement le précédent de `identifiant_hakili` (D-CEO-20) : quand la donnée référencée est hors du territoire de Django, on garde un identifiant et on documente. Deviendra une vraie FK quand `copie` passera sous Django.
- **Réglages Neon repris de D-CEO-19 :** `CONN_HEALTH_CHECKS` (= `pool_pre_ping`) et `CONN_MAX_AGE=300` (= `pool_recycle`) — sans quoi les connexions mortes après la mise en veille de Neon provoqueraient des écritures perdues, comme constaté à l'époque.
- **Sécurité posée d'emblée :** `DJANGO_SECRET_KEY` obligatoire hors DEBUG (échec au démarrage plutôt qu'une clé de repli), HTTPS forcé, cookies sécurisés, HSTS, en-tête proxy Railway/Render. Nécessaire dès que l'application quitte le poste local avec des données de mineurs.
- **Vérifié :** 15 tests Django (`manage.py test suivi`) dont **le parcours complet T0→T5 d'un élève fictif avec toutes ses transitions** — le critère de fin du module 1 tel qu'écrit dans `guide-v2.md`. Plus : transitions interdites refusées, états terminaux bloqués, `ATT` ne pouvant jamais être confirmé, atomicité de `changer_etat`, unicité d'un problème par session, immuabilité des transitions, calcul du taux de confirmation. **Les 172 tests pytest existants passent toujours** — aucune régression sur Streamlit.
- **Support SQLite ajouté** à `DATABASE_URL` pour que tests et intégration continue tournent sans Neon ; la production reste sur Neon.
- **Bloqué par :** rien. **Prochaine étape :** Module 2 (lecture des copies par zones) ou migration des écrans Streamlit vers Django — à arbitrer.

### 2026-07-30 (suite) — Migration Streamlit → Django : fondations posées
Décision : migrer l'interface **avant** de continuer les modules v2, pour ne pas maintenir deux interfaces longtemps.

**Fait**
- **Logique métier extraite de `app.py`** vers `src/services/identite_service.py` : rôles valides d'une personne, vue utilisateur par casquette, recherche insensible casse/accents/ordre, nommage des documents, appariement fichier ↔ élève en batch. C'était du métier enfermé dans un fichier Streamlit de 2 876 lignes, donc intestable et perdu avec lui. `app.py` passe à 2 778 lignes et pointe vers le service par alias — aucune duplication. **23 tests** écrits au passage, dont les pièges déjà rencontrés (recherche insensible à l'ordre des mots, casquette responsable couvrant tout le centre).
- **Authentification Django adossée au Sheet** (`comptes/`) : backend relisant le Sheet personnel à chaque connexion, compte Django miroir **sans mot de passe utilisable** (le PIN reste dans le Sheet — pas de seconde source de vérité), rôle et casquette en session, décorateurs `connexion_requise` / `admin_requis`. Gain concret : vraie session signée et expirante (8 h), CSRF, autorisation vérifiée par requête — au lieu d'un booléen dans `session_state`.
- **Écrans migrés** : liste des élèves du périmètre avec pastille de tendance (`calculer_tendance` réutilisée, pas réécrite), recherche, tri des élèves en baisse en premier, statistiques admin, en-tête avec sélecteur de casquette. Gabarits responsive (`templates_django/base.html`), champs à 16 px pour éviter le zoom automatique sur iOS, `<select>` natif pour la connexion (le sélecteur du téléphone est déjà recherchable).
- **22 tests d'accès** figeant les scénarios vérifiés à la main sur Streamlit : PIN correct/incorrect, PIN absent du Sheet, rôle non reconnu, personne retirée du Sheet, cloisonnement responsable (tout son centre) / enseignant (sa classe) / admin (tout), changement de casquette refusé si non porté, refus en GET, aucune donnée sensible à l'écran (`contact_parents`, `identifiant_hakili`).

**Trois défauts trouvés et corrigés en cours de route**
1. **`anthropic_api_key` était obligatoire à l'import de la configuration**, or `google_sheets` et `db/database` en dépendent : `manage.py check`, `migrate` et même l'affichage d'une liste d'élèves échouaient sans clé LLM, alors qu'aucun de ces chemins n'appelle un modèle. Rendue facultative à l'import, avec l'exigence rétablie dans `ClaudeClient.__init__` — là où elle sert. **Effet de bord bénéfique : les 2 erreurs de collecte pytest qui traînaient (`test_google_sheets`, `test_ui_math`) sont réparées, la suite tourne maintenant sans `.env`.**
2. **Commentaires de gabarit multi-lignes rendus en clair dans la page** : Django ne supporte `{# #}` que sur une ligne. Convertis en `{% comment %}`.
3. **Une base injoignable rendait une erreur 500** au lieu de dégrader : la liste des élèves vient des Sheets et reste affichable sans les notes. La vue affiche désormais la liste sans la tendance, en le disant — Neon se met en veille, ce cas arrivera.

**Choix de conception notable :** les modules Django importent `google_sheets` **en tant que module**, pas ses fonctions par leur nom. Une fonction importée par son nom fige sa référence et devient impossible à simuler en test sans connaître tous les modules qui l'ont importée — c'est ce qui faisait échouer les 21 premiers tests d'authentification.

**Reste à migrer** (Streamlit reste en service en attendant) :
- Historique détaillé d'un élève, profil enseignant, comparaison chronologique, aperçu et téléchargement des PDF.
- **Le flux de correction** (traitement unique et batch) — le point dur : le pipeline dure 60 à 90 s et comporte des arrêts de validation humaine (relecture de transcription, tableau de validation). Demande un état persisté et un suivi de progression, là où Streamlit s'appuyait sur `session_state` et des threads.
- Retrait effectif de Streamlit et de ses dépendances.

**Vérifié :** 37 tests Django + 218 pytest = **255 tests passent**.

### 2026-07-30 (suite) — Vues de gestion et flux de correction migrés
**Vues de gestion terminées**
- Profil d'un élève : tendance, résumé chiffré, copies chronologiques, documents. **Une seule vue pour les trois rôles** au lieu des onglets Historique / Comparaison / Profil de Streamlit : sur un même élève ils affichaient la même chronologie (constat déjà fait en D-CEO-24), les fusionner supprime la duplication sans rien retirer.
- Documents servis directement par le navigateur : **plus de conversion PDF → PNG**, que Streamlit était obligé de faire faute de pouvoir embarquer un PDF. Le type réel est lu dans les premiers octets (un scan peut être une photo), pas déduit du champ `type`.
- **Jetons signés dans les URL** (`suivi_web/jetons.py`) plutôt que `identifiant_hakili` en clair. Motif : D-CEO-25 a explicitement retiré cet identifiant de l'interface, et une URL le ferait réapparaître dans la barre d'adresse, l'historique, les journaux et les en-têtes `Referer`. Bénéfice supplémentaire : un identifiant en clair s'énumère, un jeton forgé ne passe pas la signature.
- **L'autorisation est revérifiée sur l'URL du document**, pas seulement sur la page qui affiche le lien — sans quoi une URL partagée suffirait à récupérer la copie d'un élève d'un autre centre.

**Flux de correction migré (mode copie unique)**
- `correction_web/` : dépôt de copie, transcription en tâche de fond, relecture de la transcription, correction, tableau de validation, diagnostic, résultats.
- **L'état vit en base, pas en session** : le pipeline dure 60 à 90 s et comporte deux arrêts humains. Streamlit gardait cet état dans `session_state` (mémoire du processus) — intransposable, puisque plusieurs processus servent les requêtes en production et que rien ne garantit que la requête suivante tombe sur celui qui détient l'objet.
- **Sérialisation explicite en JSON, pas de pickle** (`correction_web/serialisation.py`) : un pickle casse au moindre changement de champ et désérialiser revient à exécuter du code venant de la base. La conversion s'appuie sur `model_dump()`, déjà utilisé par le pipeline pour son export `result.json`.
- **Un thread, pas de file de tâches** : Redis + RQ serait plus robuste mais ajoute un service à déployer, pour un besoin réel de quelques corrections simultanées. Limite assumée et traitée : `signaler_si_abandonnee` passe en échec une correction qui ne progresse plus depuis 15 minutes, au lieu de laisser une barre tourner indéfiniment après un redéploiement.
- `close_old_connections()` en fin de thread — sans quoi Django laisse une connexion ouverte par thread jusqu'à saturer le pool côté Neon.
- **Une seule URL par copie**, qui affiche l'écran correspondant à l'état : l'enseignant peut recharger, fermer l'onglet et revenir, il retombe au bon endroit.

**19 tests sur le flux**, centrés sur D-CEO-16 (« l'IA propose, l'enseignant décide ») : tout accepter garde les notes de l'IA, refuser impose celle de l'enseignant, note bornée au barème (une faute de frappe ne doit pas produire un 25/20), saisie illisible valant 0 sans bloquer la copie, **virgule acceptée comme séparateur décimal** (un enseignant francophone tape « 0,5 »), élève hors périmètre refusé **avant tout appel IA** (D-CEO-20), format de fichier refusé, correction abandonnée détectée.

**À connaître pour le déploiement :** le pipeline écrit ses fichiers intermédiaires dans `runs/`, sur disque local. Sur Railway ou Render sans volume persistant, ce dossier disparaît au redéploiement — les documents durables (scan, rapport, remédiation) sont déjà en base, donc rien d'irremplaçable n'est perdu, mais une correction en cours au moment du redéploiement devra être relancée. Prévoir un volume, ou l'accepter.

**Vérifié :** 72 tests Django + 218 pytest. Migration complète rejouée sur base neuve.

### 2026-07-30 (suite) — Mode lot migré, rendu mathématique récupéré
- **Mode lot** (`correction_web:lot`) : dépôt d'une classe entière, élève de chaque copie déduit du **nom de fichier** apparié aux Sheets. Sans correspondance unique, la copie est écartée et signalée — jamais attribuée au hasard (D-CEO-20). Un fichier invalide n'empêche pas le traitement des vingt-neuf autres.
- **Différence assumée avec Streamlit :** son mode lot produisait des rapports complets **sans qu'aucun enseignant ait vu une seule note**, ce qui contredisait D-CEO-16 (« la correction automatique sans validation est inacceptable pour un document officiel »). Ici, la Phase A tourne d'affilée — la relecture de transcription reste sautée, la relire trente fois coûterait plus cher que la correction — mais **le tableau de validation est conservé** : les copies arrivent dans la liste, à valider une par une. Déposer reste une seule action.
- **Rendu mathématique récupéré** (`src/services/affichage_math.py` + filtre de gabarit `|math`) : `_mh` / `_mt` étaient enfermés dans `app.py`. Sans eux, la table de validation aurait affiché « x^2 » et « <= » au lieu de x² et ≤ — ce n'est pas cosmétique, c'est ce que l'enseignant compare pour décider d'une note. `tests/test_ui_math.py` ne dépend plus de Streamlit.
- **Défaut trouvé dans mes propres tests :** l'assertion « aucune donnée sensible à l'écran » cherchait la sous-chaîne « H3 », qui apparaît par hasard dans les signatures base64 des jetons (`…VyO4H3b8…`) — test instable qui échouait au gré des signatures. Corrigé par des identifiants de test réalistes (`HAK-2026-0001`), et le motif est documenté dans le test pour que personne ne les raccourcisse.

**Vérifié :** 77 tests Django + 218 pytest = **295 tests passent**. Plus aucun test ne dépend de Streamlit.

### 2026-07-30 (suite) — Mode libre migré
Test personnalisé (sujet hors catalogue) désormais disponible dans l'interface Django : barème vide et sujet déposé transmis au pipeline, qui en extrait le barème — exactement le fonctionnement de l'ancienne interface. Le sujet est **obligatoire** dans ce mode : sans lui, aucun barème ne peut être établi et la correction n'aurait rien à quoi se comparer. `bareme_id` est laissé vide plutôt que « libre », sinon la résolution de classe et le RAG chercheraient un test de catalogue inexistant.

**Vérifié :** 81 tests Django + 218 pytest = **299 tests passent**.

### ⚠ Retrait de Streamlit — fait le 2026-08-05 (D-CEO-39), sans l'essai qui le conditionnait
> **Cette fiche décrivait l'état antérieur au retrait.** Elle est conservée parce que le
> point bloquant qu'elle nomme — l'essai réel de bout en bout — **n'a jamais été passé**.
> Il n'est plus bloquant, il est simplement toujours à faire.

Streamlit restait en service, délibérément.

**Il manque un essai réel de bout en bout.** Cet environnement n'a pas de clés API : tous les tests simulent le pipeline. Une correction complète sur une vraie copie — vraies API, vraie base Neon, vrai Sheet — doit être passée avant de retirer le filet.

Tout le reste est prêt :
- Toutes les fonctions métier enfermées dans `app.py` ont été extraites (`src/services/identite_service.py`, `src/services/affichage_math.py`).
- Plus aucun test ne dépend de Streamlit.
- Les quatre écrans sont couverts : correction d'une copie, correction d'une classe, suivi des élèves, statistiques — plus le mode libre.

**Marche à suivre une fois l'essai passé :** supprimer `src/ui/`, retirer `streamlit` de `requirements.txt` et le dossier `.streamlit/`, mettre à jour `README.md`, `CLAUDE.md` et le registre des décisions. → **Fait le 2026-08-05**, l'essai en moins ; `pandas` et `numpy` sont partis avec, et `hakili_logo.png` a été déplacé dans `static/`.

### 2026-07-30 (suite) — Mise en service préparée
**Constat en préparant le déploiement : l'application ne pouvait pas être déployée.** Aucun serveur web dans `requirements.txt`, aucun `Procfile` — `runserver` n'est pas un serveur de production. Comblé :
- `gunicorn` et `whitenoise` ajoutés ; WhiteNoise sert les fichiers statiques sans serveur web séparé, ni Railway ni Render n'en fournissant. Chaîne `collectstatic` vérifiée (381 fichiers post-traités).
- `Procfile` valable pour Railway comme pour Render, avec `release: migrate` avant chaque mise en ligne. `--threads 4` parce que les corrections tournent dans un thread du processus web ; `--timeout 180` pour le dépôt d'un lot sur connexion lente.
- Makefile mis à jour : `make run` lance désormais Django, `make run-streamlit` reste disponible le temps de la validation.

**`manage.py verifier_installation`** : contrôle avant mise en service — configuration Django, base et migrations, Sheets, clés d'API, référentiel importé, stockage inscriptible, XeLaTeX. Chaque manque est nommé **avec sa conséquence** (« aucune correction ne peut démarrer », « l'application refusera toutes les requêtes »). Avec `--copie`, la commande exécute une correction réelle de bout en bout : c'est le contrôle qui conditionne le retrait de Streamlit, rendu accessible en une commande.

**`docs/deploiement.md`** : variables d'environnement avec leur rôle et leur criticité, procédure, et deux points qui demandent un arbitrage.

**Deux limites de déploiement identifiées, à trancher :**
1. **`runs/` est du disque local et Railway/Render l'effacent à chaque redéploiement.** Les documents durables sont en base, donc rien d'irremplaçable n'est perdu — mais une correction en cours perd ses fichiers de travail (détectée comme abandonnée après 15 minutes). Soit un volume persistant, soit l'accepter et redéployer hors heures de correction.
2. **Une seule instance.** Le suivi de progression passe par la base, mais le thread de travail vit dans un processus donné : avec plusieurs instances, une correction lancée sur l'une paraîtrait figée aux autres. Tant qu'aucune file de tâches n'est en place, rester à une instance.

**`SECURE_HSTS_PRELOAD` laissé à False délibérément** — `check --deploy` le signale, ce n'est pas un oubli : le préchargement est une porte à sens unique (radiation en plusieurs mois) et n'a aucun sens sur un sous-domaine mutualisé où l'en-tête est hérité. À réexaminer avec un domaine propre.

**Vérifié :** `check --deploy` en conditions de production ne laisse que deux avertissements, tous deux expliqués. 81 tests Django + 218 pytest = **299 tests passent**.

### 2026-07-30 (fin de soirée) — Le cycle réel, et le moteur du plan de remédiation
Trois décisions de fond ont été prises après confrontation du protocole à la pratique du centre, puis le module 6 a été attaqué dans la foulée.

**Ce que le modèle métier avait de faux, corrigé (D-CEO-32, 33, 34)**
- **Périmètre unique (D-CEO-32).** Hakili Lab est un **centre d'encadrement, pas une école** : les enseignants tournent et reprennent les copies d'un collègue absent. Le cloisonnement par centre et par classe bloquait un travail légitime sans rien protéger — il est retiré, le sélecteur de casquette avec. La sécurité se joue en amont, à l'autorisation : présent dans le Sheet du personnel avec un code d'accès, on travaille ; retiré, on ne se connecte plus. Nouvel écran `/personnel/` en lecture seule pour *voir* cet état, les comptes en défaut affichés en premier.
- **T2 retiré, évaluations répétables (D-CEO-33).** Le cycle passe à cinq étapes : T0 → T1 → remédiation hors plateforme → T3 (fin du volume horaire) → T4 (45 j) → T5 (3 mois). `UniqueConstraint(session, type)` interdisait un second T3 alors que l'enseignant relance un test tant que les lacunes tiennent : remplacée par `(session, type, numero)`, le rang étant attribué à la création. Les indicateurs du module 9 comptent des **transitions**, pas « la » T1 — ils agrègent naturellement les passages multiples.
- **États de session et inscription (D-CEO-34).** Sept états au lieu de trois, dont trois sorties **sans** remédiation distinguées à dessein : `sans_suite` (T1 n'a rien confirmé — **c'est un bon résultat**, le confondre avec un abandon transformerait une réussite en échec dans les comptes rendus), `hors_dispositif` (palier C), `abandonnee`. `Session.inscrire()` bascule les problèmes confirmés en remédiation, date l'inscription, et refuse le palier C sans motif explicite conservé dans les transitions.

**Module 6 — le moteur tourne (`suivi/plan.py`)**
- **Tri topologique sur le graphe des prérequis**, restreint aux compétences réellement en difficulté : un problème dont un prérequis est lui-même en difficulté se traite après lui. À égalité, on commence par la compétence introduite le plus tôt. C'est ce qui distingue une remédiation d'un rattrapage — travailler les identités remarquables avec un élève qui ne sait pas additionner deux relatifs est du temps perdu, et le tuteur ne le découvrirait qu'en séance.
- **Un cycle dans le graphe ne fait pas boucler** : la base l'interdit, mais un import mal formé pourrait en créer un — on verse le reste par niveau plutôt que de tourner indéfiniment.
- **Seuls les problèmes `confirme` et `en_remediation` entrent au plan.** Une hypothèse non vérifiée n'a rien à y faire : c'est tout l'objet du test de confirmation. Les problèmes déjà en remédiation y restent, sinon le tuteur perdrait sa feuille de route juste après l'inscription.
- **Chaque étape porte de la matière pour la séance** : les signatures d'erreur du référentiel propres au type diagnostiqué (4 au plus), et la liste des prérequis eux-mêmes en difficulté.
- **`repose_sur_estimation` est remonté jusqu'à l'écran** quand le plan s'appuie sur un volume de repli (D-CEO-29). Ce chiffre détermine ce qu'une famille paiera : il ne doit pas passer pour un volume officiel.
- **Écran `/parcours/<jeton>/`** : plan ordonné, volume, palier, hypothèses restantes, bouton d'inscription. Inscription **en POST seulement** — elle engage un volume horaire et vraisemblablement une facturation, elle ne doit pas pouvoir arriver par un lien cliqué. Jeton signé comme partout ailleurs (D-CEO-25), autorisation revérifiée sur l'URL.

**Ce qui manque encore au module 6 :** la **planification en séances** — la table `Seance` existe et l'admin l'expose, mais rien ne la remplit. Et le moteur n'a tourné que sur des problèmes créés à la main : sans Module 4, il n'a pas encore vu un seul diagnostic réel.

**Vérifié :** 12 tests sur le plan (ordre indépendant de l'ordre de saisie, prérequis hors difficulté ignoré, cycle non bouclant, hypothèses exclues, volume estimé signalé) + 7 sur l'écran de parcours (inscription refusée en GET, palier C exigeant un motif, bouton disparaissant une fois inscrit, parcours hors périmètre en 404). **170 tests Django + 218 pytest = 388 tests passent.**

**Bloqué par :** rien techniquement. **Prochaine étape : Module 2** (lecture des copies par zones) — c'est le seul chemin vers le Module 4, dont tout le reste dépend.

> ⚠ **Un point de gestion, hors code, qui pèse plus que le prochain module :**
> **L'essai réel de bout en bout n'a toujours pas eu lieu** (pas de clés API dans cet environnement) — c'est lui qui conditionne le retrait de Streamlit, et il conditionne aussi la confiance qu'on peut accorder à tout ce qui précède.

### 2026-07-31 (suite) — ✅ Le corpus de référence est complet
**5 copies, 66 problèmes, 70 h de remédiation cumulées.** Le jalon du module 3 est atteint : le module 4 a désormais un étalon contre lequel se mesurer.

**Cinq profils réellement distincts** — c'est ce qui décide de la valeur du corpus :

| copie | problèmes | coût | ce que le module 4 devra reconnaître |
|---|---|---|---|
| 3ème #1 | 22 | 34,5 h | effondrement conceptuel — 13 CPT, palier C |
| 3ème #2 | 10 | 8,5 h | gestes ratés sur un socle solide — PRC et ATT |
| 5ème #3 | 14 | 12,5 h | connaissances absentes et une page sautée |
| 5ème #4 | 9 | 7,0 h | exécution qui dérape, modèles justes |
| 6ème #5 | 11 | 7,5 h | 8 CNS sur 11 — vocabulaire et formules manquants |

Répartition finale : `CNS` 36 % · `CPT` 35 % · `PRC` 18 % · `ATT` 6 % · `MOD` 5 %.

**Le cas le plus instructif du corpus** reste le périmètre d'une table circulaire, posé à l'identique aux copies 3, 4 et 5 : `1,3 × 2` (formule absente, `CNS`), `1,3 × 3,14 = 1,2856` (formule juste, produit faux, `PRC`), et rien du tout (`CNS`). Une question, trois copies, deux types d'erreur, trois remédiations différentes. Aucune heuristique de notation ne distingue ça ; c'est exactement ce qu'on demandera au module 4.

**Une erreur de tagage rattrapée par le corpus lui-même.** « Complète : 290 + … = 3028 » avait été rattachée à `N.ADD` sur la copie 3 et à `N.EGT` sur la copie 5 — **deux codes valides, donc invisibles à toute validation**. Repéré en taguant la cinquième, harmonisé sur `N.EGT` et la copie 3 re-taguée. Sans cette reprise, le module 4 aurait été mesuré contre deux réponses différentes à la même question. C'est la démonstration concrète de ce que la validation automatique ne peut pas faire — et la raison pour laquelle le compte rendu rappelle désormais les libellés en toutes lettres.

**Ce que le corpus ne pourra pas mesurer, et pourquoi ce n'est pas un défaut de tagage :**
- **`RED`** — le référentiel le réserve à la partie B « où la consigne précise que la démarche est évaluée autant que le résultat ». Les tests de l'ancien format ne posent jamais cette consigne. Il faudra des copies du **nouveau format**.
- **`PRQ`** — il demande un prérequis partagé *nommable*. Sur cinq copies, les échecs ne convergent vers aucun ancêtre commun du graphe. Le graphe des prérequis est trop maigre : c'est un défaut du référentiel, à remonter au relecteur.

**16 hésitations** sur les 5 copies, rassemblées par `manage.py corpus --hesitations`. Trois questions de fond en ressortent : l'absence d'arêtes autour de `G.VOC`, la frontière `ATT`/`PRC` qui change la facture, et le fait que **ces tests d'entrée évaluent systématiquement des compétences du niveau où l'élève entre** — signalé trois fois par le contrôle de niveau.

**Un avertissement pour la suite :** le correcteur a accordé des points à une réponse fausse (`1093 ÷ 15 = 72,08`). **Les annotations rouges ne sont pas une vérité de référence.** Mesurer le module 4 contre elles reviendrait à mesurer son accord avec un correcteur, pas la justesse de son diagnostic.

**Vérifié :** 5 copies en base, coûts en accord avec le référentiel, aucune session de corpus mêlée au suivi réel.

### 2026-07-31 (suite) — Copie 4, et les correctifs éprouvés en conditions réelles
Le tagage de la copie 4 a servi de test aux six correctifs. **Les trois mécanismes nouveaux ont réagi comme voulu, sans être sollicités exprès :** les libellés rappelés (`M.PER × PRC` suivi de `└ Perimetres × Erreur procedurale`), l'avertissement de niveau (`N.FRA2` est de 5ème, le test est de niveau 5ème), et le signalement d'une compétence taguée deux fois (`M.PER`, MOD et PRC).

**Le contraste le plus utile du corpus à ce jour.** Copies 3 et 4, même sujet, **même question** — le périmètre d'une table circulaire de 1,3 m de diamètre :
- copie 3 : `1,3 × 2 = 2,6 m` → la formule n'est pas mobilisée du tout → **`M.PER × CNS`** ;
- copie 4 : `1,3 × 3,14 = 1,2856 m` → la formule est juste, π est employé, seul le produit est faux → **`M.PER × PRC`**.

Même compétence, même énoncé, deux types d'erreur — et deux remédiations qui n'ont rien à voir. C'est exactement la distinction sur laquelle le module 4 sera jugé, et le corpus la porte maintenant en pièce à conviction.

**Trois constats qui dépassent cette copie :**
1. **Les annotations rouges ne sont pas une vérité de référence.** Le correcteur a accordé 0,2 point à `1093 ÷ 15 = 72,08`, alors que le quotient est 72,86. Le corpus doit donc être établi sur la **production de l'élève**, jamais sur la note portée sur la copie. Et si un jour on mesurait le module 4 contre ces notes, on mesurerait son accord avec un correcteur, pas la justesse du diagnostic.
2. **`RED` est hors d'atteinte de ce corpus, et ce n'est pas un oubli.** Le référentiel réserve `RED` à la partie B, « où la consigne précise que la démarche est évaluée autant que le résultat ». Les tests de l'ancien format ne posent jamais cette consigne — ils demandent des résultats. Mesurer le module 4 sur `RED` exigera des copies du **nouveau format**. Taguer `RED` ici reviendrait à inventer la donnée manquante.
3. **`PRQ` bute deux fois au même endroit.** Copies 1 et 4 : les échecs ne convergent vers aucun ancêtre commun du graphe des prérequis. L'obstacle n'est pas la lecture des copies mais la **maigreur des arêtes du graphe**. Deux copies sur quatre, ce n'est plus une coïncidence — c'est un défaut du référentiel à remonter.

### 2026-07-31 (suite) — L'outil de tagage durci par l'usage
Trois copies taguées ont montré où l'outil laissait passer. Six correctifs, dans l'ordre du risque.

**1. La validation attrapait les codes inventés, pas les codes faux.** C'est le trou principal, et il s'est refermé sur moi : le tagage de la copie 1 a conclu qu'aucune compétence ne couvrait le vocabulaire géométrique, alors que `G.VOC` existe — 17 compétences de niveau primaire avaient échappé à ma lecture. Un code inventé est rejeté ; un code **valide mais mal choisi** passait sans un mot et salissait l'étalon de façon invisible. Trois parades : `--chercher <mot>` et `--chercher --niveau <niveau>` mettent le référentiel sous la main pendant le tagage ; un code rejeté fait proposer les codes proches ; le compte rendu **rappelle le libellé en toutes lettres** de chaque code retenu — relu, un mauvais choix a une chance de sauter aux yeux.

**2. Un problème de corpus pouvait contaminer le suivi réel d'un élève.** `cout_total_confirme` et `inscrire()` filtrent par **session**, pas par évaluation. Taguer une copie d'archive sous l'identifiant d'un élève réellement suivi aurait fait entrer ces problèmes dans son palier — donc dans ce que sa famille paierait. Trois verrous : la session de tagage est marquée `corpus_reference`, elle refuse `etablir_le_plan()` et `inscrire()`, et le tagage **refuse** une session de suivi réel en le disant clairement. Une reprise de données marque les sessions taguées avant l'existence du drapeau — sans elle, les trois premières copies seraient devenues des sessions « réelles ».

**3. Aucun contrôle de cohérence de niveau.** `N.FRA2` (5ème) avait été tagué sur une copie d'entrée **en** 5ème : la compétence n'est pas encore enseignée, l'échec y est normal. Un avertissement le signale désormais — sans refuser, parce que c'est un jugement.

**4. Le coût était figé au tagage.** Les 27 volumes de lycée sont des valeurs de repli (D-CEO-29) ; le jour où les vrais arriveront, les coûts du corpus resteraient faux en silence. `manage.py corpus` détecte l'écart, `--recalculer` le corrige.

**5. On ne pouvait pas relire le corpus.** `manage.py corpus` donne la composition, la répartition des sept types, et les compétences taguées plusieurs fois sur une même copie. **Premier résultat utile, immédiatement :** le corpus ne contient **aucun `PRQ` ni `RED`** — le module 4 ne pourrait pas être mesuré sur ces deux types. C'est une consigne concrète pour les deux dernières copies.

**6. Les hésitations étaient éparpillées.** `manage.py corpus --hesitations` les rassemble depuis les fichiers — 11 sur 3 copies. Elles restent en YAML à dessein : une hésitation est un jugement en attente d'arbitrage, la mettre en base lui donnerait un statut qu'elle n'a pas.

**Vérifié :** 34 tests sur le corpus, cycle de migration testé dans les deux sens, `makemigrations --check` stable. **204 Django + 242 pytest = 446 tests passent.** L'outil est ensuite repassé sur le corpus réel : les 3 copies ressortent intactes.

### 2026-07-31 (suite) — Deux premières copies taguées, et un contraste qui valide la démarche
Les 5 copies sont réunies (2 en 3ème, 2 en 5ème, 1 en 6ème). Les **deux copies de 3ème** — même sujet, même correcteur — sont taguées.

| | copie 1 | copie 2 |
|---|---|---|
| Note | 0,25/20 | forte |
| Problèmes | **22** | **10** |
| Coût | **34,5 h → palier C** | **8,5 h → palier B** |
| Types dominants | CPT (13/22) | PRC (4), ATT (3), CNS (2) |

**C'est ce contraste qui fait le corpus.** Une copie s'effondre — presque tout est conceptuel, la remédiation courte est hors de portée et le dispositif doit le dire. L'autre réussit l'essentiel et n'échoue que sur des gestes : signes dans les fractions, exposant perdu à la recopie, hachure du mauvais côté d'une inéquation pourtant bien résolue. **Le module 4 sera jugé sur sa capacité à distinguer les deux**, pas à détecter l'effondrement — que n'importe quelle heuristique repère.

Deux mécanismes déjà éprouvés en conditions réelles au passage : les trois `ATT` de la copie 2 sont **comptés 0 h**, et le palier bascule de B à C entre les deux copies sans intervention.

**Ce que le tagage a appris sur le référentiel — 8 hésitations relevées, dont trois qui comptent :**
1. **Aucune compétence ne couvre le vocabulaire géométrique de base.** La copie 1 répond « parallèle » ou « perpendiculaire » à quatre questions attendant un point ou une mesure — échec corrélé sur `G.SYMC`, `G.SYMO`, `G.ANG3`, `G.TRIP`, c'est-à-dire la signature exacte de **PRQ**. Mais PRQ exige de *nommer* le prérequis, et il n'existe pas. Faute de mieux, quatre `CPT` séparés ont été posés — ce qui **gonfle mécaniquement le coût** d'un élève dont le problème est unique. Le référentiel a-t-il besoin d'une compétence transversale de vocabulaire géométrique ?
2. **La frontière ATT / PRC n'est pas nette**, et elle n'est pas neutre : `ATT` vaut 0 h, `PRC` vaut au moins 0,5 h. Un `x³` recopié `x` est-il une inattention ou une exécution ratée ? Le classement change la facture.
3. **Trois `ATT` sur une même copie** interrogent le protocole : chacune se justifie isolément, mais les écarter toutes à T1 ferait peut-être disparaître un profil réel — élève rapide et négligent — que le référentiel ne sait pas nommer.

**Décision prise sur les données personnelles :** les copies portent nom complet, établissement et téléphone d'élèves mineurs. Le corpus emploie des identifiants **non nominatifs** (`CORPUS-3E-01`…) : c'est un instrument de mesure, il n'a aucun besoin de nommer un enfant. À confirmer si ces élèves doivent aussi être suivis pour de vrai.

**Reste :** les 3 dernières copies (2 en 5ème, 1 en 6ème, 14 pages chacune).

### 2026-07-31 (suite) — Module 3 : l'étalon a maintenant où se poser
Le module 1 avait laissé le marqueur du corpus « à définir ». Il est défini, et deux manques sont apparus en le posant.

**Ce qui a été ajouté au socle**
- `Evaluation.corpus_reference`, `tague_par`, `date_tagage`, avec une **contrainte en base** : pas de marquage sans auteur ni date. Un corpus anonyme n'est pas discutable — deux personnes ne taguent pas tout à fait pareil, et c'est une information, pas un défaut.
- **`Probleme.evaluation_origine` et `Probleme.justification`.** Le premier relie un problème à la passation qui l'a révélé — sans lui, refaire un tagage aurait obligé à supprimer *tous* les problèmes de la session, y compris le suivi réel de l'élève. Le second porte ce qu'on a lu sur la copie : c'est ce qui rendra un désaccord entre le corpus et le module 4 **arbitrable**, au lieu d'un écart de comptage muet. Le module 4 en a besoin autant que le module 3 — c'est la « citation » que le guide lui demande de produire.

**Arbitrage rendu : un fichier, pas un écran.** Le tagage est lent et discutable — on relit, on hésite, on corrige. Un fichier se relit, se compare, se reprend le lendemain ; un formulaire perd tout à la première fermeture d'onglet. `manage.py taguer_corpus --fichier … [--a-blanc] [--remplacer]`.

**La validation est complète avant toute écriture**, et c'est le point qui compte : un corpus à moitié écrit serait pire que pas de corpus du tout — il aurait l'air complet. Sont refusés : un code de compétence ou de type d'erreur absent du référentiel, une justification vide, un `ATT` confirmé, un couple en double, un état autre qu'hypothèse ou confirmation.

**Un bug de fond corrigé au passage.** `Session.Meta` construisait une contrainte à partir d'un `frozenset` : l'ordre d'itération changeant d'une exécution à l'autre, `makemigrations` croyait la contrainte modifiée **à chaque appel** et produisait une migration parasite — c'est l'origine des migrations 0003 et 0004, qui ne font rien d'autre. `sorted()` au lieu de `list()` : un second `makemigrations` ne détecte plus rien.

**Deux limites à connaître, consignées dans la fiche du module :**
1. Le module 4 **ne devra jamais écrire** dans les problèmes d'une évaluation du corpus. Un étalon qu'on corrige au fur et à mesure ne mesure plus rien.
2. Pour une copie de l'**ancien format**, aucune `Reponse` n'est enregistrable — ce modèle exige une clé étrangère vers les 280 questions v2, qu'une ancienne copie n'a pas. Seuls les `Probleme` le sont, et c'est suffisant : c'est l'unité que le module 4 produit.

**Vérifié :** 16 tests dédiés, cycle de migration testé dans les deux sens. **186 Django + 242 pytest = 428 tests passent.**

**Reste :** réunir les copies (**1 sur 5**) et faire le tagage lui-même.

### 2026-07-31 (suite) — Format des sujets confirmé, lecture rendue tolérante (D-CEO-35)
**Question posée, réponse obtenue :** les sujets v2 **conservent leurs cadres ancrés et leurs codes de question**. `TEST 4 3e.pdf` était une copie d'archive de l'ancien format, pas une préfiguration des sujets à venir. La conception du module 2 tient donc telle quelle — il ne lui manque que le recalage.

**Conséquence à ne pas perdre :** le format à cadres ancrés n'est plus une commodité de mise en page, c'est **une dépendance du diagnostic structuré**. Un sujet sans cadres ni codes ne peut pas être découpé en zones, donc ne peut pas alimenter le module 4. Toute régénération des sujets doit les conserver — c'est acté en D-CEO-35.

**Adaptation faite dans la foulée.** Les règles de lecture étaient collées aux valeurs relevées sur les 7 PDF d'aujourd'hui : gris exactement 0,478431, largeur supérieure à 480 pt, exactement 8 lignes pour une rédaction. Le sujet est un document vivant : régénéré, il changera de marges et de teintes. Les règles sont désormais exprimées en **plages de gris** et en **fractions de la largeur de page**, et toute question de plus de 2 lignes est une rédaction. Ce qui était en jeu : avec des valeurs exactes, une simple retouche du gabarit d'impression aurait fait échouer la lecture **totalement** — zéro cadre trouvé, module 2 arrêté net — et non partiellement.

**Vérifié :** les 280 cadres des 7 sujets sont toujours retrouvés avec les règles tolérantes, et 2 tests verrouillent la tolérance (une teinte différente, une rédaction à 6 lignes). 24 tests sur les zones, **170 Django + 242 pytest = 412 tests passent**.

### 2026-07-31 (suite) — Un scan réel, et ce qu'il a corrigé dans la conception
**Contrainte posée :** le scan se fait **hors plateforme**. Ce qui entre est un **PDF multipage ou des images** — jamais un flux scanner piloté par l'application. Pris en compte : `resolution_scan()` donne la définition native de la source, et `ingest_pdf` accepte désormais un `dpi` (150 reste le défaut, D-CEO-10) pour ne pas rendre un scan 200 DPI dans une image 150 DPI, puis recadrer au dixième de page ce qui a déjà été dégradé.

**Le fichier reçu (`TEST 4 3e.pdf`) est un test de l'ancien format**, pas un sujet socle : pas de cadres ancrés, pas de codes de question, dotté de pointillés et déjà corrigé au stylo rouge. Il ne peut pas servir de pièce d'essai au module 2 — il n'y a aucun gabarit sur lequel le recaler. Il reste précieux pour deux autres choses : il **calibre le côté scan** (tableau dans la fiche du module 2), et c'est exactement le matériau que demande le **module 3** (« rassembler ≥5 anciennes copies »).

**Ce que les mesures ont changé :**
- **Le recalage ne peut pas s'appuyer sur le rectangle de la page.** La hauteur varie de **835 à 851 pt d'une feuille à l'autre du même fichier**, et la largeur est de 612 pt là où le sujet en fait 595,3. Une mise à l'échelle sur les bords de page serait fausse de 2 à 3 %. L'ancrage doit se faire sur le **contenu** — les cadres eux-mêmes.
- **L'inclinaison varie d'une page à l'autre** (−1,25°, −1,25°, +1,00°) : redressement par page, jamais global.
- **La correction de l'enseignant est séparable par la couleur** (2,3 % de pixels rouges contre 22 % de bleu élève et 75 % d'imprimé neutre). Sur une ancienne copie corrigée à la main, un diagnostic qui ignore la couleur lit la correction du professeur comme la production de l'élève. À traiter au module 3.
- **Le scan compte 12 pages pour un sujet de 10** (page de garde, page de renseignements) : l'appariement page scannée ↔ page du sujet ne peut pas être supposé 1:1.

**Ajouté en conséquence :** `decouper_zones` **refuse** une page dont les proportions ne sont pas celles du sujet. Sans ce garde-fou, un scan brut se découpait sans rien signaler, avec un décalage de plusieurs millimètres en bas de page — assez pour attraper la ligne de la question voisine, pas assez pour que le résultat ait l'air faux.

**Données personnelles :** ce scan porte le nom complet d'une élève, son établissement et un numéro de téléphone. Il n'est **pas** versionné et n'a pas été copié dans le dépôt. C'est le point ouvert #4 sous sa forme concrète, plus une question de principe.

**Essai de bout en bout sur le scan reçu**, pour voir ce qui tient sur du vrai matériel :
1. `resolution_scan` → **200 DPI**, et le rendu se fait à 200 au lieu de 150. ✅
2. `ingest_pdf` → **12 pages** extraites (1700×2348, 1700×2356… — les hauteurs diffèrent d'une page à l'autre, comme mesuré). ✅
3. `decouper_zones` contre le gabarit du sujet 3ème → **refusé**, avec le motif exact : « 2,3 % d'écart entre les échelles horizontale et verticale ». Le garde-fou fonctionne sur du matériel réel, c'était son objet. ✅
4. Nettoyage appliqué à de vrais pixels scannés → **l'écriture de l'élève ressort intacte**, mais **les lignes pointillées imprimées survivent** (8,8 % de pixels conservés). ⚠️

**Le point 4 est le résultat qui compte, et c'est une mauvaise nouvelle utile.** Ces pointillés sont imprimés en noir : le seuillage ne pouvait pas les enlever, et il ne le prétendait pas. Mais il ouvre une question que le rendu numérique du PDF ne pouvait pas poser — **une imprimante laser rend un aplat gris 0,749 par un tramage de points noirs**, pas par un gris uniforme. Si c'est le cas, les lignes de guidage des sujets socle se comporteront une fois imprimées comme ces pointillés, et `decouper_zones` les laissera passer alors que tous ses tests passent sur le PDF d'origine. **Le seuillage seul ne suffira peut-être pas** ; le repli est l'effacement par **position connue**, puisque le gabarit porte déjà la position exacte de chaque ligne.

**Vérifié :** 22 tests sur les zones, **170 Django + 240 pytest = 410 tests passent**.

**Prochaine étape :** le recalage, dès qu'un sujet socle imprimé aura été scanné. **Le même scan tranche le risque du point 4** — même vierge, il suffit à mesurer le gris des lignes imprimées. En attendant, le **Module 3** est le seul chantier qui n'attend rien, et le fichier reçu en est la première pièce.

### 2026-07-31 (suite) — Module 2 : le gabarit ne se devine pas, il se lit
**La question qui a décidé du module :** faut-il détecter les cadres sur le scan, comme le prescrit `guide-v2.md` ? **Non.** Les 7 sujets sont produits par WeasyPrint et leur PDF porte la position exacte de chaque cadre et son code. Vérifié avant d'écrire la moindre ligne : **280/280 cadres retrouvés sur les 7 sujets**, 0 manquant, 0 en trop, 0 doublon, et le nombre de lignes de guidage concorde avec le format annoncé par le barème sur les 280 (qcm 71 × 1 ligne, court 139 × 2, redige 63 × 8, construction 7 × 0).

Conséquence : **l'OCR disparaît de la chaîne.** C'était le premier point de panne — trois caractères à 150 DPI, à côté de l'écriture d'un élève —, et une confusion `G1`/`G7` aurait attribué une réponse à la mauvaise question sans que rien ne le signale. Le seul problème qui reste sur le scan est le recalage.

**La signature graphique des sujets, relevée sur pièces** (c'est elle qui rend le gabarit lisible) : les cadres sont des aplats gris, pas des traits. Bord **0,478** pour les cadres à lignes, **0,600** pour les cadres vides de `construction`, lignes de guidage **0,749**. Le code de la question est imprimé **deux fois** — en marge à côté de l'énoncé, et à l'intérieur du cadre en haut à gauche : c'est l'inclusion dans le rectangle qui les départage, rien d'autre.

**Deux choses trouvées en écrivant les tests, qui auraient coûté cher plus tard :**
1. **Le code imprimé dans le cadre est noir**, donc indiscernable de l'écriture au seuillage. Laissé en place, il met de l'encre dans toute zone découpée et **aucune copie vierge n'aurait jamais été reconnue comme telle**. Il est maintenant effacé à partir de sa position exacte, elle aussi lue dans le PDF.
2. **`numpy` n'était pas déclaré** dans `requirements.txt` — il n'arrivait que par `pandas`, qui part avec Streamlit. Le retrait du filet aurait cassé la découpe. Déclaré explicitement.

**Livré :** `src/pipeline/zones.py` — `extraire_gabarit`, `verifier_gabarit`, `decouper_zones`. Indépendant du framework. La découpe blanchit le fond plutôt que de binariser franchement (un trait de crayon clair reste lisible pour un modèle de vision), et signale les zones vierges : « pas de réponse » est une donnée de diagnostic à part entière, et ça évite d'envoyer une image blanche au modèle.

**`verifier_gabarit` est un garde-fou d'exploitation, pas une aide au développement :** le format est déduit de la géométrie du cadre, jamais lu dans le barème, puis les deux sont confrontés. Si un enseignant scanne un sujet d'une autre version que celle chargée en base, les codes ou les formats divergent — et on l'apprend avant d'attribuer des réponses aux mauvaises questions.

**Vérifié :** `tests/test_zones.py`, 20 tests. 13 tournent sur un sujet fabriqué dans le test lui-même, qui reproduit la signature graphique des vrais — les 7 sujets sont des PDF non versionnés, la CI ne les a pas. Les 7 autres vérifient les 280 cadres réels contre les barèmes, et sont **ignorés** faute de fichiers plutôt que de tomber en échec. **170 tests Django + 238 pytest = 408 tests passent.**

**Bloqué par :** une copie **imprimée, remplie à la main, scannée**. Le recalage et le seuil d'encre ne peuvent pas être calibrés sur un rendu numérique parfait — il n'y a rien à y redresser, et le contraste y est idéal. Consignes d'impression rappelées sur `/sujets/` : noir et blanc, recto seul, **sans réduction**.

**Prochaine étape :** avec un scan, le recalage puis la calibration du seuil. Sans scan, le **Module 3** (corpus de référence) peut avancer en parallèle — il ne dépend que du module 1 et se fait à la main.

### 2026-07-31 — Le travail est versionné
Le socle Django n'était pas suivi par git : rien n'avait été commité depuis le **2026-07-23**, une semaine de travail ne tenait que sur un disque. Corrigé — **10 commits découpés par domaine** sur la branche `chantier/urie-v2-django` (nom hérité, à renommer séparément), poussée sur `origin`.

Découpage : nettoyage des documents périmés · socle Django + authentification · `referentiel/` (module 1) · `suivi/` (modules 1 et 6) · `suivi_web/` · `correction_web/` · extraction de la logique métier hors de l'interface · scripts et barèmes · mise en service · documentation.

**Branche plutôt que `main`** : `main` est partagée avec le collègue (l'historique porte plusieurs fusions) et cette semaine de travail n'a pas été relue. Le rattrapage sera un fast-forward.

**Vérifié avant de commiter :** aucun secret n'entre dans le dépôt (`.env`, `credentials/`, `*.json`, `logs/`, `runs/`, `dev.db` couverts par `.gitignore` — les 138 fichiers ajoutés ont été scannés) ; les 22 suppressions étaient bien intentionnelles (doc périmée et sources remplacées). **170 tests Django + 218 pytest = 388 tests passent** sur l'arbre commité.

**Reste inchangé :** l'essai réel de bout en bout, toujours en attente de clés API. **Prochaine étape technique : Module 2.**

### 2026-08-01 — ✅ Module 2 terminé : le recalage marchait sur le papier, pas sur les pixels

Le recalage était écrit mais n'avait jamais tourné. Mis à l'épreuve, il s'est révélé **décoratif** : il rendait `angle = 0` sur une page penchée de 1,25°, et les zones d'une copie vierge ressortaient couvertes d'encre.

**La cause vaut d'être retenue, elle se reproduira ailleurs.** L'estimation d'inclinaison faisait tourner l'image à chaque angle candidat pour comparer la concentration de l'encre. Or **une rotation ré-échantillonne** : un trait d'un pixel s'étale sur deux, dont aucun n'atteint le seuil, et le trait disparaît. Mesuré : **2 616 pixels d'encre à 0°, moins de 600 à tout autre angle**. L'angle 0, seul à ne rien ré-échantillonner, gardait toute son encre et gagnait donc *quelles que soient* les données. Le critère ne mesurait pas l'inclinaison, il mesurait la quantité d'encre survivante. Corrigé en estimant sur les **coordonnées** des pixels d'encre — les mêmes pixels d'un angle à l'autre, donc des scores enfin comparables — et en confiant le cisaillement à la transformation affine du découpage : **une seule interpolation, sur la zone seule**, au lieu de faire tourner la page entière.

**Deux autres défauts trouvés en mesurant, pas en relisant :**
1. **La grille de recherche excluait la bonne échelle.** Elle était centrée sur `largeur de l'image / largeur de la page` à ±5 %. Mais le scanner ne rend pas la page du gabarit : ce qu'il ajoute autour fausse le rapport sans toucher au contenu. L'échelle vraie tombait **hors** de la grille, et l'ajustement se rabattait sur la moins mauvaise — faux, mais confiant. Élargi à 12 %, ce qui couvre le cas le plus coûteux à diagnostiquer : une copie numérisée en Letter au lieu d'A4.
2. **L'axe horizontal n'a que deux repères.** Tous les cadres partagent les mêmes bords gauche et droit : deux points pour deux inconnues, et le moindre trait en marge emportait l'ajustement — c'est ce qui arrivait, il se calait sur le code imprimé en marge. Or un scanner échantillonne à la même définition dans les deux sens : l'échelle horizontale est cherchée **autour de la verticale**, qui dispose d'une quinzaine de repères. L'indétermination est levée au lieu d'être subie.

**Appariement des pages (ce que le scan réel avait annoncé et que personne n'avait traité).** 12 pages scannées pour un sujet de 10 — page de garde, page de renseignements. `decouper_zones` supposait un appariement 1:1 : **toutes les zones auraient été prises sur la mauvaise page, et le résultat aurait eu l'air normal**, chaque zone contenant bien de l'écriture. Chaque page du scan est désormais confrontée à chaque page du sujet, et l'affectation retenue maximise le total des scores **en gardant l'ordre** — une copie se numérise dans l'ordre, et l'exiger empêche deux pages qui se ressemblent de s'échanger. Coût mesuré sur un cas réaliste (12 × 10) : **4,6 s**, dans un pipeline qui en dure 60 à 90.

**Le risque du tramage a changé de nature — et le repli prévu était impossible.** La fiche disait : si les lignes survivent au seuillage, on les effacera à leur position connue. Mesuré sur les 7 sujets : les « lignes de guidage » **ne sont pas des traits** mais des bandes de 21 pt **jointives** (853 relevées) qui pavent toute la zone de réponse. L'élève écrit sur un **aplat gris**. Leur position, c'est la zone entière — l'effacement l'effacerait entière, ce qu'a montré le test écrit pour l'occasion avant que le mécanisme ne soit retiré. Le vrai problème est le retrait d'une **trame**, un filtrage qui distingue un point isolé d'un trait de stylo, et il dépend de trois grandeurs qu'aucun rendu numérique ne donne. **Rien n'a été livré à sa place** : mieux vaut un risque ouvert et correctement décrit qu'un mécanisme dont la prémisse vient d'être réfutée. Verrouillé par un test paramétré sur les 7 sujets, pour que la fausse piste ne soit pas re-suivie.

**Branché sur le pipeline.** `_lire_zones` s'intercale entre l'ingestion et la transcription, déclenché par la seule présence d'un `sujet_pdf` — pas par une liste de tests à tenir à jour. La transcription continue de lire la page entière (D-CEO-27 : l'élève compose *sur le sujet*). **Aucun échec de cette étape n'arrête la correction** : le module 4 n'existe pas encore, personne ne consomme les zones, et casser une copie pour un service qui n'est pas rendu n'aurait servi à rien. Les anomalies remontent en avertissement à l'enseignant — c'est là qu'un sujet d'une autre version que celle chargée en base se voit.

**`scipy` est installé mais absent de `requirements.txt`.** Il n'arrive que par transitivité. Rien ne s'appuie dessus — le projet s'est déjà fait piéger par `numpy`, qui n'arrivait que par `pandas`, lequel part avec Streamlit.

**Vérifié :** 43 tests sur les zones (24 avant), dont le recalage sur cinq déformations de numérisation, l'appariement avec deux pages intercalées, et la géométrie réelle des 7 sujets. **207 tests Django + 261 pytest = 468 tests passent.**

**Bloqué par :** rien. **Le Module 4 est ouvert — c'est la prochaine étape, et tout le reste en dépend.** Le tramage reste à trancher, mais il ne bloque pas le module 4 : il se mesurera d'abord sur le corpus de référence, qui est constitué de copies de l'ancien format.
