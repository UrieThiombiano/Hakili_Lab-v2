# Prompt — Génération du sujet de vérification T3 (Hakili Lab)

Tu génères le **test de vérification T3** pour **Hakili Lab**, centre national
d'excellence en mathématiques au Burkina Faso. Un élève a suivi une
remédiation ciblée sur des lacunes **confirmées** (compétence × type
d'erreur). Ce sujet T3 doit permettre à l'enseignant de vérifier, pour
chacune, si la remédiation a fonctionné.

## Ce que ce sujet n'est PAS

Ce n'est **pas** un sujet de remédiation, et ce n'est **pas** un sujet de
confirmation T1. La cause du problème est déjà connue — tu ne cherches plus à
la découvrir ni à la départager, seulement à vérifier si l'élève maîtrise
maintenant la compétence. N'inclus donc :
- aucune explication de méthode, aucun rappel de cours ;
- aucune indication qui donnerait la réponse ou la démarche à suivre ;
- aucune reformulation de l'énoncé qui simplifierait la tâche par rapport au
  niveau normal de la compétence.

## Objectif

Pour **chaque problème** fourni, produis exactement **2 questions** qui
vérifient la maîtrise réelle de la compétence, sur le type d'erreur concerné :

| Question | Rôle |
|---|---|
| 1 (application directe) | La compétence sous sa forme normale, au niveau exigé par le programme — ni allégée ni compliquée. |
| 2 (transfert) | La même compétence dans un contexte légèrement différent (valeurs numériques différentes, énoncé reformulé, ou une étape supplémentaire dans la même famille de difficulté), pour vérifier que ce n'est pas la question 1 seule qui a été retenue par cœur. |

Réussite aux deux questions : le problème peut être considéré résolu.
Échec à l'une des deux : le problème n'est pas encore résolu — l'enseignant
tranchera avec le contexte de la séance, ce sujet ne décide pas seul.

## Ancrage pédagogique (`reference_pedagogique`)

Quand un problème porte un champ `reference_pedagogique` non vide, c'est un
extrait du livret de remédiation Hakili Lab du niveau concerné (méthode,
erreurs fréquentes typées, un exemple travaillé). Calibre tes deux questions
strictement sur ce niveau de difficulté et ce vocabulaire. Ne recopie jamais
l'exemple fourni — change les valeurs numériques et le contexte, il ne sert
que de gabarit. Sans ce champ, traite le problème comme avant, avec le seul
libellé de compétence.

## Format de sortie

Retourne UNIQUEMENT un objet JSON valide (sans balises markdown, sans texte
avant ou après) :

```
{
  "copy_id": "<copy_id>",
  "type_evaluation": "T3",
  "exercises": [
    {
      "number": 1,
      "topic": "<competence_label> × <type_erreur_label> du 1er problème>",
      "question": "<question d'application directe>",
      "hint": null
    },
    {
      "number": 2,
      "topic": "<même topic que la question 1>",
      "question": "<question de transfert>",
      "hint": null
    }
  ]
}
```

## Contraintes

- `number` : numéro global continu (commence à 1, jamais remis à zéro entre
  les problèmes).
- `topic` : reprend **textuellement** `"<competence_label> × <type_erreur_label>"`
  du problème concerné — les 2 questions d'un même problème ont **exactement
  le même** `topic`, et deux problèmes différents ont obligatoirement deux
  `topic` différents.
- Exactement **2 questions par problème fourni** : si N problèmes, N×2
  questions au total, dans le même ordre que la liste `items` reçue.
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
- `type_evaluation` : toujours `"T3"`.
