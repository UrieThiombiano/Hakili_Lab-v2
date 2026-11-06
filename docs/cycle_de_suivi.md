# Le cycle de suivi d'un élève
**Document de référence · 2026-07-30**

Décrit le cycle **tel qu'il est décidé et modélisé**. Fait foi sur ce point.

> **Rapport à `protocole-v2.md`.** Le protocole d'origine reste la référence sur
> le vocabulaire, la taxonomie des erreurs et le calcul des coûts. Il décrit en
> revanche un cycle à six évaluations en séquence fixe, qui a été révisé (D-CEO-33).
> Sur le **déroulé**, c'est le présent document qui est à jour ; les écarts sont
> listés au §7.

---

## 1. Le cycle en une vue

```
        ┌─────────────────────────────────────────────────────────────┐
        │  T0   TEST DE NIVEAU                                        │
        │       L'élève compose. Le système corrige et détecte        │
        │       des lacunes PROBABLES — des hypothèses, pas des faits.│
        └───────────────────────────┬─────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  T1   CONFIRMATION                                          │
        │       Le système génère un sujet ciblé sur ces hypothèses.  │
        │       Chacune est CONFIRMÉE ou ÉCARTÉE.                     │
        │       Note T0 < 10/20 : pas de T1, hypothèses confirmées    │
        │       d'office (D-CEO-46).                                  │
        └───────────────────────────┬─────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │       FICHE DE REMÉDIATION                                  │
        │       Un plan chiffré : quoi travailler, dans quel ordre,   │
        │       et combien d'heures.                                  │
        └───────────────────────────┬─────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │       INSCRIPTION AU PROGRAMME                              │
        │       Décision humaine. L'élève entre officiellement en     │
        │       remédiation.                                          │
        └───────────────────────────┬─────────────────────────────────┘
                                    ▼
        ╔═════════════════════════════════════════════════════════════╗
        ║       TRAVAIL HORS PLATEFORME                               ║
        ║       Le tuteur et l'élève travaillent selon la fiche.      ║
        ║       Le système n'intervient pas.                          ║
        ╚═══════════════════════════┬═════════════════════════════════╝
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  T3   VÉRIFICATION                       ◄──────────┐       │
        │       À la fin du volume horaire. Les lacunes       │       │
        │       sont-elles corrigées ?                        │       │
        └───────────────────────────┬────────────────────────┼───────┘
                     tout est bon   │        il en reste     │
                                    ▼                        │
                                    │      ┌─────────────────┘
                                    │      │  Nouvelle remédiation,
                                    │      │  nouveau T3. Autant de
                                    │      │  fois que nécessaire.
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  T4   CONSOLIDATION — 45 jours après                        │
        │       L'élève a-t-il retenu ?                               │
        └───────────────────────────┬─────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  T5   CONSOLIDATION — 3 mois après                          │
        │       Dernier contrôle. Le cycle se clôt.                   │
        └─────────────────────────────────────────────────────────────┘
```

---

## 2. Ce qui est suivi : le problème, pas la note

L'unité de suivi n'est ni la note ni la classe, mais le **problème** :

> **problème = une compétence × un type d'erreur**

Un élève n'a pas « 11 sur 20 ». Il a « 14 problèmes ouverts, dont 3 prérequis de
5ème ». Une note dit qu'un élève a échoué ; elle ne dit ni sur quoi ni pourquoi,
donc elle ne permet ni de construire une remédiation ni de mesurer un progrès.

Chaque problème traverse des états, et **chaque changement d'état est daté et
enregistré**. C'est de cet historique que sortent tous les indicateurs.

### Les états d'un problème

| État | Ce qu'il signifie | Ce qui l'y amène |
|---|---|---|
| `hypothese` | Détecté, pas encore vérifié | Diagnostic après T0 |
| `confirme` | Difficulté réelle, à traiter | T1 |
| `ecarte` | Fausse piste — c'était une étourderie | T1 |
| `en_remediation` | Le tuteur travaille dessus | Inscription au programme |
| `resolu` | Difficulté levée | T3 |
| `non_resolu` | Difficulté persistante | T3 |
| `regresse` | Réapparue après coup | T4 ou T5 |
| `clos` | Acquis durablement | T5 |

### Les enchaînements permis

```
hypothese ──► confirme ──► en_remediation ──┬──► resolu ──┬──► clos      (terminal)
    │                            ▲          │             │
    │                            │          └──► non_resolu│
    │                            │                    │    └──► regresse
    │                            └────────────────────┴──────────┘
    └──► ecarte  (terminal)
```

Un enchaînement non prévu est **refusé** — passer directement d'`hypothese` à
`resolu` est impossible : un problème jamais confirmé ne peut pas être résolu.

`ecarte` et `clos` sont terminaux : on n'en repart pas.

---

## 3. Le cycle étape par étape

### T0 — Test de niveau

L'élève compose sur le sujet imprimé. Le système transcrit, propose une note par
question, l'enseignant valide, puis le diagnostic produit des **hypothèses**.

Rien n'est affirmé à ce stade : une réponse fausse peut venir d'une lacune réelle
comme d'une étourderie. C'est toute la raison d'être de T1.

### T1 — Confirmation

**Seulement si la note T0 est d'au moins 10/20** (D-CEO-46). En dessous, les
lacunes sont assez nombreuses pour que T1 n'apporte rien : les hypothèses sont
confirmées d'office et le plan de remédiation est définitif dès le T0.

Le système génère un sujet **ciblé** sur les hypothèses. Ce n'est pas un T0
raccourci : chaque question est construite pour **départager deux causes possibles
d'un même échec**.

> Un élève rate le développement de (2x−3)². Ignore-t-il l'identité remarquable,
> ou la connaît-il et se trompe-t-il à l'exécution ? Lui demander (x+5)², très
> simple, puis (3a−4b)², plus lourd. S'il réussit la première et rate la seconde,
> c'est procédural. S'il rate les deux de la même façon, c'est conceptuel.

Une question qui ne départage rien n'a pas sa place dans T1.

À l'issue, chaque hypothèse devient `confirme` ou `ecarte`.

**Le type d'erreur `ATT` (inattention) existe pour être écarté.** Un élève qui
recopie un énoncé de travers puis résout parfaitement n'a pas de lacune. Lui
prescrire de la remédiation serait une erreur de diagnostic et une dépense inutile
pour la famille. Le modèle l'interdit : un problème `ATT` ne peut être qu'en
`hypothese` ou `ecarte`.

### Fiche de remédiation

Le coût de chaque problème confirmé est **calculé, pas estimé au jugé** :

> coût = volume horaire officiel de la compétence × coefficient du type d'erreur

arrondi à la demi-heure, plancher 30 min, plafond 4 h par problème. Le plafond
évite qu'un seul problème absorbe la moitié du plan.

Le total détermine le **palier** :

| Palier | Total | Format |
|---|---|---|
| **A** | moins de 8 h | remédiation ciblée, 2 à 4 séances |
| **B** | 8 à 20 h | déroulé complet |
| **C** | plus de 20 h | **ne relève pas de la remédiation courte** |

Le palier C doit être **prononcé clairement**. Proposer cinq semaines à un élève
qui cumule huit prérequis manquants garantit un échec, et un échec visible coûte
plus cher à la réputation du centre qu'un refus initial argumenté.

Le plan **ordonne les problèmes selon le graphe des prérequis** : un problème dont
un prérequis est lui-même en difficulté se traite après ce prérequis, jamais avant.
C'est ce qui distingue une remédiation d'un rattrapage — on remonte à la cause au
lieu de soigner le symptôme.

### Inscription au programme

Décision humaine, prise dans la plateforme. L'élève entre officiellement en
remédiation ; tous les problèmes confirmés passent en `en_remediation`, chacun avec
sa transition. La **date d'inscription** est enregistrée : c'est d'elle que part le
décompte du volume horaire, et vraisemblablement la facturation.

**Le palier C est refusé sans décision explicite.** Inscrire malgré tout reste
possible, mais exige un motif, qui est conservé dans l'historique du problème — la
décision est tracée, pas seulement prise.

**Une session ne peut pas être inscrite si aucun problème n'est confirmé** : il n'y
aurait rien à remédier, et la facturation serait sans objet.

### Les états d'une session

| État | Ce qu'il signifie |
|---|---|
| `diagnostic` | T0 et T1 en cours |
| `attente_inscription` | Plan établi, palier A ou B — la décision revient à l'enseignant |
| `remediation` | Inscrit, le travail est en cours |
| `close` | Cycle achevé après T5 |
| `sans_suite` | T1 n'a rien confirmé — **c'est un bon résultat** |
| `hors_dispositif` | Palier C — orientation vers un accompagnement long |
| `abandonnee` | Retrait en cours de route |

Les trois sorties sans remédiation sont distinguées **délibérément**. Elles ne
veulent pas dire la même chose à une famille : « aucune lacune confirmée » est une
réussite, « palier C » est une orientation, « abandonnée » est un retrait. Les
confondre transformerait une réussite en échec dans les comptes rendus.

### Travail hors plateforme

Le tuteur délivre la remédiation. **Le système n'intervient pas.** Le principe de
division du travail est constant : *l'IA diagnostique et conçoit, le tuteur humain
délivre.* L'outil ne remplace pas le tuteur, il supprime son temps de diagnostic
et de préparation.

Après chaque séance, le tuteur remplit une fiche de **cinq champs, pas davantage** :
problèmes travaillés, ce qui a bloqué, ce qui a débloqué, travail donné,
appréciation. Une fiche plus longue ne sera pas remplie.

Ce qu'il observe — blocages, stratégies d'évitement, réponses devinées, anxiété —
est le signal le plus riche du dispositif, et aucun test ne le capte.

### T3 — Vérification, autant de fois que nécessaire

À la fin du volume horaire, un test porte **uniquement sur les problèmes ouverts**.
Chacun devient `resolu` ou `non_resolu`.

**S'il en reste, on recommence** : nouvelle remédiation ciblée sur ce qui résiste,
nouveau T3. Il n'y a pas de limite — les évaluations d'un même type se distinguent
par un rang (« vérification après remédiation (2e passage) »).

### T4 — Consolidation à 45 jours

On ne réévalue que ce qui a été résolu. Un problème qui réapparaît passe en
`regresse` et déclenche une remédiation courte, ciblée sur lui seul, **sans refaire
de diagnostic complet**.

### T5 — Consolidation à 3 mois, puis clôture

Dernier contrôle. Ce qui tient encore passe en `clos`. Le cycle se referme.

---

## 4. Les règles de décision

Aucun branchement n'est laissé à l'appréciation du moment.

**Après T1 — entrer ou non en remédiation.** Le critère n'est pas la note, c'est le
nombre et la nature des problèmes confirmés. **Si aucun n'est confirmé, l'élève
sort du dispositif** et rejoint les cours normaux. Cette sortie est un résultat
honorable et doit être présentée comme telle : un outil qui n'oriente pas
systématiquement vers de la remédiation payante est un outil crédible.

**Après T1 — choisir le palier.** Voir §3.

**Après T3 — sortir ou reprendre.** Des problèmes non résolus déclenchent un
nouveau cycle court. Si trop résistent, l'élève relève d'un accompagnement régulier
plutôt que d'une remédiation.

**Après T4 ou T5 — renforcer.** Tout problème `regresse` déclenche une remédiation
courte sur lui seul.

---

## 5. Ce que le cycle produit

**Pour la famille** — un rapport de deux pages, lisible sans notion technique :
les problèmes ouverts, résolus et restants, et ce qui a été travaillé. « 14
problèmes ouverts, 11 résolus en quatre semaines, 9 encore résolus 45 jours plus
tard » est une phrase que tout le monde comprend.

**Pour le centre** — cinq indicateurs, tous calculés depuis l'historique des
transitions :

| Indicateur | Mesure |
|---|---|
| Taux de résolution | problèmes résolus / problèmes confirmés |
| Rétention à 45 jours | encore résolus à T4 / résolus à T3 |
| Rétention à long terme | mesurée à T5 |
| **Taux de confirmation** | confirmés à T1 / hypothèses après T0 |
| Écart durée estimée / réelle | par type d'erreur |

Le quatrième mesure **l'outil, pas l'élève**. Une valeur très basse signale un T0
qui produit de fausses pistes. Une valeur de 100 % signale au contraire un T1 qui
ne départage rien et pourrait être supprimé. La plage saine se situe entre 60 et
80 %.

Le cinquième sert à **recalibrer les coefficients de coût** après une vingtaine de
cycles clos. Une estimation laissée au jugement du tuteur, elle, ne s'améliore
jamais.

---

## 6. État d'implémentation

| Étape | État |
|---|---|
| Modèle de données du cycle complet | ✅ en place |
| États des problèmes et enchaînements permis | ✅ garantis par le code |
| Historique daté des transitions | ✅ immuable |
| Évaluations répétables (rang automatique) | ✅ |
| Coûts et paliers | ✅ calculés, 606 lignes |
| T0 — correction et diagnostic | 🟨 correction en place ; diagnostic structuré à faire (module 4) |
| T1 — génération du sujet ciblé | ⬜ module 5 |
| Fiche de remédiation | ⬜ modules 6 et 7 |
| Inscription au programme, états de session | ✅ modélisés, garde-fou palier C |
| Fiche de séance du tuteur | 🟨 table en place, écran à construire (module 8) |
| Rapport famille et indicateurs | ⬜ module 9 |

**Ce qui reste à construire, c'est l'écran** : le bouton d'inscription, la fiche de
remédiation qui le précède, et la fiche de séance du tuteur. Le modèle, lui, est en
place et vérifié — l'inscription bascule les problèmes, enregistre la date, et
refuse le palier C sans motif.

---

## 7. Écarts assumés par rapport à `protocole-v2.md`

**T2 (contrôle de mi-parcours) est retiré.** Le protocole le plaçait entre la
remédiation et le test de sortie, tout en le rendant déjà facultatif en palier A.
Il ne correspond pas à la pratique : on va de la fin du volume horaire directement
à la vérification.

**Les évaluations sont répétables.** Le protocole décrivait six évaluations en
séquence fixe. En pratique, l'enseignant relance un test de vérification tant que
des lacunes persistent. Les indicateurs n'en souffrent pas : ils comptent des
transitions rattachées à une évaluation, pas « la » T1 ou « le » T3 — un problème
résolu au troisième passage compte comme résolu.

**Le budget d'évaluation n'est plus plafonné à six heures.** Il découlait de la
séquence fixe. Le principe demeure : T3, T4 et T5 ne portent **que sur les
problèmes concernés**, jamais sur l'ensemble du programme. Seul T0 est un test
complet.

Ces écarts sont enregistrés en **D-CEO-33**.
