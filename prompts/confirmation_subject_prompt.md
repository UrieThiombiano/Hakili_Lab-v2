# Prompt — Génération du sujet de confirmation T1 (Hakili Lab)

Tu génères le **test de confirmation T1** pour **Hakili Lab**, centre national
d'excellence en mathématiques au Burkina Faso. Un premier test (T0) a produit
des **hypothèses** de lacunes — des soupçons, pas des faits. Ce sujet T1 doit
permettre à l'enseignant de trancher, pour chacune, entre lacune réelle et
étourderie, et entre difficulté conceptuelle et difficulté procédurale.

## Ce que ce sujet n'est PAS

Ce n'est **pas** un sujet de remédiation. Tu ne cherches pas à faire progresser
l'élève ni à lui enseigner la compétence manquante. Tu cherches à **vérifier**
si la lacune existe vraiment. N'inclus donc :
- aucune explication de méthode, aucun rappel de cours ;
- aucun exercice d'entraînement répétitif ;
- aucune indication qui donnerait la réponse ou la démarche à suivre.

## Objectif

Pour **chaque hypothèse** fournie, produis exactement **2 questions** qui
départagent deux causes possibles d'un même échec :

| Question | Rôle |
|---|---|
| 1 (simple) | Teste la compétence sous sa forme la plus directe, sans piège ni habillage. Si l'élève la réussit, la notion de base est acquise. |
| 2 (renforcée) | Teste la même compétence sous une forme plus exigeante (calcul plus long, valeurs moins commodes, ou une étape supplémentaire) — sans changer de notion. |

**Grille de lecture que l'enseignant appliquera à vos deux questions** (à
garder en tête en les rédigeant, tu n'as pas à l'écrire) :
- réussite aux deux → probablement une étourderie à T0, hypothèse à écarter ;
- échec à la 1 → difficulté conceptuelle, à confirmer ;
- réussite à la 1, échec à la 2 → difficulté procédurale, à confirmer.

Pour qu'une telle lecture soit possible, les deux questions doivent porter sur
**exactement la même notion** — seule la difficulté d'exécution change. Deux
questions qui testent deux notions différentes ne départagent rien et sont un
défaut de conception.

## Cas particulier : hypothèse `is_att` (inattention)

Quand `is_att` est vrai, ne construis pas une question conceptuelle vs
procédurale : les deux questions doivent être des répétitions proches de la
situation qui a produit l'erreur à T0 (mêmes nombres d'ordre de grandeur
similaire, même structure), pour voir si l'erreur se reproduit. Une hypothèse
`ATT` ne peut jamais être confirmée comme lacune — le sujet sert seulement à
vérifier si l'erreur se répète (à noter par l'enseignant) ou non (étourderie
confirmée, hypothèse écartée).

## Ancrage pédagogique (`reference_pedagogique`)

Quand une hypothèse porte un champ `reference_pedagogique` non vide, c'est un
extrait du livret de remédiation Hakili Lab du niveau concerné (méthode,
erreurs fréquentes typées à ce niveau précis, un exemple travaillé). **Calibre
tes deux questions strictement sur ce niveau de difficulté et ce
vocabulaire** — c'est la garantie que la question reste dans le programme
réellement enseigné à cet élève, ni en-deçà ni au-delà.

**Ne recopie jamais l'exemple fourni.** Il sert de gabarit de difficulté et de
style, pas de contenu à réutiliser : change systématiquement les valeurs
numériques, le contexte, ou l'angle d'attaque. Une hypothèse sans
`reference_pedagogique` (compétence hors couverture actuelle du
rapprochement) se traite exactement comme avant, avec le seul libellé de
compétence.

## Exigences de forme

- Chaque question est autonome, sans référence à « la question 1 » de T0.
- Rédaction complète attendue, avec étapes numérotées si la question en
  comporte plusieurs — même règle de format que pour un sujet d'évaluation
  standard (voir « Format obligatoire de `question` » plus bas).
- Aucune des deux questions ne porte d'indice (`hint` toujours `null`) : donner
  un indice fausserait la mesure que T1 cherche à faire.
- Notation ASCII pour les symboles mathématiques uniquement : N, Z, Q, R (pas
  ℕ,ℤ,ℚ,ℝ), a^n (pas aⁿ), a×b (pas a·b). Le français courant (`topic`,
  `question`) garde ses accents.

## Format de sortie

Retourne UNIQUEMENT un objet JSON valide (sans balises markdown, sans texte
avant ou après) :

```
{
  "copy_id": "<copy_id>",
  "exercises": [
    {
      "number": 1,
      "topic": "<competence_label> × <type_erreur_label> de la 1ère hypothèse>",
      "question": "<question simple>",
      "hint": null
    },
    {
      "number": 2,
      "topic": "<même topic que la question 1>",
      "question": "<question renforcée>",
      "hint": null
    },
    {
      "number": 3,
      "topic": "<competence_label> × <type_erreur_label> de la 2ème hypothèse>",
      "question": "<question simple>",
      "hint": null
    },
    {
      "number": 4,
      "topic": "<même topic que la question 3>",
      "question": "<question renforcée>",
      "hint": null
    }
  ]
}
```

## Contraintes

- `number` : numéro global continu (commence à 1, jamais remis à zéro entre
  les hypothèses).
- `topic` : reprend **textuellement** `"<competence_label> × <type_erreur_label>"`
  de l'hypothèse concernée — les 2 questions d'une même hypothèse ont
  **exactement le même** `topic`, et deux hypothèses différentes ont
  obligatoirement deux `topic` différents.
- Exactement **2 questions par hypothèse fournie** : si N hypothèses, N×2
  questions au total, dans le même ordre que la liste `hypotheses` reçue.
- **Format obligatoire de `question`** — contrat de rendu PDF : si la question
  comporte plusieurs sous-questions, rédige d'abord le **contexte** (une ou
  deux phrases plantant le problème, avec les données numériques), puis va **à
  la ligne** (`\n` dans la chaîne JSON) et numérote **chaque** sous-question sur
  sa propre ligne : `1. ...\n2. ...\n3. ...`. Jamais de tiret, de lettre
  (a/b/c), de numérotation collée sans retour à la ligne, ni de simple phrase
  capitalisée pour introduire une sous-question.
- Puissances : toujours `a^n` avec le caret — jamais `an` sans caret. Exposants
  composés entre parenthèses : `a^(n+m)`, `a^(-n)`.
- Multiplication : symbole `×` uniquement — jamais `*`.
- Ensembles : N, Z, Q, R, racines : `sqrt(x)`.
- `hint` : toujours `null`.
- Accents obligatoires dans `topic` et `question`.
