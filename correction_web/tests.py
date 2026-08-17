"""
Tests du flux de correction.

Le pipeline lui-même n'est pas exécuté : ces tests vérifient l'enchaînement des
états, les deux arrêts de validation humaine, la primauté de la décision de
l'enseignant sur la proposition de l'IA, et le cloisonnement par élève.

Le point le plus important est `TestValidationDesNotes` : c'est là que se joue
D-CEO-16 — « l'IA propose, l'enseignant décide ». Une régression y produirait des
notes fausses sur des bulletins réels.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.tests import _ELEVES, _PERSONNEL, _cle
from correction_web.models import Correction, EtatCorrection
from correction_web.serialisation import deserialiser, serialiser
from suivi_web.jetons import jeton_eleve


def _resultat_apres_correction(copy_id="copie-test"):
    """`PipelineResult` minimal, tel qu'il est après la Phase A."""
    from pathlib import Path

    from src.models.domain import (
        CopyGrade,
        IngestionResult,
        PageTranscription,
        QuestionGrade,
        Rubric,
        RubricItem,
        TranscriptionResult,
    )
    from src.pipeline.pipeline import PipelineResult

    rubric = Rubric(
        subject="mathematics",
        total_points=2.0,
        items=[
            RubricItem(id="N1", label="Écrire en chiffres", max_score=1.0),
            RubricItem(id="N2", label="Comparer deux décimaux", max_score=1.0),
        ],
    )
    grade = CopyGrade(
        copy_id=copy_id,
        total_score=1.0,
        total_possible=2.0,
        questions=[
            QuestionGrade(
                rubric_item_id="N1", score=1.0, confidence=0.9, comment="juste",
                observed_answer="147", correct_answer="147", requires_review=False,
            ),
            QuestionGrade(
                rubric_item_id="N2", score=0.0, confidence=0.4, comment="faux",
                observed_answer="7,09", correct_answer="7,5", requires_review=True,
            ),
        ],
    )
    return PipelineResult(
        copy_id=copy_id,
        student_name="Charles KABRE",
        ingestion=IngestionResult(
            copy_id=copy_id, total_pages=1, pages=[Path("p1.png")], output_dir=Path(".")
        ),
        transcription=TranscriptionResult(
            copy_id=copy_id,
            global_quality="good",
            pages=[PageTranscription(page_number=1, content="N1) 147", confidence=0.9)],
        ),
        grade=grade,
        rubric=rubric,
    )


class BaseCorrection(TestCase):
    def setUp(self) -> None:
        for cible, valeur in (("get_personnel", _PERSONNEL), ("get_eleves", _ELEVES)):
            c = patch(f"src.integrations.google_sheets.{cible}", return_value=valeur)
            c.start()
            self.addCleanup(c.stop)

        c = patch(
            "src.integrations.google_sheets.get_eleve_by_identifiant",
            side_effect=lambda i: next(
                (e for e in _ELEVES if e["identifiant_hakili"] == i), None
            ),
        )
        c.start()
        self.addCleanup(c.stop)

    def connecter(self, nom="DIANE", prenom="Abasse", pin="1234"):
        return self.client.post(
            reverse("comptes:connexion"), {"cle": _cle(nom, prenom), "pin": pin}, follow=True
        )

    def correction_en_validation(self, identifiant="HAK-2026-0001") -> Correction:
        resultat = _resultat_apres_correction()
        return Correction.objects.create(
            copy_id=resultat.copy_id,
            identifiant_hakili=identifiant,
            eleve_nom="KABRE",
            eleve_prenom="Charles",
            bareme_id="socle_3eme",
            etat=EtatCorrection.VALIDATION,
            progression=60,
            resultat=serialiser(resultat),
        )


class TestSerialisation(TestCase):
    def test_aller_retour_conserve_le_contenu(self) -> None:
        """Sérialisation explicite plutôt que pickle : elle doit rendre exactement
        les mêmes objets, sinon la correction reprend sur des données fausses."""
        origine = _resultat_apres_correction()
        copie = deserialiser(serialiser(origine))

        self.assertEqual(copie.copy_id, origine.copy_id)
        self.assertEqual(copie.grade.total_possible, 2.0)
        self.assertEqual(len(copie.grade.questions), 2)
        self.assertEqual(copie.grade.questions[1].observed_answer, "7,09")
        self.assertEqual(len(copie.rubric.items), 2)
        self.assertEqual(copie.transcription.pages[0].content, "N1) 147")

    def test_serialisation_est_json_compatible(self) -> None:
        import json

        json.dumps(serialiser(_resultat_apres_correction()))


class TestRelectureTranscription(BaseCorrection):
    def test_les_corrections_de_l_enseignant_sont_conservees(self) -> None:
        resultat = _resultat_apres_correction()
        correction = Correction.objects.create(
            copy_id=resultat.copy_id,
            identifiant_hakili="HAK-2026-0001",
            eleve_nom="KABRE",
            etat=EtatCorrection.RELECTURE,
            resultat=serialiser(resultat),
        )
        self.connecter()

        with patch("correction_web.taches.lancer_correction") as lancer:
            self.client.post(
                reverse(
                    "correction_web:valider_transcription",
                    args=[jeton_eleve(correction.copy_id)],
                ),
                {"page_1": "N1) 147 corrigé à la main"},
            )

        correction.refresh_from_db()
        relu = deserialiser(correction.resultat)
        self.assertEqual(relu.transcription.pages[0].content, "N1) 147 corrigé à la main")
        lancer.assert_called_once()

    def _correction_en_relecture_avec_scan(self, tmp_dir) -> Correction:
        """Une correction en relecture dont la page 1 a une image réellement sur
        disque, comme au sortir de l'ingestion (`src/pipeline/ingestion.py`)."""
        from pathlib import Path

        image = Path(tmp_dir) / "page_01.jpg"
        image.write_bytes(b"\xff\xd8\xff\xe0donnees-jpeg-factices")

        resultat = _resultat_apres_correction()
        resultat.ingestion.pages = [image]
        return Correction.objects.create(
            copy_id=resultat.copy_id,
            identifiant_hakili="HAK-2026-0001",
            eleve_nom="KABRE",
            etat=EtatCorrection.RELECTURE,
            resultat=serialiser(resultat),
        )

    def test_relecture_affiche_la_copie_scannee_a_cote_de_la_transcription(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            correction = self._correction_en_relecture_avec_scan(tmp_dir)
            self.connecter()
            jeton = jeton_eleve(correction.copy_id)

            reponse = self.client.get(reverse("correction_web:suivre", args=[jeton]))

            self.assertContains(
                reponse,
                reverse("correction_web:page_image", args=[jeton, 1]),
            )

    def test_page_sans_image_sur_disque_reste_relisible(self) -> None:
        """`runs/` peut avoir disparu (pas de volume persistant, voir
        `correction_web/serialisation.py`) : la relecture doit rester utilisable
        sans image plutôt que de casser l'écran."""
        resultat = _resultat_apres_correction()  # ingestion.pages pointe vers un fichier inexistant
        correction = Correction.objects.create(
            copy_id=resultat.copy_id,
            identifiant_hakili="HAK-2026-0001",
            eleve_nom="KABRE",
            etat=EtatCorrection.RELECTURE,
            resultat=serialiser(resultat),
        )
        self.connecter()
        jeton = jeton_eleve(correction.copy_id)

        reponse = self.client.get(reverse("correction_web:suivre", args=[jeton]))

        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, 'class="relecture-image"')

    def test_page_image_sert_le_fichier_a_une_personne_autorisee(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            correction = self._correction_en_relecture_avec_scan(tmp_dir)
            self.connecter()

            reponse = self.client.get(
                reverse("correction_web:page_image", args=[jeton_eleve(correction.copy_id), 1])
            )

            self.assertEqual(reponse.status_code, 200)
            self.assertEqual(reponse["Content-Type"], "image/jpeg")
            self.assertEqual(reponse.content, b"\xff\xd8\xff\xe0donnees-jpeg-factices")

    def test_page_image_inexistante_donne_404(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            correction = self._correction_en_relecture_avec_scan(tmp_dir)
            self.connecter()

            reponse = self.client.get(
                reverse("correction_web:page_image", args=[jeton_eleve(correction.copy_id), 7])
            )

            self.assertEqual(reponse.status_code, 404)


class TestValidationDesNotes(BaseCorrection):
    """D-CEO-16 : la décision de l'enseignant prime toujours."""

    def _valider(self, correction, donnees):
        with patch("correction_web.taches.lancer_diagnostic") as lancer:
            self.client.post(
                reverse(
                    "correction_web:valider_notes", args=[jeton_eleve(correction.copy_id)]
                ),
                donnees,
            )
        correction.refresh_from_db()
        return deserialiser(correction.resultat), lancer

    def test_tout_accepter_garde_les_notes_de_l_ia(self) -> None:
        correction = self.correction_en_validation()
        self.connecter()
        resultat, lancer = self._valider(
            correction, {"decision_N1": "accepted", "decision_N2": "accepted"}
        )
        self.assertEqual(resultat.grade.final_score, 1.0)
        self.assertEqual(resultat.grade.final_score_on_20, 10.0)
        lancer.assert_called_once()

    def test_refuser_impose_la_note_de_l_enseignant(self) -> None:
        """L'IA avait mis 0 à N2 ; l'enseignant estime la réponse juste."""
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction,
            {"decision_N1": "accepted", "decision_N2": "refused", "note_N2": "1"},
        )
        self.assertEqual(resultat.grade.final_score, 2.0)
        self.assertEqual(resultat.grade.final_score_on_20, 20.0)

    def test_note_saisie_bornee_au_bareme(self) -> None:
        """Une saisie au-delà du barème ne doit pas gonfler la note au-dessus du
        maximum — sinon une faute de frappe produit un 25/20."""
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction,
            {"decision_N1": "accepted", "decision_N2": "refused", "note_N2": "99"},
        )
        self.assertEqual(resultat.grade.questions[1].teacher_score, 1.0)

    def test_note_illisible_vaut_zero_sans_bloquer(self) -> None:
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction,
            {"decision_N1": "accepted", "decision_N2": "refused", "note_N2": "abc"},
        )
        self.assertEqual(resultat.grade.questions[1].teacher_score, 0.0)

    def test_note_negative_ramenee_a_zero(self) -> None:
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction,
            {"decision_N1": "accepted", "decision_N2": "refused", "note_N2": "-5"},
        )
        self.assertEqual(resultat.grade.questions[1].teacher_score, 0.0)

    def test_virgule_acceptee_comme_separateur(self) -> None:
        """Un enseignant francophone tape « 0,5 », pas « 0.5 »."""
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction,
            {"decision_N1": "accepted", "decision_N2": "refused", "note_N2": "0,5"},
        )
        self.assertEqual(resultat.grade.questions[1].teacher_score, 0.5)

    def test_toutes_les_questions_sont_decidees(self) -> None:
        correction = self.correction_en_validation()
        self.connecter()
        resultat, _ = self._valider(
            correction, {"decision_N1": "accepted", "decision_N2": "accepted"}
        )
        self.assertTrue(resultat.grade.validation_complete)


class TestCloisonnement(BaseCorrection):
    def test_correction_ouverte_a_toute_personne_autorisee(self) -> None:
        """Élève de Tampouy, enseignant de Siao : autorisé. Un enseignant peut
        reprendre la correction d'un collègue absent."""
        correction = self.correction_en_validation(identifiant="HAK-2026-0001")
        self.connecter("SANOU", "Feryel", "5678")
        reponse = self.client.get(
            reverse("correction_web:suivre", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertEqual(reponse.status_code, 200)

    def test_correction_accessible_dans_le_perimetre(self) -> None:
        correction = self.correction_en_validation(identifiant="HAK-2026-0001")
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:suivre", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Valider les notes")

    def test_flux_exige_une_connexion(self) -> None:
        correction = self.correction_en_validation()
        reponse = self.client.get(
            reverse("correction_web:suivre", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertEqual(reponse.status_code, 302)

    def test_jeton_invalide_donne_404(self) -> None:
        self.connecter()
        reponse = self.client.get(reverse("correction_web:suivre", args=["forge"]))
        self.assertEqual(reponse.status_code, 404)


class TestSuppression(BaseCorrection):
    def test_supprime_la_correction_et_la_copie_persistee(self) -> None:
        from suivi.models import Copie, Document

        correction = self.correction_en_validation(identifiant="HAK-2026-0001")
        Copie.objects.create(
            copy_id=correction.copy_id,
            identifiant_hakili="HAK-2026-0001",
            classe="3e",
            annee_scolaire="2025-2026",
        )
        Document.objects.create(copie_id=correction.copy_id, type="scan", fichier=b"x")

        self.connecter()
        reponse = self.client.post(
            reverse("correction_web:supprimer", args=[jeton_eleve(correction.copy_id)]),
            follow=True,
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Correction.objects.filter(copy_id=correction.copy_id).exists())
        self.assertFalse(Copie.objects.filter(copy_id=correction.copy_id).exists())
        self.assertFalse(Document.objects.filter(copie_id=correction.copy_id).exists())

    def test_supprimable_par_toute_personne_du_perimetre(self) -> None:
        """Même règle de périmètre que le reste du flux — un enseignant peut
        supprimer la copie déposée par un collègue absent."""
        correction = self.correction_en_validation(identifiant="HAK-2026-0001")
        self.connecter("SANOU", "Feryel", "5678")
        self.client.post(
            reverse("correction_web:supprimer", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertFalse(Correction.objects.filter(copy_id=correction.copy_id).exists())

    def test_hors_perimetre_refuse(self) -> None:
        correction = self.correction_en_validation(identifiant="HAK-9999-9999")
        self.connecter()
        reponse = self.client.post(
            reverse("correction_web:supprimer", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertEqual(reponse.status_code, 403)
        self.assertTrue(Correction.objects.filter(copy_id=correction.copy_id).exists())

    def test_get_ne_supprime_rien(self) -> None:
        correction = self.correction_en_validation()
        self.connecter()
        self.client.get(
            reverse("correction_web:supprimer", args=[jeton_eleve(correction.copy_id)])
        )
        self.assertTrue(Correction.objects.filter(copy_id=correction.copy_id).exists())


class TestDepot(BaseCorrection):
    def test_eleve_hors_perimetre_refuse_avant_tout_appel_ia(self) -> None:
        """D-CEO-20 : une copie attribuée au hasard produirait un diagnostic faux au
        nom d'un autre enfant. On refuse plutôt que de deviner."""
        self.connecter("SANOU", "Feryel", "5678")
        with patch("correction_web.taches.lancer_transcription") as lancer:
            self.client.post(reverse("correction_web:nouvelle"), {"eleve": "HAK-2026-0001"})
        lancer.assert_not_called()
        self.assertEqual(Correction.objects.count(), 0)

    def test_sans_fichier_rien_n_est_lance(self) -> None:
        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            self.client.post(
                reverse("correction_web:nouvelle"), {"eleve": "HAK-2026-0001", "test": "socle_3eme"}
            )
        lancer.assert_not_called()

    def test_format_refuse(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            reponse = self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "test": "socle_3eme",
                    "copie": SimpleUploadedFile("copie.docx", b"pas une image"),
                },
            )
        lancer.assert_not_called()
        self.assertContains(reponse, "format accepté")


class TestSujetsImprimables(BaseCorrection):
    """Les élèves composent sur le sujet : l'enseignant doit pouvoir l'imprimer."""

    def test_liste_des_sujets(self) -> None:
        self.connecter()
        reponse = self.client.get(reverse("correction_web:sujets"))
        self.assertEqual(reponse.status_code, 200)
        # Sans l'apostrophe : elle est échappée en HTML (`d&#x27;entrée`).
        self.assertContains(reponse, "entrée en 3ème")
        self.assertContains(reponse, "entrée en Terminale D")

    def test_sujet_servi_en_pdf(self) -> None:
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:sujet", args=["socle_3eme"])
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_telechargement_sur_demande(self) -> None:
        self.connecter()
        url = reverse("correction_web:sujet", args=["socle_3eme"])
        self.assertIn("inline", self.client.get(url)["Content-Disposition"])
        self.assertIn(
            "attachment", self.client.get(url + "?telecharger=1")["Content-Disposition"]
        )

    def test_sujet_reserve_aux_personnes_connectees(self) -> None:
        """Un sujet d'évaluation diffusé à l'avance perd sa valeur diagnostique."""
        reponse = self.client.get(reverse("correction_web:sujet", args=["socle_3eme"]))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_test_inconnu_donne_404(self) -> None:
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:sujet", args=["test_inexistant"])
        )
        self.assertEqual(reponse.status_code, 404)

    def test_sujet_d_un_test_archive_indisponible(self) -> None:
        """Les anciens tests n'ont plus de sujet — ils ne doivent pas être
        distribuables."""
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:sujet", args=["hakili_3e_v1"])
        )
        self.assertEqual(reponse.status_code, 404)


class TestModeLibre(BaseCorrection):
    """Test personnalisé : le barème n'est pas connu à l'avance, le pipeline
    l'extrait du sujet déposé."""

    def _fichier(self, nom="copie.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(nom, b"%PDF-1.4 copie")

    def test_sujet_obligatoire_en_mode_libre(self) -> None:
        """Sans sujet, aucun barème ne peut être établi : mieux vaut refuser que
        lancer une correction qui n'aura rien à quoi se comparer."""
        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            reponse = self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "test": "libre",
                    "copie": self._fichier(),
                },
            )
        lancer.assert_not_called()
        self.assertContains(reponse, "ajoutez le sujet")

    def test_mode_libre_transmet_le_sujet_et_un_bareme_vide(self) -> None:
        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "test": "libre",
                    "copie": self._fichier(),
                    "sujet": self._fichier("sujet.pdf"),
                },
            )
        lancer.assert_called_once()
        _, _, rubric, test, sujet = lancer.call_args[0]
        self.assertIsNone(test)
        self.assertEqual(rubric.items, [])
        self.assertIsNotNone(sujet)
        self.assertTrue(str(sujet).endswith("sujet_sujet.pdf"))

    def test_mode_libre_n_enregistre_pas_de_bareme_id(self) -> None:
        """`bareme_id` sert à retrouver un test du catalogue : le laisser à
        « libre » ferait échouer la résolution de classe et le RAG."""
        self.connecter()
        with patch("correction_web.taches.lancer_transcription"):
            self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "test": "libre",
                    "copie": self._fichier(),
                    "sujet": self._fichier("sujet.pdf"),
                },
            )
        self.assertEqual(Correction.objects.get().bareme_id, "")

    def test_sujet_au_format_refuse(self) -> None:
        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            reponse = self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "test": "libre",
                    "copie": self._fichier(),
                    "sujet": self._fichier("sujet.docx"),
                },
            )
        lancer.assert_not_called()
        self.assertContains(reponse, "format accepté")


class TestDepotEnLot(BaseCorrection):
    """L'élève vient du nom de fichier, mais n'est jamais deviné."""

    def _deposer(self, noms: list[str]):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fichiers = [SimpleUploadedFile(n, b"%PDF-1.4 copie") for n in noms]
        with patch("correction_web.taches.lancer_phase_a_complete") as lancer:
            reponse = self.client.post(
                reverse("correction_web:lot"),
                {"test": "socle_3eme", "copies": fichiers},
                follow=True,
            )
        return reponse, lancer

    def test_copies_bien_nommees_sont_lancees(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        _, lancer = self._deposer(["KABRE_Charles.pdf", "ZONGO_Ibrahim.pdf"])
        self.assertEqual(lancer.call_count, 2)
        self.assertEqual(Correction.objects.count(), 2)

    def test_eleve_ambigu_ecarte_et_signale(self) -> None:
        """Deux Kanazoé au Sheet : le nom de famille seul ne tranche pas. Attribuer
        au hasard produirait un diagnostic au nom d'un autre enfant."""
        self.connecter("ADMIN", "Hakili", "9999")
        reponse, lancer = self._deposer(["KABRE_Charles.pdf", "inconnu.pdf"])
        self.assertEqual(lancer.call_count, 1)
        self.assertContains(reponse, "introuvable ou ambigu")

    def test_depot_ouvert_a_tous_les_eleves(self) -> None:
        """Un enseignant dépose la copie de n'importe quel élève du centre
        d'encadrement — c'est le fonctionnement réel, les enseignants tournent."""
        self.connecter("SANOU", "Feryel", "5678")  # Siao/4e
        _, lancer = self._deposer(["KABRE_Charles.pdf"])  # Tampouy/3e
        lancer.assert_called_once()

    def test_format_refuse_sans_bloquer_le_reste_du_lot(self) -> None:
        """Un fichier invalide ne doit pas faire perdre les vingt-neuf autres."""
        self.connecter("ADMIN", "Hakili", "9999")
        reponse, lancer = self._deposer(["KABRE_Charles.pdf", "ZONGO_Ibrahim.docx"])
        self.assertEqual(lancer.call_count, 1)
        self.assertContains(reponse, "format non accepté")

    def test_lot_conserve_la_validation_enseignant(self) -> None:
        """Différence assumée avec le mode lot de Streamlit, qui produisait des
        rapports complets sans qu'aucun enseignant ait vu une note — contraire à
        D-CEO-16. Ici la Phase A s'arrête sur le tableau de validation."""
        from correction_web import taches

        self.connecter("ADMIN", "Hakili", "9999")
        correction = Correction.objects.create(
            copy_id="copie-lot", identifiant_hakili="HAK-2026-0001", eleve_nom="KABRE"
        )
        with patch("correction_web.taches._dans_un_thread"):
            taches.lancer_phase_a_complete(correction, [], None, None)

        # L'état de départ est bien la transcription, et le chemin d'arrivée prévu
        # est VALIDATION — pas TERMINEE.
        correction.refresh_from_db()
        self.assertEqual(correction.etat, EtatCorrection.TRANSCRIPTION)


class TestCorrectionAbandonnee(BaseCorrection):
    def test_correction_bloquee_passe_en_echec(self) -> None:
        """Si le processus est arrêté en cours de route, l'enseignant ne doit pas
        voir une barre de progression tourner indéfiniment."""
        from datetime import timedelta

        from correction_web.taches import signaler_si_abandonnee

        correction = self.correction_en_validation()
        correction.etat = EtatCorrection.TRANSCRIPTION
        correction.save()
        Correction.objects.filter(pk=correction.pk).update(
            maj_le=timezone.now() - timedelta(hours=2)
        )
        correction.refresh_from_db()

        self.assertTrue(signaler_si_abandonnee(correction))
        correction.refresh_from_db()
        self.assertEqual(correction.etat, EtatCorrection.ECHEC)
        self.assertTrue(correction.erreurs)

    def test_correction_recente_non_touchee(self) -> None:
        from correction_web.taches import signaler_si_abandonnee

        correction = self.correction_en_validation()
        correction.etat = EtatCorrection.TRANSCRIPTION
        correction.save()
        self.assertFalse(signaler_si_abandonnee(correction))
        correction.refresh_from_db()
        self.assertEqual(correction.etat, EtatCorrection.TRANSCRIPTION)


class TestNouvellePreselectionEleve(BaseCorrection):
    """`?eleve=<jeton>` verrouille l'élève depuis le profil (dashboard élève) :
    plus besoin de le reresélectionner dans le combobox — voir eleve_detail.html
    et session_detail.html."""

    def test_jeton_valide_preselectionne_l_eleve(self) -> None:
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:nouvelle"),
            {"eleve": jeton_eleve("HAK-2026-0001")},
        )
        self.assertEqual(
            reponse.context["eleve_preselectionne"]["identifiant_hakili"],
            "HAK-2026-0001",
        )
        self.assertContains(reponse, "KABRE")

    def test_type_evaluation_preselectionne(self) -> None:
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:nouvelle"),
            {"eleve": jeton_eleve("HAK-2026-0001"), "type_evaluation": "T3"},
        )
        self.assertEqual(reponse.context["type_evaluation_preselectionnee"], "T3")

    def test_type_evaluation_inconnu_retombe_sur_t0(self) -> None:
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:nouvelle"), {"type_evaluation": "T9"}
        )
        self.assertEqual(reponse.context["type_evaluation_preselectionnee"], "T0")

    def test_jeton_invalide_retombe_sur_le_combobox(self) -> None:
        """Un jeton forgé ou périmé n'est pas une erreur bloquante — juste un
        confort en moins, cf. `views.nouvelle`."""
        self.connecter()
        reponse = self.client.get(
            reverse("correction_web:nouvelle"), {"eleve": "nimportequoi"}
        )
        self.assertIsNone(reponse.context["eleve_preselectionne"])

    def test_sans_parametre_le_combobox_reste_actif(self) -> None:
        self.connecter()
        reponse = self.client.get(reverse("correction_web:nouvelle"))
        self.assertIsNone(reponse.context["eleve_preselectionne"])

    def test_formulaire_pre_rempli_reste_postable(self) -> None:
        """Le champ caché porte l'identifiant comme avant : `_creer_correction`
        n'a besoin d'aucun changement pour un dépôt venu du profil élève."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.connecter()
        with patch("correction_web.taches.lancer_transcription"):
            self.client.get(
                reverse("correction_web:nouvelle"),
                {"eleve": jeton_eleve("HAK-2026-0001")},
            )
            self.client.post(
                reverse("correction_web:nouvelle"),
                {
                    "eleve": "HAK-2026-0001",
                    "type_evaluation": "T1",
                    "test": "libre",
                    "sujet": SimpleUploadedFile("sujet.pdf", b"%PDF-1.4 x"),
                    "copie": SimpleUploadedFile("copie.pdf", b"%PDF-1.4 x"),
                },
            )
        self.assertEqual(
            Correction.objects.filter(
                identifiant_hakili="HAK-2026-0001", type_evaluation="T1"
            ).count(),
            1,
        )


class TestSoumissionConfirmationT1(BaseCorrection):
    """`soumettre_confirmation` : dépôt du scan T1 quand le sujet (module 5) a
    déjà été généré — le barème est construit depuis ce sujet persisté, rien
    n'est extrait ni deviné du fichier déposé."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Evaluation, Probleme, Session, TypeEvaluation

        cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        idr = Competence.objects.create(
            code="L.IDR", domaine="Calcul litteral et algebre",
            libelle="Identites remarquables", niveau_intro="4eme",
            volume_horaire=Decimal("2"),
        )
        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        self.probleme = Probleme.objects.create(
            session=self.session, competence=idr, type_erreur=cpt,
            etat=EtatProbleme.HYPOTHESE, cout_estime=Decimal("0.5"),
            exercices_confirmation=[1, 2],
        )
        self.evaluation_t0 = Evaluation.objects.create(
            session=self.session, type=TypeEvaluation.T0,
            sujet_confirmation=[
                {"numero": 1, "topic": "Identites remarquables × Erreur conceptuelle",
                 "question": "Développer (x+5)^2.", "hint": None},
                {"numero": 2, "topic": "Identites remarquables × Erreur conceptuelle",
                 "question": "Développer (3a-4b)^2.", "hint": None},
            ],
        )
        self.jeton_session = jeton_eleve(str(self.session.pk))

    def _url(self):
        return reverse("correction_web:soumettre_confirmation", args=[self.jeton_session])

    def _fichier(self, nom="copie.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(nom, b"%PDF-1.4 copie")

    def test_redirige_si_aucun_sujet_disponible(self) -> None:
        self.evaluation_t0.sujet_confirmation = None
        self.evaluation_t0.save(update_fields=["sujet_confirmation"])

        self.connecter()
        reponse = self.client.get(self._url(), follow=True)
        self.assertRedirects(
            reponse,
            reverse("suivi_web:session_detail", args=[self.jeton_session]),
        )
        self.assertContains(reponse, "Aucun sujet de confirmation T1 disponible")

    def test_formulaire_affiche_quand_le_sujet_existe(self) -> None:
        self.connecter()
        reponse = self.client.get(self._url())
        self.assertContains(reponse, "Lancer la correction")

    def test_depot_construit_le_bareme_depuis_le_sujet_persiste(self) -> None:
        from suivi.models import TypeEvaluation

        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            self.client.post(self._url(), {"copie": self._fichier()})

        lancer.assert_called_once()
        correction, chemins, rubric, test, sujet, subject_text = lancer.call_args[0]
        self.assertEqual(correction.type_evaluation, TypeEvaluation.T1)
        self.assertEqual(correction.bareme_id, "")
        self.assertEqual(correction.identifiant_hakili, "HAK-2026-0001")
        self.assertIsNone(test)
        self.assertIsNone(sujet)
        self.assertEqual({item.id for item in rubric.items}, {"1", "2"})
        self.assertIn("Développer (x+5)^2.", subject_text)

    def test_sans_fichier_refuse(self) -> None:
        self.connecter()
        with patch("correction_web.taches.lancer_transcription") as lancer:
            reponse = self.client.post(self._url(), {}, follow=True)
        lancer.assert_not_called()
        self.assertContains(reponse, "Ajoutez la copie scannée")

    def test_exige_une_connexion(self) -> None:
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])


class TestConfirmationAutomatiqueT1(BaseCorrection):
    """`_ecrire_hypotheses_module4` doit trancher automatiquement les
    hypothèses pour une copie T1, pas en écrire de nouvelles — c'est le trou
    que `Correction.type_evaluation` documentait sans que le code le comble."""

    def _hypothese(self, identifiant="HAK-2026-0001", exercices=(1, 2)):
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        cpt, _ = TypeErreur.objects.get_or_create(
            code="CPT", defaults=dict(
                libelle="Erreur conceptuelle", definition="…", signature="…",
                coefficient=Decimal("0.35"), remediable=True,
            ),
        )
        idr, _ = Competence.objects.get_or_create(
            code="L.IDR", defaults=dict(
                domaine="Calcul litteral et algebre", libelle="Identites remarquables",
                niveau_intro="4eme", volume_horaire=Decimal("2"),
            ),
        )
        session = Session.objects.create(identifiant_hakili=identifiant)
        return Probleme.objects.create(
            session=session, competence=idr, type_erreur=cpt,
            etat=EtatProbleme.HYPOTHESE, cout_estime=Decimal("0.5"),
            exercices_confirmation=list(exercices),
        )

    def _resultat_t1(self, copy_id, notes):
        from src.models.domain import CopyGrade, QuestionGrade
        from src.pipeline.pipeline import PipelineResult

        grade = CopyGrade(
            copy_id=copy_id, total_score=sum(s for _, s in notes),
            total_possible=float(len(notes)),
            questions=[
                QuestionGrade(
                    rubric_item_id=str(n), score=s, confidence=0.9, comment="",
                    observed_answer="…", requires_review=False,
                )
                for n, s in notes
            ],
        )
        return PipelineResult(
            copy_id=copy_id, student_name="Charles KABRE", ingestion=None, grade=grade,
        )

    def test_copie_t1_confirme_au_lieu_decrire_une_hypothese(self) -> None:
        from correction_web.taches import _ecrire_hypotheses_module4
        from suivi.models import EtatProbleme, TypeEvaluation

        probleme = self._hypothese(exercices=(1, 2))
        correction = Correction.objects.create(
            copy_id="copie-t1-01", identifiant_hakili="HAK-2026-0001",
            eleve_nom="KABRE", eleve_prenom="Charles",
            bareme_id="", type_evaluation=TypeEvaluation.T1,
        )
        resultat = self._resultat_t1("copie-t1-01", [(1, 1.0), (2, 0.0)])

        _ecrire_hypotheses_module4(correction, resultat)

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.CONFIRME)

    def test_copie_t1_ecarte_si_tout_reussi(self) -> None:
        from correction_web.taches import _ecrire_hypotheses_module4
        from suivi.models import EtatProbleme, TypeEvaluation

        probleme = self._hypothese(exercices=(1, 2))
        correction = Correction.objects.create(
            copy_id="copie-t1-02", identifiant_hakili="HAK-2026-0001",
            eleve_nom="KABRE", eleve_prenom="Charles",
            bareme_id="", type_evaluation=TypeEvaluation.T1,
        )
        resultat = self._resultat_t1("copie-t1-02", [(1, 1.0), (2, 1.0)])

        _ecrire_hypotheses_module4(correction, resultat)

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.ECARTE)
