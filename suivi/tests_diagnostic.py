"""
Tests de l'écriture des problèmes du module 4 et de la mesure contre le corpus.

Le risque principal que ces tests couvrent : **le module 4 écrasant l'étalon
contre lequel il est censé se mesurer.** Un corpus qu'on corrige au fur et à
mesure ne mesure plus rien, et le défaut serait invisible — les chiffres
s'amélioreraient tout seuls.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from referentiel.models import Competence, CoutRemediation, TypeErreur
from src.models.domain import (
    CopyGrade,
    DiagnosticContraint,
    ProblemeDetecte,
    QuestionGrade,
    SourceProbleme,
    TeacherDecision,
)
from suivi.diagnostic import confirmer_depuis_correction, enregistrer
from suivi.mesure import comparer, repartition_par_type
from suivi.models import (
    EtatProbleme,
    Evaluation,
    Probleme,
    Session,
    TypeEvaluation,
)


class BaseSuivi(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        cls.prc = TypeErreur.objects.create(
            code="PRC", libelle="Erreur procédurale", definition="…",
            signature="…", coefficient=Decimal("0.15"), remediable=True,
        )
        cls.att = TypeErreur.objects.create(
            code="ATT", libelle="Inattention", definition="…",
            signature="…", coefficient=Decimal("0"), remediable=False,
        )
        cls.idr = Competence.objects.create(
            code="L.IDR", domaine="Calcul litteral et algebre",
            libelle="Identites remarquables", niveau_intro="4eme",
            volume_horaire=Decimal("2"),
        )
        cls.per = Competence.objects.create(
            code="M.PER", domaine="Mesures et grandeurs",
            libelle="Perimetres", niveau_intro="6eme", volume_horaire=Decimal("4"),
        )
        for competence, type_erreur, cout in (
            (cls.idr, cls.cpt, "0.5"), (cls.idr, cls.prc, "0.5"),
            (cls.per, cls.cpt, "1.5"), (cls.per, cls.prc, "0.5"),
        ):
            CoutRemediation.objects.create(
                competence=competence, type_erreur=type_erreur,
                cout_heures=Decimal(cout),
            )
        # Aucune ligne pour `ATT` : c'est voulu, il n'est pas remédiable.

    def _evaluation(self, *, corpus: bool = False) -> Evaluation:
        session = Session.objects.create(
            identifiant_hakili="CORPUS-3E-01" if corpus else "HK-0042",
            corpus_reference=corpus,
        )
        return Evaluation.objects.create(
            session=session,
            type=TypeEvaluation.T0,
            corpus_reference=corpus,
            tague_par="Prénom Nom" if corpus else "",
            date_tagage="2026-07-31" if corpus else None,
        )

    def _diagnostic(self, *couples) -> DiagnosticContraint:
        return DiagnosticContraint(
            copy_id="C1",
            niveau_test="3eme",
            problemes=[
                ProblemeDetecte(
                    code_question=code_q,
                    code_competence=competence,
                    code_type_erreur=type_erreur,
                    citation=citation,
                    source=source,
                )
                for code_q, competence, type_erreur, citation, source in couples
            ],
        )


class TestEcriture(BaseSuivi):
    def test_les_problemes_entrent_en_hypothese(self) -> None:
        """Jamais en `confirme` : c'est T1 qui tranche, pas un modèle de langage."""
        evaluation = self._evaluation()
        resultat = enregistrer(
            evaluation,
            self._diagnostic(
                ("L7", "L.IDR", "CPT", "(x-5)^2", SourceProbleme.modele),
            ),
        )
        probleme = resultat.crees[0]
        self.assertEqual(probleme.etat, EtatProbleme.HYPOTHESE)
        self.assertEqual(probleme.evaluation_origine, evaluation)
        self.assertEqual(probleme.cout_estime, Decimal("0.50"))

    def test_la_citation_devient_la_justification(self) -> None:
        """C'est elle qui rend un désaccord avec le corpus arbitrable."""
        resultat = enregistrer(
            self._evaluation(),
            self._diagnostic(("L7", "L.IDR", "CPT", "écrit (x-5)^2", SourceProbleme.modele)),
        )
        self.assertIn("écrit (x-5)^2", resultat.crees[0].justification)
        self.assertIn("L7", resultat.crees[0].justification)

    def test_deux_questions_une_seule_lacune(self) -> None:
        """La base n'accepte qu'un couple par session — les citations sont gardées,
        pas perdues, parce qu'elles justifient le même problème deux fois."""
        resultat = enregistrer(
            self._evaluation(),
            self._diagnostic(
                ("L5", "L.IDR", "CPT", "option a", SourceProbleme.qcm),
                ("L7", "L.IDR", "CPT", "(x-5)^2", SourceProbleme.modele),
            ),
        )
        self.assertEqual(len(resultat.crees), 1)
        justification = resultat.crees[0].justification
        self.assertIn("L5", justification)
        self.assertIn("L7", justification)
        self.assertIn("(QCM)", justification)

    def test_un_couple_deja_suivi_nest_pas_redouble(self) -> None:
        evaluation = self._evaluation()
        enregistrer(evaluation, self._diagnostic(
            ("L7", "L.IDR", "CPT", "a", SourceProbleme.modele)))
        resultat = enregistrer(evaluation, self._diagnostic(
            ("L9", "L.IDR", "CPT", "b", SourceProbleme.modele)))
        self.assertEqual(resultat.crees, [])
        self.assertEqual(len(resultat.deja_suivis), 1)
        self.assertEqual(Probleme.objects.count(), 1)

    def test_att_coute_zero_et_nest_pas_une_ligne_manquante(self) -> None:
        resultat = enregistrer(
            self._evaluation(),
            self._diagnostic(("L7", "L.IDR", "ATT", "exposant recopié", SourceProbleme.modele)),
        )
        self.assertEqual(resultat.crees[0].cout_estime, Decimal("0"))

    def test_le_cout_total_est_celui_du_referentiel(self) -> None:
        resultat = enregistrer(
            self._evaluation(),
            self._diagnostic(
                ("L7", "L.IDR", "CPT", "a", SourceProbleme.modele),
                ("M3", "M.PER", "CPT", "b", SourceProbleme.modele),
            ),
        )
        self.assertEqual(resultat.cout_total, 2.0)  # 0,5 + 1,5


class TestCorpusProtege(BaseSuivi):
    def test_le_module_4_nécrit_jamais_dans_le_corpus(self) -> None:
        """Un étalon qu'on corrige au fur et à mesure ne mesure plus rien."""
        evaluation = self._evaluation(corpus=True)
        with self.assertRaises(ValidationError) as leve:
            enregistrer(evaluation, self._diagnostic(
                ("L7", "L.IDR", "CPT", "a", SourceProbleme.modele)))
        self.assertIn("étalon", str(leve.exception))
        self.assertEqual(Probleme.objects.count(), 0)

    def test_rien_nest_ecrit_partiellement(self) -> None:
        """L'écriture est atomique : un corpus à moitié écrasé aurait l'air valide."""
        evaluation = self._evaluation(corpus=True)
        with self.assertRaises(ValidationError):
            enregistrer(evaluation, self._diagnostic(
                ("L5", "L.IDR", "CPT", "a", SourceProbleme.modele),
                ("M3", "M.PER", "PRC", "b", SourceProbleme.modele),
            ))
        self.assertEqual(Probleme.objects.count(), 0)


class TestMesure(TestCase):
    """La comparaison est arithmétique — elle se teste sans base ni référentiel."""

    def test_accord_parfait(self) -> None:
        ecart = comparer([("L.IDR", "CPT")], [("L.IDR", "CPT")])
        self.assertEqual(len(ecart.exacts), 1)
        self.assertEqual(ecart.precision, 1.0)
        self.assertEqual(ecart.rappel, 1.0)

    def test_competence_juste_type_faux(self) -> None:
        """Le cas instructif du corpus : périmètre du cercle, `CNS` contre `PRC`.
        Même compétence, deux remédiations sans rapport."""
        ecart = comparer([("M.PER", "CNS")], [("M.PER", "PRC")])
        self.assertEqual(ecart.exacts, [])
        self.assertEqual(ecart.type_faux, [("M.PER", "CNS", "PRC")])
        self.assertEqual(ecart.rappel, 0.0)
        self.assertEqual(ecart.rappel_competence, 1.0)

    def test_manque_et_en_trop(self) -> None:
        ecart = comparer([("L.IDR", "CPT")], [("M.PER", "PRC")])
        self.assertEqual(ecart.manques, [("L.IDR", "CPT")])
        self.assertEqual(ecart.en_trop, [("M.PER", "PRC")])

    def test_un_exact_nest_pas_consomme_par_un_appariement_approximatif(self) -> None:
        """Si l'appariement sur la compétence passait en premier, l'exact
        disparaîtrait et le taux serait faux à la baisse."""
        ecart = comparer(
            [("L.IDR", "CPT"), ("L.IDR", "PRC")],
            [("L.IDR", "PRC")],
        )
        self.assertEqual(ecart.exacts, [("L.IDR", "PRC")])
        self.assertEqual(ecart.manques, [("L.IDR", "CPT")])
        self.assertEqual(ecart.type_faux, [])

    def test_etalon_vide_ne_divise_pas_par_zero(self) -> None:
        ecart = comparer([], [("L.IDR", "CPT")])
        self.assertEqual(ecart.rappel, 0.0)
        self.assertEqual(ecart.precision, 0.0)

    def test_repartition_par_type(self) -> None:
        couples = [("L.IDR", "CPT"), ("M.PER", "CPT"), ("N.ADD", "PRC")]
        self.assertEqual(repartition_par_type(couples), {"CPT": 2, "PRC": 1})


class TestConfirmationAutomatique(BaseSuivi):
    """`confirmer_depuis_correction` — module 5 (suite) : la copie T1 est déjà
    corrigée et validée, il ne reste qu'à trancher confirmé/écarté."""

    def _hypothese(self, *, competence, type_erreur, exercices, session=None) -> Probleme:
        session = session or Session.objects.create(identifiant_hakili="HK-0042")
        return Probleme.objects.create(
            session=session, competence=competence, type_erreur=type_erreur,
            etat=EtatProbleme.HYPOTHESE, cout_estime=Decimal("0.5"),
            exercices_confirmation=exercices,
        )

    def _evaluation_t1(self, session) -> Evaluation:
        return Evaluation.objects.create(session=session, type=TypeEvaluation.T1)

    def _grade(self, *notes) -> CopyGrade:
        return CopyGrade(
            copy_id="copie-t1",
            total_score=sum(score for _, score in notes),
            total_possible=float(len(notes)),
            questions=[
                QuestionGrade(
                    rubric_item_id=str(numero), score=score, confidence=0.9,
                    comment="", observed_answer="…", requires_review=False,
                )
                for numero, score in notes
            ],
        )

    def test_toutes_les_questions_reussies_ecarte(self) -> None:
        probleme = self._hypothese(competence=self.idr, type_erreur=self.cpt, exercices=[1, 2])
        resultat = confirmer_depuis_correction(
            self._evaluation_t1(probleme.session), self._grade((1, 1.0), (2, 1.0)),
        )
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.ECARTE)
        self.assertEqual(resultat.ecartes, [probleme])
        self.assertEqual(resultat.confirmes, [])

    def test_une_question_ratee_confirme(self) -> None:
        probleme = self._hypothese(competence=self.idr, type_erreur=self.cpt, exercices=[1, 2])
        resultat = confirmer_depuis_correction(
            self._evaluation_t1(probleme.session), self._grade((1, 1.0), (2, 0.0)),
        )
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.CONFIRME)
        self.assertEqual(resultat.confirmes, [probleme])

    def test_question_absente_de_la_correction_compte_comme_ratee(self) -> None:
        """Une absence ne se devine jamais en réussite (même principe que
        `referentiel.diagnostic`)."""
        probleme = self._hypothese(competence=self.idr, type_erreur=self.cpt, exercices=[1, 2])
        resultat = confirmer_depuis_correction(
            self._evaluation_t1(probleme.session), self._grade((1, 1.0)),
        )
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.CONFIRME)
        self.assertEqual(resultat.confirmes, [probleme])

    def test_att_toujours_ecarte_meme_ratee(self) -> None:
        """`ATT` ne peut jamais être confirmé (protocole §3) — même raté aux
        deux questions, il est écarté, jamais promu vers la remédiation."""
        probleme = self._hypothese(competence=self.idr, type_erreur=self.att, exercices=[1, 2])
        resultat = confirmer_depuis_correction(
            self._evaluation_t1(probleme.session), self._grade((1, 0.0), (2, 0.0)),
        )
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.ECARTE)
        self.assertEqual(resultat.ecartes, [probleme])

    def test_decision_enseignant_prime_sur_lia(self) -> None:
        """Un refus enseignant avec sa propre note l'emporte sur la proposition IA
        — la même règle que `reponses_depuis_correction`."""
        probleme = self._hypothese(competence=self.idr, type_erreur=self.cpt, exercices=[1, 2])
        grade = self._grade((1, 1.0), (2, 1.0))
        grade.questions[1].teacher_decision = TeacherDecision.refused
        grade.questions[1].teacher_score = 0.0
        resultat = confirmer_depuis_correction(self._evaluation_t1(probleme.session), grade)
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.CONFIRME)
        self.assertEqual(resultat.confirmes, [probleme])

    def test_hypothese_sans_exercices_non_touchee(self) -> None:
        """Retombe sur la saisie manuelle — aucune correspondance devinée."""
        session = Session.objects.create(identifiant_hakili="HK-0042")
        probleme = self._hypothese(
            competence=self.idr, type_erreur=self.cpt, exercices=[], session=session,
        )
        resultat = confirmer_depuis_correction(
            self._evaluation_t1(session), self._grade((1, 0.0)),
        )
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.HYPOTHESE)
        self.assertEqual(resultat.confirmes, [])
        self.assertEqual(resultat.ecartes, [])

    def test_session_corpus_refusee(self) -> None:
        session = Session.objects.create(
            identifiant_hakili="CORPUS-3E-01", corpus_reference=True,
        )
        probleme = self._hypothese(
            competence=self.idr, type_erreur=self.cpt, exercices=[1], session=session,
        )
        evaluation = Evaluation.objects.create(
            session=session, type=TypeEvaluation.T1, corpus_reference=True,
            tague_par="Prénom Nom", date_tagage="2026-07-31",
        )
        resultat = confirmer_depuis_correction(evaluation, self._grade((1, 1.0)))
        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.HYPOTHESE)
        self.assertEqual(resultat.confirmes, [])
        self.assertEqual(resultat.ecartes, [])


class CommandeDepuisCorrection(TestCase):
    """`manage.py diagnostiquer --correction <id>` — le chemin de production.

    Ce que ces tests protègent : la commande refuse **avant** de diagnostiquer
    quand la reprise serait fausse plutôt qu'incomplète. Un diagnostic tiré d'une
    correction en mode libre rattacherait des réponses à des questions qui ne
    sont pas les leurs, et rien dans le compte rendu ne le signalerait.
    """

    def _correction(self, **kwargs):
        from correction_web.models import Correction

        defauts = dict(
            copy_id="copie-01", identifiant_hakili="HK-0042",
            bareme_id="socle_5eme", resultat=None,
        )
        return Correction.objects.create(**{**defauts, **kwargs})

    def _lancer(self, correction) -> str:
        from io import StringIO

        from django.core.management import call_command

        sortie = StringIO()
        call_command(
            "diagnostiquer", correction=correction.pk, sans_modele=True, stdout=sortie
        )
        return sortie.getvalue()

    def test_correction_inconnue(self) -> None:
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "identifiant 9999"):
            call_command("diagnostiquer", correction=9999, sans_modele=True)

    def test_mode_libre_refuse(self) -> None:
        """Sans barème v2, il n'y a aucun code de question à rattacher."""
        from django.core.management.base import CommandError

        correction = self._correction(bareme_id="")
        with self.assertRaisesMessage(CommandError, "mode libre"):
            self._lancer(correction)

    def test_test_archive_refuse(self) -> None:
        from django.core.management.base import CommandError

        correction = self._correction(bareme_id="hakili_3e_v1")
        with self.assertRaisesMessage(CommandError, "référentiel v2"):
            self._lancer(correction)

    def test_correction_sans_resultat_refusee(self) -> None:
        from django.core.management.base import CommandError

        correction = self._correction()
        with self.assertRaisesMessage(CommandError, "pas de résultat"):
            self._lancer(correction)

    def test_correction_arretee_avant_la_notation(self) -> None:
        """Transcrite mais pas notée : il n'y a pas de réponses à reprendre."""
        from django.core.management.base import CommandError

        correction = self._correction(
            resultat={"copy_id": "copie-01", "ingestion": {}, "grade": None}
        )
        with self.assertRaisesMessage(CommandError, "jusqu'à la notation"):
            self._lancer(correction)

    def test_relecture_enseignant_inachevee_signalee(self) -> None:
        """Elle n'empêche pas de diagnostiquer, mais elle doit être dite : une
        partie des réponses est prise telle que l'IA les a notées."""
        correction = self._correction(resultat={
            "copy_id": "copie-01",
            "ingestion": {},
            "rubric": {
                "subject": "mathematics", "total_points": 1.0,
                "items": [{"id": "D1", "label": "…", "max_score": 1.0}],
            },
            "grade": {
                "copy_id": "copie-01", "total_score": 0.0, "total_possible": 1.0,
                "validation_complete": False,
                "questions": [{
                    "rubric_item_id": "D1", "score": 0.0, "confidence": 0.9,
                    "comment": "", "observed_answer": "4800", "requires_review": False,
                }],
            },
        })
        compte_rendu = self._lancer(correction)
        self.assertIn("1 question(s), dont 1 non réussie(s)", compte_rendu)
        self.assertIn("validation enseignant", compte_rendu)
