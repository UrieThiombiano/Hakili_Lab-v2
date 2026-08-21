"""
Diagnostic contraint d'une copie (module 4).

    python manage.py diagnostiquer --correction 42                # une copie corrigée
    python manage.py diagnostiquer --fichier data/reponses/copie.yaml
    python manage.py diagnostiquer --correction 42 --sans-modele  # QCM seuls
    python manage.py diagnostiquer --correction 42 --enregistrer 7   # écrit en base
    python manage.py diagnostiquer --fichier … --comparer 12      # contre le corpus

Les deux entrées, et pourquoi il y en a deux
--------------------------------------------
`--correction` est le chemin de production : il repart d'une copie **déjà
corrigée**, dont chaque réponse a été relevée par la correction et validée par
l'enseignant. Aucune lecture supplémentaire de la copie, aucun découpage — le
barème porte les mêmes codes de question que le référentiel.

`--fichier` reste pour les essais et le rejeu : un YAML écrit à la main se relit,
se compare et se reprend, ce qui n'est vrai d'aucune sortie de modèle.

Pourquoi l'écriture n'est pas le comportement par défaut
--------------------------------------------------------
`taguer_corpus` écrit par défaut et `--a-blanc` s'abstient : il ne touche que des
sessions de corpus, qui n'engagent personne. Ici, écrire dépose des hypothèses
dans le parcours d'un **élève réel** — donc dans son coût total, son palier, et
vraisemblablement ce que sa famille paiera. L'asymétrie est délibérée : il faut le
demander.

Format du fichier de réponses
-----------------------------
    identifiant_hakili: HK-0042
    niveau_test: 3eme
    copy_id: ""                 # facultatif
    reponses:
      - question: L5
        reponse: "a"            # QCM : la lettre cochée
      - question: L7
        reponse: ""
        vide: true              # l'élève n'a rien écrit
      - question: N3
        reponse: "12,5"
        correcte: true          # question réussie — non diagnostiquée
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from referentiel.diagnostic import (
    ReponseEleve,
    diagnostiquer,
    reponses_depuis_correction,
)
from referentiel.models import Competence, NiveauTest, TypeErreur
from src.models.domain import SourceProbleme
from suivi.diagnostic import enregistrer
from suivi.mesure import comparer, repartition_par_type
from suivi.models import Evaluation


class Command(BaseCommand):
    help = "Diagnostic contraint d'une copie — module 4 du chantier v2."

    def add_arguments(self, parser) -> None:
        entree = parser.add_mutually_exclusive_group(required=True)
        entree.add_argument(
            "--correction",
            type=int,
            metavar="ID_CORRECTION",
            help="Copie déjà corrigée : les réponses sont reprises de la "
            "correction, sans relire la copie.",
        )
        entree.add_argument("--fichier", help="Fichier YAML des réponses.")
        parser.add_argument(
            "--sans-modele",
            action="store_true",
            help="N'appelle aucun modèle : seuls les QCM sont diagnostiqués. "
            "Utile sans clé d'API, et pour vérifier la part mécanique seule.",
        )
        parser.add_argument(
            "--enregistrer",
            type=int,
            metavar="ID_EVALUATION",
            help="Écrit les problèmes dans la session de cette évaluation. "
            "Sans cette option, rien n'est écrit.",
        )
        parser.add_argument(
            "--comparer",
            type=int,
            metavar="ID_EVALUATION",
            help="Compare le résultat aux problèmes d'une évaluation du corpus "
            "de référence, et mesure l'écart (jalon du module 4).",
        )

    def handle(self, *args, **options) -> None:
        # Le compte rendu emploie « └ », absent de cp1252 — l'encodage par défaut
        # d'une console Windows. Sans ça, le rapport s'interrompt sur une trace
        # d'encodage au milieu de la liste des problèmes, ce qui donne l'illusion
        # d'un diagnostic en échec alors qu'il a abouti.
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, OSError):  # flux déjà remplacé (tests)
            pass

        if options["correction"]:
            niveau, reponses, copy_id = self._depuis_correction(options["correction"])
        else:
            chemin = Path(options["fichier"])
            if not chemin.exists():
                raise CommandError(f"{chemin} est introuvable.")

            donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
            niveau, reponses, copy_id = self._valider(donnees, chemin)

        client = None if options["sans_modele"] else self._client()

        resultat = diagnostiquer(
            niveau_test=niveau, reponses=reponses, client=client, copy_id=copy_id
        )
        self._rendre_compte(resultat)

        if options["comparer"]:
            self._comparer(resultat, options["comparer"])

        if options["enregistrer"]:
            self._enregistrer(resultat, options["enregistrer"])
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nRien n'a été écrit. `--enregistrer <id évaluation>` pour "
                    "déposer ces hypothèses dans le parcours de l'élève."
                )
            )

    # ── Entrée ───────────────────────────────────────────────────────────────

    def _valider(self, donnees: dict, chemin: Path) -> tuple[str, list[ReponseEleve], str]:
        niveau = donnees.get("niveau_test")
        if not niveau:
            raise CommandError("`niveau_test` est obligatoire (6eme, 5eme, … tleD).")
        if niveau not in NiveauTest.values:
            raise CommandError(
                f"Niveau {niveau!r} inconnu. Attendu parmi "
                f"{', '.join(NiveauTest.values)}."
            )

        brutes = donnees.get("reponses")
        if not isinstance(brutes, list) or not brutes:
            raise CommandError(f"{chemin.name} : `reponses` doit être une liste non vide.")

        reponses: list[ReponseEleve] = []
        for rang, item in enumerate(brutes, start=1):
            if not isinstance(item, dict) or not item.get("question"):
                raise CommandError(f"réponse {rang} : `question` est obligatoire.")
            reponses.append(
                ReponseEleve(
                    code_question=str(item["question"]).strip(),
                    contenu=str(item.get("reponse") or ""),
                    vide=bool(item.get("vide", False)),
                    correcte=item.get("correcte"),
                )
            )

        return niveau, reponses, str(donnees.get("copy_id") or chemin.stem)

    def _depuis_correction(self, identifiant: int) -> tuple[str, list[ReponseEleve], str]:
        """Reprend les réponses d'une copie déjà corrigée.

        Rien n'est relu de la copie : la correction a déjà relevé, pour chaque
        question du barème, ce que l'élève a écrit. Les seuls contrôles portent
        sur ce qui rendrait la reprise fausse plutôt qu'incomplète — un test hors
        référentiel, ou une correction qui n'est pas allée jusqu'au bout.
        """
        from correction_web.models import Correction
        from src.pipeline.serialisation import deserialiser

        try:
            correction = Correction.objects.get(pk=identifiant)
        except Correction.DoesNotExist:
            raise CommandError(f"Aucune correction n'a l'identifiant {identifiant}.")

        if not correction.bareme_id.startswith("socle_"):
            raise CommandError(
                f"La correction {identifiant} porte sur "
                f"{correction.bareme_id or 'le mode libre'}, dont les questions ne "
                f"sont pas celles du référentiel v2. Le diagnostic contraint ne "
                f"peut rien y rattacher."
            )
        niveau = correction.bareme_id.removeprefix("socle_")
        if niveau not in NiveauTest.values:
            raise CommandError(f"Niveau {niveau!r} inconnu (barème {correction.bareme_id}).")

        if not correction.resultat:
            raise CommandError(
                f"La correction {identifiant} n'a pas de résultat enregistré "
                f"(état : {correction.etat})."
            )

        resultat = deserialiser(correction.resultat)
        if resultat.grade is None or resultat.rubric is None:
            raise CommandError(
                f"La correction {identifiant} n'est pas allée jusqu'à la notation "
                f"(état : {correction.etat}) — il n'y a pas de réponses à reprendre."
            )

        reponses = reponses_depuis_correction(resultat.grade, resultat.rubric)
        traitees = [r for r in reponses if r.correcte is not True]
        self.stdout.write(
            f"Correction {identifiant} — {correction.copy_id}, {correction.bareme_id} : "
            f"{len(reponses)} question(s), dont {len(traitees)} non réussie(s) à "
            f"diagnostiquer."
        )
        if not correction.resultat.get("grade", {}).get("validation_complete"):
            # Le diagnostic prend la décision de l'enseignant quand elle existe ;
            # si la relecture n'est pas finie, il travaille en partie sur des
            # propositions de l'IA. Ça ne l'empêche pas de tourner, mais celui qui
            # lit le compte rendu doit le savoir.
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠ La validation enseignant de cette copie n'est pas terminée : "
                    "les questions non tranchées sont prises telles que l'IA les a notées."
                )
            )

        return niveau, reponses, correction.copy_id

    def _client(self):
        """Le client de diagnostic, ou rien — sans jamais faire échouer la commande.

        Une clé d'API absente ne doit pas empêcher la part mécanique de tourner :
        les QCM se diagnostiquent sans modèle, et c'est un quart des questions
        (71 sur 280).
        """
        try:
            from src.api.claude_client import ClaudeClient

            return ClaudeClient()
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(
                self.style.WARNING(
                    f"Aucun client de diagnostic ({exc}). Seuls les QCM seront "
                    f"traités — les autres questions seront écartées et listées."
                )
            )
            return None

    # ── Compte rendu ─────────────────────────────────────────────────────────

    def _rendre_compte(self, resultat) -> None:
        libelles = dict(Competence.objects.values_list("code", "libelle"))
        types = dict(TypeErreur.objects.values_list("code", "libelle"))

        mecaniques = sum(
            1 for p in resultat.problemes if p.source == SourceProbleme.qcm
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(resultat.problemes)} problème(s) — {mecaniques} par QCM "
                f"(sans modèle), {len(resultat.problemes) - mecaniques} par "
                f"reconnaissance de signature."
            )
        )

        for p in resultat.problemes:
            self.stdout.write(
                f"  {p.code_question:5} {p.code_competence:12} × "
                f"{p.code_type_erreur:4} [{p.source.value}]"
            )
            # Le libellé en toutes lettres est rappelé pour la même raison qu'au
            # tagage du corpus : un code valide mais mal choisi passe toute la
            # validation sans un mot, et ne se voit qu'à la relecture.
            self.stdout.write(
                f"  {'':5} └ {libelles.get(p.code_competence, '?')} × "
                f"{types.get(p.code_type_erreur, '?')}"
            )
            self.stdout.write(f"  {'':5}   « {p.citation.strip()[:110]} »")

        if resultat.questions_ecartees:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(resultat.questions_ecartees)} question(s) écartée(s) — "
                    f"personne ne les a jugées, leur absence de problème ne vaut "
                    f"pas réussite :"
                )
            )
            for code, motif in sorted(resultat.questions_ecartees.items()):
                self.stdout.write(f"  · {code:5} {motif}")

        if resultat.rejets:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{len(resultat.rejets)} sortie(s) du modèle refusée(s) après "
                    f"redemande — la copie ne compte pas comme sortie valide au "
                    f"jalon du module 4 :"
                )
            )
            for motif in resultat.rejets:
                self.stdout.write(f"  · {motif}")
        elif resultat.appels_modele:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSortie valide — aucun code hors référentiel "
                    f"({resultat.appels_modele} appel(s) au modèle)."
                )
            )

    # ── Mesure contre le corpus ──────────────────────────────────────────────

    def _comparer(self, resultat, id_evaluation: int) -> None:
        evaluation = Evaluation.objects.filter(pk=id_evaluation).first()
        if evaluation is None:
            raise CommandError(f"Aucune évaluation {id_evaluation}.")
        if not evaluation.corpus_reference:
            raise CommandError(
                f"L'évaluation {id_evaluation} n'appartient pas au corpus de "
                f"référence. La mesure n'a de sens que contre un tagage manuel."
            )

        etalon = list(
            evaluation.problemes_reveles.values_list("competence_id", "type_erreur_id")
        )
        produit = [(p.code_competence, p.code_type_erreur) for p in resultat.problemes]
        ecart = comparer(etalon, produit)

        self.stdout.write(
            self.style.SUCCESS(f"\n── Écart contre le corpus (évaluation {id_evaluation})")
        )
        self.stdout.write(
            f"  étalon {ecart.total_etalon} problème(s) · produit {ecart.total_produit}"
        )
        self.stdout.write(
            f"  exacts {len(ecart.exacts)} · compétence juste type faux "
            f"{len(ecart.type_faux)} · manqués {len(ecart.manques)} · en trop "
            f"{len(ecart.en_trop)}"
        )
        self.stdout.write(
            f"  précision {ecart.precision:.0%} · rappel {ecart.rappel:.0%} · "
            f"rappel sur la compétence seule {ecart.rappel_competence:.0%}"
        )
        self.stdout.write(
            f"  coût : étalon {ecart.cout_etalon:g} h, produit "
            f"{ecart.cout_produit:g} h, écart {ecart.ecart_cout:+g} h"
        )

        if ecart.type_faux:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Compétence trouvée, type d'erreur différent — c'est ce qui "
                    "envoie le tuteur travailler la mauvaise chose :"
                )
            )
            for competence, attendu, obtenu in ecart.type_faux:
                self.stdout.write(f"    {competence:12} corpus {attendu} ≠ module 4 {obtenu}")

        for titre, couples in (
            ("Manqués (lacune non vue)", ecart.manques),
            ("En trop (lacune inventée)", ecart.en_trop),
        ):
            if couples:
                self.stdout.write(self.style.WARNING(f"\n  {titre} :"))
                for competence, type_erreur in couples:
                    self.stdout.write(f"    {competence:12} × {type_erreur}")

        self.stdout.write(
            f"\n  répartition étalon  : {repartition_par_type(etalon)}"
        )
        self.stdout.write(
            f"  répartition module 4: {repartition_par_type(produit)}"
        )

    # ── Écriture ─────────────────────────────────────────────────────────────

    def _enregistrer(self, resultat, id_evaluation: int) -> None:
        evaluation = Evaluation.objects.filter(pk=id_evaluation).first()
        if evaluation is None:
            raise CommandError(f"Aucune évaluation {id_evaluation}.")

        ecriture = enregistrer(evaluation, resultat)
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(ecriture.crees)} problème(s) écrits en hypothèse sur la "
                f"session {evaluation.session_id} — {ecriture.cout_total:g} h estimées."
            )
        )
        if ecriture.deja_suivis:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(ecriture.deja_suivis)} couple(s) déjà suivis sur cette "
                    f"session, non redoublés :"
                )
            )
            for ligne in ecriture.deja_suivis:
                self.stdout.write(f"  · {ligne}")
        self.stdout.write(
            "\nCes problèmes sont des **hypothèses**. C'est T1 qui les confirme "
            "ou les écarte — jamais le diagnostic automatique."
        )
