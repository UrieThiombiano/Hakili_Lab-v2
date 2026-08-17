# Harmonisation des données — ancien système ↔ référentiel v2
**Document d'analyse et de décision · 2026-07-30, mis à jour le 2026-08-13**
**Statut : investigation terminée. Arbitrages A, D, B et H rendus et appliqués (H clos le 2026-08-13) ; C, E, F toujours en attente.**

> **Décisions prises (2026-07-30)**
> - **A → A1, archiver.** Les 6 anciens tests sont marqués `archive: True` dans `src/knowledge/test_registry.py`. Appliqué et vérifié.
> - **D → barème sur 20 en base.** L'échelle du sujet fait foi ; le classeur (sur 60) est converti à la génération. Voir §4.
> - **Source des données des 7 nouveaux tests → le classeur, pas les PDF** (les énoncés ne sont pas extractibles, voir §3bis). `scripts/generer_baremes_socle.py` produit les 7 `data/knowledge/bareme_socle_*.yaml`. **Les 7 tests sont opérationnels et sélectionnables.**
> - **Corrigés manquants → champs vides pour l'instant.** `reponse_attendue` / `solution` émis vides sur les 209 questions non-QCM, prêts à être remplis sans changement de schéma. Les 71 QCM sont pleinement corrigeables.

> **Décision prise (2026-08-12)**
> - **B → corrigés produits, relus et validés par un enseignant de mathématiques.** Livraison `data/New-docs/` : 7 sujets PDF recomposés + 7 corrigés enseignant PDF complets (structure Automatismes/Savoir-faire/Raisonnement). Intégrés au dépôt : sujets dans `data/Documents/` (anciens déplacés vers `data/Documents/archive/`), corrigés dans `data/Documents/corriges/`, servis par `correction_web` (`sujets/<bareme_id>/corrige/`). **Mais** cette recomposition n'était reflétée ni dans `Referentiel_Socle_v0.xlsx` ni dans `bareme_socle_*.yaml` — voir **Arbitrage H**, ci-dessous.

> **Décision close (2026-08-13)**
> - **H → les 7 `bareme_socle_*.yaml` (6eme à tleD) reconstruits à la main**, directement depuis les sujets et corrigés PDF recomposés, sans attendre la mise à jour de `Referentiel_Socle_v0.xlsx` (décision utilisateur du 2026-08-12 : « le classeur n'est pas la priorité, la plateforme si »). Ces 7 fichiers font foi en avance sur le classeur. Détail §7.

---

## Pourquoi ce document

Le chantier v2 suppose que les données de test soient exprimées dans le vocabulaire du référentiel (compétences canoniques, types d'erreur, codes de question). Or le code existant dans `Hakili_Lab/` porte un **deuxième système de données complet**, construit avant le référentiel, avec sa propre numérotation, son propre vocabulaire de compétences et son propre mécanisme d'ancrage pédagogique.

Les deux systèmes décrivent le même métier mais ne partagent **aucun identifiant**. Tant que ce point n'est pas tranché, le module 1 (socle de données) ne peut pas être écrit sans figer un choix implicite, et le module 4 (diagnostic contraint) ne peut pas remplacer l'ancien diagnostic.

C'est la phase critique du projet : **c'est ici que se décide ce qui survit de l'existant.**

---

## 1. Résultat central de l'investigation

> **Les 7 nouveaux sujets PDF et le classeur `Referentiel_Socle_v0.xlsx` sont parfaitement alignés. L'ancien système ne l'est avec rien.**

Vérifié par script, extraction des codes de cadre des 7 PDF confrontée à l'onglet `04_Questions` :

| Test | Codes dans le PDF | Codes dans le classeur | Écart |
|---|---|---|---|
| 6eme, 5eme, 4eme, 3eme, 2ndeC, 1ereD, tleD | 40 chacun | 40 chacun | **0 partout** |

280 questions, 280 correspondances exactes, aucun code manquant ni en trop. Contrôle complémentaire sur le contenu : les intitulés de `04_Questions` pour le test de 6ème correspondent mot pour mot aux questions imprimées dans `Test_diagnostique_entree_6eme.pdf` (N1 « soixante mille quatre-vingt-douze », N3 « 3 608 + 947 », N5 « 326 × 48 »…).

**Conséquence :** le couple *(nouveaux PDF + classeur)* forme un système cohérent, complet et directement exploitable. Le travail d'harmonisation ne consiste donc **pas** à réconcilier deux systèmes vivants, mais à décider **quoi faire de l'ancien**, qui n'a plus de sujet correspondant.

> ⚠️ **Ce constat ne tient plus pour les sujets livrés le 2026-08-12.** Les 7 PDF de `data/New-docs/` recomposent les tests (items déplacés entre parties, repondérés, nouveaux problèmes de synthèse) sans que `Referentiel_Socle_v0.xlsx` ait changé (hash identique à la version du 2026-07-29). L'alignement décrit ci-dessus vaut pour les PDF **archivés** dans `data/Documents/archive/`, pas pour les PDF actifs depuis le 2026-08-12. Détail : **Arbitrage H**, §7.

---

## 2. Les deux systèmes face à face

| Dimension | Ancien système (`Hakili_Lab/data/knowledge/`) | Référentiel v2 |
|---|---|---|
| **Sujets** | 6 tests, fichiers DOCX (2 sans DOCX du tout) | 7 tests, PDF à cadres ancrés |
| **Niveaux** | 6e, 3e ×2, 4e, 2ndeC, Tle | 6e, 5e, 4e, 3e, 2ndeC, 1ereD, TleD |
| **Nombre de questions** | Variable : 26, 32, 33, 38, 46, 54 | **40 par test, systématiquement** |
| **Codes de question** | `Q_NUM_01`, `Q_GEO_07a` — sectionnés numérique/géométrique | `N1`, `L5`, `G13`, `D1`, `F1`, `M3` — par domaine, imprimés sur le sujet |
| **Vocabulaire de compétence** | `competences_cibles` : **texte libre**, ex. « Effectuer des opérations sur les entiers relatifs » | **101 codes canoniques** : `L.IDR`, `G.THA`, `N.NUM` |
| **Ancrage pédagogique** | `chunk_ids` → 121 chunks de `curriculum_*.yaml` | `code_competence` → onglet `02_Competences` |
| **Couverture de l'ancrage** | 6e → 3e uniquement | Primaire → 1ereD |
| **Typologie d'erreur** | Aucune (`lacune_type` en texte libre, uniquement dans le test 6e) | **7 types fermés** + 1031 signatures observables |
| **Structure de l'épreuve** | Aucune notion de partie | Partie A (30 q. courtes) / Partie B (10 exercices rédigés) |
| **Format de réponse** | Non modélisé | `qcm` / `court` / `redige` / `construction` |
| **Corrigés** | **Complets** : `reponse` + `solution` par question | **Absents sauf QCM** (voir §3) |
| **Coût de remédiation** | Aucun | 444 valeurs précalculées |

**Aucun identifiant n'est commun aux deux systèmes.** Il n'existe aucune table de correspondance entre `Q_NUM_01` et `N1`, ni entre `6e_NUM_Ch6_L1` et `N.RELOP`. Les deux vocabulaires sont disjoints.

---

## 3. Le manque bloquant : le référentiel n'a pas de corrigé

C'est le point le plus important de ce document.

Le classeur contient tout pour **diagnostiquer** une erreur, mais rien pour **savoir si la réponse est juste**. Vérifié colonne par colonne sur les 9 onglets : aucun n'expose une « bonne réponse » en dehors de `06_Distracteurs`, qui ne concerne que les QCM.

| Format | Questions | Bonne réponse disponible ? |
|---|---|---|
| `qcm` | 71 | ✅ oui, via `06_Distracteurs` (colonne « Bonne reponse ») |
| `court` | 139 | ❌ **non** |
| `redige` | 63 | ❌ **non** |
| `construction` | 7 | ❌ **non** |
| **Total** | **280** | ❌ **209 questions sans corrigé (75 %)** |

**Ce que cela empêche :** la Phase A (correction) est impossible sur 209 des 280 questions. Sans corrigé, ni l'IA ni l'enseignant ne peuvent statuer « juste / faux », donc aucun problème ne peut être créé, donc les modules 4 à 9 n'ont pas de matière.

`05_Grille_diagnostic` ne comble pas ce manque : elle décrit ce qu'on lit **quand l'élève se trompe** (« Écrit 4x² + 9 »), pas ce qu'il fallait écrire. On peut parfois déduire la bonne réponse par élimination des signatures, mais c'est une reconstruction fragile, pas une donnée.

**Ce manque n'est signalé ni dans `guide-v2.md`, ni dans `protocole-v2.md`, ni dans `00_Notice`.** Le classeur se présente comme « complet » sur le tagage des 280 questions — ce qui est vrai pour le diagnostic, mais la correction n'est pas couverte.

**Point positif :** l'ancien système possède des corrigés de bonne qualité (champ `reponse` = réponse attendue, champ `solution` = démarche détaillée), complets à 99 % (voir §5). Ils portent sur les anciens sujets, donc ne sont pas réutilisables tels quels — mais ils constituent un **modèle de format éprouvé** pour produire les corrigés manquants.

---

## 3bis. Les énoncés ne sont pas extractibles des PDF *(constat du 2026-07-30)*

Les 7 sujets sont produits par **WeasyPrint** (métadonnée `producer` du PDF), donc depuis une source HTML. Les mathématiques y sont rendues en **vectoriel** : 211 tracés sur une page, aucun span de texte les portant. L'extraction texte ne rend que la prose :

| Question | Extraction PDF (tous modes d'extraction testés) |
|---|---|
| `N5` (3ème) | `" Recopier et compléter avec le symbole  ou le symbole  :  et  ."` |
| `N1` (3ème) | `"Parmi les nombres ; ; ; , écrire ceux qui appartiennent à ."` |

Nombres, formules et symboles ont disparu. Aucune source HTML ni script générateur n'a été trouvé sur le disque.

**Ce que cela implique — et ce que cela n'implique pas :**
- ❌ Impossible de reconstituer les énoncés littéraux depuis les PDF.
- ✅ **Les codes de cadre, eux, s'extraient parfaitement** — c'est ce qui a permis la vérification 280/280 du §1, et c'est tout ce dont le module 2 a besoin (il lit le code, découpe la zone, n'interprète pas la page).
- ✅ **Le classeur porte la même information en texte** : `04_Questions` donne l'intitulé de chaque question (« Développer (2x−3)² »), `06_Distracteurs` donne les 4 options de chaque QCM avec la bonne réponse. C'est donc lui la source retenue.
- ✅ **L'énoncé complet n'est pas nécessaire au pipeline** : dans ce format, l'élève compose *sur le sujet*. La copie scannée porte donc l'énoncé imprimé, que l'IA transcrit en même temps que la réponse. C'est ce qui rend l'absence de `subject_text` acceptable, alors qu'elle aurait été bloquante dans l'ancien format à copie séparée.

**Limite cosmétique connue :** les intitulés du classeur sont majoritairement sans accents (« Ecrire », « Frequence » — 254 des 280 sont en ASCII replié). Ils apparaissent tels quels comme libellés de question dans l'interface. Corrigeable plus tard sans changement de schéma ; sans effet sur la correction ou le diagnostic.

**Si la source HTML est retrouvée**, elle donnerait les énoncés exacts avec leurs formules : cela vaudrait la peine de la demander, sans être bloquant.

---

## 4. Divergence de barème entre le classeur et les sujets

Le classeur et les PDF ne notent pas sur la même échelle.

| Source | Partie A | Partie B | Total |
|---|---|---|---|
| Onglet `04_Questions` | 30 q. × 1 pt = **30 pts** | 10 ex. × 3 pts = **30 pts** | **60 pts** |
| PDF (les 7, texte imprimé) | « Questions courtes (**10 points**) » | « Exercices à rédiger (**10 points**) » | « Barème total **20 points** » |

Le rapport est exactement 3, uniformément — la conversion est donc mécanique (`points_sur_20 = bareme_classeur / 3`), et les **poids relatifs sont identiques** : un exercice de partie B vaut 3 questions de partie A dans les deux échelles. Il n'y a pas de contradiction pédagogique, seulement deux unités.

`guide-v2.md` §9 confirme l'intention : « Les sujets sont aussi notés sur 20 au lieu de 60 ». Le classeur a conservé l'ancienne échelle.

### ✅ Décision (2026-07-30) : **le barème est stocké sur 20**

L'échelle imprimée sur le sujet fait foi. La conversion `bareme_sur_20 = bareme_classeur / 3` est faite **à l'import** (module 1), pas à l'affichage. Conséquence : une question de partie A vaut `1/3` de point, un exercice de partie B vaut `1` point.

**Le tiers de point n'est pas représentable exactement en décimal** — 30 × 0,3333 = 9,999 et non 10. Cette imprécision est sans conséquence **à condition de ne jamais utiliser un total déclaré comme dénominateur** :

> **Règle à appliquer partout : la note se calcule contre la somme réelle des `max_score`, jamais contre un « total » écrit en métadonnée.**

Avec cette règle, une copie parfaite vaut `19,999 / 19,999 × 20 = 20,00` exactement, quelle que soit la précision de stockage. Sans elle, on retombe précisément sur le bug §5.1, qui vient de ce que `compute_final_score()` divise par `total_possible` (valeur déclarée) au lieu de la somme réelle.

Cette règle est donc à la fois la manière de rendre la décision D sans risque **et** le correctif du bug §5.1. Elle rend le champ `rubric_actual_max` (déjà présent dans `CopyGrade`, actuellement inutilisé) enfin utile : c'est lui le dénominateur.

**Précision de stockage recommandée :** `Numeric(8,4)` — 0,3333 suffit largement, l'erreur cumulée sur 30 questions (0,001) est absorbée par l'arrondi au quart de point déjà en place.

---

## 5. État de santé de l'ancien système (constaté, non corrigé)

Ces défauts existent **aujourd'hui, en production**. Ils sont documentés ici parce qu'ils pèsent sur la décision du §7 : réparer l'ancien système a un coût réel qui doit entrer dans l'arbitrage.

### 5.1 Bug de notation actif — une copie parfaite n'obtient pas 20/20

`CopyGrade.compute_final_score()` (`src/models/domain.py:88`) utilise `total_possible` comme dénominateur, en écartant explicitement `rubric_actual_max` par un commentaire assumé. Or les deux valeurs divergent dans la moitié des barèmes :

| Barème | Somme réelle des `max_score` | `total_possible` déclaré | Note d'une copie parfaite |
|---|---|---|---|
| `bareme_test_2ndeC.yaml` | 20 | 20 | 20 / 20 ✅ |
| `bareme_test_4e.yaml` | 20 | 20 | 20 / 20 ✅ |
| `bareme_test_6e.yaml` | 20 | 20 | 20 / 20 ✅ |
| `bareme_test_3e.yaml` | 33 | 32 | **20,5 / 20** ❌ |
| `bareme_test_3e_v2.yaml` | 18,5 | 20 | **18,5 / 20** ❌ |
| `bareme_test_tle.yaml` | 19,5 | 20 | **19,5 / 20** ❌ |

Un élève sans faute au test 3e v2 est plafonné à 18,5/20 ; au test 3e v1, une copie parfaite dépasse le maximum. **Trois tests sur six sont concernés.**

### 5.2 Métadonnées fausses dans 4 barèmes sur 6

`meta.total_questions` ne correspond pas au nombre réel d'items : 3e annonce 32 pour 33, 3e v2 annonce 25 pour 26, 4e annonce 30 pour 32, 6e annonce 20 pour 38. Ces valeurs ne sont pas utilisées par le pipeline (le compte réel est recalculé), mais elles sont affichées à l'enseignant et faussent la lecture.

### 5.3 Champ de points incohérent entre fichiers

`bareme_test_3e.yaml` utilise `score_max` ; les cinq autres utilisent `points_originaux`. Or `_build_rubric_from_yaml()` (`src/knowledge/test_registry.py:148`) ne lit que `points_originaux`, avec `1.0` en valeur de repli. Pour le test 3e, **le champ réellement présent est ignoré** et tous les items retombent sur le défaut. Le résultat est correct par coïncidence (`score_max` y vaut 1 partout) — mais toute évolution de ce fichier produirait un barème silencieusement faux.

### 5.4 Ancrage RAG dégradé silencieusement

- **16 `chunk_ids` pointent vers des leçons inexistantes** (ex. `Q_GEO_02 → 6e_GEO_Ch2_L3`, `Q_NUM_12 → 5e_NUM_Ch8_L1`), répartis sur 3 barèmes.
- **69 des 121 chunks du curriculum ne sont jamais référencés** — 57 % de la base de connaissance est morte.
- **38 questions n'ont aucun `chunk_id`.**
- Le retriever journalise ces liens cassés en `logger.debug` (`src/knowledge/curriculum_retriever.py:168`) : **en exploitation normale, la dégradation est totalement invisible.** Le diagnostic sort appauvri sans que personne ne le sache.

### 5.5 Corrigés : incohérences mineures

`bareme_test_3e.yaml` : `Q_GEO_15` sans corrigé. `bareme_test_3e_v2.yaml` : `Q_GEO_01` et `Q_GEO_07` sans corrigé, et deux corrigés orphelins (`Q_GEO_1a`, `Q_GEO_07a`) qui ne correspondent à aucune question — vraisemblablement des identifiants mal saisis. Les 4 autres tests sont complets.

---

## 6. Ce que devient le curriculum RAG (121 leçons)

Les deux systèmes portent une description du programme officiel, avec un recouvrement partiel et des forces différentes.

| | `curriculum_*.yaml` (121 chunks) | `02_Competences` (101 codes) |
|---|---|---|
| Couverture | 6e, 5e, 4e, 3e | Primaire → 1ereD (dont lycée) |
| Prérequis | `prerequis_ids` | `Prerequis directs` |
| Contenu pédagogique | `savoir`, `savoir_faire[]`, `mots_cles[]`, `erreurs_frequentes[]` | `Description`, `Volume horaire officiel` |
| Erreurs | `erreurs_frequentes` génériques, par leçon | 1031 signatures observables, **par question** |
| Volume horaire | absent | présent (collège uniquement) |

Exemple de recouvrement : le chunk `4e_NUM_Ch4_L3` (« Identités remarquables ») et la compétence `L.IDR` décrivent la même chose. Le chunk est **plus riche pédagogiquement** (savoir-faire détaillés, erreurs fréquentes rédigées) ; la compétence est **plus exploitable** (code stable, prérequis chaînés jusqu'au primaire, volume horaire, coût de remédiation).

Ces deux objets ne sont pas concurrents s'ils sont articulés : le code canonique sert de **clé**, le chunk sert de **contenu** pour la génération des fiches de remédiation (module 7). Un rapprochement manuel des 121 chunks vers les 101 codes serait exploitable — mais il est à faire, il n'existe pas.

---

## 7. Les trois arbitrages à rendre

Ces décisions ne sont pas techniques : elles engagent le produit. Elles ne doivent pas être prises par l'implémentation.

### Arbitrage A — Que deviennent les 6 anciens tests ?

Les nouveaux sujets remplacent les anciens (« Les sept tests d'entrée ont été refaits », `guide-v2.md` §9). Trois voies :

| Option | Conséquence |
|---|---|
| **A1 — Archiver** *(recommandé)* | Les 6 anciens tests sortent du `_TEST_CATALOG`, leurs YAML sont conservés en lecture seule pour l'historique des copies déjà corrigées. Les bugs du §5 ne sont pas corrigés (inutile de réparer ce qui ne tourne plus). Le catalogue est reconstruit sur les 7 nouveaux tests. |
| **A2 — Faire coexister** | Les 6 anciens restent utilisables pendant une transition. Impose de corriger les bugs §5.1 à §5.4 (sinon on continue de produire des notes fausses) et de maintenir deux pipelines de diagnostic en parallèle. Coût réel, bénéfice limité si les nouveaux sujets sont prêts. |
| **A3 — Ré-aligner l'ancien sur le nouveau** | Retagger les 229 anciennes questions avec les codes canoniques. **Non recommandé** : travail considérable sur des sujets destinés à disparaître, et les anciens sujets n'ont ni cadres ancrés ni structure A/B — ils resteraient inexploitables par les modules 2 et 5. |

**Recommandation : A1.** Elle évite de payer la dette d'un système sortant.

### Arbitrage B — Qui produit les 209 corrigés manquants ?

C'est le chemin critique : sans corrigé, rien ne fonctionne en aval.

- **Périmètre :** 139 `court` + 63 `redige` + 7 `construction`.
- **Nature du travail :** pédagogique, pas technique. Il faut résoudre chaque question et rédiger la réponse attendue.
- **Ce sur quoi s'appuyer :** le format de l'ancien système (`reponse` = réponse attendue courte, `solution` = démarche) est éprouvé et directement transposable.
- **Répartition possible :** les 139 `court` attendent une réponse unique et fermée (un nombre, une expression) — production rapide, vérifiable mécaniquement. Les 63 `redige` demandent une démarche attendue et des critères de validation partielle. Les 7 `construction` posent une question distincte (comment valide-t-on un tracé ?) et peuvent être traités en dernier, voire renvoyés à la correction humaine.
- **Qui :** relève de la validation pédagogique, comme la relecture du référentiel (`00_Notice` : « À VALIDER par un enseignant de mathématiques »). À confier à la même personne, dans le même passage.

**Décision attendue :** qui produit ces corrigés, sous quel format, et dans quel délai. Tant que ce point n'est pas tranché, les modules 3 à 9 sont bloqués pour les questions non-QCM.

**✅ Rendu le 2026-08-12.** Un enseignant de mathématiques a relu et validé les corrigés des 7 tests, livrés sous forme de 7 PDF imprimables dans `data/New-docs/` (intégrés à `data/Documents/corriges/`). C'est la relecture `00_Notice` qui manquait. **Mais** ce corrigé décrit une composition de test différente de celle encodée dans `bareme_socle_*.yaml` — voir Arbitrage H, qui reste bloquant pour le diagnostic structuré (module 4) et la notation automatique.

### Arbitrage C — Le curriculum RAG survit-il ? *(tranché 2026-08-13, D-CEO-41)*

| Option | Conséquence |
|---|---|
| **C1 — Rapprocher les 121 chunks des 101 codes** | Ajouter une colonne `code_competence` à chaque chunk. Le contenu pédagogique (savoir-faire, erreurs fréquentes) reste disponible pour le module 7, indexé par une clé stable. Travail manuel estimé de l'ordre de 121 décisions, faisable en une passe. Ne couvre que le collège. |
| **C2 — Abandonner** | Le référentiel devient la seule source. Perte du contenu pédagogique rédigé ; le module 7 devra générer ses fiches sans matière préexistante. |
| **C3 — Laisser en l'état** | Deux ancrages parallèles, non reliés. **À écarter** : c'est exactement le schéma « deux sources de vérité » que le projet a déjà démoli deux fois (D-CEO-20, D-CEO-21). |
| **C4 — Rapprocher `remediation/` des 101 codes** *(retenu)* | Une source externe au dépôt (`remediation/`, 79 modules, 6e→Tle D) apporte ce que C1 ne pouvait pas donner à budget égal : les 7 niveaux (pas seulement le collège), et surtout des leçons complètes avec méthode, erreurs fréquentes **et** 2 838 exercices notés ★/★★/★★★ corrigés — l'exercice noté qu'aucun chunk curriculum ne portait. Le rapprochement (`manage.py rapprocher_remediation`) suit le principe de C1/`scripts/rapprocher_curriculum.py` (score de similarité), avec un seuil auto-validé plutôt qu'un classeur de relecture bloquant — décision explicite avec l'utilisateur, écart assumé avec Arbitrage B/C1. `curriculum_*.yaml` n'est pas retiré (C3 ne s'applique pas à lui) : il continue de servir l'ancien pipeline `src/pipeline/pipeline.py`, un chemin distinct du module 7. Détail complet : D-CEO-41. |

### Arbitrage H — Les 7 sujets recomposés du 2026-08-12 divergent de `bareme_socle_*.yaml` *(clos le 2026-08-13)*

**Constat.** `data/New-docs/` (livré le 2026-08-12) apporte 7 sujets PDF et 7 corrigés enseignant PDF, validés par un enseignant de mathématiques (Arbitrage B). Réconciliation automatique (grille de report de chaque corrigé, comparée code par code à `bareme_socle_*.yaml`) :

| Niveau | Items dans le corrigé PDF | Items dans le YAML | Items du YAML absents du corrigé | Nouveaux problèmes de synthèse (partie C, absents du YAML) | Items reclassés partie A→B (repondérés) |
|---|---|---|---|---|---|
| 6eme, 5eme, 4eme, 3eme | 31 | 40 | 13 | 4 (P1–P4) | 11 |
| 2ndeC, 1ereD, tleD | 40 | 40 | 6 | 6 (P1–P6) | 14 |

Le motif est identique et cohérent sur les 7 niveaux : passage d'une structure à 2 parties (Automatismes 30×1pt + Rédigé 10×3pt, celle du classeur actuel) à une structure à **3 parties** (Automatismes / Savoir-faire / Raisonnement — cette dernière faite de problèmes croisant plusieurs compétences). Confirmé auprès de l'utilisateur (2026-08-12) : **c'est une recomposition délibérée et définitive**, pas une erreur de version.

**Ce qui n'a pas bougé :** `Referentiel_Socle_v0.xlsx` — hash MD5 identique à la version du 2026-07-29 (comparé au fichier `Referentiel_Urie_v0.xlsx` livré en même temps, lui-même un doublon exact). La recomposition n'existe donc **que dans la mise en page des 7 PDF**, nulle part dans une donnée structurée. `bareme_socle_*.yaml`, généré le 2026-08-07 depuis ce même classeur non modifié, reflète encore l'ancienne composition à 2 parties.

**Conséquence si rien n'est fait :** le pipeline note les copies contre un barème (`bareme_socle_*.yaml`, 2 parties) qui ne correspond plus au sujet réellement composé par l'élève (3 parties, imprimé depuis `data/Documents/`). Les 4 à 6 problèmes de synthèse de la partie C n'ont **aucun** `RubricItem` — une réponse à ces questions ne peut pas être notée par `compute_final_score()`.

**Décision actée avec l'utilisateur (2026-08-12) : régénérer depuis le classeur.** `Referentiel_Socle_v0.xlsx` doit être mis à jour (onglets `04_Questions`, `06_Distracteurs`, `02_Competences` si de nouveaux codes de compétence sont nécessaires pour les problèmes croisés) pour refléter la composition des 7 corrigés PDF, puis `scripts/generer_baremes_socle.py` doit être relancé — **en sauvegardant d'abord tout `reponse_attendue`/`solution` déjà saisi à la main**, la régénération écrase ces champs.

**Ce que ça implique concrètement, dans l'ordre :**
1. Mettre à jour le classeur (travail pédagogique — code de compétence pour chaque problème de la nouvelle partie C, en particulier ; aucun code inventé, cf. `CLAUDE.md`).
2. Relancer `scripts/generer_baremes_socle.py`.
3. Re-remplir `reponse_attendue`/`solution` pour les items dont le code ou le barème a changé (les 11–14 reclassés par niveau, plus les nouveaux problèmes de synthèse) — le corrigé PDF sert de source pour cette étape, il est déjà validé.
4. Revérifier avec le même script de réconciliation (`reconcile.py`, écarts nuls attendus) avant de considérer le module 1 à jour pour ces 7 niveaux.

**Bloque :** module 1 (socle de données) pour un import strict des 7 tests, module 4 (diagnostic contraint — les nouveaux problèmes croisés n'ont pas de code de compétence), notation automatique fiable de la partie C.

**✅ Pilote appliqué sur `socle_6eme` le 2026-08-12, décision actée avec l'utilisateur : « le classeur n'est pas la priorité, la plateforme si ».** Plutôt que d'attendre la mise à jour du classeur, `data/knowledge/bareme_socle_6eme.yaml` a été **reconstruit à la main** directement depuis le sujet et le corrigé PDF (43 items : 16 A + 11 B + 4 problèmes de partie C, chacun décomposé en 4 sous-items `Pxa`–`Pxd`, un seul code de compétence canonique par sous-item — voir méthode ci-dessous). `Referentiel_Socle_v0.xlsx` reste non modifié : **`bareme_socle_6eme.yaml` fait temporairement foi en avance sur le classeur**, jusqu'à ce que celui-ci soit repris.

*Méthode retenue pour la décomposition de la partie C* — au lieu d'ajouter un champ « compétences multiples » pour porter les 3 à 5 codes que le corrigé associe à chaque problème (« croisée : G-a, M-a, N-c »), chaque problème est éclaté en autant de `RubricItem` que de termes dans son barème imprimé (`Barème. 1 + 2 + 1 + 1` → 4 sous-items), chacun avec **une seule** compétence — schéma existant, aucun champ inventé. Un champ `probleme_parent` (optionnel) regroupe les sous-items pour l'affichage. La compétence de chaque sous-item a été déduite du texte « Si l'élève échoue » et recoupée avec le tableau officiel « profil par domaine » du corrigé (N 10 pts, M 6 pts, G 1 pt, D 5 pts) : l'allocation retenue tombe à N 11 / M 5 — à 1 point près, sur un seul item (`P3b`) qui mélange deux savoir-faire dans un même terme de barème imprimé. Écart mineur, signalé mais non bloquant.

Deux corrections faites en cours de route :
- Les codes de question (`N1`, `D2`…) ne sont **pas** des identifiants stables entre l'ancien classeur et le nouveau sujet — ce sont des étiquettes de position dans le document. La correspondance a donc été faite par **contenu** (texte des questions, valeurs numériques lues visuellement sur les pages du corrigé PDF rendues en image — les nombres y sont vectoriels, invisibles à l'extraction texte), pas par égalité de code.
- `G5` et `G6` (tracé de perpendiculaires, construction d'un carré + cercle) ont été retagués `format: construction` (et non `redige`) — ce sont des tracés au compas/équerre, pas des réponses rédigées. Leur `reponse_attendue` reste vide, cohérent avec la convention déjà en place pour les questions `construction` (arbitrage F).

**Validé par les tests :** `tests/test_baremes_socle.py` mis à jour (nouveau jeu d'assertions pour les niveaux « recomposés », ancien jeu conservé pour les 6 niveaux pas encore repris) — 65/65 passent. Suite pipeline complète (`pytest tests/`) : 246/246. `manage.py check` propre.

**Reste à faire :** répliquer la même méthode aux 2 autres niveaux (1ereD, tleD).

**✅ `socle_5eme` reconstruit le 2026-08-12, même jour.** 45 items (16 A + 13 B + 16 sous-items C). Ce corrigé est plus explicite que celui de 6e : chaque terme du barème de partie C indique son domaine entre parenthèses, et la grille finale donne, par problème, la répartition par domaine. Résultat : la vérification contre le tableau officiel « profil par domaine » tombe **exactement juste** (G 2 / M 4 / N 10 / D 6 = 22, aucun écart), sans l'approximation nécessaire en 6e.

Une différence structurelle propre à ce niveau : deux items de partie B (`G7`, `G9`) mélangent calcul et tracé au compas dans un même item à 2 points — contrairement aux items 6e qui étaient soit entièrement rédigés, soit entièrement construction. Décomposés en deux sous-items chacun (`G7a`/`G7b`, `G9a`/`G9b`), portant la partie B à **13 items pour 22 points inchangés**. Le test `test_structure_a_3_parties` a été généralisé en conséquence (somme des points de partie B ± cardinalité, plutôt qu'un compte fixe de 11 items).

Point d'incertitude signalé (pas résolu) : `G3`/`G6` portent sur des angles **supplémentaires** (somme 180°), sans code canonique dédié dans le référentiel actuel — `G.ANG2` (angles complémentaires, somme 90°) est retenu comme meilleure approximation disponible.

Tests : `tests/test_baremes_socle.py` (64/64), suite pipeline complète (245/245), `manage.py check` propre.

**✅ `socle_4eme` reconstruit le 2026-08-13.** 48 items (16 A + 12 B + 20 sous-items C). Ce corrigé est le plus explicite des trois : au-delà du domaine par terme, il donne une phrase récapitulative de la répartition exacte par problème (« P1 donne 2 points à M et 3 à N ; P2, 4 points à L et 1 à D… »), ce qui a permis un recoupement **exact** avec le tableau « profil par domaine », sans aucune approximation.

Deux différences propres à ce niveau :
- Un nouveau domaine apparaît : **L (calcul littéral et équations)**, distinct de N — première apparition dans la progression 6e→tleD.
- Le nombre de sous-items par problème de partie C **n'est plus fixé à 4** : certains problèmes ont 5 ou 6 termes de barème distincts (ex. P2 a 5 sous-questions à 1 pt chacune). `test_sous_items_partie_c_rattaches_a_un_probleme` généralisé en conséquence (3 à 6 sous-items, plus la somme exacte du barème).
- Un seul item mixte calcul/construction cette fois (`G5`, décomposé en `G5a`/`G5b`) — Partie B passe à 12 items pour 22 points inchangés.

Point d'incertitude signalé : `N6` (calcul d'un PPCM) rattaché à `N.PGCD`, faute de code canonique dédié au PPCM dans le référentiel actuel.

Tests : `tests/test_baremes_socle.py` 63/63, suite pipeline complète 244/244, `manage.py check` propre.

**✅ `socle_3eme` reconstruit le 2026-08-13.** 50 items (16 A + 12 B + 22 sous-items C). **Différence méthodologique importante avec 5e/4e :** ce corrigé ne donne pas le domaine de chaque terme de barème en partie C — il rattache chaque problème en bloc à un unique domaine dominant (« P1 et P2 en G, P3 en L, P4 en F »), sans répartition fine. La décomposition en sous-items a donc été maintenue (une compétence par sous-item, cohérente avec le principe du module 4), mais **sans le recoupement exact** qui validait fortement les niveaux précédents. Plusieurs sous-items portent une mention explicite de confiance basse dans leur `objet` (code canonique disponible le plus proche, sans certitude) — à confirmer avec l'enseignant qui a validé le corrigé avant tout usage en notation automatique de ces items précis.

Autres nouveautés : apparition des domaines **G.VEC (vecteurs)** et **F (applications/fonctions)** ; `G7` (partie B) décomposé en construction + déduction, même motif que les niveaux précédents.

Tests : `tests/test_baremes_socle.py` 62/62, suite pipeline complète 243/243, `manage.py check` propre.

**✅ `socle_2ndeC` reconstruit le 2026-08-13 — premier niveau lycée.** 66 items (20 A + 14 B + 32 sous-items C, 6 problèmes). Échelle différente du collège : barème classeur 80 pts, converti /20 par **division par 4** (collège : ÷3) — `tests/test_baremes_socle.py` distingue maintenant les niveaux lycée pour cette conversion.

Ce corrigé revient au motif précis de 5e/4e : répartition exacte des points de chaque problème par domaine (« P1 donne 2 pts à G et 3 pts à N »), recoupement **exact** avec le tableau officiel, aucune approximation — contrairement à 3e. Aucun item hybride calcul/construction cette fois (pas de construction géométrique au programme de ce niveau).

Tests : `tests/test_baremes_socle.py` 61/61, suite pipeline complète 242/242, `manage.py check` propre.

**✅ `socle_1ereD` reconstruit le 2026-08-13 — deuxième niveau lycée, recoupement exact.** 59 items (20 A
+ 14 B + 25 sous-items C, 6 problèmes). Comme pour 2ndeC, le corrigé donne le tableau « profil par
domaine » avec les totaux (N 12,5 / L 16,5 / F 22 / G 22,5 / D 6,5 = 80 pts) et une clé de répartition
explicite des points de chaque problème de partie C entre domaines — recoupement **exact** sur les 5
domaines, aucun écart. Deux sous-items isolés (`P5d`, `P6e`) n'ont pas de code canonique qui colle
exactement à leur contenu (comparaison numérique de deux carrés ; signalement d'une donnée manquante) —
rattachés par approximation à `N.RAC` et `N.PROB`, sans effet sur les totaux par domaine.

Tests : `tests/test_baremes_socle.py` 60/60, suite pipeline complète 241/241, `manage.py check` propre.

**✅ `socle_tleD` reconstruit le 2026-08-13 — dernier niveau, arbitrage H clos.** 66 items (20 A + 14 B
+ 32 sous-items C, 6 problèmes). Le corrigé de ce niveau est le plus favorable des 7 : sa grille de fin
donne directement le barème officiel par domaine (N 4 / L 11 / F 30 / S 11 / T 8 / D 4 / G 12 = 80 pts)
**et** la clé de répartition exacte des points de chaque problème de partie C entre domaines — recoupement
**exact** sur les 7 domaines, sans qu'aucune lecture visuelle n'ait été nécessaire pour déterminer la clé
elle-même (contrairement aux niveaux précédents, où seuls les totaux par domaine étaient parfois donnés).
Deux nouveautés : 7 domaines actifs (`S` suites/récurrence et `T` trigonométrie apparaissent comme
domaines à part entière) ; le corrigé classe lui-même les fonctions rationnelles tantôt `L` (résolution
algébrique isolée) tantôt `F` (étude de variation), suivi à l'identique. Trois sous-items isolés
(`P4a`/`P4b`, `P6d`) n'ont pas de code canonique dédié à leur contenu précis — rattachés par approximation,
sans effet sur les totaux par domaine.

Tests : `tests/test_baremes_socle.py` 59/59 (+4 tests devenus vides, `_NIVEAUX_HERITES` est désormais
une liste vide), suite pipeline complète 240 passent + 4 vides, `manage.py check` propre.

**Arbitrage H clos.** Les 7 niveaux (`6eme` à `tleD`) sont reconstruits à la main sur la structure à 3
parties. `Referentiel_Socle_v0.xlsx` reste non modifié — ces 7 fichiers YAML font foi jusqu'à ce que le
classeur soit repris, décision actée avec l'utilisateur le 2026-08-12 (« le classeur n'est pas la priorité,
la plateforme si »). Reporter cette recomposition dans le classeur reste un travail pédagogique séparé,
non bloquant pour la suite du chantier v2.

---

## 8. Plan d'harmonisation proposé

Sous réserve des arbitrages ci-dessus (hypothèse : A1 + C1).

### Étape 1 — Geler l'ancien système *(rapide, sans risque)*
- Retirer les 6 anciens tests du `_TEST_CATALOG` actif (`src/knowledge/test_registry.py`) ou les marquer `archive: True`.
- Conserver les YAML tels quels : les copies déjà corrigées y font référence.
- Ne **pas** corriger les bugs §5.1–§5.4 si l'option A1 est retenue — les documenter comme dette assumée d'un système sortant.
- **Si A2 était retenue à la place**, alors ces 4 bugs deviennent bloquants et doivent être traités en premier.

### Étape 2 — Corriger la classe de bug §5.1 dans le code *(indépendant de l'arbitrage A)*
Le défaut de dénominateur (`total_possible` vs somme réelle) est dans `domain.py`, pas dans les données : il frappera de la même manière les nouveaux tests si le barème saisi diverge du total déclaré. À traiter comme un correctif de code, avec un test unitaire « une copie parfaite vaut exactement 20/20 » applicable à tout barème.

### Étape 3 — Importer le référentiel *(module 1)*
Comme prévu dans `v2_roadmap.md`. L'import peut être strict (échec sur code inconnu) : l'intégrité du classeur a été vérifiée au module 0, zéro violation.

### Étape 4 — Produire les corrigés manquants *(arbitrage B — chemin critique)*
- Définir le schéma de stockage : soit une colonne supplémentaire dans la banque de questions (`question.reponse_attendue`, `question.solution`), soit une table dédiée. Recommandation : colonnes sur `question`, le lien est 1-à-1.
- Prévoir dès maintenant la colonne dans le modèle du module 1, même si elle reste vide au départ — l'ajouter plus tard coûterait une migration supplémentaire.
- Ordre de production suggéré : 139 `court` → 63 `redige` → 7 `construction`.

### Étape 5 — Rapprocher le curriculum du référentiel *(arbitrage C1)*
- Ajouter `code_competence` aux 121 chunks (fichiers YAML existants, champ supplémentaire).
- Contrôler la couverture : quels codes canoniques n'ont aucun chunk (attendu : les 27 du lycée, et probablement d'autres).
- Le `CurriculumRetriever` devient un fournisseur de contenu indexé par code canonique, plus un système d'ancrage autonome.

### Étape 6 — Retirer le `chunk_id` du chemin de diagnostic
Une fois le module 4 en place pour un niveau, `CompetencyGap.chunk_id` n'est plus l'ancrage : le couple `(code_competence, code_type_erreur)` l'est. Le chunk redevient une ressource de contenu. À faire niveau par niveau, comme prévu pour le remplacement du diagnostic.

---

## 9. Récapitulatif des points à trancher

| # | Question | Qui décide | Bloque | Statut |
|---|---|---|---|---|
| A | Archiver / faire coexister / ré-aligner les 6 anciens tests | Utilisateur | Modules 1, 8 | ✅ **A1 — archivés** (2026-07-30, appliqué) |
| D | Échelle de barème en base : 60 (classeur) ou 20 (sujets) | Utilisateur | Module 1 | ✅ **sur 20** (2026-07-30, §4) |
| G | Source des données des 7 nouveaux tests | Utilisateur | Modules 1, 8 | ✅ **le classeur** (2026-07-30, §3bis — 7 tests générés et opérationnels) |
| B | **Qui produit les 209 corrigés manquants, sous quel format, quand** | Utilisateur + enseignant de maths | **Modules 3 à 9 — chemin critique** | ✅ **relus et validés par un enseignant de mathématiques (2026-08-12)** — 7 corrigés PDF complets, `data/Documents/corriges/`. Validation `00_Notice` faite. Mais leur composition ne correspond plus à `bareme_socle_*.yaml` — voir **arbitrage H**, nouveau chemin critique. |
| C | Sort du curriculum RAG (121 chunks) | Utilisateur | Modules 4, 7 | 🟨 **rapprochement préparé** — 31 propositions nettes, 85 à trancher, 5 sans candidat ; classeur à valider |
| E | Volumes horaires du lycée absents → palier incalculable en 2ndeC/1ereD | Utilisateur (point ouvert #2) | Module 6 | ⬜ en attente |
| F | Format `construction` : diagnostic automatique ou saisie humaine ? | Utilisateur | Modules 2, 4 | ⬜ en attente |
| H | **Les 7 sujets recomposés (2026-08-12) divergent de `bareme_socle_*.yaml`** | Utilisateur + enseignant de maths | Module 1 (import strict), module 4, notation auto | ✅ **clos (2026-08-13) : les 7 `bareme_socle_*.yaml` (6eme à tleD) reconstruits à la main** depuis les sujets/corrigés PDF, en avance sur le classeur. Reporter la recomposition dans `Referentiel_Socle_v0.xlsx` reste un travail pédagogique séparé, non bloquant. Voir §7 Arbitrage H. |

### État du catalogue de tests après harmonisation

L'archivage a été fait de façon à **ne pas casser l'historique** : `get_test()` continue de résoudre les 6 tests archivés, car `pipeline.py:375` s'en sert pour déterminer la classe d'une copie déjà corrigée. Seul `available_tests()` les masque.

| Test | Statut | Questions | Corrigé |
|---|---|---|---|
| `socle_6eme` → `socle_tleD` (7) | ✅ actifs | 40 chacun dans le YAML · 31 à 40 dans le sujet/corrigé imprimé (arbitrage H) | ✅ PDF enseignant complet et validé (`data/Documents/corriges/`), servi via `correction_web:corrige` |
| `hakili_*` (6) | 🗄 archivés | — | conservés, non corrigés (dette assumée) |

Les 7 nouveaux tests sont **opérationnels et sélectionnables**. Chacun déclare `classe` = une classe canonique unique (`6e`, `5e`, `4e`, `3e`, `2nde`, `1ere`, `Tle`), ce qui améliore la détermination de la classe par rapport aux anciens tests : `resolve_classe` dispose d'un garde-fou exact et, en cas d'échec d'extraction de l'en-tête, d'un repli fiable (un seul niveau déclaré). Les anciens tests déclaraient les *niveaux évalués* (« 6e · 5e · 4e »), ce qui pouvait faire échouer le garde-fou quand la classe extraite était celle de l'élève.

**Attention si le classeur est mis à jour :** les fichiers `bareme_socle_*.yaml` sont générés. Relancer `python scripts/generer_baremes_socle.py` — mais **sauvegarder d'abord tout corrigé saisi à la main**, la régénération écrase les champs `reponse_attendue` / `solution`.

**Sujets imprimables (`data/Documents/*.pdf`) mis à jour le 2026-08-12** — ce sont désormais les 7 sujets recomposés (structure Automatismes/Savoir-faire/Raisonnement), pas ceux décrits au §1/§4 de ce document. Les anciens sont conservés dans `data/Documents/archive/` pour l'historique des copies déjà corrigées avec l'ancienne composition. Voir **arbitrage H** pour le désalignement avec `bareme_socle_*.yaml` que cette mise à jour a révélé.

---

## Annexe — Méthode de vérification

Tous les chiffres de ce document proviennent de contrôles scriptés sur les fichiers réels, pas d'une lecture. Contrôles effectués :

- Extraction des codes de cadre des 7 PDF (PyMuPDF) confrontée à `04_Questions` → 280/280.
- Comparaison des intitulés `04_Questions` au texte imprimé du PDF 6ème → correspondance mot à mot.
- Intégrité référentielle du classeur (compétences, types d'erreur, distracteurs, couverture) → 0 violation.
- Reproduction de `_build_rubric_from_yaml()` sur les 6 barèmes pour simuler la note d'une copie parfaite → 3 anomalies.
- Résolution des `chunk_ids` de tous les barèmes contre les 121 chunks définis → 16 liens cassés, 69 chunks orphelins, 38 questions sans ancrage.
- Comparaison des identifiants barème ↔ corrigé sur les 6 tests → 3 manques, 2 orphelins.
- Recherche d'une colonne « bonne réponse » sur les 9 onglets → présente uniquement dans `06_Distracteurs`.
