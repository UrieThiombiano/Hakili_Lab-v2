"""
Tests des vues de suivi : profil d'un élève et accès aux documents.

Le point le plus important est `TestAccesDocuments` : un document est une copie
d'élève, et l'autorisation doit être vérifiée sur l'URL du document lui-même, pas
seulement sur la page qui affiche le lien. Sans cela une URL devinée ou partagée
suffirait à récupérer la copie d'un élève d'un autre centre.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from comptes.tests import _ELEVES, _PERSONNEL, _cle
from suivi.models import Copie, Document
from suivi_web.jetons import identifiant_depuis_jeton, jeton_eleve

_PDF = b"%PDF-1.4 faux document de test"


def _copie(copy_id: str, identifiant: str, note=12.0) -> Copie:
    return Copie.objects.create(
        copy_id=copy_id,
        identifiant_hakili=identifiant,
        classe="3e",
        annee_scolaire="2026",
        date_soumission=date(2026, 5, 12),
        notes_finales=note,
    )


class BaseSuivi(TestCase):
    def setUp(self) -> None:
        for cible, valeur in (
            ("get_personnel", _PERSONNEL),
            ("get_eleves", _ELEVES),
        ):
            correctif = patch(
                f"src.integrations.google_sheets.{cible}", return_value=valeur
            )
            correctif.start()
            self.addCleanup(correctif.stop)

        correctif_eleve = patch(
            "src.integrations.google_sheets.get_eleve_by_identifiant",
            side_effect=lambda ident: next(
                (e for e in _ELEVES if e["identifiant_hakili"] == ident), None
            ),
        )
        correctif_eleve.start()
        self.addCleanup(correctif_eleve.stop)

        # Les copies ne sont plus simulées : `copie` et `document` sont sous
        # Django depuis D-CEO-40, donc la base de test les porte pour de vrai.
        # Ces tests portent sur les autorisations et n'ont besoin d'aucune copie ;
        # ceux qui en veulent une la créent (voir TestAccesDocuments).

    def connecter(self, nom: str, prenom: str, pin: str):
        return self.client.post(
            reverse("comptes:connexion"), {"cle": _cle(nom, prenom), "pin": pin}, follow=True
        )


class TestJetons(TestCase):
    def test_aller_retour(self) -> None:
        self.assertEqual(identifiant_depuis_jeton(jeton_eleve("HAK-2026-0001")), "HAK-2026-0001")

    def test_jeton_forge_rejete(self) -> None:
        self.assertIsNone(identifiant_depuis_jeton("nimportequoi"))

    def test_jeton_altere_rejete(self) -> None:
        jeton = jeton_eleve("HAK-2026-0001")
        altere = jeton[:-3] + ("aaa" if not jeton.endswith("aaa") else "bbb")
        self.assertIsNone(identifiant_depuis_jeton(altere))

    def test_le_jeton_ne_contient_pas_l_identifiant_en_clair(self) -> None:
        """C'est tout l'objet : `identifiant_hakili` ne doit apparaître ni dans
        l'URL, ni dans l'historique du navigateur, ni dans les journaux."""
        self.assertNotIn("HAK-2026-0001", jeton_eleve("HAK-2026-0001"))


class TestProfilEleve(BaseSuivi):
    def test_responsable_accede_a_un_eleve_de_son_centre(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[jeton_eleve("HAK-2026-0001")])
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "KABRE")

    def test_acces_ouvert_a_toute_personne_autorisee(self) -> None:
        """Centre d'encadrement : un enseignant de Siao accède à un élève de
        Tampouy. Le cloisonnement par centre et classe a été retiré — il bloquait
        un enseignant reprenant les copies d'un collègue absent."""
        self.connecter("SANOU", "Feryel", "5678")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[jeton_eleve("HAK-2026-0001")])
        )
        self.assertEqual(reponse.status_code, 200)

    def test_eleve_inconnu_donne_404(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[jeton_eleve("INEXISTANT")])
        )
        self.assertEqual(reponse.status_code, 404)

    def test_jeton_invalide_donne_404(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(reverse("suivi_web:eleve_detail", args=["forge"]))
        self.assertEqual(reponse.status_code, 404)

    def test_profil_exige_une_connexion(self) -> None:
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[jeton_eleve("HAK-2026-0001")])
        )
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_aucune_donnee_sensible_sur_le_profil(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        contenu = self.client.get(
            reverse("suivi_web:eleve_detail", args=[jeton_eleve("HAK-2026-0001")])
        ).content.decode()
        self.assertNotIn("70000001", contenu)  # contact_parents
        self.assertNotIn("HAK-2026-0001", contenu)        # identifiant_hakili


class TestFicheEleveHypotheses(BaseSuivi):
    """Les lacunes présumées (module 4, état `hypothese`) doivent apparaître
    sur la fiche de l'élève, avec la mention qu'elles restent à confirmer par
    le second test (T1) — sans ça, un problème détecté mais pas encore vérifié
    reste invisible tant que personne n'ouvre l'écran de parcours."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import Probleme, Session

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
        Probleme.objects.create(
            session=self.session, competence=idr, type_erreur=cpt,
            cout_estime=Decimal("0.5"),
        )
        self.jeton = jeton_eleve("HAK-2026-0001")

    def test_la_fiche_affiche_la_lacune_presumee(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[self.jeton])
        )
        self.assertContains(reponse, "Identites remarquables")
        self.assertContains(reponse, "à confirmer par le second test (T1)")

    def test_la_fiche_affiche_le_volume_horaire_estime(self) -> None:
        """Le volume d'encadrement estimé doit être visible dès le diagnostic
        initial, pas seulement une fois les hypothèses confirmées (T1)."""
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[self.jeton])
        )
        self.assertContains(reponse, "0,50 h estimées")

    def test_rien_affiche_une_fois_la_lacune_tranchee(self) -> None:
        from suivi.models import EtatProbleme

        self.session.problemes.get().changer_etat(EtatProbleme.ECARTE)
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:eleve_detail", args=[self.jeton])
        )
        self.assertNotContains(reponse, "à confirmer par le second test (T1)")


class TestEcranParcours(BaseSuivi):
    """Le plan de remédiation et le bouton d'inscription."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, Prerequis, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        dev1 = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        idr = Competence.objects.create(
            code="L.IDR", domaine="Calcul litteral et algebre",
            libelle="Identites remarquables", niveau_intro="4eme",
            volume_horaire=Decimal("2"),
        )
        Prerequis.objects.create(competence=idr, prerequis=dev1)

        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        for competence in (idr, dev1):
            Probleme.objects.create(
                session=self.session, competence=competence, type_erreur=cpt,
                cout_estime=Decimal("2"),
            ).changer_etat(EtatProbleme.CONFIRME)
        self.session.etablir_le_plan()
        self.jeton = jeton_eleve(str(self.session.pk))

    def _url(self, nom: str = "session_detail") -> str:
        return reverse(f"suivi_web:{nom}", args=[self.jeton])

    def test_le_plan_est_ordonne_par_prerequis(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        contenu = self.client.get(self._url()).content.decode()
        self.assertLess(
            contenu.index("Developpement et reduction"),
            contenu.index("Identites remarquables"),
        )

    def test_le_volume_et_le_palier_sont_affiches(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(self._url())
        self.assertContains(reponse, "4 h")
        self.assertContains(reponse, "Inscrire au programme")

    def test_inscription_depuis_l_ecran(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("inscrire"))

        self.session.refresh_from_db()
        self.assertTrue(self.session.inscrite)
        self.assertIsNotNone(self.session.date_inscription)

    def test_inscription_refusee_en_get(self) -> None:
        """Une inscription engage un volume horaire et une facturation : elle ne
        doit pas pouvoir arriver par un lien cliqué ailleurs."""
        self.connecter("DIANE", "Abasse", "1234")
        self.client.get(self._url("inscrire"))
        self.session.refresh_from_db()
        self.assertFalse(self.session.inscrite)

    def test_inscription_exige_une_connexion(self) -> None:
        reponse = self.client.post(self._url("inscrire"))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_bouton_disparait_une_fois_inscrit(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("inscrire"))
        reponse = self.client.get(self._url())
        self.assertNotContains(reponse, "Inscrire au programme")

    def test_palier_c_demande_un_motif(self) -> None:
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        cpt = TypeErreur.objects.get(code="CPT")
        session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        for i in range(12):
            competence = Competence.objects.create(
                code=f"Z.{i}", domaine="Activites numeriques", libelle=f"Z{i}",
                niveau_intro="4eme", volume_horaire=Decimal("4"),
            )
            Probleme.objects.create(
                session=session, competence=competence, type_erreur=cpt,
                cout_estime=Decimal("2"),
            ).changer_etat(EtatProbleme.CONFIRME)
        session.etablir_le_plan()
        jeton = jeton_eleve(str(session.pk))

        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(reverse("suivi_web:session_detail", args=[jeton]))
        self.assertContains(reponse, "Palier C")
        self.assertContains(reponse, "Motif de la dérogation")

        # Sans motif : refusé.
        self.client.post(reverse("suivi_web:inscrire", args=[jeton]), {"forcer": "1"})
        session.refresh_from_db()
        self.assertFalse(session.inscrite)

        # Avec motif : accepté et tracé.
        self.client.post(
            reverse("suivi_web:inscrire", args=[jeton]),
            {"forcer": "1", "motif": "Accord écrit de la famille"},
        )
        session.refresh_from_db()
        self.assertTrue(session.inscrite)
        derniere = session.problemes.first().transitions.order_by("-pk").first()
        self.assertIn("Accord écrit de la famille", derniere.commentaire)

    def test_parcours_hors_perimetre_donne_404(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:session_detail", args=[jeton_eleve("99999")])
        )
        self.assertEqual(reponse.status_code, 404)

    def test_le_volume_des_hypotheses_est_affiche_avant_confirmation(self) -> None:
        """Avant le test de confirmation (T1), les lacunes ne sont que des
        hypothèses — `construire()` ne les compte pas dans `plan.total_heures`.
        L'enseignant doit malgré tout voir un ordre de grandeur du volume
        horaire dès ce stade, pas seulement une fois les hypothèses confirmées."""
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import Probleme, Session

        cpt = TypeErreur.objects.get(code="CPT")
        competence = Competence.objects.create(
            code="L.HYP", domaine="Calcul litteral et algebre",
            libelle="Hypothese en attente", niveau_intro="4eme",
            volume_horaire=Decimal("1.5"),
        )
        session = Session.objects.create(identifiant_hakili="HAK-2026-0002")
        Probleme.objects.create(
            session=session, competence=competence, type_erreur=cpt,
            cout_estime=Decimal("1.5"),
        )
        jeton = jeton_eleve(str(session.pk))

        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(reverse("suivi_web:session_detail", args=[jeton]))
        self.assertContains(reponse, "1,50 h")


class TestFicheRemediation(BaseSuivi):
    """Téléchargement de la fiche de remédiation (module 7) — générée à la
    demande à partir du plan, jamais stockée."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        competence = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        Probleme.objects.create(
            session=self.session, competence=competence, type_erreur=cpt,
            cout_estime=Decimal("2"),
        ).changer_etat(EtatProbleme.CONFIRME)
        self.jeton = jeton_eleve(str(self.session.pk))

    def _url(self) -> str:
        return reverse("suivi_web:fiche_remediation", args=[self.jeton])

    def test_telechargement_rend_un_pdf(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(self._url() + "?telecharger=1")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_exige_une_connexion(self) -> None:
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_sans_probleme_confirme_redirige_avec_message(self) -> None:
        from suivi.models import Session

        session_vide = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        jeton_vide = jeton_eleve(str(session_vide.pk))

        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(
            reverse("suivi_web:fiche_remediation", args=[jeton_vide]), follow=True
        )
        self.assertContains(reponse, "Aucun problème confirmé")


class TestConfirmationT1(BaseSuivi):
    """La saisie du résultat T1 — module 5 : confirmer ou écarter une
    hypothèse, jamais y aller directement depuis le diagnostic."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        self.cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        self.att = TypeErreur.objects.create(
            code="ATT", libelle="Inattention", definition="…",
            signature="…", coefficient=Decimal("0"), remediable=False,
        )
        self.competence = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        self.competence2 = Competence.objects.create(
            code="L.IDR", domaine="Calcul litteral et algebre",
            libelle="Identites remarquables", niveau_intro="4eme",
            volume_horaire=Decimal("2"),
        )

        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        self.hyp_confirmable = Probleme.objects.create(
            session=self.session, competence=self.competence, type_erreur=self.cpt,
            cout_estime=Decimal("2"), justification="3(x+1) traité comme 3x+1",
        )
        self.hyp_att = Probleme.objects.create(
            session=self.session, competence=self.competence2, type_erreur=self.att,
            cout_estime=Decimal("0"),
        )
        self.jeton = jeton_eleve(str(self.session.pk))

    def _url(self) -> str:
        return reverse("suivi_web:confirmer_hypotheses", args=[self.jeton])

    def test_confirmation_change_l_etat_et_trace_une_evaluation_t1(self) -> None:
        from suivi.models import EtatProbleme, Evaluation, TypeEvaluation

        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url(), {f"decision_{self.hyp_confirmable.pk}": "confirme"})

        self.hyp_confirmable.refresh_from_db()
        self.assertEqual(self.hyp_confirmable.etat, EtatProbleme.CONFIRME)

        transition = self.hyp_confirmable.transitions.order_by("-pk").first()
        self.assertIsNotNone(transition.evaluation)
        self.assertEqual(transition.evaluation.type, TypeEvaluation.T1)
        self.assertEqual(
            Evaluation.objects.filter(session=self.session, type=TypeEvaluation.T1).count(), 1
        )

    def test_ecartement_change_l_etat(self) -> None:
        from suivi.models import EtatProbleme

        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url(), {f"decision_{self.hyp_confirmable.pk}": "ecarte"})

        self.hyp_confirmable.refresh_from_db()
        self.assertEqual(self.hyp_confirmable.etat, EtatProbleme.ECARTE)

    def test_att_ne_peut_pas_etre_confirmee(self) -> None:
        """Contrainte du modèle (`Probleme.clean`) : la vue doit l'encaisser
        sans planter, pas la contourner."""
        from suivi.models import EtatProbleme

        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.post(
            self._url(), {f"decision_{self.hyp_att.pk}": "confirme"}, follow=True
        )

        self.hyp_att.refresh_from_db()
        self.assertEqual(self.hyp_att.etat, EtatProbleme.HYPOTHESE)
        self.assertContains(reponse, "ne peut être")

    def test_decision_vide_ne_change_rien(self) -> None:
        from suivi.models import EtatProbleme

        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url(), {})

        self.hyp_confirmable.refresh_from_db()
        self.assertEqual(self.hyp_confirmable.etat, EtatProbleme.HYPOTHESE)

    def test_refuse_en_get(self) -> None:
        from suivi.models import EtatProbleme

        self.connecter("DIANE", "Abasse", "1234")
        self.client.get(self._url())

        self.hyp_confirmable.refresh_from_db()
        self.assertEqual(self.hyp_confirmable.etat, EtatProbleme.HYPOTHESE)

    def test_exige_une_connexion(self) -> None:
        reponse = self.client.post(self._url())
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_formulaire_visible_sur_le_parcours(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(reverse("suivi_web:session_detail", args=[self.jeton]))
        self.assertContains(reponse, "Confirmée")
        self.assertContains(reponse, "Écartée")
        self.assertContains(reponse, "ne peut être qu'écartée")

    def test_bouton_soumission_t1_absent_sans_sujet_genere(self) -> None:
        """Sans sujet T1 persisté (module 5 jamais tourné, ou pas de client IA
        disponible à T0), seule la saisie manuelle est proposée."""
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(reverse("suivi_web:session_detail", args=[self.jeton]))
        self.assertNotContains(reponse, "Soumettre la copie pour le test de confirmation")

    def test_bouton_soumission_t1_visible_avec_sujet_genere(self) -> None:
        from suivi.models import Evaluation, TypeEvaluation

        Evaluation.objects.create(
            session=self.session, type=TypeEvaluation.T0,
            sujet_confirmation=[
                {"numero": 1, "topic": "x", "question": "…", "hint": None},
                {"numero": 2, "topic": "x", "question": "…", "hint": None},
            ],
        )
        self.hyp_confirmable.exercices_confirmation = [1, 2]
        self.hyp_confirmable.save(update_fields=["exercices_confirmation"])

        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(reverse("suivi_web:session_detail", args=[self.jeton]))
        self.assertContains(reponse, "Soumettre la copie pour le test de confirmation")


class TestVuePersonnel(BaseSuivi):
    """L'admin doit voir qui a accès — et surtout qui ne l'a pas."""

    def test_reservee_a_l_administrateur(self) -> None:
        self.connecter("SANOU", "Feryel", "5678")
        self.assertEqual(
            self.client.get(reverse("suivi_web:personnel")).status_code, 403
        )

    def test_liste_tout_le_personnel(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(reverse("suivi_web:personnel"))
        self.assertEqual(reponse.status_code, 200)
        for personne in _PERSONNEL:
            self.assertContains(reponse, personne["nom"])

    def test_personne_sans_code_signalee_et_non_masquee(self) -> None:
        """Elle figure dans le Sheet en croyant avoir accès, et ne peut pas se
        connecter : c'est exactement ce que l'admin doit voir."""
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(reverse("suivi_web:personnel"))
        self.assertContains(reponse, "SANSPIN")
        self.assertContains(reponse, "Aucun code")

    def test_role_non_reconnu_signale(self) -> None:
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(reverse("suivi_web:personnel"))
        self.assertContains(reponse, "ROLEFAUX")
        self.assertContains(reponse, "non reconnu")

    def test_renvoie_vers_le_sheet_pour_modifier(self) -> None:
        """Aucune modification ici : le Sheet fait foi (D-CEO-21)."""
        self.connecter("ADMIN", "Hakili", "9999")
        reponse = self.client.get(reverse("suivi_web:personnel"))
        self.assertContains(reponse, "dans le Google Sheet")

    def test_aucun_code_d_acces_affiche(self) -> None:
        """Le PIN est en clair dans le Sheet ; il n'a rien à faire à l'écran."""
        self.connecter("ADMIN", "Hakili", "9999")
        contenu = self.client.get(reverse("suivi_web:personnel")).content.decode()
        for personne in _PERSONNEL:
            if personne["pin"]:
                self.assertNotIn(personne["pin"], contenu)


class TestAccesDocuments(BaseSuivi):
    """L'autorisation doit être revérifiée sur l'URL du document."""

    def setUp(self) -> None:
        super().setUp()
        self.copie = _copie("copie-H1", "HAK-2026-0001")
        self.doc = Document.objects.create(
            copie=self.copie, type="rapport", fichier=_PDF
        )

    def _url(self) -> str:
        return reverse(
            "suivi_web:document", args=[jeton_eleve("copie-H1"), "rapport"]
        )

    def test_document_servi_a_qui_y_a_droit(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertEqual(reponse.content, _PDF)

    def test_document_servi_a_toute_personne_autorisee(self) -> None:
        """Périmètre unique : tout enseignant autorisé accède au document."""
        self.connecter("SANOU", "Feryel", "5678")
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 200)

    def test_document_refuse_sans_connexion(self) -> None:
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])

    def test_nom_de_fichier_sans_donnee_sensible(self) -> None:
        """Ces fichiers circulent par WhatsApp et par mail."""
        self.connecter("DIANE", "Abasse", "1234")
        disposition = self.client.get(self._url())["Content-Disposition"]
        self.assertIn("KABRE_Charles_rapport", disposition)
        self.assertNotIn("70000001", disposition)
        self.assertNotIn("HAK-2026-0001", disposition)

    def test_apercu_par_defaut_telechargement_sur_demande(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        self.assertIn("inline", self.client.get(self._url())["Content-Disposition"])
        self.assertIn(
            "attachment",
            self.client.get(self._url() + "?telecharger=1")["Content-Disposition"],
        )

    def test_type_reel_detecte_et_non_devine(self) -> None:
        """Un scan peut être une photo, contrairement au rapport toujours en PDF :
        le format est lu dans les octets, pas déduit du champ `type`."""
        self.doc.fichier = b"\xff\xd8\xff\xe0 faux jpeg"
        self.doc.save(update_fields=["fichier"])
        self.connecter("DIANE", "Abasse", "1234")
        self.assertEqual(self.client.get(self._url())["Content-Type"], "image/jpeg")


class TestTrancherEvaluation(BaseSuivi):
    """Généralisation de l'écran T1 (`confirmer_hypotheses`) à T3/T4/T5 — voir
    `_trancher` / `_REGLES_VERDICT` dans `suivi_web/views.py`."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import Session

        self.cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        self.competence = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        self.jeton = jeton_eleve(str(self.session.pk))

    def _probleme(self, etat: str):
        from decimal import Decimal

        from suivi.models import Probleme

        return Probleme.objects.create(
            session=self.session, competence=self.competence, type_erreur=self.cpt,
            cout_estime=Decimal("2"), etat=etat,
        )

    def _url(self, type_evaluation: str) -> str:
        return reverse("suivi_web:trancher_evaluation", args=[self.jeton, type_evaluation])

    def test_t3_resolu_change_l_etat_et_trace_une_evaluation_t3(self) -> None:
        from suivi.models import EtatProbleme, Evaluation, TypeEvaluation

        probleme = self._probleme(EtatProbleme.EN_REMEDIATION)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("T3"), {f"decision_{probleme.pk}": "resolu"})

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.RESOLU)
        self.assertEqual(
            Evaluation.objects.filter(session=self.session, type=TypeEvaluation.T3).count(), 1
        )

    def test_t3_non_resolu_change_l_etat(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.EN_REMEDIATION)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("T3"), {f"decision_{probleme.pk}": "non_resolu"})

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.NON_RESOLU)

    def test_t4_ne_peut_pas_clore(self) -> None:
        """`clos` n'est pas une option permise à T4 — réservée au dernier
        contrôle (T5, `_REGLES_VERDICT`). Une décision hors options est
        ignorée, pas appliquée en silence."""
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.RESOLU)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("T4"), {f"decision_{probleme.pk}": "clos"})

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.RESOLU)

    def test_t4_regresse_change_l_etat(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.RESOLU)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("T4"), {f"decision_{probleme.pk}": "regresse"})

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.REGRESSE)

    def test_t5_peut_clore(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.RESOLU)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url("T5"), {f"decision_{probleme.pk}": "clos"})

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.CLOS)

    def test_type_invalide_donne_404(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.post(self._url("T9"), {})
        self.assertEqual(reponse.status_code, 404)

    def test_exige_une_connexion(self) -> None:
        reponse = self.client.post(self._url("T3"), {})
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])


class TestRelancer(BaseSuivi):
    """Relancer un problème `non_resolu` ou `regresse` en remédiation — une
    décision du tuteur, jamais un effet automatique d'un contrôle."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import Session

        self.cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        self.competence = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        self.jeton = jeton_eleve(str(self.session.pk))

    def _probleme(self, etat: str):
        from decimal import Decimal

        from suivi.models import Probleme

        return Probleme.objects.create(
            session=self.session, competence=self.competence, type_erreur=self.cpt,
            cout_estime=Decimal("2"), etat=etat,
        )

    def _url(self, probleme_id: int) -> str:
        return reverse("suivi_web:relancer", args=[self.jeton, probleme_id])

    def test_non_resolu_relance_en_remediation(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.NON_RESOLU)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url(probleme.pk))

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.EN_REMEDIATION)

    def test_regresse_relance_en_remediation(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.REGRESSE)
        self.connecter("DIANE", "Abasse", "1234")
        self.client.post(self._url(probleme.pk))

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.EN_REMEDIATION)

    def test_transition_non_permise_refusee_proprement(self) -> None:
        """Un problème déjà résolu ne peut pas être « relancé » : ce n'est pas
        une transition permise (`TRANSITIONS_PERMISES`). La vue doit
        l'encaisser sans planter."""
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.RESOLU)
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.post(self._url(probleme.pk), follow=True)

        probleme.refresh_from_db()
        self.assertEqual(probleme.etat, EtatProbleme.RESOLU)
        self.assertContains(reponse, "non permise")

    def test_exige_une_connexion(self) -> None:
        from suivi.models import EtatProbleme

        probleme = self._probleme(EtatProbleme.NON_RESOLU)
        reponse = self.client.post(self._url(probleme.pk))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])


class TestGenererSujet(BaseSuivi):
    """Génération à la demande du sujet T3 (vérification) ou T4/T5 (rétention)
    — jamais stockée, comme la fiche de remédiation (`TestFicheRemediation`)."""

    def setUp(self) -> None:
        super().setUp()
        from decimal import Decimal

        from referentiel.models import Competence, TypeErreur
        from suivi.models import EtatProbleme, Probleme, Session

        cpt = TypeErreur.objects.create(
            code="CPT", libelle="Erreur conceptuelle", definition="…",
            signature="…", coefficient=Decimal("0.35"), remediable=True,
        )
        competence = Competence.objects.create(
            code="L.DEV1", domaine="Calcul litteral et algebre",
            libelle="Developpement et reduction", niveau_intro="5eme",
            volume_horaire=Decimal("4.5"),
        )
        self.session = Session.objects.create(identifiant_hakili="HAK-2026-0001")
        Probleme.objects.create(
            session=self.session, competence=competence, type_erreur=cpt,
            cout_estime=Decimal("2"), etat=EtatProbleme.EN_REMEDIATION,
        )
        self.jeton = jeton_eleve(str(self.session.pk))

    def _url(self, type_evaluation: str) -> str:
        return reverse("suivi_web:generer_sujet", args=[self.jeton, type_evaluation])

    def test_sujet_genere_rend_un_pdf(self) -> None:
        from src.models.domain import Exercise, VerificationSubject

        sujet = VerificationSubject(
            copy_id="verif-x", type_evaluation="T3",
            exercises=[
                Exercise(
                    number=1,
                    topic="Developpement et reduction × Erreur conceptuelle",
                    question="Developpe 3(x+1)", hint=None,
                ),
            ],
        )
        self.connecter("DIANE", "Abasse", "1234")
        with patch("suivi.generation.generer_sujet_verification", return_value=sujet):
            reponse = self.client.get(self._url("T3"))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_rien_a_generer_redirige_avec_message(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        with patch("suivi.generation.generer_sujet_verification", return_value=None):
            reponse = self.client.get(self._url("T3"), follow=True)
        self.assertContains(reponse, "Rien à générer")

    def test_type_invalide_donne_404(self) -> None:
        self.connecter("DIANE", "Abasse", "1234")
        reponse = self.client.get(self._url("T9"))
        self.assertEqual(reponse.status_code, 404)

    def test_exige_une_connexion(self) -> None:
        reponse = self.client.get(self._url("T3"))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse["Location"])
