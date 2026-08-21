# Registre des Décisions — Hakili Lab AI Correction
**Mis à jour le : 2026-06-11 (réorientation vers correction assistée)**

---

## Décisions initiales d'architecture (fondations techniques)

| ID | Décision | Statut | Justification |
|---|---|---|---|
| D001 | Ingestion par copie complète PDF/images, pas question par question | **Validée** | Plus rapide, moins fastidieux, meilleur flux terrain |
| D002 | JSON structuré comme source de vérité, PDF comme rendu | **Validée** | Facilite évaluation, audit et réutilisation |
| D003 | Streamlit pour l'interface MVP | **Validée** | Plus rapide à implémenter en Python |
| D004 | Stockage local anonymisé pour prototype | **Validée** | Simplicité + confidentialité |
| D005 | Évaluation sur 100 copies avec enseignant référent | **Validée** | Exigence du cahier de charges |

---

## Décisions CEO — 2026-05-08

### D-CEO-01 — Périmètre matières et niveaux du MVP
**Décision :** Mathématiques uniquement, tous niveaux du secondaire : **6e à la Terminale**.

---

### D-CEO-02 — Format du barème
**Décision :** Notation binaire — **1 ou 0** par question (ou sous-question).

**Règle métier clé :** Une question comportant N sous-questions est décomposée en N questions indépendantes, chacune valant 1 point. Il n'y a pas de notation partielle : une réponse est correcte (1) ou incorrecte (0).

*Exemple : Question 3 avec 3 sous-questions → Q3a (1 pt), Q3b (1 pt), Q3c (1 pt). La note de Q3 = somme des sous-questions.*

**Impact :** Le module de parsing du barème et le schéma `grading.json` sont simplifiés : `max_score` est toujours un entier, `score` est toujours 0 ou 1 par item.

---

### D-CEO-03 — Stratégie fournisseurs IA *(révisée 2026-06-05)*
**Décision initiale (2026-05-08) :** Anthropic Claude exclusivement.
**Décision révisée (2026-06-05) :** **Architecture multi-provider avec routing automatique par tâche.**

**Contexte de révision :** Un run réel sur une copie de 15-20 pages a coûté ~$8 avec Claude Opus 4.7 exclusif. L'analyse comparative a montré que chaque tâche a un provider optimal différent.

**Répartition finale :**

| Tâche | Provider | Modèle | Justification clé |
|---|---|---|---|
| Transcription | Google Gemini | gemini-2.0-flash | Vision native, tier gratuit 1M tok/j |
| Correction | DeepSeek | deepseek-chat (V3) | MATH-500 ~90%, 18× moins cher qu'Opus |
| Diagnostic | DeepSeek | deepseek-reasoner (R1) | Modèle de raisonnement, causes cachées |
| Remédiation | Mistral | mistral-small-latest | Français académique natif |
| Extraction structurée | Claude | claude-sonnet-4-6 | tool_use forcé, fiabilité JSON |

**Routing :** automatique selon clés API disponibles dans `.env` — fallback Claude si clé absente.

**Analyse complète :** [docs/ai_providers_analysis.md](ai_providers_analysis.md)

**Coût résultant :** ~$0.02/copie vs ~$8.00/copie initial — réduction ×400.

---

### D-CEO-04 — Couche d'instructions expert (optionnelle)
**Décision :** Ajout d'une **couche optionnelle d'instructions expert** injectée dans le prompt de correction.

**Fonctionnement :** Avant de lancer la correction, l'enseignant peut saisir des instructions contextuelles propres au devoir : attentes spécifiques, points de vigilance, critères d'interprétation. Ces instructions sont injectées dans le prompt système de l'IA pour affiner la correction.

**Tolérance :** La tolérance d'erreur cible est volontairement ambitieuse (proche de ±0 pt) grâce à cette couche contextuelle. L'objectif est que l'IA produise une correction de très haute qualité lorsque les instructions expert sont fournies.

**Cette couche est optionnelle :** sans instructions, la correction reste basée uniquement sur l'énoncé et le barème.

---

### D-CEO-05 — Validation humaine
**Décision :** La **validation humaine est supprimée du pipeline applicatif**.

**Justification :** Elle se fait hors plateforme, par l'enseignant directement sur le rapport généré. Le système ne bloque plus la restitution en attente d'une validation dans l'interface.

**Conséquence :** Le flag `requires_teacher_review` reste présent dans les données JSON (information utile), mais aucun écran de validation n'est intégré dans le flux.

---

### D-CEO-06 — Format du rapport PDF
**Décision :** Contenu minimal du rapport :

- Note totale et détail par question (avec sous-questions)
- Commentaire pédagogique par question
- Zones marquées "Révision requise" (si confiance IA faible)
- Diagnostic des compétences maîtrisées / lacunes
- Plan de remédiation élève
- Score de confiance IA visible
- Logo Hakili Lab
- Numéro d'anonymisation de l'élève (pas de nom)

**Mode d'affichage :** Le contenu du rapport est d'abord affiché directement dans l'interface Streamlit. Un bouton "Télécharger le PDF" permet ensuite d'exporter le rapport.

---

### D-CEO-07 — Politique d'identification *(anonymisation supprimée)*
**Décision :** **Suppression de l'anonymisation.** Les copies sont identifiées par le nom réel de l'élève.

**Processus :**
1. L'enseignant saisit le nom de l'élève (copie unique) ou le fichier est nommé avec le nom de l'élève (batch).
2. Un identifiant technique sûr (slug, ex. `aminata_sawadogo`) est dérivé du nom pour les dossiers et fichiers.
3. Le PDF exporté affiche le nom réel de l'élève.
4. Aucune fiche de correspondance n'est générée.

**Justification :** La correction est un acte pédagogique interne — l'anonymisation compliquait le flux sans apporter de valeur dans le contexte d'utilisation réel.

---

### D-CEO-08 — Ressources internes pour la remédiation
**Décision :** Reporté — remédiation **générique** pour le MVP. L'IA suggère des thèmes et types d'exercices sans pointer vers une base de ressources. Option B (librairie Hakili) réservée à une version ultérieure.

---

### D-CEO-09 — Deux modes d'interface
**Décision :** L'interface Streamlit propose **deux modes distincts** :

| Mode | Description |
|---|---|
| **Copie Unique** | Traitement et correction d'une seule copie, résultat immédiat |
| **Batch** | Traitement d'un lot de copies (plusieurs élèves en une session), rapport consolidé |

Les deux modes partagent le même pipeline. Le mode Batch ajoute une boucle d'itération et une synthèse de classe (distribution des notes, compétences globales).

---

### D-CEO-10 — Format d'entrée optimal *(nouveau 2026-06-05)*
**Décision :** **PDF multi-pages scanné à 150 DPI, mode niveaux de gris.**

> **DPI** (*Dots Per Inch*) : nombre de pixels capturés par pouce (2,54 cm) de document physique. Un scan A4 à 150 DPI produit une image de 1 240 × 1 754 pixels, suffisant pour lire exposants et barres de fraction. À 300 DPI, l'image est 4× plus lourde sans gain de qualité pour un LLM.

**Justification :**
- 150 DPI satisfait le critère de Nyquist pour les traits manuscrits (≥ 2× la fréquence des éléments les plus fins)
- Scanner = distorsion perspective nulle (θ = 0°) vs photo téléphone (θ = 20-35° → 13% compression)
- Niveaux de gris : conserve les demi-tons (traits pâles) contrairement au N&B pur
- 300 DPI = overkill : +80% de tokens sans gain perceptible pour un LLM

**Matériel recommandé :**
- Usage régulier : Scanner ADF (ex. Epson WorkForce ES-65W, ~$130)
- Terrain : Smartphone + Microsoft Lens (mode Document → correction perspective automatique)

**Analyse complète :** [docs/input_pipeline_analysis.md](input_pipeline_analysis.md)

---

### D-CEO-11 — Coût cible et volume de référence *(nouveau 2026-06-05)*
**Décision :** Coût cible en production validé : **~$0.02/copie (avec Gemini), ~$12/an pour 540 copies.**

**Hypothèse de référence :**
- Volume : 3 classes × 6 évaluations × 30 élèves = 540 copies/an
- Pages/copie : ~11 pages (constaté sur copie réelle, 150 DPI)
- Total pages : ~5 940 pages/an → 33 pages/jour scolaire (Gemini tier gratuit : 1M tok/j)

**Coût réel mesuré par scénario (11 pages, 150 DPI) :**

| Scénario | Transcription | Correction | Diagnostic | Remédiation | **Total/copie** | **Total 100 copies** |
|---|---|---|---|---|---|---|
| Optimal (Gemini actif) | Gemini Flash ~$0.008 | DeepSeek V3 | DeepSeek R1 | Mistral | **~$0.028** | ~$2.80 |
| Actuel (Gemini KO, région) | Sonnet 4.6 ~$0.27 | DeepSeek V3 | DeepSeek R1 | Mistral | **~$0.29** | ~$29 |
| Fallback total (Claude seul) | Sonnet 4.6 ~$0.27 | Sonnet 4.6 | Haiku 4.5 | Sonnet 4.6 | **~$0.48** | ~$48 |

**Poste dominant : la transcription (vision).** Elle représente 93% du coût actuel parce que Claude Sonnet traite les images à $3/M tokens vs $0.10/M pour Gemini Flash. Réactiver Gemini réduirait le coût par 10.

**Seuil d'alerte :** si le volume dépasse 200 copies/jour avec Gemini actif, passer au tier payant (~$2/an supplémentaires).

---

### D-CEO-12 — Diagnostic ancré sur le programme officiel (RAG) *(nouveau 2026-06-08)*
**Décision :** Implémenter un système **RAG (Retrieval-Augmented Generation)** basé sur les curricula officiels du Burkina Faso pour le secondaire (6e → 3e).

**Architecture RAG :**
1. **Base de connaissance** (`data/knowledge/curriculum_*.yaml`) — 121 leçons structurées par classe, domaine, chapitre et leçon, avec `savoir`, `savoir_faire[]`, `prerequis_ids[]`, `mots_cles[]`, `erreurs_frequentes[]`
2. **Barèmes enrichis** (`data/knowledge/bareme_test_*.yaml`) — chaque question du test est mappée à ses `chunk_ids` de curriculum
3. **Retrieval** (`src/knowledge/curriculum_retriever.py`) — à la fin de la correction, les chunks associés aux questions échouées sont récupérés et injectés dans le prompt diagnostic via `{{CURRICULUM_CONTEXT}}`
4. **Sortie structurée** — `DiagnosticResult.competency_gaps: list[CompetencyGap]` avec chunk_id, classe, domaine, leçon, savoir_faire, erreurs_fréquentes

**Justification :** Un diagnostic qui dit "lacune en algèbre" est inutilisable. Un diagnostic qui dit "l'élève ne maîtrise pas `[4e_NUM_Ch4_L3] Identités remarquables` — erreur fréquente : (a+b)² = a²+b² (oubli de 2ab)" est actionnable par l'enseignant et valorisable auprès des parents.

**Couverture actuelle :** 6e, 5e, 4e, 3e. Le primaire (CE1–CM2, pertinent pour le test 6e) n'a pas encore de chunks — le diagnostic reste valide mais sans références de leçons spécifiques.

**Backward-compatible :** `get_diagnostic_context()` retourne `""` si `bareme_id` absent ou si aucune question échouée → le pipeline tourne sans RAG sans modification.

---

### D-CEO-13 — Tests Hakili pré-chargés (TestRegistry) *(nouveau 2026-06-08)*
**Décision :** Créer un **catalogue de tests standards Hakili** (`src/knowledge/test_registry.py`) qui auto-charge l'énoncé et le barème de chaque test standard au démarrage de la session.

**Flux enseignant avec TestRegistry :**
1. L'enseignant sélectionne "Test d'entrée en 3e" dans le menu déroulant
2. Un bandeau confirme : `✓ Énoncé pré-chargé (3 777 car.) · ✓ Barème 33 questions · ✓ RAG activé`
3. L'enseignant charge **uniquement la copie de l'élève** (PDF ou photos)
4. Aucun upload d'énoncé ni de barème n'est demandé

**Tests disponibles (v1) :**

| ID | Label | DOCX source | Barème YAML | Questions |
|---|---|---|---|---|
| `hakili_3e_v1` | Test d'entrée en 3e | `Hakilisso test de niveau 3e.docx` | `bareme_test_3e.yaml` | 33 (NUM + GEO) |
| `hakili_6e_v1` | Test d'entrée en 6e | `TEST DE NIVEAU,6eme,GROUPE 1.docx` | `bareme_test_6e.yaml` | 33 (NUM + GEO) |

**Justification :** Éliminer la friction opérationnelle (upload énoncé + saisie barème à chaque copie) est critique pour que l'outil soit utilisé quotidiennement par les enseignants Hakili sans formation.

**Extension :** Ajouter un test = ajouter une entrée dans `_TEST_CATALOG` + un DOCX dans `data/Documents/` + un YAML dans `data/knowledge/`. Aucune modification du code pipeline nécessaire.

---

### D-CEO-14 — Interface premium et positionnement marketing *(nouveau 2026-06-08)*
**Décision :** L'interface doit refléter le positionnement premium de Hakili Lab et fonctionner comme **instrument marketing** auprès des parents d'élèves.

**Implémentation (`src/ui/progress.py`) :**
- **Écran "Analyse en cours"** (remplace le spinner Streamlit générique) avec 7 étapes nommées, barre de progression temps réel (%, transition CSS cubic-bezier), logo Hakili animé (pulsation avec lueur)
- **Palette identitaire** : `#001e4a` (bleu marine), `#4a90e2` (bleu Hakili), `#27ae60` (vert validation)
- **Langage** : "Correction intelligente — ensemble voting", "Diagnostic pédagogique approfondi", "Génération du plan de remédiation" — vocabulaire expert qui justifie la valeur
- **Validation** : bandeau vert "✓ Analyse complète — rapport disponible" à la fin

**Étapes visibles (7) :**

| Étape | Label affiché | % déclenchement |
|---|---|---|
| ingestion | Ingestion & contrôle qualité image | 8% |
| transcription | Transcription multimodale (manuscrit) | 28% |
| correction | Correction intelligente — ensemble voting | 55% |
| rag | Récupération du contexte programme | 68% |
| diagnostic | Diagnostic pédagogique approfondi | 80% |
| remediation | Génération du plan de remédiation | 90% |
| export | Export PDF & rapport JSON | 98% |

**Modèle commercial visé :** Outil interne Hakili Lab pour les enseignants. Le rapport PDF + sujet de remédiation constituent le livrable.

**Justification :** Un outil qui produit un "spinner" générique n'est pas facturable. Un outil qui montre en temps réel une "Transcription multimodale" puis un "Diagnostic pédagogique approfondi" ancré sur le programme officiel justifie un prix premium.

---

### D-CEO-16 — Réorientation vers la correction assistée par IA *(nouveau 2026-06-11)*
**Décision :** Le système passe d'une **correction automatique** à une **correction assistée** où l'IA propose et l'enseignant valide.

**Ancien mode :** L'IA corrige, génère un rapport, l'enseignant le consulte hors système.
**Nouveau mode :** L'IA propose une note par question → l'enseignant accepte ou refuse dans l'interface → le score final est calculé en priorisant les décisions enseignant.

**Justification :**
- La correction automatique sans validation est inacceptable pour un document officiel
- L'enseignant doit rester le garant pédagogique — l'IA est un assistant, pas un décideur
- La validation in-app est plus rapide et traçable que la révision hors plateforme
- Elle ouvre la voie à l'amélioration continue du système (on mesure les désaccords IA/enseignant)

**Impact sur le pipeline :**
- Le pipeline se scinde en Phase A (correction IA + validation enseignant) et Phase B (diagnostic)
- `QuestionGrade` est enrichi : `teacher_decision` (accepted/refused/pending) + `teacher_score`
- `CopyGrade` est enrichi : `final_score` (basé sur les décisions enseignant)
- Le diagnostic (Phase B) ne se déclenche qu'après la validation complète de la Phase A

---

### D-CEO-17 — Le diagnostic approfondi comme objectif central *(nouveau 2026-06-11)*
**Décision :** Le **diagnostic pédagogique approfondi** est positionné comme la **valeur principale** du produit — pas la correction.

**Ce que produit le diagnostic :**
- Pour chaque question échouée : identification des causes cachées (pas des symptômes)
- Ancrage sur une leçon précise du programme officiel (chunk_id)
- Identification de la classe concernée (la lacune vient de quelle année ?)
- Exemples concrets de l'erreur type pour chaque lacune (depuis `erreurs_frequentes` du curriculum)
- Le tout organisé par domaine (numérique / géométrique)

**Ce que le diagnostic ne fait plus :**
- Lister des commentaires par question (supprimé du rapport)
- Produire une note (rôle de la Phase A)

**Structure du rapport final :**
1. Tableau bonnes réponses (N° question · points)
2. Tableau mauvaises réponses (N° question · 0/points)
3. Corps : diagnostic approfondi par domaine + plan de remédiation ciblé

**Justification :** Un enseignant peut corriger une copie manuellement. Ce qu'il ne peut pas faire facilement : identifier que "la confusion entre (a+b)² et a²+b²" vient d'une lacune de 4e non comblée, ni produire 5 exercices ciblés sur cette lacune en 2 minutes. C'est là la valeur différenciante.

---

### D-CEO-15 — Migration génération PDF vers XeLaTeX *(nouveau 2026-06-11)*
**Décision :** Remplacer ReportLab par **XeLaTeX + Jinja2** pour la génération des rapports PDF.

**Contexte :** ReportLab impose un layouting manuel (coordonnées pixel par pixel) qui rendait les rapports structurellement rigides et visuellement basiques. Les formules mathématiques et tableaux étaient difficiles à rendre proprement.

**Architecture mise en place :**
- `src/pipeline/pdf_report_latex.py` — rapport de correction (note, commentaires, diagnostic, compétences)
- `src/pipeline/pdf_remediation_latex.py` — sujet de remédiation élève
- `templates/` — templates Jinja2 `.tex` avec commandes LaTeX custom (`\skillbadge`, etc.)
- Fonction `_le()` — escape automatique des caractères spéciaux LaTeX dans les données élèves
- **Fallback automatique ReportLab** si `xelatex` n'est pas installé sur la machine

**Avantages :**
- Rendu typographique professionnel (formules mathématiques natives, tableaux, mise en page)
- Facilité de modification du template sans toucher au code Python
- Compatible avec le positionnement premium de l'outil auprès des parents

**Fichiers supprimés :**
- `src/pipeline/pdf_report.py` (ReportLab)
- `src/pipeline/image_quality.py` (contrôle qualité image standalone — logique intégrée dans l'ingestion)

**Prérequis :** TeX Live ou MiKTeX installé sur la machine de l'enseignant (optionnel — le fallback ReportLab garantit que le pipeline ne bloque pas si xelatex est absent).

---

### D-CEO-18 — Portail de consultation Neon Postgres *(nouveau 2026-07-09)*
**Décision :** Ajout d'une couche de persistance PostgreSQL (Neon) — tables `centre`, `eleve`, `copie`, `document`, `utilisateur` (rôles admin / responsable_centre / enseignant) — et d'un portail de consultation Streamlit (login + historique élève + recherche par rôle).

**Statut : scaffolding uniquement.** Ce qui existe : modèles SQLAlchemy (`src/db/models.py`), connexion + migrations Alembic (`migrations/`), services CRUD (`src/services/`), pages Streamlit protégées par login (`src/ui/pages/`), intégrées nativement dans l'app existante (`src/ui/app.py` reste inchangé — Streamlit détecte `src/ui/pages/` automatiquement).

**Ce qui n'est PAS encore fait (dette explicite) :**
- Le pipeline de correction (`src/pipeline/pipeline.py`) n'écrit **rien** dans ces tables — aucune copie n'est persistée automatiquement après une correction. Câblage différé à une tâche ultérieure.
- Aucun compte admin n'est pré-créé — la table `utilisateur` est vide après migration ; le premier compte doit être inséré manuellement via `create_utilisateur()`.
- Les fichiers (scans, rapports, remédiations) sont stockés en `BYTEA` directement en base (v1) — connu comme un anti-pattern à moyen terme (stockage objet à envisager si le volume grossit), accepté pour le prototype.

**Tension avec D004** ("Stockage local pour prototype") : D004 concernait le pipeline de correction (JSON/PDF en local, `runs/`), qui reste inchangé. D-CEO-18 ouvre une persistance cloud parallèle pour un besoin différent (consultation multi-centres/multi-rôles), sans remplacer D004 tant que le câblage pipeline n'est pas fait.

**Sécurité :** mots de passe hashés en PBKDF2-HMAC-SHA256 salé (stdlib, 600k itérations) — pas de dépendance externe ajoutée. La connection string Neon vit uniquement dans `.env` (jamais dans un fichier versionné).

---

### D-CEO-19 — Câblage du pipeline sur la persistance Neon *(nouveau 2026-07-15)*
**Décision :** Acte les évolutions réelles depuis D-CEO-18 — celui-ci reste tel quel comme enregistrement daté de l'état du 2026-07-09 ; les points ci-dessous en sont la suite, pas une réécriture.

**Navigation :** `src/ui/pages/` (pages Streamlit multi-fichiers protégées par login) abandonné. `src/ui/app.py` porte désormais toute la navigation via un menu interne (radio dans la sidebar, branchement par variable `page`). `src/ui/auth.py` (`require_login`, `render_logout_button`), écrit pour l'ancien modèle par pages, n'était plus importé nulle part — supprimé.

**Pipeline branché sur la base (dette D-CEO-18 comblée) :** `src/pipeline/pipeline.py` écrit désormais en base à 5 points d'injection, tous best-effort (n'échouent jamais le pipeline, journalisés `[DB OK]` / `[DB WARNING]`) :
1. Réception de la copie — création Élève + Copie (placeholder) + document `scan`
2. Rapport de correction généré — document `rapport`
3. Sujet de remédiation généré — document `remediation`
4. Note finale — écrite en provisoire (4a, avant validation enseignant) puis en définitive (4b, après validation, écrase 4a)
5. Classe réelle — extraite de l'en-tête transcrit (`EVALUATION {classe}`, `src/core/classe_normalizer.py`) et écrasant le placeholder posé au point 1 ; jamais devinée, laissée en placeholder si l'extraction échoue

**Rattrapage des copies déjà en base :** `backfill_classe.py` et `backfill_notes.py` (scripts ponctuels, non intégrés au pipeline) ont corrigé les copies écrites avant le câblage des points 4 et 5, à partir de `runs/<copy_id>/result.json` déjà sur disque — même logique d'extraction que le pipeline, aucune valeur devinée en cas d'échec.

**Comptes utilisateurs (dette D-CEO-18 comblée) :** `seed_users.py` (idempotent) crée admin + un responsable par centre + enseignants de test. `create_admin.py` (non idempotent, faisait doublon) supprimé.

**Robustesse Neon :** `pool_pre_ping=True` et `pool_recycle=300` ajoutés à `create_engine` (`src/db/database.py`). Neon (pooler PgBouncer) met la base en veille après inactivité ; les connexions gardées dans le pool SQLAlchemy devenaient mortes sans le savoir, provoquant des écritures silencieusement perdues. `pool_pre_ping` teste chaque connexion avant usage et la remplace si morte ; `pool_recycle` évite de garder des connexions que Neon aura de toute façon fermées. Le retry tenacity existant reste en complément pour les erreurs réseau transitoires.

**`annee_scolaire` :** abandonnée comme clé d'affichage de l'évolution d'un élève — l'onglet Comparaison est désormais strictement chronologique (tri sur `date_soumission`), motivé par le fonctionnement réel d'un centre d'appui (tests continus toute l'année, le découpage en années scolaires n'a pas de sens). La colonne reste en base et continue d'être alimentée par le pipeline (`datetime.now().year`) — elle peut resservir, seul son usage pour le regroupement/tri en UI a été retiré.

**Logs :** `TimedRotatingFileHandler` ajouté (`logs/`, rotation quotidienne à minuit, 30 jours conservés) en complément de la sortie console existante, pour que les avertissements d'écriture base (`[DB WARNING]`) survivent à la fermeture du terminal. `logs/` ajouté au `.gitignore` (données personnelles potentielles — noms d'élèves dans les messages de log).

---

### D-CEO-20 — Élèves et profs migrés vers Google Sheets, table ELEVE supprimée *(nouveau 2026-07-17)*
**Décision :** Les élèves et les profs ne vivent plus dans PostgreSQL mais dans deux Google Sheets distincts, contrôlés par un tiers (le docteur). PostgreSQL ne garde plus que ce qui concerne la correction elle-même : `identifiant_hakili` (texte, calculé depuis les Sheets), les documents (scan/rapport/remédiation) et les notes. Fondation de lecture posée d'abord (`src/integrations/google_sheets.py`, D-CEO-19 et suivants), câblage du pipeline et démolition de l'ancien modèle actés ici.

**Schéma :** table `eleve` supprimée. `copie.eleve_id` (UUID, FK vers `eleve.id`) remplacé par `copie.identifiant_hakili` (texte). Migration `25898695d3c4` (« supprime table eleve, copie.eleve_id devient identifiant_hakili »). Corrigé au passage : le `downgrade()` de la migration initiale (`3eee6db8ae6e`) ne supprimait pas le type ENUM Postgres `userrole`, ce qui cassait la procédure `alembic downgrade base` puis `alembic upgrade head` (« type userrole already exists ») — ajout du drop du type ENUM dans son downgrade.

**Élève choisi explicitement, jamais deviné :** en mode Copie unique, l'enseignant sélectionne l'élève dans une liste déroulante alimentée par `get_eleves()` (nom, prénom, classe, centre — jamais `contact_parents`), affichée à gauche du choix de test. En mode batch, une sélection manuelle par fichier n'a pas de sens pour 30 copies d'un coup : le nom du fichier (convention déjà en place, nom+prénom de l'élève) est mis en correspondance avec le roster Sheets (comparaison repliée, insensible aux accents/casse) ; sans correspondance unique, cette copie précise est bloquée et journalisée, le reste du lot continue.

**Blocage avant tout appel IA :** `_db_persist_scan` (point d'injection 1) vérifie l'existence de l'élève via `get_eleve_by_identifiant` en tout premier — avant la construction des clients IA. Élève introuvable → exception, aucun appel IA, `[DB WARNING]` journalisé. C'est la seule étape non best-effort du pipeline ; l'écriture en base une fois l'élève confirmé reste best-effort comme les autres points d'injection.

**Décision classe — Sheet comme repli, extraction toujours souveraine :** `Copie.classe` continue d'être déterminée par l'extraction de l'en-tête transcrit (`EVALUATION {classe}`, inchangée depuis D-CEO-19) — pas par la colonne `classe` du Sheet. Motif : `Copie.classe` est un fait par copie (quelle classe au moment de CET examen), alors que la colonne du Sheet est le statut administratif COURANT de l'élève (peut changer en cours d'année — `reprend_la_classe`) ; l'utiliser comme source écraserait la variation historique dont dépend l'onglet Comparaison (détection de changement de classe entre deux copies). En revanche, la classe du Sheet sert désormais de **valeur initiale** au point d'injection 1 (remplace le placeholder générique "Non renseignée" par une vraie info déjà connue), toujours écrasée au point 5 si l'extraction donne un résultat fiable et différent.

**Suppressions (plus de source, plus de raison d'être) :**
- `src/services/eleve_service.py` — fichier entier supprimé : chaque fonction (`get_or_create_eleve`, `get_eleve_by_identifiant`, `get_eleves_by_centre*`, `update_eleve_date_naissance`, `preview_eleve_upsert`, `upsert_eleve_from_import`...) manipulait la table `eleve`. `get_historique_eleve` déplacée dans `copie_service.py`, adaptée pour filtrer par `identifiant_hakili`.
- Vues Admin « Ajouter élève », « Importer Excel », « Compléter profil élève » et la recherche/suppression d'élève — toutes du CRUD sur une table qui n'existe plus (créer/modifier un élève se fait désormais dans le Sheet, hors de cette application). L'onglet Admin ne garde que Statistiques.
- `backfill_classe.py`, `backfill_notes.py` — scripts de rattrapage ponctuels pour des copies écrites avant le câblage des points 4/5 (bug déjà résolu) ; la base étant vidée pour ce chantier, il n'y a plus de copie historique à rattraper.
- `create_admin.py` déjà supprimé en D-CEO-19 ; `init_centres.py` et `seed_users.py` conservés (Centre/Utilisateur inchangés, hors périmètre login).

**Suivi (Historique / Tableau des élèves / Comparaison) adapté a minima :** `get_accessible_eleves`/`can_access_eleve` (`user_service.py`) lisent désormais `get_eleves()` (Sheets) et filtrent par centre/classe de l'utilisateur au lieu de requêter `eleve`/`eleve_id` ; `afficher_historique` et `_render_comparaison_view` acceptent un dict Sheets au lieu d'un objet `Eleve`. Refonte visuelle de ces vues non traitée ici (prévue plus tard).

---

### D-CEO-21 — Login branché sur le Sheet profs, table UTILISATEUR supprimée *(nouveau 2026-07-17)*
**Décision :** Suite directe de D-CEO-20 côté profs — les comptes (admin, responsables, enseignants) ne vivent plus dans PostgreSQL mais dans le Sheet profs (email, nom, prénom, role, centre, classe), en lecture seule pour l'application. **Le Sheet fait foi pour le droit d'accès, à chaque connexion** : un email retiré du Sheet perd l'accès même s'il a toujours un mot de passe en base. Nom, rôle, centre, classe ne sont plus jamais écrits en base — uniquement en session, relus depuis le Sheet à chaque login.

**Stockage du mot de passe — table dédiée `credentials` (option retenue plutôt que réduire `utilisateur`) :** `email` (clé primaire) + `password_hash` + `date_creation`, aucune autre colonne. Retenu plutôt que de garder `utilisateur` amputée de ses colonnes d'identité : le nom `utilisateur` continue d'évoquer une identité complète, ce qui inviterait quelqu'un à y recoller un jour nom/rôle/centre par habitude et à recréer le second point de vérité qu'on cherche justement à éliminer. `credentials` nomme sans ambiguïté ce qui reste : un mot de passe attaché à un email, rien d'autre.

**Schéma :** tables `utilisateur` et `centre` supprimées, table `credentials` créée. Migration `d919411e7423`. Même piège ENUM Postgres que D-CEO-20 (`userrole` non nettoyé par un simple `drop_table`) — corrigé dans cette migration ; cycle complet `alembic downgrade base` → `alembic upgrade head` sur les 3 migrations retesté et validé.

**`centre` supprimée aussi :** vérifié qu'aucune table ne la référence plus après le retrait de `utilisateur.centre_id` (`Copie` n'a jamais référencé `Centre`). Les noms de centre vivent dans la colonne `centre` des Sheets (élèves et profs) — une table `Centre` séparée en base serait redevenue un second point de vérité. Décision prise après vérification explicite des dépendances, signalée ici en toute transparence : à objecter si une dépendance future y était prévue.

**`UserRole` (enum Python, `src/db/models.py`) :** n'est plus le type d'une colonne SQL — gardé comme enum de confort pour comparer proprement le profil choisi au login. Valeurs alignées sur le vocabulaire réel du Sheet (`administrateur`, `responsable`, `enseignant`) plutôt que sur les anciennes valeurs internes (`admin`, `responsable_centre`), pour éviter une table de correspondance supplémentaire qui pourrait diverger.

**`src/services/auth_service.py` (nouveau) :** `authentifier(db, profil_choisi, email, mot_de_passe=None)` — lit le Sheet d'abord (existence + rôle), ne regarde le mot de passe qu'ensuite ; retourne un statut explicite (`email_absent` / `role_mismatch` / `creation_requise` / `mot_de_passe_incorrect` / `ok`). `creer_mot_de_passe(...)` re-vérifie le Sheet avant d'écrire, jamais de création "à l'aveugle". `hash_password`/`_verify_hash` (PBKDF2-HMAC-SHA256, 600k itérations) déplacés depuis `user_service.py`, logique inchangée.

**Suppressions :** `create_utilisateur` (déjà retiré en D-CEO-19) ; `get_utilisateur_by_email`, `get_utilisateur_by_id`, `verify_password` (`user_service.py`) — leur table n'existe plus. `seed_users.py` et `init_centres.py` supprimés (créaient des lignes dans des tables qui n'existent plus) — mise à jour de ce qui était noté conservé en D-CEO-20.

**`get_accessible_eleves`/`can_access_eleve` adaptées :** prennent désormais un dict Sheet (avec un champ `role_enum` ajouté en session au login) au lieu d'un objet `Utilisateur` ; comparent `centre`/`classe` en texte directement (Sheet à Sheet), sans plus jamais résoudre via une table `Centre`.

**Vérifié en conditions réelles** (Sheet profs réel, `resp.tampouy@hakili.com`) : première connexion → création de mot de passe → reconnexion avec bon mot de passe → OK ; mauvais mot de passe → refusé ; bon email/mauvais profil choisi (enseignant Tampouy essayant "Responsable") → refusé ; email absent du Sheet → refusé ; email avec mot de passe en base mais absent du Sheet (simulé) → refusé, confirmant la règle « le Sheet fait foi ». `get_accessible_eleves`/`can_access_eleve` retestées avec le nouveau format de session : mêmes résultats qu'en D-CEO-20 (admin 12, responsable Tampouy 4, enseignant 3e Tampouy 2).

---

### D-CEO-22 — Liste de centres autorisée + détection des divergences Sheets *(nouveau 2026-07-17)*
**Décision :** Depuis la suppression de la table CENTRE (D-CEO-21), les noms de centre ne sont plus que du texte libre dans la colonne `centre` des deux Sheets (élèves, profs), potentiellement saisis par des personnes différentes — une faute de frappe dans l'un des deux casse silencieusement le lien de permission (comparaison texte à texte). On introduit une liste officielle et une vérification systématique à la lecture.

**Emplacement de la liste — nouveau module `src/core/centre_normalizer.py`, pas `config.py` :** le projet a déjà un précédent directement comparable pour ce genre de donnée (`CANONICAL_CLASSES` dans `src/core/classe_normalizer.py` — une petite liste canonique métier, pas un réglage d'environnement). `config.py`/`.env` sont réservés aux clés API, URLs et chemins qui varient par déploiement ; la liste des 4 centres Hakili Lab n'est pas de cette nature, elle est stable et partagée par tout le monde. Suivre le précédent déjà établi plutôt qu'ouvrir un second pattern pour un besoin identique. Ajouter un centre = modifier `CENTRES_AUTORISES` dans ce seul fichier, rien d'ailleurs à toucher.

**Normalisation anodine (`fold_centre`) :** minuscule, sans accents, espaces réduits — strictement l'esprit de `classe_normalizer._fold`, sans jamais toucher aux lettres elles-mêmes. `" tampouy "` / `"TAMPOUY"` → `"Tampouy"` (reconnu), mais `"Tampuy"` (vraie faute) reste `"Tampuy"` (non reconnu) puisque la lettre manquante change la forme repliée. Vérifié en conditions réelles avec `hashlib`-style tests directs sur les 5 cas (centre correct, variation espaces, variation casse, vraie faute, centre vide) : comportement exact dans les 5 cas.

**Comportement retenu pour un centre non reconnu — ligne conservée, pas rejetée :** `_verifier_et_normaliser_centre` (`google_sheets.py`) journalise `[SHEETS WARNING]` (ligne, Sheet, valeur brute, liste autorisée) mais garde la ligne avec le centre tel quel plutôt que de la jeter ou de deviner un centre. Motif : faire disparaître silencieusement un élève ou un prof à cause d'une faute de frappe serait pire que le problème lui-même — l'alerte suffit à signaler au docteur qu'il faut corriger le Sheet, sans perdre la ligne en attendant. Un centre vide (ex. l'admin, qui n'en a pas) n'est pas une alerte — cas légitime distinct d'un centre erroné.

**Centres reconnus normalisés en place, à la source :** une variation anodine reconnue est remplacée par sa forme canonique directement dans le dict retourné par `get_eleves()`/`get_profs()` — tout le reste du code voit ensuite des valeurs déjà propres, sans repasser par une normalisation à chaque comparaison.

**Cohérence lecture ↔ permissions :** `get_accessible_eleves`/`can_access_eleve` (`user_service.py`) comparent désormais via `centres_correspondent()` (même module), pas une égalité texte nue — défense en profondeur : même si la centralisation à la lecture suffirait en théorie, la comparaison elle-même tolère aussi casse/accents/espaces sans jamais faire correspondre deux fautes différentes entre elles (repli sur égalité texte stricte si l'un des deux centres n'est pas reconnu).

**UI — Statistiques (Admin) :** avertissement `st.warning` si un centre non reconnu apparaît dans les données chargées (« Attention : centre(s) non reconnu(s)... »), en plus des logs — ne passe pas inaperçu même sans consulter les logs.

**Vérifié en conditions réelles** (Sheets fictifs réels) : les 4 centres actuels (Siao, Saaba, Nagrin, Tampouy) chargent sans aucune alerte, forme canonique confirmée des deux côtés (élèves et profs). `get_accessible_eleves`/`can_access_eleve` retestées avec un centre de session délibérément sale (`" TAMPOUY "`) : toujours 4/2 élèves accessibles comme attendu, `can_access_eleve` toujours `True` malgré la casse — et toujours `False` pour un responsable d'un autre centre (Siao face à un élève de Tampouy). Test direct de `_verifier_et_normaliser_centre` sur les 5 cas (correct / espaces / casse / vraie faute / vide) : résultat exact dans chaque cas, alerte journalisée uniquement pour la vraie faute.

---

### D-CEO-23 — Vue de suivi Responsable avec code couleur de tendance *(nouveau 2026-07-18)*
**Décision :** Un responsable de centre voit désormais ses élèves (déjà filtrés par centre via `get_accessible_eleves`) avec une pastille reflétant leur PROGRESSION dans le temps, pas une photo figée de la dernière note — comparaison des deux dernières copies notées.

**Règle de tendance :** écart entre les deux dernières notes (copies avec `notes_finales` non NULL, triées par `date_soumission`) : `>= +1` progresse (vert), entre -1 et +1 exclu stagne (orange), `<= -1` régresse (rouge). Moins de 2 copies notées → « insuffisant » (gris, « pas assez de données ») — l'élève reste affiché, jamais caché.

**Seuil configurable — nouveau module `src/core/tendance.py`, pas `config.py` :** même raisonnement qu'en D-CEO-22 pour `CENTRES_AUTORISES` — le projet a déjà deux précédents directs (`CANONICAL_CLASSES` dans `classe_normalizer.py`, `CENTRES_AUTORISES` dans `centre_normalizer.py`) pour une constante métier stable, éditable à un seul endroit, sans dépendre de l'environnement de déploiement. `SEUIL_TENDANCE = 1.0` vit dans ce module, à côté de la fonction pure `calculer_tendance()` qui l'utilise — cohérent avec le fait que `config.py` contient déjà `confidence_review_threshold` pour un besoin différent (réglage pipeline IA, pas règle d'affichage figée) ; les deux emplacements coexistent pour des raisons différentes, choix assumé et documenté ici plutôt que tranché en silence.

**Performance — chargement groupé, pas une requête par élève :** `get_copies_pour_identifiants(db, identifiants)` (`copie_service.py`) charge en une seule requête (`WHERE identifiant_hakili IN (...)`) les copies de tous les élèves du centre, puis regroupe en mémoire. Une requête par élève aurait fait N requêtes pour un centre à N élèves — inutile alors qu'une seule requête groupée suffit.

**Portée :** seule la vue Responsable change (`_render_tableau_responsable`, appelée dans "Tableau des élèves" uniquement si `role_enum == responsable_centre`). Admin et enseignant gardent exactement le tableau existant, inchangé — le rôle enseignant aura sa propre vue dédiée dans un chantier séparé (tableau-profil).

**Mise en avant des élèves en baisse :** tri (régresse d'abord, puis stagne, progresse, insuffisant) + compteur visible en haut (« N élève(s) en baisse »).

**Vérifié :** 10 tests unitaires sur `calculer_tendance` (`tests/test_tendance.py`) — progression nette, régression, stagnation, une seule copie, zéro copie, note NULL ignorée (y compris au milieu d'un historique plus long), bornes exactes du seuil, ordre d'entrée indifférent au tri : 10/10 passent. Vérification de bout en bout avec de vraies données Tampouy (4 élèves réels, copies de test créées puis supprimées) : KABRE Charles Eliel 10→13 progresse, KANAZOE Abdoul Hafiz 14→11 régresse, KANAZOE Rachidatou 12→12.5 stagne, ZONGO Ibrahim 0 copie → insuffisant mais bien présent dans la liste ; tri et compteur (« 1 élève en baisse ») corrects ; `contact_parents` jamais lu dans le chemin d'affichage.

---

### D-CEO-24 — Vue Enseignant : tableau-profil individuel d'un élève *(nouveau 2026-07-18)*
**Décision :** Complète D-CEO-23 côté enseignant — vue individuelle (un élève choisi dans une liste déroulante restreinte à son centre+classe) plutôt que la vue d'ensemble du responsable. `_render_profil_enseignant` branché dans "Tableau des élèves" (`sub_tab2`) uniquement si `role_enum == enseignant` ; admin et responsable gardent leur rendu exact, inchangé.

**Réutilisation, pas de duplication :** `calculer_tendance()` et `_TENDANCE_STYLE`/`SEUIL_TENDANCE` (D-CEO-23) appelés tels quels — même pastille, même seuil, aucune deuxième implémentation. `_afficher_documents_copie` (téléchargement + aperçu, déjà utilisée par l'onglet Historique) réutilisée verbatim pour les documents de chaque copie — l'aperçu PDF passe par `_doc_pdf_pages_png` déjà en place, pas de nouveau moteur de rendu.

**Bug trouvé et corrigé en vérifiant PARTIE 4 (sécurité) :** `can_access_eleve` pour un enseignant vérifiait l'existence d'une `Copie` en base avec la bonne classe — critère différent de `get_accessible_eleves`, qui filtre sur la classe déclarée dans le Sheet. Un élève sans copie soumise (donc listé par `get_accessible_eleves` via son rôle Sheet, mais sans aucune `Copie` en base) se voyait refuser l'accès à son propre profil par `can_access_eleve` — bloquant la fonctionnalité pour tout élève n'ayant pas encore de copie. Corrigé : `can_access_eleve` compare désormais `eleve.get("classe") == user.get("classe")` (Sheet), exactement le même critère que `get_accessible_eleves`. Ancien critère hérité de l'ère pré-Sheets, où la classe n'existait que sur `Copie` (`Eleve` n'avait pas de champ classe) — devenu incohérent depuis que l'identité vient des Sheets.

**Chargement des copies — une seule requête par profil, pas de N+1 :** `get_historique_eleve(db, identifiant)` appelée une seule fois par sélection d'élève, réutilisée à la fois pour la tendance, le résumé chiffré et la liste chronologique. `get_copies_pour_identifiants` (chargement groupé multi-élèves, D-CEO-23) non nécessaire ici : la vue ne traite jamais qu'UN élève à la fois, contrairement à la vue responsable qui balaie tout un centre.

**Vérifié en conditions réelles** (Sheet Tampouy réel + copies de test) : enseignant 3e Tampouy voit exactement 2 élèves (KABRE Charles Eliel, ZONGO Ibrahim), pas les autres classes/centres. Test de permission forcé : élève de la bonne classe → accès autorisé ; élève de la même école mais mauvaise classe (KANAZOE Abdoul Hafiz, 4e) → refusé ; élève d'un autre centre (Siao) → refusé. Profil complet vérifié sur KABRE Charles Eliel (3 copies test, dont une non notée) : tendance "progresse" (9.0→12.5) cohérente avec le même calcul que la vue responsable, résumé chiffré correct (3 copies, dernière note retrouvée rétroactivement, date de la dernière copie distincte de la date de la dernière note notée), chronologie ascendante correcte, copie non notée affichée "Non notée" sans être masquée. Aperçu PDF testé sur un vrai document stocké en base (rendu PNG réussi via `_doc_pdf_pages_png`). `contact_parents` absent de tout le chemin d'affichage (vérifié par grep). Données de test supprimées après vérification.

---

### D-CEO-25 — Connexion nom+PIN, personnel unifié, centres dérivés des Sheets *(nouveau 2026-07-20, corrigé 2026-07-20)*
**Décision :** Remplacement complet de la connexion email + mot de passe par une sélection du nom (liste déroulante recherchable) + code PIN à 4 chiffres, les deux lus dans le Sheet personnel à chaque connexion. Table `credentials` supprimée de PostgreSQL (migration `f8928cd01df9`) — PostgreSQL ne porte plus aucune donnée d'authentification, tout vit dans les Sheets. Le PIN est stocké EN CLAIR dans le Sheet (choix assumé du docteur, Sheet réservé, aucun anti-forçage demandé).

**Rôle et clé de regroupement :** le rôle (enseignant/responsable/administrateur) vient désormais d'une colonne "role" du Sheet personnel, plus du fichier d'origine — l'administrateur est une ligne du Sheet comme les autres, avec un PIN. Regroupement des lignes (une par affectation) par **(nom, prénom)** repliés au lieu de l'email, devenu peu fiable (colonne optionnelle, vide chez la quasi-totalité des enseignants réels). Limite assumée : deux vrais homonymes (même nom ET prénom) fusionneraient à tort leurs affectations — cas jugé assez rare pour être accepté, à signaler si observé en pratique.

**`ADMIN_EMAILS` rendu dormant, pas supprimé :** la liste blanche mise en place au chantier précédent (D-CEO-21 et suivants) n'est plus lue par `auth_service.py` — l'admin s'authentifie désormais comme tout le monde via le Sheet. Le champ `settings.admin_emails`/`admin_emails_list` reste défini en config (documenté comme dormant) : RECOMMANDATION faite au docteur de le garder comme accès de secours si les Sheets deviennent injoignables (aucun autre chemin de connexion n'existerait alors), ou de le retirer s'il est jugé inutile — décision non tranchée en silence, signalée explicitement ici et dans le rapport de chantier.

**Centres dérivés dynamiquement, plus de liste figée :** `CENTRES_AUTORISES` retirée de `centre_normalizer.py`. `deriver_centres()` construit désormais la liste des centres réels à partir de TOUTES les valeurs "centre" vues dans les Sheets (élèves + personnel), regroupées par forme repliée (casse/accents/espaces) ; la graphie la plus fréquente devient la forme canonique. Un centre vu `SEUIL_CENTRE_SUSPECT` (= 1) fois ou moins est signalé "suspect" (alerte discrète côté admin + log `[SHEETS WARNING]`) sans jamais être bloqué ni corrigé — le docteur ajoute un centre en l'écrivant simplement dans un Sheet, aucune modification de code. `centres_correspondent()` simplifiée en conséquence : comparaison directe des formes repliées, sans dépendre d'une liste.

**Colonnes optionnelles :** `_resoudre_colonnes`/`_fetch_sheet_rows` acceptent désormais un paramètre `optionnelles` — une colonne logique absente du Sheet (pas seulement vide) ne lève plus d'erreur si elle est listée comme optionnelle (`classe`, `email` pour le personnel). `role` et `pin`, eux, restent **obligatoires** : tant que le docteur n'a pas ajouté ces deux colonnes au Sheet personnel réel, `get_personnel()` lève une `GoogleSheetsError` claire (colonnes manquantes nommées + en-têtes trouvés) plutôt que de charger un personnel sans rôle ni PIN exploitable — comportement voulu, cohérent avec le reste du module (jamais de dégradation silencieuse sur une donnée structurante).

**UI :** écran de connexion simplifié (plus de radio "Profil", plus de flux "créer mon mot de passe") ; nouveau composant réutilisable `_selectbox_recherchable` (recherche + selectbox) appliqué à la connexion, à la sélection d'élève (traitement unique, vue enseignant) — recherche insensible à la casse/aux accents ET à l'ORDRE des mots (`_correspond_recherche`, bug trouvé et corrigé en vérifiant : une recherche "Nom Prénom" ne retrouvait pas un élève affiché "Prénom Nom"). Placeholders sans tirets cadratin. Vue "Personnel par centre" (admin) réécrite sur les centres dérivés, affiche tout le personnel y compris sans PIN (mention "PIN manquant" discrète) et y compris administrateur/rôles non reconnus (jamais masqué). Tableau élèves (admin) : colonnes École/Boursier/Redoublant ajoutées, colonne "Identifiant" (identifiant_hakili) retirée — jamais affiché à l'écran. Recherche nom/prénom ajoutée côté responsable (tri par tendance et compteur de baisse inchangés). Paragraphe obsolète ("la gestion des élèves se fait dans les Sheets...") retiré de l'onglet Administration.

**CORRECTION (même jour) — un seul Sheet personnel, pas deux :** les fichiers enseignants et responsables ont été fusionnés par le docteur en un unique Google Sheet. `GOOGLE_SHEET_ENSEIGNANTS_ID` et `GOOGLE_SHEET_RESPONSABLES_ID` remplacées par une seule variable `GOOGLE_SHEET_PERSONNEL_ID` (`config.py`, `.env.example`). `_load_personnel()`/`_centres_bruts_toutes_sources()` lisent désormais ce Sheet unique ; toute la logique de fusion/dédoublonnage entre deux Sheets (`_personnel_sheet_ids()`) a été retirée, devenue inutile. Le rôle continue de venir de la colonne "role" de chaque ligne, inchangé. **Le docteur doit mettre à jour son `.env` local** pour remplacer les deux anciennes variables par `GOOGLE_SHEET_PERSONNEL_ID=<identifiant du Sheet fusionné>` — sans cela, l'application ne démarre plus (Pydantic rejette les variables d'environnement inconnues).

**Vérifié :** 10 tests dans `tests/test_google_sheets.py` (regroupement nom+prénom multi-affectation, rôle depuis la colonne, personne sans PIN comptée mais chargée, colonnes optionnelles absentes sans crash, dérivation de centres avec convergence anodine + détection de centre suspect, et désormais un test dédié confirmant qu'enseignant/responsable/administrateur se chargent et se connectent tous les trois depuis le MÊME identifiant de Sheet) — 10/10 passent. Contre les vrais Sheets : élèves inchangés (84 chargés) ; personnel lève l'erreur claire attendue tant que les colonnes Role/PIN n'existent pas encore côté réel (le docteur doit les ajouter — c'est l'objet même de ce chantier). Scénarios simulés avec données réalistes : connexion PIN correct/incorrect, enseignant "Tle" voit TleD et TleC de son centre sans voir un autre centre, Pissy apparaît dans les centres dérivés via son seul enseignant (aucun élève), recherche responsable insensible à l'ordre des mots confirmée avec un vrai nom (SANOU Feryel, centre SIAO réel), aucune fuite de `identifiant_hakili`/`contact_parents` à l'écran, enseignant/responsable/admin authentifiés depuis un Sheet personnel unique simulé. App bootée en headless sur toutes les pages : aucun crash.

---

### D-CEO-26 — Anciens tests archivés, barème stocké sur 20 *(nouveau 2026-07-30)*
**Décision :** premiers arbitrages du chantier v2 (référentiel `Referentiel_Socle_v0.xlsx`, nouveaux sujets à cadres ancrés). Analyse complète : [docs/harmonisation_donnees.md](harmonisation_donnees.md) ; avancement : [docs/v2_roadmap.md](v2_roadmap.md).

**Contexte :** l'investigation d'harmonisation a établi que les 7 nouveaux sujets PDF et le classeur sont parfaitement alignés (280/280 codes de question identiques, intitulés correspondant mot à mot), tandis que les 6 tests existants ne partagent **aucun identifiant** avec le référentiel : codes de question différents (`Q_NUM_01` vs `N1`), compétences en texte libre au lieu des 101 codes canoniques, ancrage par `chunk_ids` disjoint, nombre de questions variable (26 à 54) contre 40 systématiques. Les sujets ayant été refaits, ces 6 tests n'ont plus de sujet correspondant.

**Anciens tests archivés (arbitrage A → A1) :** champ `archive: True` sur les 6 entrées de `_TEST_CATALOG` (`src/knowledge/test_registry.py`), nouveau champ `HakiliTest.archive`. `available_tests()` (menu de sélection UI) les masque ; `all_tests()` ajouté pour l'historique.

**Archivage et non suppression — motif :** `get_test()` doit continuer à résoudre les tests archivés. `_apply_extracted_classe` (`pipeline.py`) s'en sert pour lire les niveaux déclarés d'un test lors de la détermination de la classe d'une copie. Retirer les entrées du catalogue aurait dégradé silencieusement la relecture des copies déjà corrigées — même classe de piège que les `chunk_ids` cassés journalisés en `debug` (§5.4 du document d'harmonisation). Vérifié après changement : `get_test('hakili_3e_v1')` résout toujours, niveaux intacts.

**Les 4 défauts actifs des anciens barèmes ne sont pas corrigés, délibérément** — bug de notation (copie parfaite à 20,5/20 au test 3e v1, 18,5/20 au 3e v2, 19,5/20 au tle), `meta.total_questions` faux dans 4 fichiers sur 6, `score_max` ignoré par le loader dans `bareme_test_3e.yaml`, 16 `chunk_ids` cassés + 69/121 chunks orphelins. Réparer un système sortant n'a pas de valeur ; ils sont documentés comme dette assumée. **Exception : la classe de bug de notation est corrigée dans le code** (voir ci-dessous), car elle frapperait identiquement les nouveaux tests.

**Conséquence visible assumée :** tant que les 7 nouveaux tests ne sont pas intégrés, l'interface ne propose plus aucun test Hakili — seul « Test personnalisé » reste. Comportement attendu de A1.

**Barème stocké sur 20 (arbitrage D) :** l'échelle imprimée sur le sujet fait foi. Le classeur note sur 60 (30 questions × 1 pt en partie A, 10 exercices × 3 pts en partie B) ; la conversion `bareme_classeur / 3` est faite **à l'import**. Les poids relatifs sont identiques dans les deux échelles — un exercice de partie B vaut 3 questions de partie A —, il ne s'agit que d'une unité.

**Règle de calcul du score, conséquence directe de D :** une question de partie A vaut 1/3 de point, non représentable exactement en décimal (30 × 0,3333 = 9,999). **La note doit donc toujours se calculer contre la somme réelle des `max_score`, jamais contre un total déclaré en métadonnée.** Avec cette règle, une copie parfaite vaut exactement 20,00 quelle que soit la précision de stockage. C'est aussi le correctif du bug de notation constaté : `CopyGrade.compute_final_score()` divise aujourd'hui par `total_possible` (valeur déclarée) au lieu de la somme réelle — le champ `rubric_actual_max`, déjà présent mais explicitement inutilisé, devient le dénominateur.

**Vérifié :** `available_tests()` vide, `all_tests()`/`ids` complets à 6, `get_test()` résout les archivés. Suite de tests : 102 passent (les 2 erreurs de collecte sur `test_google_sheets.py` et `test_ui_math.py` sont pré-existantes — absence de `.env` local, `ANTHROPIC_API_KEY` requise à l'import de `config.py`).

**Arbitrages encore ouverts** (§9 de `harmonisation_donnees.md`) : C — sort du curriculum RAG (121 chunks) ; E — volumes horaires du lycée absents, palier incalculable en 2ndeC/1ereD ; F — traitement du format `construction`. **B rendu le 2026-08-06** : 202/209 corrigés produits (brouillon calculé, relu et validé par l'utilisateur, pas encore par un enseignant de maths) — détail au journal de `docs/v2_roadmap.md`.

---

### D-CEO-27 — Les 7 tests v2 générés depuis le classeur *(nouveau 2026-07-30)*
**Décision :** les données des 7 nouveaux tests diagnostiques sont générées depuis `Referentiel_Socle_v0.xlsx`, et non extraites des sujets PDF. Suite directe de D-CEO-26.

**Motif — les énoncés ne sont pas extractibles des PDF :** les 7 sujets sont produits par WeasyPrint et **toutes les mathématiques y sont rendues en vectoriel** (211 tracés sur une page, aucun span de texte les portant). L'extraction ne rend que la prose : la question `N5` du test de 3ème donne « Recopier et compléter avec le symbole  ou le symbole  :  et  . » — nombres, formules et symboles disparus. Tous les modes d'extraction PyMuPDF ont été testés ; aucune source HTML ni script générateur n'existe sur le disque. **Nuance :** les codes de cadre, eux, s'extraient parfaitement — c'est tout ce dont le module 2 aura besoin, il lit le code et découpe la zone sans interpréter la page.

**Pourquoi l'absence d'énoncé n'est pas bloquante :** dans ce format, l'élève compose **sur le sujet**. La copie scannée porte donc l'énoncé imprimé, que l'IA transcrit avec la réponse. `subject_text` devient non critique — il aurait été bloquant dans l'ancien format à copie séparée.

**Livré :** `scripts/generer_baremes_socle.py` (idempotent, vérifié par hachage) produit `data/knowledge/bareme_socle_<niveau>.yaml` pour les 7 niveaux. Source : `04_Questions` (code, partie, format, barème, compétence, intitulé), `06_Distracteurs` (options QCM + bonne réponse), `02_Competences` (domaine). **280 questions, 71 QCM avec bonne réponse, 209 champs `reponse_attendue`/`solution` émis vides** — l'arbitrage B pourra être rendu sans migration corrective.

**Format YAML plat (`questions`) plutôt que l'ancien découpage :** les 7 domaines du référentiel (N, L, G, D, F, M, S, T) ne rentrent pas dans `questions_numeriques` / `questions_geometriques`. `_build_rubric_from_yaml` détecte désormais les deux formats — l'ancien reste lu pour les tests archivés, qui ne doivent pas cesser de se charger.

**`label` et `niveaux` non dupliqués dans le catalogue :** les entrées `socle_*` de `_TEST_CATALOG` les laissent vides ; ils sont lus dans le `meta` du barème (`titre`, `classe`). Écrire le titre à deux endroits aurait créé deux valeurs qui divergent — même raisonnement que pour les Sheets en D-CEO-20/21.

**Classe canonique unique par test, au lieu des niveaux évalués :** chaque test déclare `classe` = `6e`, `5e`, `4e`, `3e`, `2nde`, `1ere` ou `Tle`. Vérifié au passage que `normalize_classe` ne reconnaît **pas** `2ndeC`, `1ereD` ni `TleD` (retourne `None`) — d'où l'emploi des formes canoniques, sans quoi la classe n'aurait pas été écrite en base. Bénéfice sur les anciens tests, qui déclaraient les niveaux évalués (« 6e · 5e · 4e ») : `resolve_classe` disposait alors d'un garde-fou qui pouvait rejeter la classe réelle de l'élève ; il a maintenant un garde-fou exact et un repli fiable en cas d'échec d'extraction de l'en-tête (un seul niveau déclaré).

**Propriété centrale vérifiée :** une copie parfaite vaut **exactement 20,0/20 sur les 7 tests**, malgré les tiers de point de la partie A (somme réelle 19,99999, absorbée par l'arrondi au quart déjà en place). C'est la règle de D-CEO-26 mise à l'épreuve ; verrouillée par test de régression pour qu'une régénération ou un changement de barème ne la casse pas en silence.

**Vérifié :** `tests/test_baremes_socle.py` — 40 questions par test, structure 30 A + 10 B, barème /20 = classeur/3 question par question, classe reconnue par le normaliseur, codes uniques, QCM à bonne réponse unique, distracteurs tous tagués par un type de la liste fermée, 209 sans corrigé correspondant exactement aux non-QCM, copie parfaite = 20/20, copie nulle = 0/20, tests archivés masqués de la sélection mais toujours résolus avec leurs niveaux. **168 tests passent** (102 avant ce chantier).

**Limite cosmétique assumée :** les intitulés du classeur sont majoritairement en ASCII replié (254/280 sans accents : « Ecrire », « Frequence ») et apparaissent tels quels comme libellés de question dans l'interface. Sans effet sur la correction ni le diagnostic ; corrigeable plus tard sans changement de schéma. Si la source HTML des sujets est retrouvée, elle donnerait les énoncés exacts avec leurs formules — cela vaut d'être demandé, sans être bloquant.

**Régénération :** relancer `python scripts/generer_baremes_socle.py` après toute mise à jour du classeur — mais **sauvegarder d'abord les corrigés saisis à la main**, la régénération écrase `reponse_attendue` et `solution`.

---

### D-CEO-28 — Sortie de Streamlit vers Django, socle de données posé *(nouveau 2026-07-30)*
**Décision :** l'interface passe de Streamlit à **Django + HTMX** en rendu serveur, hébergée sur Railway ou Render, base **Neon inchangée**. Analyse complète : [docs/architecture_cible.md](architecture_cible.md).

**Contraintes tranchées :** pas de fonctionnement hors ligne, pas de PWA, données restant sur Neon. Ces trois réponses lèvent la seule réserve qui pesait sur le choix : sans besoin hors ligne, aucune API séparée n'est nécessaire et Django REST Framework devient inutile.

**Motifs, mesurés et non génériques :** `src/ui/app.py` fait 2 876 lignes (26 % du projet, 342 appels `st.*`, 71 usages de `session_state`, 30 blocs HTML concaténés) mais **70 % du code est déjà indépendant du framework** — pipeline, 5 clients IA, RAG, PDF et Sheets migrent intacts. Deux besoins que Streamlit ne peut pas porter : (1) une **authentification réelle** — le PIN à 4 chiffres vit en clair dans un Google Sheet, sans jeton de session ni autorisation par requête, alors que le dispositif conserve des données scolaires nominatives d'élèves mineurs sur sept mois (point ouvert #4, CIL Burkina Faso) ; (2) le **mobile**, exigence explicite du module 8 (« une fiche qui exige un ordinateur ne sera pas remplie »). L'`admin` Django couvre par ailleurs une part importante des écrans à construire sur 11 tables relationnelles.

**Moment choisi délibérément :** avant le module 1. Les 11 tables n'étaient pas écrites — écrire des modèles SQLAlchemy et une migration Alembic pour les réécrire ensuite aurait été du travail jeté.

**Module 1 livré dans la cible :** projet `hakili/` + apps `referentiel` et `suivi`, 11 tables migrées (cycle descente/remontée testé), `manage.py importer_referentiel` idempotent chargeant 7 types d'erreur, 101 compétences, 136 prérequis, 444 coûts, 280 questions, 1031 signatures et 284 options — chiffres identiques au module 0. Contrôle d'intégrité avant toute écriture : un code inconnu fait échouer l'import avec un message précis plutôt que d'écrire à moitié. `src/` n'a pas été touché et Streamlit continue de tourner.

**`Transition` protégée par le code :** `Probleme.changer_etat()` refuse un enchaînement non prévu par le graphe d'états, écrit la transition dans la même opération atomique, et `Transition.save()` refuse toute modification après création. L'admin met `etat` en lecture seule pour qu'on ne puisse pas contourner la méthode. Sans cela, un état modifié sans transition rendrait les 5 indicateurs du module 9 faux en silence.

**Les settings Django ne lisent pas `src/core/config.py`** — `Settings()` exige `anthropic_api_key` sans valeur par défaut, ce qui ferait échouer `manage.py migrate` sur une machine sans clé LLM, alors qu'une migration n'appelle aucun modèle. Les deux configurations coexistent pour des besoins différents.

**`Evaluation.copy_id` est un champ texte, pas une clé étrangère.** Tenté d'abord en FK vers une `Copie` déclarée `managed = False` : les tests ont révélé que Django ne crée pas les tables non gérées en base de test, donc toute insertion d'évaluation échouait, et le contournement habituel (lanceur flexant `managed`) ne fonctionne pas non plus puisque les migrations figent `managed: False`. Le lien souple est de toute façon le bon choix : c'est le précédent de `identifiant_hakili` (D-CEO-20) — quand la donnée référencée est hors du territoire de Django, on garde un identifiant et on documente le lien. Deviendra une vraie clé étrangère quand `copie` passera sous Django, à la fin de la migration.

**Réglages Neon repris de D-CEO-19 :** `CONN_HEALTH_CHECKS` (équivalent de `pool_pre_ping`) et `CONN_MAX_AGE=300` (équivalent de `pool_recycle`). Neon met la base en veille et les connexions gardées ouvertes meurent sans prévenir — c'est ce qui provoquait des écritures silencieusement perdues avant D-CEO-19.

**Sécurité posée d'emblée :** `DJANGO_SECRET_KEY` obligatoire hors DEBUG (échec au démarrage plutôt qu'une clé de repli qui rendrait les sessions falsifiables), `SECURE_SSL_REDIRECT`, cookies de session et CSRF sécurisés, HSTS un an, en-tête proxy Railway/Render. Indispensable dès que l'application quitte le poste local avec des données nominatives de mineurs.

**Support SQLite ajouté** à `DATABASE_URL` pour que les tests et l'intégration continue tournent sans base Postgres ; la production reste sur Neon.

**Vérifié :** 15 tests Django dont **le parcours complet T0→T5 d'un élève fictif avec toutes ses transitions enregistrées** — le critère de fin du module 1 tel qu'écrit dans `guide-v2.md`. Plus : transitions interdites refusées, états terminaux bloqués, `ATT` ne pouvant jamais être confirmé (l'inattention existe pour être écartée), atomicité de `changer_etat`, unicité d'un problème par session, immuabilité des transitions, calcul du taux de confirmation. En base, L5 du test de 3ème redonne exactement la réponse du module 0 : `L.IDR × CPT`, 0,50 h, bonne réponse `d`. **Les 172 tests pytest existants passent toujours** — aucune régression sur Streamlit.

**Reste à faire :** migrer les écrans Streamlit (connexion, tableaux de bord, correction) puis retirer Streamlit ; remplacer la connexion nom + PIN par l'authentification Django (les rôles deviendront des groupes).

---

### D-CEO-29 — Volume horaire de repli pour le lycée : 4 h *(nouveau 2026-07-30)*
**Décision :** les 27 compétences de lycée sans volume horaire officiel reçoivent un volume de repli de **4 heures**, permettant enfin de calculer leur coût de remédiation et donc le palier d'un élève de 2nde ou de 1ère.

**Contexte :** les documents officiels du secondaire ne donnent qu'une progression mensuelle, sans volume par chapitre (point ouvert #2). Sans volume, `coût = volume × coefficient` n'est pas calculable, aucune ligne n'existe dans `08_Cout_remediation`, et le palier A/B/C reste indéterminable — le dispositif ne peut tout simplement pas tourner sur ces niveaux.

**Pourquoi 4 h et pas 20 h.** La consigne initiale était « sur la base de 20 h ». Le calcul, fait avant application, a montré que cette valeur rendait le dispositif **dégénéré** : avec le plafond de 4 h par problème (protocole §4), `PRQ` (20 × 0,50 = 10 h), `CPT` (7 h) et `MOD` (5 h) tombaient **tous les trois à 4 h**. Le type d'erreur n'aurait plus eu aucun effet sur le coût, donc sur le palier, sur l'ensemble du lycée — et deux problèmes confirmés auraient suffi à basculer en palier B, cinq en palier C. Toute la finesse du diagnostic aurait été perdue là où elle sert le plus.

**4 h est la médiane des 74 volumes réels du collège** (moyenne 5,3 h, étendue 1,5 à 20,5 h). Elle donne six coûts distincts — PRQ 2 h, CPT 1,5 h, MOD 1 h, PRC/RED/CNS 0,5 h — et des paliers qui gardent leur sens : 2 problèmes PRQ → 4 h (palier A), 5 → 10 h (B), 11 → 22 h (C).

**C'est une estimation, et elle est marquée comme telle.** `Competence.volume_estime` et `CoutRemediation.estime` distinguent un chiffre dérivé du curriculum d'une valeur de repli ; l'admin les affiche en orange avec la mention « estimé ». Le classeur source, lui, continue d'indiquer « non disponible » — on ne réécrit pas la source avec une valeur inventée. Le remplacement sera trivial le jour où les vrais volumes seront connus.

**Effet :** `CoutRemediation` passe de 444 à **606 lignes** (101 compétences × 6 types remédiables). `ATT` n'y figure toujours pas — non remédiable, coefficient 0 : le module 6 doit traiter son absence comme un coût nul, pas comme une anomalie.

**Formule isolée dans `referentiel/couts.py`** — arrondi à la demi-heure, plancher 0,5 h, plafond 4 h — avec le motif du choix en docstring, plutôt que dispersée dans l'import.

**Vérifié :** 10 tests dédiés, dont un **test de garde** qui documente pourquoi 20 h a été écarté : il échouera si quelqu'un relève `VOLUME_REPLI_LYCEE` sans mesurer l'effet du plafond. Import réel rejoué : 444 officiels + 162 estimés = 606, six valeurs distinctes, zéro compétence de 2nde C sans coût. 97 tests Django + 218 pytest passent.

---

### D-CEO-30 — Ancrage du diagnostic reconstruit sur le référentiel *(nouveau 2026-07-30)*
**Décision :** le contexte programme injecté au diagnostic est désormais construit depuis le **référentiel** (compétences, prérequis, signatures d'erreur), et non plus depuis les `chunk_ids` du curriculum.

**Défaut découvert, et il était silencieux.** Le nettoyage des fichiers obsolètes a révélé que l'ancrage passait par le champ `chunk_ids` des anciens barèmes. Les barèmes générés depuis le classeur (D-CEO-27) n'ont pas ce champ — le classeur ne le fournit pas. Mesuré : `socle_3eme` recevait **0 caractère** de contexte programme, là où `hakili_3e_v1` en recevait 2 048. Le pipeline n'échouait pas ; il produisait un diagnostic générique, c'est-à-dire précisément ce que D-CEO-12 qualifie d'inutilisable (« un diagnostic qui dit *lacune en algèbre* est inutilisable »). Personne ne l'aurait vu avant une correction réelle.

**Pourquoi le référentiel plutôt que d'attendre l'arbitrage C.** Le rapprochement leçon ↔ compétence n'est pas validé, mais il n'est pas nécessaire : le référentiel porte déjà tout ce qu'il faut, et de façon vérifiée (module 0, zéro violation d'intégrité) — `Question.competence` (lien fiable et complet), `Prerequis` (la chaîne remontante, exactement ce que le protocole demande : « remonter d'un échec vers la lacune ancienne qui l'explique »), et `SignatureErreur` (1 031 signatures **par question**).

**Le nouveau contexte est meilleur que l'ancien**, pas seulement fonctionnel : les signatures sont propres à la question posée, là où un chunk de curriculum décrivait une leçon entière. Le modèle n'a plus à deviner, il reconnaît — ce que le guide demande pour le module 4. Mesuré sur données réelles : 3 490 caractères et 3 lacunes pour trois questions de 3ème.

**La frontière `src/` reste étanche.** Le référentiel vit dans une application Django ; `src/pipeline/` ne doit dépendre d'aucun framework, sous peine de ne plus pouvoir servir les deux interfaces. `run_phase_b` reçoit donc un paramètre `ancrage` — une fonction fournie par l'appelant — au lieu d'importer les modèles. Vérifié : aucun import Django dans `src/`.

**Chemin historique conservé.** Sans `ancrage`, le pipeline retombe sur les `chunk_ids` : c'est ce qui sert au mode libre et aux anciens tests. Et un diagnostic qui se retrouve sans aucun ancrage est désormais **journalisé en avertissement** au lieu de passer inaperçu — c'est ce silence qui avait laissé le défaut vivre.

**Le curriculum n'est pas abandonné :** une fois l'arbitrage C validé, son contenu rédigé (savoir-faire, erreurs fréquentes) enrichira ce contexte. Il s'ajoutera, il ne remplacera pas.

**Vérifié :** 15 tests dédiés — contexte non vide, compétence et code présents, chaîne de prérequis remontée sur deux niveaux, signatures de la question, consigne de ne jamais inventer de code, compatibilité avec `CompetencyGap` sans adaptation, mode libre et ancien test retombant proprement sur l'ancien chemin. 112 tests Django + 218 pytest passent.

---

### D-CEO-31 — Nettoyage des fichiers et bibliothèques obsolètes *(nouveau 2026-07-30)*
**Supprimés** (tous suivis par git, donc récupérables) : `AGENTS.md` et `docs/implementation_plan.md` (décrivaient un état antérieur à D-CEO-16, contredisaient la réalité) ; `data/schemas/` (6 schémas JSON sans aucune référence depuis que `jsonschema` n'est plus utilisé) ; `docs/generate_guide_maths_pdf.py` et le PDF qu'il produisait ; `emoji_check.txt`, `test_diagnostic_run.py`, une capture d'écran, `setup.ps1`.

**Bibliothèques retirées :** `jsonschema`, `opencv-python-headless` (le contrôle qualité image a été supprimé en D-CEO-15, plus aucun import de `cv2`), `httpx`.

**Faux positifs écartés — à ne pas retirer :** `alembic`, `gunicorn`, `whitenoise` et `psycopg2-binary` n'apparaissent dans aucun `import`, mais sont indispensables : chargés par nom (middleware, pilote de base) ou lancés en ligne de commande. Une analyse d'imports seule les aurait condamnés à tort.

**Conservés délibérément :** les 6 anciens barèmes et corrigés `*_test_*.yaml` — ils alimentent le seul ancrage encore fonctionnel pour le mode libre, et servent de référence le temps de rebrancher le RAG (D-CEO-30). `streamlit` et `pandas` restent jusqu'à l'essai réel de bout en bout.

**Correction d'une justification erronée de D-CEO-26 :** j'y écrivais qu'il fallait garder les tests archivés résolvables « pour les copies déjà corrigées ». C'est faux — `bareme_id` n'est jamais stocké dans la table `copie`, il ne circule qu'au moment de la correction. Les tests archivés sont donc inaccessibles et supprimables ; ils sont conservés pour la raison ci-dessus, pas pour celle-là.

---

### D-CEO-32 — Périmètre unique : centre d'encadrement, pas école *(nouveau 2026-07-30)*
**Décision :** toute personne autorisée accède à **tous les élèves** et peut corriger **n'importe quelle copie**. Le cloisonnement par centre et par classe est retiré.

**Motif — le modèle métier avait été mal compris.** Hakili Lab est un **centre d'encadrement**, pas une école : les enseignants n'ont pas « leurs » classes au sens scolaire. Ils tournent, se remplacent, reprennent les copies d'un collègue absent. Le filtrage par centre et classe (D-CEO-23, D-CEO-24) bloquait un travail parfaitement légitime sans rien protéger d'utile — une copie mal attribuée est empêchée par la **sélection explicite de l'élève** (D-CEO-20), pas par le périmètre.

**Où se joue désormais la sécurité :** en amont, à l'autorisation. Une personne présente dans le Sheet du personnel avec un code d'accès peut travailler ; retirée du Sheet, elle ne peut plus se connecter, immédiatement. C'est un contrôle binaire et lisible, là où le filtrage par classe donnait une illusion de finesse.

**Le rôle ne commande plus qu'une chose :** l'accès à l'administration (statistiques, référentiel, écran des accès). Il ne détermine plus quels élèves sont visibles.

**Conséquences :**
- `get_accessible_eleves` rend tous les élèves ; `can_access_eleve` est vrai pour toute personne autorisée. Les deux restent alignés — leur divergence avait déjà causé un bug (D-CEO-24).
- **Le sélecteur de casquette est retiré** : il ne servait qu'à basculer entre périmètres. Sans périmètres distincts, il n'aurait fait qu'induire en erreur.
- `casquette_par_defaut` privilégie désormais `administrateur` : cacher ses propres écrans à un administrateur n'aurait pas de sens.
- Les affectations (centre, classe) restent lues du Sheet, mais **à titre informatif**.

**Gestion des accès — le Sheet reste la source de vérité (voie A retenue).** L'administrateur *est* le docteur, qui contrôle déjà le Sheet : il ajoute une ligne, la personne se connecte ; il la retire, elle perd l'accès. **Aucun code n'a été écrit pour cela** — D-CEO-21 et D-CEO-25 sont confirmées, pas renversées. Gérer les comptes des deux côtés aurait recréé la seconde source de vérité que ce projet a démolie deux fois.

**Ce qui manquait, en revanche, c'était de *voir* l'état.** Nouvel écran `/personnel/`, réservé à l'administrateur et **en lecture seule** : qui peut se connecter, qui ne le peut pas. Personne n'y est masqué — surtout pas les cas en défaut : une personne sans code d'accès ou au rôle non reconnu figure dans le Sheet en croyant avoir accès, et c'est précisément ce que l'administrateur doit repérer. Les comptes en défaut sont affichés en premier. **Les codes d'accès ne sont jamais affichés**, bien qu'ils soient en clair dans le Sheet.

**Vérifié :** 130 tests Django + 218 pytest. Les tests qui encodaient l'ancien cloisonnement ont été réécrits pour affirmer le nouveau modèle, pas supprimés — un enseignant de Siao accède désormais à un élève de Tampouy, et c'est ce qui est testé.

---

### D-CEO-33 — Cycle de suivi : T2 retiré, évaluations répétables *(nouveau 2026-07-30)*
**Décision :** le cycle passe de six à cinq étapes, et un même type d'évaluation peut se répéter autant de fois que nécessaire.

**Le cycle réel, tel qu'il se pratique :**
1. **T0** — test de niveau → des lacunes probables sont détectées
2. **T1** — le système génère un sujet ciblé pour les confirmer ou les écarter
3. Fiche de remédiation avec volume horaire, puis inscription de l'élève au programme
4. Travail **hors plateforme**, avec le tuteur, selon la fiche
5. **T3** — à la fin du volume horaire, vérification que les lacunes sont corrigées
6. **T4** — 45 jours après, contrôle de rétention
7. **T5** — 3 mois après, dernier contrôle, puis clôture du cycle

**T2 (contrôle de mi-parcours) est retiré.** Le protocole le plaçait entre la remédiation et le test de sortie, mais le rendait déjà facultatif en palier A. Il ne correspond pas à la pratique du centre : on va de la fin du volume horaire directement à la vérification.

**Un même type peut désormais se répéter.** Tant que des lacunes ne sont pas corrigées, l'enseignant relance un test de vérification. La contrainte `UniqueConstraint(session, type)` l'interdisait — un second T3 était rejeté par la base. Elle est remplacée par `UniqueConstraint(session, type, numero)` : les évaluations d'un même type se distinguent par un **rang**, attribué automatiquement à la création. Le calculer côté modèle plutôt que de le laisser à l'appelant évite qu'un rang oublié fasse échouer l'insertion avec un message incompréhensible.

**Les indicateurs du module 9 ne sont pas cassés**, et c'est ce qui a permis ce changement sans dommage : ils comptent des **transitions** rattachées à une évaluation, pas « la » T1 ou « le » T3. Avec plusieurs T3, ils agrègent naturellement l'ensemble — un problème résolu au troisième passage compte comme résolu, ce qui est le comportement souhaité.

**Le cycle de vie des problèmes supportait déjà la boucle :** `non_resolu → en_remediation → resolu` était permis, autant de fois que nécessaire. Seule la contrainte sur les évaluations bloquait.

**Vérifié :** cycle réel simulé (T0, T1, trois T3 successifs, T4, T5) — les rangs s'attribuent seuls, les libellés signalent « 2e passage », « 3e passage ». 135 tests Django + 218 pytest passent. Les tables de suivi étant encore vides, la migration ne touche aucune donnée.

**Reste à trancher :** l'**inscription au programme de remédiation** (étape 3). C'est un état de session à part entière — aujourd'hui une session est `ouverte / close / abandonnée`, sans distinguer « diagnostiquée, en attente d'inscription » de « inscrite, en remédiation ». C'est probablement le moment où la facturation démarre, donc l'endroit à nommer précisément.

---

### D-CEO-34 — États de session et inscription au programme *(nouveau 2026-07-30)*
**Décision :** la session porte désormais l'avancement du cycle, et l'inscription au programme de remédiation devient une action explicite et tracée.

**Sept états au lieu de trois.** `ouverte / close / abandonnee` ne distinguait pas « diagnostiquée, en attente » de « inscrite, en remédiation » — or c'est le moment où le palier cesse d'être une estimation pour devenir un engagement, et vraisemblablement celui où la facturation démarre.

**Trois sorties sans remédiation, distinguées délibérément :**
- `sans_suite` — T1 n'a confirmé aucun problème. **C'est un bon résultat**, et le protocole insiste : « un outil qui n'oriente pas systématiquement vers de la remédiation payante est un outil crédible. » Le confondre avec un abandon transformerait une réussite en échec dans les comptes rendus d'un centre.
- `hors_dispositif` — palier C, orientation vers un accompagnement long. Une orientation, pas un renoncement.
- `abandonnee` — retrait de l'élève ou de la famille.

**`Session.inscrire()` — la décision humaine du cycle.** Bascule tous les problèmes confirmés en remédiation avec leur transition, enregistre `date_inscription`, et **refuse le palier C sans décision explicite**. Le passage outre reste possible mais exige un motif, conservé dans le commentaire des transitions : la décision est tracée, pas seulement prise. Inscrire sans aucun problème confirmé est refusé — il n'y aurait rien à remédier et la facturation serait sans objet.

**Un point de conception trouvé en testant :** `hors_dispositif` étant terminal, le contrôle générique « session terminée » masquait le message du palier C — alors que c'est précisément l'état où une dérogation se demande. L'état est désormais laissé passer jusqu'au garde-fou du palier, dont le message explique quoi faire. Et une inscription forcée depuis cet état lève la date de clôture : la session repart.

**Deux contraintes en base, pas des conventions :** une session non terminée ne peut pas porter de date de clôture (elle fausserait les indicateurs de durée), et l'état `remediation` exige une date d'inscription.

**Vérifié :** 15 tests dédiés, dont le refus du palier C, le passage outre avec motif tracé, le refus d'un motif vide, la double inscription, l'inscription sans problème confirmé, et les trois orientations après T1. Cycle réel simulé de bout en bout. 150 tests Django + 218 pytest passent.

---

### D-CEO-35 — Le gabarit des zones est lu dans le PDF du sujet *(2026-07-31)* ⛔ **CADUQUE (D-CEO-38, 2026-08-05)**
> Le module 2 est supprimé. Conservée pour mémoire : elle explique pourquoi l'OCR avait été écarté, argument qui reste valable si la question du découpage se rouvre un jour.

**Décision :** les sujets socle **conservent leurs cadres de réponse ancrés et leurs codes de question**. Le module 2 lit donc la position de chaque zone **dans le PDF du sujet**, au lieu de la détecter sur la copie scannée.

**Ce qui est écarté, et pourquoi.** `guide-v2.md` prescrit de détecter les rectangles sur le scan puis de lire au **OCR** le code de chaque cadre. C'était le premier point de panne de toute la chaîne : trois caractères à 150 DPI, imprimés à côté de l'écriture d'un élève. Une confusion `G1`/`G7` aurait attribué une réponse à la mauvaise question **sans que rien ne le signale** — pas d'erreur, pas d'alerte, un diagnostic faux. Le PDF du sujet porte déjà l'information exacte : 280/280 cadres retrouvés sur les 7 sujets, 0 manquant, 0 en trop, 0 doublon.

**Conséquence sur le format des sujets :** un sujet sans cadres ni codes ne peut pas être découpé en zones. Le format à cadres ancrés n'est plus une commodité de mise en page, c'est **une dépendance du diagnostic structuré**. Toute régénération des sujets doit les conserver.

**Ce qui a été rendu tolérant :** les règles de lecture sont exprimées en **plages de gris et en fractions de la largeur de page**, jamais en égalité aux valeurs relevées sur les sujets d'aujourd'hui (0,478431 ; 480 pt ; 8 lignes). Une régénération changera les marges et les teintes ; avec des valeurs exactes, la lecture du gabarit aurait échoué **totalement** — zéro cadre trouvé — et non partiellement.

**Confrontation au barème plutôt que confiance :** le format d'une question est déduit de la **géométrie** du cadre, jamais lu dans le barème, puis les deux sont comparés (`verifier_gabarit`). C'est ce qui détecte qu'un enseignant a scanné une autre version du sujet — avant que des réponses ne soient attribuées aux mauvaises questions.

**Vérifié :** 24 tests, dont 7 sur les vrais sujets (ignorés si les PDF sont absents, ils ne sont pas versionnés) et 2 qui verrouillent la tolérance aux teintes et au nombre de lignes.

---

### D-CEO-36 — Le recalage s'ancre sur le contenu, et rien n'est livré contre le tramage *(2026-08-01)* ⛔ **CADUQUE (D-CEO-38, 2026-08-05)**
> Le module 2 est supprimé. Son risque ouvert — le tramage d'impression — a été mesuré le 2026-08-05 et **n'existe pas** : l'imprimante ne rend pas les bandes de guidage du tout.

**Décision :** la page scannée est recalée sur les **cadres eux-mêmes**, jamais sur le rectangle de la page ; l'appariement page scannée ↔ page du sujet **n'est pas supposé 1:1** ; et **aucun mécanisme n'est livré contre le tramage d'impression** tant qu'il n'a pas été mesuré sur papier.

**Ancrage sur le contenu.** Un scanner ne rend pas la page du gabarit : hauteur variant de 835 à 851 pt d'une feuille à l'autre du même fichier, largeur 612 pt contre 595,3. Une mise à l'échelle sur les bords de page serait fausse de 2 à 3 %. Deux conséquences tirées en mesurant : l'estimation d'inclinaison se fait sur les **coordonnées** des pixels d'encre et jamais en faisant tourner l'image — une rotation ré-échantillonne, efface les traits fins (2 616 pixels d'encre à 0° contre moins de 600 ailleurs) et fait gagner l'angle 0 quelles que soient les données ; et l'échelle horizontale est cherchée **autour de la verticale**, parce que les cadres partagent tous les mêmes bords gauche et droit et que deux repères ne suffisent pas à fixer deux inconnues sans se laisser emporter par un trait de marge.

**Appariement des pages.** Le scan mesuré comptait **12 pages pour un sujet de 10** (page de garde, page de renseignements). Découpées dans l'ordre, toutes les zones auraient été prises sur la mauvaise page — et le résultat aurait eu l'air normal, chaque zone contenant bien de l'écriture. L'affectation retenue maximise le total des scores de recalage **en gardant l'ordre des pages**.

**Ce qui n'est pas livré, et pourquoi.** Le repli prévu contre le tramage laser — « effacer les lignes de guidage à leur position connue » — a été écrit, puis retiré : mesuré sur les 7 sujets, les « lignes » sont des bandes de 21 pt **jointives** qui pavent toute la zone de réponse. L'élève écrit sur un **aplat gris**, pas sur un lignage ; leur position est la zone entière, l'effacement l'effacerait entière. Le vrai problème est le retrait d'une **trame**, qui dépend de la finesse de la trame, de la résolution du scanner et de l'épaisseur du trait — trois grandeurs qu'aucun rendu numérique ne donne. Un mécanisme réglé à l'aveugle aurait été confiant et faux ; le risque reste ouvert, correctement décrit, et se tranche en imprimant un sujet et en le scannant **même vierge**.

**Vérifié :** 43 tests sur les zones, dont le recalage sur cinq déformations de numérisation, l'appariement avec deux pages intercalées, et un test paramétré sur les 7 sujets qui verrouille la géométrie réelle pour que la fausse piste ne soit pas re-suivie.

---

### D-CEO-37 — Identités factices en développement, sans deuxième source de vérité *(nouveau 2026-08-05)*
**Décision :** un jeu d'élèves et de personnel **inventés** (`src/integrations/sheets_factices.py`) peut remplacer la lecture des Google Sheets **en développement seulement**, branché au ras du réseau et verrouillé sur `DEBUG`.

**Le problème qu'il traite.** L'identité vit dans les Sheets du docteur et nulle part ailleurs (D-CEO-20/21/25). Sur une machine de développement, les identifiants de Sheet ne sont pas renseignés : `get_eleves()` et `get_personnel()` échouent, et **cinq écrans sur sept** affichent « momentanément indisponible ». Impossible d'y travailler la mise en page, impossible de se connecter, impossible de voir un parcours. Le travail sur l'interface se faisait donc à l'aveugle, ou en renseignant les vrais Sheets sur un poste de développement — ce qui est pire.

**Pourquoi ce n'est pas la deuxième source de vérité que ce projet a démolie deux fois.** Le défaut d'une deuxième source n'est pas qu'elle existe, c'est qu'elle **diverge en silence** de la première et finisse par être prise pour elle. Trois propriétés l'en empêchent ici :
1. **Rien n'est écrit** — des lignes en mémoire, aucune table, aucune migration, aucun fichier. Il n'y a rien qui puisse diverger.
2. **Inatteignable en production** — il faut `HAKILI_SHEETS_FACTICES` **et** `DEBUG`. Hors `DEBUG`, le réglage est ignoré et l'oubli journalisé bruyamment, comme `HAKILI_ACCES_LIBRE`. Servir des élèves inventés à un enseignant qui croit consulter sa classe serait **pire qu'un écran en panne** : l'écran en panne, on le signale ; des données plausibles mais fausses, on les recopie.
3. **Branché à la place de la lecture réseau, pas de la logique** — le point d'insertion est `_fetch_raw_rows`, et les lignes rendues portent les **en-têtes réels du Sheet** (`"Contact Parents"`, `"Prenom"`, `"Role"`…). Tout l'aval s'exécute pour de vrai : résolution tolérante des colonnes, construction de `identifiant_hakili`, normalisation des classes, dérivation des centres, vérification du PIN. Un écran qui marche sur ces données marche sur les vraies, et une régression dans cette chaîne se voit ici aussi.

**Le jeu couvre les cas limites, pas le cas nominal.** Les 7 niveaux ; un centre vu une seule fois (le cas « suspect » de `deriver_centres()`, signalé sans jamais être bloqué) ; deux frères et sœurs au même contact, qui vérifient que `build_identifiant_hakili` les distingue ; une personne affectée à **deux centres**, dont le Sheet réel porte deux lignes et que `_load_personnel` doit regrouper en un seul compte. Un jeu nominal n'aurait exercé aucun de ces chemins.

**Ce qui l'accompagne :** `manage.py donnees_demo` crée trois parcours de démonstration pour l'écran `/parcours/<jeton>/` — en attente d'inscription, en remédiation, et palier C, le seul cas où `inscrire()` refuse sans motif tracé (D-CEO-34). Les états sont atteints par `changer_etat()`, jamais en écrivant `etat`, pour que chaque `Transition` existe. La commande refuse de tourner hors `DEBUG` (ces sessions portent un palier, donc un devis) et **ne touche jamais aux cinq sessions `CORPUS-*`**, qui sont l'étalon du module 4.

**Ce que ça ne résout pas :** le fichier de clé JSON du compte de service reste nécessaire pour tout usage réel. Le jeu factice **masque** son absence en développement, il ne la remplace pas.

**Vérifié :** 11 tests, dont le refus hors `DEBUG` avec journalisation, et le fait qu'un Sheet inconnu rende `None` et non une liste vide — une liste vide afficherait « aucun élève » au lieu de la panne de configuration.

---

### D-CEO-38 — Le module 2 est supprimé ; le diagnostic se branche sur la correction *(nouveau 2026-08-05)*
**Décision :** la lecture des copies par zones (`src/pipeline/zones.py`, module 2) est **retirée du projet**. Le diagnostic contraint prend ses réponses dans la **correction déjà faite**, via `reponses_depuis_correction()`. **D-CEO-35 et D-CEO-36 sont caduques** — elles décrivaient la conception d'un module qui n'existe plus.

**Ce qui a déclenché la décision.** Trois copies réelles de 5ème, imprimées, composées et scannées (200 DPI), passées dans la chaîne le 2026-08-05 : **les trois sont refusées**, aucune n'est découpable. La mesure a désigné la cause exacte, et elle n'est pas réparable par un réglage. Dans le PDF, un bord de cadre est une rangée dont **100 % des pixels** sont à 121–156 ; après impression laser et numérisation, il ne subsiste qu'entre **243 et 248**, contre un papier à 251,6 — huit niveaux d'écart. `SEUIL_ENCRE_DEFAUT = 140` ne le voit jamais : le recalage s'accrochait au **texte imprimé** au lieu des cadres. Conséquence mesurée contre une vérité terrain obtenue par corrélation avec le sujet rendu : échelle fausse jusqu'à **−10 %**, soit **85 pt (3 cm) de dérive** en bas de page, et **4 pages sur 10 acceptées** (score 50 %) avec 20 à 35 pt de décalage. Vérifié à l'œil : une zone découpée attrapait l'énoncé imprimé et perdait le bas de la réponse ; sur une autre page les cadres tombaient **une question plus bas**, chacun contenant de l'écriture — donc sans que rien n'ait l'air anormal.

**Le tramage, lui, n'existe pas** — c'est le seul point où la mesure a rassuré, et elle l'a fait dans l'autre sens. À l'intérieur d'un cadre, le scan est uniformément blanc (moyenne 251,6, écart-type 1,1, **0,00 % de pixels sous 200**) là où le PDF porte des gris à 191–246. L'imprimante n'a pas tramé les bandes de guidage, elle ne les a pas imprimées. Le risque ouvert de D-CEO-36 se referme sans qu'une ligne soit écrite contre lui.

**Pourquoi remplacer plutôt que réparer.** Une correction était possible — chercher les repères juste sous le niveau du papier ramène 8 pages sur 10 à moins de 7 pt de dérive — mais elle échoue encore sur une page par copie, **en annonçant 100 % de confiance**, ce qui est le pire des cas. Surtout, elle n'attaque pas le fond : le module 2 fait dépendre le diagnostic de la **géométrie d'un objet physique** qu'on ne maîtrise pas. Impression sans réduction, scan droit, bon nombre de pages dans le bon ordre, cadres survivant au toner. En production de masse, aucune de ces conditions n'est tenable, et chacune est un refus de copie.

**Ce qui le remplace était déjà là.** La correction lit la copie **page entière** et rend, pour chaque question du barème, ce que l'élève a écrit (`observed_answer`) et si c'est juste. Or l'identifiant d'item du barème **est** le code de question du référentiel (`D1`, `L5`…), avec sa compétence et ses options QCM. La correspondance que le module 2 reconstituait par la géométrie existait donc déjà, produite par une étape en service, sans appel de modèle supplémentaire. Le code de la question est **imprimé dans son cadre, à côté de la réponse** : le lire est plus robuste que le déduire d'une géométrie subie.

**Ce qui est supprimé :** `src/pipeline/zones.py` (893 lignes), `tests/test_zones.py` (578), `_lire_zones` et `PipelineResult.zones`. Rien ne les consommait — le pipeline lui-même le disait : « personne ne consomme les zones ». `HakiliTest.formats` est **conservé** : le format d'une question décide de ce que le diagnostic peut en faire (un QCM se tranche sans modèle, une construction géométrique ne se diagnostique pas).

**Deux gains de justesse en chemin,** qui n'étaient pas l'objet mais qui comptent :
1. **La décision de l'enseignant prime** pour dire ce qui est réussi. Diagnostiquer une question que l'enseignant vient de valider produirait une lacune que personne ne constate.
2. **« Illisible » cesse d'être confondu avec « rien écrit ».** Le moteur annonçait « réponse illisible » parmi ses cas écartés sans avoir de quoi le distinguer. Une lecture ratée est un trou — la question part en écartée avec un motif qui dit à l'enseignant qu'il y a là une réponse à relire ; une zone vierge est un signal de diagnostic à part entière.

**Ce que ça change pour l'impression des sujets :** plus rien. Les cadres et les codes restent utiles (ils guident l'élève et ancrent la lecture), mais ils ne sont plus **une dépendance du diagnostic** — c'était la conséquence explicite de D-CEO-35, elle tombe.

**Vérifié :** 268 tests Django + 239 pytest passent après suppression. 15 tests neufs couvrent le pont : correspondance des codes, réussite non diagnostiquée, priorité de l'enseignant dans les deux sens, absence vs illisible, question hors barème diagnostiquée par prudence, QCM repris sans aucun appel de modèle, et les refus de la commande (mode libre, test archivé, correction non notée).

---

### D-CEO-39 — Streamlit est retiré, sans l'essai réel qui le conditionnait *(nouveau 2026-08-05)*
**Décision :** `src/ui/` est **supprimé** (3 106 lignes), avec `streamlit`, `pandas` et `numpy`. Django porte seul l'interface. **Le jalon qui conditionnait ce retrait — un essai de correction réel de bout en bout — n'a pas été passé, et c'est assumé plutôt que masqué.**

**Ce qui est supprimé :** `src/ui/app.py` (2 778 lignes, le plus gros fichier du projet), `src/ui/progress.py` (328), la configuration `.streamlit/`, la cible `make run-streamlit`. `hakili_logo.png` est **déplacé** dans `static/` : c'est le seul exemplaire de la marque dans le dépôt, et Django le sert désormais.

**Trois dépendances tombent avec.** `streamlit` et `pandas` ne servaient qu'à cette interface. `numpy` n'y servait pas — il était déclaré explicitement pour `src/pipeline/zones.py`, supprimé par D-CEO-38 le même jour ; plus rien ne l'utilise. Une dépendance de moins est une surface de rupture de moins, et ces trois-là sont parmi les plus mouvantes de l'écosystème.

**Pourquoi maintenant.** Le filet ne rattrapait plus rien. Django porte les onze écrans depuis le 30 juillet ; Streamlit n'a plus servi depuis. Il ne pouvait de toute façon pas dépanner : sans la clé du compte de service Google, **aucune des deux interfaces** ne permet de se connecter — le point de panne est commun, le second exemplaire ne le contourne pas. Ce qui restait était le coût : deux interfaces à tenir à jour, dont une que personne n'ouvre, et le risque qu'une correction soit faite deux fois ou dans une seule.

**Ce que le retrait coûte, dit franchement.** `verifier_installation --copie … --test … --eleve …` exécute une correction complète sur une vraie copie : c'est le seul contrôle qui prouve que la chaîne Django tient de bout en bout, et **il n'a jamais tourné**. Les 268 tests Django couvrent les vues, l'état, les décisions ; ils ne remplacent pas une copie réelle traversant le pipeline. Ce contrôle reste à faire — il est simplement découplé du retrait, au lieu de le bloquer indéfiniment. Le code reste dans l'historique Git si un besoin de comparaison se présentait.

**Ce que ça débloque.** `Copie` et `Document` vivent sous SQLAlchemy/Alembic parce que Streamlit les écrivait ; `Evaluation.copy_id` est un champ texte et non une clé étrangère pour la même raison. La condition est levée : ces deux tables peuvent passer sous Django, ce qui retire un second ORM, un second système de migrations, et un piège permanent. C'est le chantier suivant, pas un effet de bord de celui-ci.

**Vérifié :** 268 tests Django + 239 pytest passent, inchangés — rien ne dépendait de `src/ui`. `manage.py check` et `verifier_installation` ne signalent que le manque déjà connu (clé Google).

---

### D-CEO-40 — Un seul ORM : `copie` et `document` passent sous Django *(nouveau 2026-08-05)*
**Décision :** SQLAlchemy et Alembic sont **retirés du projet**. Les deux tables qu'ils portaient — `copie` et `document` — passent sous l'ORM Django, avec les autres. Un seul ORM, un seul système de migrations, une seule façon d'écrire en base.

**Ce qui est supprimé :** `src/db/` (modèles + moteur), `src/services/copie_service.py`, `migrations/` (4 révisions Alembic), `alembic.ini`, et les dépendances `sqlalchemy` et `alembic`. **24 paquets au lieu de 26.**

**Pourquoi maintenant.** Cette cohabitation n'a jamais été un choix : elle datait de Streamlit, qui écrivait ces deux tables. Streamlit est parti (D-CEO-39), et il ne restait qu'un coût — deux moteurs de connexion sur la même base Neon, deux façons de décrire un schéma, deux commandes de migration, et un piège permanent : `Evaluation.copy_id` est un champ texte **parce que** Django ne pouvait pas poser de clé étrangère vers une table qu'il ne gérait pas.

**Le pipeline ne connaît toujours pas Django, et c'est délibéré.** La difficulté était là : `src/pipeline/` écrit en base à cinq points d'injection (D-CEO-19), et la règle « `src/` sans dépendance de framework » interdit d'y importer l'ORM Django. La couture est `src/pipeline/depot.py` — un contrat de quatre méthodes et un dépôt courant, que `CorrectionWebConfig.ready()` installe au démarrage. Le pipeline dépose, il ne sait pas dans quoi.

Cette règle aurait pu être abandonnée : Django est le seul appelant depuis D-CEO-39. Elle est gardée pour deux raisons vérifiables — le retrait de Streamlit, 3 106 lignes, n'a touché **aucun test** précisément parce que `src/` ignorait l'interface ; et les 239 tests de `tests/` importent le pipeline **sans configurer Django**, ce qu'un import direct de l'ORM rendrait impossible.

**Un dépôt neutre par défaut, plutôt qu'une erreur.** Sans base configurée, le pipeline corrige quand même — c'est un mode réel (essais hors ligne, tests du pipeline). L'écriture en base est best-effort partout sauf en un point (D-CEO-19) ; ne rien écrire est donc le comportement juste. La seule vérification non best-effort — l'élève existe-t-il dans le Sheet — ne passe pas par le dépôt : elle reste dans le pipeline, avant tout appel IA payant.

**🔴 Un défaut trouvé en chemin, et il était invisible.** Le pipeline enveloppe chaque écriture dans un retry (`_retry_db`), parce qu'une base serverless refuse parfois la première connexion après une inactivité. **Ce retry ne pouvait rien rattraper** : la seconde tentative rappelait `create_copie`, qui échouait sur la clé primaire, ou `add_document_to_copie`, qui ajoutait un **second** document du même type. Et `get_document_by_type` prenait « le premier trouvé », sans ordre garanti — une copie recorrigée pouvait donc servir l'ancien rapport. Les quatre opérations du dépôt sont maintenant **rejouables** : `get_or_create` pour la copie, remplacement par type pour les documents. Le retry fonctionne enfin, et la recorrection sert le bon document.

**L'étape de mise en service, à ne pas manquer.** Sur Neon les deux tables existent déjà : la migration `suivi/0007` s'y applique avec `--fake`, une seule fois (`docs/deploiement.md`). Appliquée sans, elle échoue sur « relation existe déjà », la transaction est annulée et rien n'est perdu — bruyant plutôt que silencieux, ce qui est le bon défaut. Sur une base neuve elle crée les deux tables normalement. Django ne sait pas convertir un modèle `managed = False` en modèle géré — il produit un `AlterModelOptions` qui ne crée aucune table ; la migration est donc écrite à la main, et le piège est expliqué dedans.

**Ce qui n'a pas changé :** `identifiant_hakili` reste un champ **texte**, jamais une clé étrangère — l'identité vit dans les Sheets (D-CEO-20). Le passage sous Django rendait techniquement possible une table `eleve` ; elle n'a pas été créée, et ne doit pas l'être. `Evaluation.copy_id` reste texte lui aussi pour l'instant : le transformer en clé étrangère est désormais possible, mais c'est une décision séparée.

**Vérifié :** 275 tests Django + 239 pytest passent, dont **7 neufs sur le dépôt** — les quatre opérations rejouées, un document par type, les types qui ne se chassent pas entre eux, une mise à jour sur copie absente qui ne lève pas, l'installation du dépôt au démarrage, et le dépôt neutre qui n'écrit rien. Les tests des vues de suivi ont cessé de simuler la base : ils créent de vraies lignes, ce qui teste davantage avec moins de code.

---

### D-CEO-41 — Arbitrage C tranché : `remediation/` comme matière du module 7 *(nouveau 2026-08-13)*

**Décision :** Arbitrage C (`docs/harmonisation_donnees.md` §7 — « le curriculum RAG survit-il ? ») est tranché en faveur d'une nouvelle source, **`remediation/`** (hors de ce dépôt, 79 modules rédigés sur 7 niveaux, 6e à Tle D), plutôt que d'un rapprochement des 121 chunks `curriculum_*.yaml` existants. `curriculum_*.yaml` et `CurriculumRetriever` (`src/knowledge/curriculum_retriever.py`) **ne sont pas retirés** : ils restent le RAG de l'ancien pipeline (`src/pipeline/pipeline.py`, `DiagnosticResult` en texte libre), non touchés ici.

**Pourquoi `remediation/` plutôt que les 121 chunks.** Le curriculum RAG ne couvre que le collège et ne porte que de la métadonnée de leçon (savoir, savoir-faire, mots-clés, erreurs fréquentes) — aucun exercice, aucun corrigé. `remediation/` couvre les 7 niveaux et porte, par module, un diagnostic express, des leçons complètes (méthode, exemple résolu, erreurs fréquentes typées, déclic) et **2 838 exercices notés ★/★★/★★★ tous corrigés**. C'est la matière que le module 7 (génération des fiches) attendait, nommée comme telle dans Arbitrage C.

**Ce qui a été construit.** `src/knowledge/remediation_parser.py` (extraction déterministe du gabarit fixe des modules), `scripts/generer_remediation_yaml.py` (produit `data/knowledge/remediation_<niveau>.yaml`, un chunk par leçon), `manage.py rapprocher_remediation` (rapproche les leçons des 101 compétences canoniques — score de similarité de libellé + recouvrement de mots-clés + écart de niveau, produit `remediation_competences_map.yaml`), `src/knowledge/remediation_retriever.py` (`RemediationRetriever.get_by_competence(code, niveau)`).

**Seuil auto-validé, pas de classeur de relecture.** À la différence de la pratique suivie pour Arbitrage B et pour le rapprochement curriculum existant (`scripts/rapprocher_curriculum.py`), le rapprochement compétence ↔ leçon de remédiation est retenu automatiquement au-delà d'un seuil de score unique, sans relecture pédagogique préalable bloquante — décision explicite avec l'utilisateur. Couverture actuelle (162 paires niveau × compétence, sur 707 possibles) : 10 à 32 compétences sur 101 selon le niveau, le reste dégrade sans erreur (aucun ancrage injecté plutôt qu'un mauvais).

**Branché dans :** `referentiel/contexte.py::contexte_diagnostic()` (module 4, enrichissement additif, conforme à l'invitation du docstring), `ConfirmationHypothesis`/`VerificationItem` (`src/models/domain.py`) via `correction_web/taches.py` (T1) et `suivi/generation.py` (T3/T4/T5) — nouveau champ `reference_pedagogique`, jamais la banque d'exercices notés (pas de fuite de réponse), toujours dégradable à `None`. `prompts/confirmation_subject_prompt.md` et `prompts/verification_subject_prompt.md` mis à jour pour l'exploiter sans jamais recopier l'exemple fourni.

**Ce qui reste ouvert :** la couverture n'est pas exhaustive (79 modules ne recouvrent pas les 101 compétences avec la même densité à tous les niveaux), et le générateur de fiches du module 7 lui-même n'est pas construit — cette décision lui prépare la matière, elle ne le remplace pas.

---

### D-CEO-42 — Django+HTMX remplacé par FastAPI + React/Vite/Tailwind *(nouveau 2026-08-20)*

**Décision :** D-CEO-39 (« Django porte seul l'interface ») et D-CEO-40 (« un seul ORM ») sont **inversées**, à la demande explicite de l'utilisateur : le rendu serveur Django est remplacé par une API **FastAPI** (SQLAlchemy 2.0 synchrone + Alembic — un deuxième ORM revient, sciemment) et une interface **React + Vite + TypeScript + Tailwind v4**, motivé par un objectif de rendu visuel nettement plus professionnel qu'un rendu serveur Django+CSS artisanal ne permettait pas d'atteindre facilement. Décision prise en toute connaissance de cause : l'utilisateur a été prévenu que ça inversait ces deux décisions actées avant de confirmer.

**Ce qui ne change pas.** Toute la discipline qui a survécu à la migration Streamlit→Django survit à celle-ci : `src/pipeline/`, `src/api/`, `src/knowledge/`, `src/models/`, `src/core/`, `src/integrations/`, `src/services/` restent **indépendants du framework** — FastAPI les réutilise sans une ligne modifiée, exactement comme Django l'avait fait. Le contrat de persistance (`src/pipeline/depot.py::DepotCopies`, 4 méthodes) reste le point d'accroche unique ; `DepotFastAPI` l'implémente, `DepotDjango` continue d'exister en parallèle tant que Django tourne. Google Sheets reste la source de vérité identité (aucune table `eleve`/`utilisateur` recréée, D-CEO-20/21/25 tiennent). Le pipeline reste synchrone et tourne dans un thread, pas dans une file de tâches externe.

**Construction à côté, pas de double écriture en production.** `backend/` (FastAPI) et `frontend/` (React) sont construits et validés contre une base de développement séparée pendant que Django continue de servir la production sans interruption — jamais les deux stacks contre la même base Neon en même temps, pour ne pas reproduire l'erreur à deux systèmes divergents déjà corrigée deux fois (D-CEO-20/21). La bascule elle-même (adoption du schéma Neon existant via `alembic stamp`, déploiement sur le VPS Hetzner, retrait de Django) n'a **pas** eu lieu à la date de cette entrée — elle demande les accès de production (Neon, SSH) et une fenêtre de maintenance choisie par l'utilisateur, documentée mais pas exécutée (`backend/docs/bascule_neon.md`).

**Portée du chantier à cette date, `/admin` explicitement exclu.** À la demande de l'utilisateur, tout le périmètre de l'admin Django (CRUD des 13 tables référentiel/suivi, saisie des corrigés manquants, historique `Transition` en lecture seule) reste **hors scope** — l'admin Django continue de faire foi pour ces opérations tant qu'une section React équivalente n'est pas construite. Le reste des 17 écrans (connexion, accueil, profil élève, parcours/session, correction unique/lot/suivi, sujets, à propos) est porté en entier, avec un `importer_referentiel` réécrit pour SQLAlchemy, une protection CSRF double-soumission (le cookie de session est `httponly`, un second cookie lisible en JS le complète), et un durcissement production (HSTS + redirection HTTPS) mirroir de celui de Django.

**Vérifié :** 95 tests `pytest backend/tests/` (dont un import réel du classeur produisant des comptes strictement identiques à ceux déjà documentés en D-CEO-28/D-CEO-27), 240 tests `pytest tests/` toujours verts (`src/` intact), 40 tests Vitest côté frontend, un aller-retour réel de bout en bout (vraies clés API, base SQLite isolée neuve, jamais Neon ni `dev.db`) rejoué deux fois — une fois sans référentiel importé (dégradation gracieuse du diagnostic constatée), une fois avec (hypothèses ancrées à une compétence réelle constatées). Comparaison écran par écran contre les gabarits Django : 8 pertes d'information silencieuses trouvées et corrigées avant cette entrée.

---

## Tableau de synthèse

| ID | Sujet | Décision finale | Date |
|---|---|---|---|
| D001 | Flux d'ingestion | Copie complète (pas exercice par exercice) | 2026-05-08 |
| D002 | Source de vérité | JSON → PDF | 2026-05-08 |
| D003 | Interface | Streamlit | 2026-05-08 |
| D004 | Stockage | Local pour prototype | 2026-05-08 |
| D005 | Volume cible | 100 copies réelles | 2026-05-08 |
| D-CEO-01 | Matières et niveaux | Mathématiques, **6e à la Terminale** | 2026-05-08 |
| D-CEO-02 | Format barème | Binaire 0/1 par question et sous-question | 2026-05-08 |
| D-CEO-03 | Stratégie IA | **Multi-provider** (Gemini + DeepSeek + Mistral + Claude) | **2026-06-05** |
| D-CEO-04 | Instructions expert | Couche optionnelle d'instructions contextuelles | 2026-05-08 |
| D-CEO-05 | Validation humaine | Hors plateforme (enseignant sur PDF exporté) | 2026-05-08 |
| D-CEO-06 | Rapport PDF | Note · commentaires · diagnostic · remédiation · confiance | 2026-05-08 |
| D-CEO-07 | Identification | Nom réel de l'élève (slug technique pour fichiers) | 2026-05-08 |
| D-CEO-08 | Remédiation | Sujet d'exercices personnalisé (5 exos/lacune) | 2026-05-08 |
| D-CEO-09 | Modes interface | Copie Unique + Batch | 2026-05-08 |
| D-CEO-10 | Format entrée | **PDF scanner 150 DPI, niveaux de gris** | **2026-06-05** |
| D-CEO-11 | Coût cible | **~$0.02/copie · ~$12/an** pour 540 copies | **2026-06-05** |
| D-CEO-12 | Diagnostic RAG | Ancré sur programme officiel MEN Burkina Faso (121 leçons 6e→3e) | **2026-06-08** |
| D-CEO-13 | Tests Hakili pré-chargés | TestRegistry : énoncé + barème auto · enseignant charge uniquement la copie | **2026-06-08** |
| D-CEO-14 | UI premium · marketing | Écran animé Hakili · 7 étapes en temps réel · logo pulsant · facturable parents | **2026-06-08** |
| D-CEO-15 | Génération PDF | Migration ReportLab → **XeLaTeX + Jinja2** (fallback ReportLab si xelatex absent) | **2026-06-11** |
| **D-CEO-16** | **Mode correction** | **Correction assistée : IA propose, enseignant valide dans l'interface** | **2026-06-11** |
| **D-CEO-17** | **Objectif central** | **Diagnostic approfondi = valeur principale — rapport centré sur les lacunes** | **2026-06-11** |
| **D-CEO-18** | **Portail de consultation** | **Persistance Neon Postgres + login par rôle — scaffolding, pipeline non câblé** | **2026-07-09** |
| **D-CEO-19** | **Câblage pipeline ↔ Neon** | **5 points d'injection DB, comptes seed idempotents, pool_pre_ping, comparaison chronologique (date_soumission), logs fichier** | **2026-07-15** |
| **D-CEO-20** | **Élèves/profs → Google Sheets** | **Table ELEVE supprimée, COPIE.identifiant_hakili ; élève choisi explicitement, bloqué avant appel IA si absent des Sheets** | **2026-07-17** |
| **D-CEO-21** | **Login → Sheet profs** | **Table UTILISATEUR (+ CENTRE) supprimée, table `credentials` (email + password_hash) ; le Sheet fait foi à chaque connexion** | **2026-07-17** |
| **D-CEO-22** | **Liste de centres autorisée** | **`CENTRES_AUTORISES` dans `centre_normalizer.py` ; alerte `[SHEETS WARNING]` sur centre non reconnu, ligne conservée ; même normalisation lecture ↔ permissions** | **2026-07-17** |
| **D-CEO-23** | **Vue Responsable — tendance** | **Pastille vert/orange/rouge/gris sur les 2 dernières notes, `SEUIL_TENDANCE` dans `tendance.py`, chargement groupé par centre, baisses triées en premier** | **2026-07-18** |
| **D-CEO-24** | **Vue Enseignant — profil élève** | **Sélection déroulante restreinte + profil détaillé (tendance réutilisée, copies chronologiques, documents) ; bug de permission `can_access_eleve`/enseignant corrigé** | **2026-07-18** |
| **D-CEO-25** | **Connexion nom+PIN, centres dérivés** | **Table `credentials` supprimée, rôle+PIN lus dans le Sheet personnel, regroupement par (nom, prénom) ; `CENTRES_AUTORISES` remplacée par `deriver_centres()` (détection de centre suspect, plus de liste figée)** | **2026-07-20** |
| **D-CEO-26** | **v2 — archivage + barème** | **Les 6 anciens tests archivés (`archive: True`, masqués de la sélection mais toujours résolus pour l'historique) ; barème stocké sur 20, note calculée contre la somme réelle des `max_score` et jamais contre un total déclaré** | **2026-07-30** |
| **D-CEO-27** | **7 tests v2 générés depuis le classeur** | **Énoncés non extractibles des PDF (maths en vectoriel, WeasyPrint) → source = `Referentiel_Socle_v0.xlsx` via `scripts/generer_baremes_socle.py` ; 280 questions, 71 QCM corrigés, 209 corrigés en attente ; classe canonique unique par test ; copie parfaite = 20,0/20 vérifiée** | **2026-07-30** |
| **D-CEO-35** ⛔ | *(caduque — D-CEO-38)*  **Gabarit des zones lu dans le PDF** | **Les sujets conservent cadres ancrés et codes ; la position des zones est lue à la source, pas détectée sur le scan. L'OCR sort de la chaîne — c'était le premier point de panne, et une confusion de code aurait fauté sans rien signaler. Règles exprimées en plages, pas en valeurs relevées** | **2026-07-31** |
| **D-CEO-36** ⛔ | *(caduque — D-CEO-38)*  **Recalage ancré sur le contenu ; rien contre le tramage** | **La page est recalée sur les cadres, jamais sur le rectangle de page ; l'inclinaison s'estime sur les coordonnées de l'encre, pas en tournant l'image ; l'appariement page scannée ↔ page du sujet n'est pas 1:1 (12 pages scannées pour un sujet de 10). Aucun mécanisme livré contre le tramage d'impression : le repli prévu (effacer les lignes à leur position) est impossible, les « lignes » pavent toute la zone** | **2026-08-01** |
| **D-CEO-40** | **Un seul ORM** | **SQLAlchemy et Alembic retirés ; `copie` et `document` passent sous Django. La cohabitation datait de Streamlit, partie en D-CEO-39. Le pipeline reste sans dépendance de framework via `src/pipeline/depot.py`, installé au démarrage par `CorrectionWebConfig.ready()`. Défaut corrigé en chemin : le retry des écritures ne rattrapait rien (opérations non rejouables) et une copie recorrigée pouvait servir l'ancien rapport. ⚠ `migrate suivi 0007 --fake` une fois sur Neon** | **2026-08-05** |
| **D-CEO-41** | **Arbitrage C tranché : `remediation/`** | **`remediation/` (79 modules, 7 niveaux, 2 838 exercices corrigés) remplace les 121 chunks curriculum comme matière du module 7 ; `RemediationRetriever` branché sur le module 4 (contexte diagnostic) et le module 5 (T1, T3/T4/T5) via `reference_pedagogique` ; rapprochement compétence ↔ leçon auto-validé au-delà d'un seuil, sans classeur de relecture** | **2026-08-13** |
| **D-CEO-42** | **Django+HTMX → FastAPI + React/Vite/Tailwind** | **D-CEO-39/40 inversées à la demande explicite de l'utilisateur : rendu serveur remplacé par API FastAPI (SQLAlchemy+Alembic) et SPA React/Tailwind, pour un rendu visuel professionnel. `src/` intact et réutilisé tel quel ; `backend/`/`frontend/` construits à côté de Django sur une base de dev séparée, jamais contre Neon en double écriture ; `/admin` explicitement hors scope ; bascule production non exécutée** | **2026-08-20** |
| **D-CEO-39** | **Streamlit retiré** | **`src/ui/` supprimé (3 106 lignes) avec `streamlit`, `pandas` et `numpy` — ce dernier ne servait qu'au module 2, parti le même jour. Django porte seul l'interface depuis le 30 juillet et le filet ne rattrapait plus rien : sans la clé Google, aucune des deux interfaces ne permet de se connecter. L'essai réel de bout en bout qui conditionnait le retrait n'a pas été passé — il reste à faire, découplé plutôt que bloquant. Débloque le passage de `copie`/`document` sous Django** | **2026-08-05** |
| **D-CEO-38** | **Module 2 supprimé, diagnostic branché sur la correction** | **Trois copies 5e réelles imprimées/scannées : les trois refusées. Cause mesurée — un bord de cadre passe de 121–156 dans le PDF à 243–248 après impression (papier 251,6), le seuil d'encre à 140 ne le voit pas et le recalage s'accroche au texte : dérive jusqu'à 85 pt, 4 pages/10 acceptées à tort. Le tramage, lui, n'existe pas (0,00 % de pixels sous 200 dans un cadre). Remplacé par `reponses_depuis_correction()` : la correction rend déjà `observed_answer` par code de question, et le code du barème est celui du référentiel. D-CEO-35 et D-CEO-36 caduques** | **2026-08-05** |
| **D-CEO-37** | **Identités factices en développement** | **Élèves et personnel inventés à la place de la lecture des Sheets, verrouillés sur `DEBUG` + `HAKILI_SHEETS_FACTICES` : rien n'est écrit, le branchement est au ras du réseau (`_fetch_raw_rows`) avec les en-têtes réels, donc toute la chaîne aval s'exécute pour de vrai. Cas limites couverts (centre vu une fois, fratrie, double affectation). `donnees_demo` ajoute trois parcours, sans jamais toucher aux sessions `CORPUS-*`** | **2026-08-05** |
| **D-CEO-34** | **États de session et inscription** | **Sept états ; l'inscription bascule les problèmes, date la facturation et refuse le palier C sans motif tracé. Trois sorties sans remédiation distinguées — « aucune lacune » est une réussite, pas un abandon** | **2026-07-30** |
| **D-CEO-33** | **Cycle : T2 retiré, tests répétables** | **Cinq étapes au lieu de six ; un même type d'évaluation peut se répéter (rang automatique) tant que les lacunes persistent. Les indicateurs, qui comptent des transitions, restent valides** | **2026-07-30** |
| **D-CEO-32** | **Périmètre unique** | **Centre d'encadrement, pas école : toute personne autorisée voit tous les élèves et corrige toute copie. Cloisonnement centre/classe retiré, sélecteur de casquette supprimé ; le Sheet reste la source des accès, avec un écran de consultation** | **2026-07-30** |
| **D-CEO-31** | **Nettoyage fichiers et bibliothèques** | **`AGENTS.md`, `implementation_plan.md`, `data/schemas/`, 3 bibliothèques inutilisées retirés ; faux positifs (`gunicorn`, `whitenoise`, `alembic`, `psycopg2`) écartés car chargés par nom** | **2026-07-30** |
| **D-CEO-30** | **Ancrage du diagnostic reconstruit** | **Le RAG était mort sur les 7 nouveaux tests (0 caractère de contexte) : reconstruit sur le référentiel — compétence, chaîne de prérequis, signatures par question. `src/` reste sans dépendance framework via un paramètre `ancrage`** | **2026-07-30** |
| **D-CEO-29** | **Volume de repli lycée : 4 h** | **Médiane du collège, marquée « estimé » ; 20 h écarté après calcul — le plafond de 4 h y écrasait PRQ/CPT/MOD à la même valeur. 606 coûts au lieu de 444, palier enfin calculable en 2nde et 1ère** | **2026-07-30** |
| **D-CEO-28** | **Streamlit → Django + HTMX, socle de données** | **Rendu serveur, Railway/Render, Neon inchangé ; 11 tables migrées en Django, référentiel importé (idempotent, contrôle d'intégrité avant écriture), admin configuré ; `Transition` immuable et `changer_etat()` atomique ; parcours T0→T5 vérifié** | **2026-07-30** |
