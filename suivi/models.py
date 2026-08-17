"""
Le suivi d'un élève — alimenté par l'usage, du premier test au dernier contrôle.

L'unité de suivi n'est ni la note ni la classe : c'est le **problème**, couple
d'une compétence et d'un type d'erreur (protocole-v2.md §2). Un élève n'a pas
« 11 sur 20 », il a « 14 problèmes ouverts, dont 3 prérequis de 5ème ».

Deux points de conception à ne pas défaire
------------------------------------------
1. **`Transition` est le cœur du dispositif.** Aucun changement d'état de problème
   ne doit se faire sans y écrire une ligne datée : c'est d'elle que sortent les 5
   indicateurs du module 9, et sans elle le dispositif n'est plus mesurable.
   `Probleme.changer_etat()` existe pour rendre l'oubli difficile.

2. **L'identité de l'élève n'est pas ici.** Elle vit dans les Google Sheets, et
   `identifiant_hakili` (texte) fait le lien — pas une clé étrangère vers une table
   `eleve`. Cette table a déjà été créée puis démolie deux fois (D-CEO-20, D-CEO-21)
   parce qu'elle constituait une seconde source de vérité qui divergeait. Ne pas la
   recréer.
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class Copie(models.Model):
    """Une copie corrigée : l'objet que le pipeline produit et persiste.

    **Passée sous Django le 2026-08-05 (D-CEO-40).** Elle appartenait à
    SQLAlchemy parce que Streamlit l'écrivait ; Streamlit est parti (D-CEO-39) et
    elle n'avait plus de raison de vivre dans un second ORM. La table est la
    même — la migration qui l'adopte ne crée rien en production, elle s'y
    applique avec `--fake` (voir `docs/deploiement.md`).

    L'identité de l'élève (nom, prénom, centre, contact) n'est **pas** ici : elle
    vit dans les Google Sheets. `identifiant_hakili` est un champ texte, jamais
    une clé étrangère — c'est la discipline D-CEO-20, et c'est ce qui a permis de
    démolir deux fois une table `eleve` sans rien casser.
    """

    copy_id = models.CharField(max_length=255, primary_key=True)
    identifiant_hakili = models.CharField(max_length=255)
    classe = models.CharField(max_length=50)
    annee_scolaire = models.CharField(max_length=50)
    date_soumission = models.DateField(default=timezone.localdate)
    notes_finales = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "copie"
        verbose_name = "copie"
        verbose_name_plural = "copies"

    def __str__(self) -> str:
        return self.copy_id


class Document(models.Model):
    """Un fichier attaché à une copie : le scan, le rapport, la remédiation.

    Le contenu est stocké **en base** (`bytea`) et non sur disque : l'hébergement
    n'a pas de volume persistant, un fichier écrit à côté disparaît au
    redéploiement (`docs/deploiement.md`). Servi par jeton signé, jamais par une
    URL portant `identifiant_hakili` (D-CEO-25).
    """

    TYPES = (
        ("scan", "scan"),
        ("rapport", "rapport"),
        ("sujet_confirmation", "sujet de confirmation (T1)"),
        ("remediation", "remédiation"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    copie = models.ForeignKey(
        Copie, on_delete=models.CASCADE, db_column="copy_id", related_name="documents"
    )
    type = models.CharField(max_length=50, choices=TYPES)
    fichier = models.BinaryField()
    date_creation = models.DateField(default=timezone.localdate)

    class Meta:
        db_table = "document"
        verbose_name = "document"
        verbose_name_plural = "documents"

    def __str__(self) -> str:
        return f"{self.type} de {self.copie_id}"

    def __str__(self) -> str:
        return self.copy_id


class TypeEvaluation(models.TextChoices):
    """Les étapes du cycle de suivi.

    Chaque évaluation porte un nom distinct : des évaluations toutes appelées
    « test diagnostique » deviendraient impossibles à distinguer en base et dans
    les comptes rendus (protocole-v2.md §5).

    Deux écarts assumés par rapport au protocole d'origine :

    · **T2 (contrôle de mi-parcours) a été retiré.** Le cycle réel va de la fin du
      volume horaire de remédiation directement au test de vérification. Le
      protocole le prévoyait entre les deux, mais le rendait déjà facultatif en
      palier A ; il ne correspond pas à la pratique du centre.

    · **Un même type peut se répéter** — voir `Evaluation.numero`. Tant que des
      lacunes ne sont pas corrigées, l'enseignant relance un test de vérification
      autant de fois qu'il le faut. Le protocole supposait une séquence fixe.
    """

    T0 = "T0", "T0 — test de niveau"
    T1 = "T1", "T1 — confirmation des lacunes"
    T3 = "T3", "T3 — vérification après remédiation"
    T4 = "T4", "T4 — consolidation à 45 jours"
    T5 = "T5", "T5 — consolidation à 3 mois"


class EtatProbleme(models.TextChoices):
    """Cycle de vie d'un problème. Les transitions permises sont déclarées dans
    `Probleme.TRANSITIONS_PERMISES` — la liste des états seule ne suffit pas à
    empêcher un enchaînement absurde."""

    HYPOTHESE = "hypothese", "Hypothèse — détecté, pas encore vérifié"
    CONFIRME = "confirme", "Confirmé — difficulté réelle, à traiter"
    ECARTE = "ecarte", "Écarté — c'était une étourderie"
    EN_REMEDIATION = "en_remediation", "En remédiation"
    RESOLU = "resolu", "Résolu"
    NON_RESOLU = "non_resolu", "Non résolu"
    REGRESSE = "regresse", "Régressé — réapparu au contrôle"
    CLOS = "clos", "Clos — acquis durablement"


class Palier(models.TextChoices):
    """Intensité du parcours, déterminée par le coût total des problèmes confirmés.

    Le palier C doit être prononcé clairement plutôt que déguisé en plan : proposer
    cinq semaines à un élève qui cumule huit prérequis manquants garantit un échec,
    et un échec visible coûte plus cher qu'un refus argumenté (protocole §7).
    C'est pourquoi `Session.inscrire()` refuse le palier C sans décision explicite
    et motivée.
    """

    A = "A", "A — ciblé (moins de 8 h, 2 à 4 séances)"
    B = "B", "B — complet (8 à 20 h)"
    C = "C", "C — hors dispositif (plus de 20 h)"


class EtatSession(models.TextChoices):
    """Où en est le parcours d'un élève.

    Trois sorties sans remédiation sont distinguées, et ce n'est pas de la
    finesse gratuite : elles ne veulent pas dire la même chose à une famille.

    · `SANS_SUITE` — T1 n'a confirmé aucun problème. **C'est un bon résultat.**
      Le protocole le dit : « un outil qui n'oriente pas systématiquement vers de
      la remédiation payante est un outil crédible. » Le confondre avec un abandon
      transformerait une réussite en échec dans les comptes rendus.
    · `HORS_DISPOSITIF` — palier C. L'élève cumule trop de lacunes pour une
      remédiation courte ; il relève d'un accompagnement long. C'est une
      orientation, pas un renoncement.
    · `ABANDONNEE` — l'élève ou la famille s'est retiré en cours de route.
    """

    DIAGNOSTIC = "diagnostic", "Diagnostic en cours (T0, T1)"
    ATTENTE_INSCRIPTION = "attente_inscription", "Plan établi — en attente d'inscription"
    REMEDIATION = "remediation", "Inscrit en remédiation"
    CLOSE = "close", "Cycle clos"
    SANS_SUITE = "sans_suite", "Sortie sans remédiation — aucune lacune confirmée"
    HORS_DISPOSITIF = "hors_dispositif", "Orienté hors dispositif (palier C)"
    ABANDONNEE = "abandonnee", "Abandonnée"


#: États terminaux : le parcours ne reprend pas depuis là.
ETATS_SESSION_TERMINES = frozenset(
    {
        EtatSession.CLOSE,
        EtatSession.SANS_SUITE,
        EtatSession.HORS_DISPOSITIF,
        EtatSession.ABANDONNEE,
    }
)


class Session(models.Model):
    """Le parcours complet d'un élève, du premier test au dernier contrôle de
    rétention — environ sept mois.

    Nommée `Session` côté Python mais stockée en `session_suivi` : « session » seul
    prêterait à confusion avec les sessions d'authentification Django, dans la même
    base.
    """

    identifiant_hakili = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Lien vers l'élève dans le Google Sheet. Jamais une clé étrangère "
        "— l'identité ne vit pas en base (D-CEO-20).",
    )
    date_debut = models.DateField(default=timezone.localdate)
    palier = models.CharField(
        max_length=1,
        choices=Palier.choices,
        blank=True,
        help_text="Vide jusqu'à T1 : le palier découle du coût des problèmes confirmés.",
    )
    etat = models.CharField(
        max_length=20, choices=EtatSession.choices, default=EtatSession.DIAGNOSTIC
    )
    date_inscription = models.DateField(
        "date d'inscription au programme",
        null=True,
        blank=True,
        help_text="Entrée officielle en remédiation. C'est de cette date que part "
        "le décompte du volume horaire — et vraisemblablement la facturation.",
    )
    date_cloture = models.DateField(null=True, blank=True)
    corpus_reference = models.BooleanField(
        "session du corpus de référence",
        default=False,
        db_index=True,
        help_text="Session ouverte pour taguer une copie du corpus (module 3). "
        "Ce n'est pas le parcours d'un élève : elle ne peut ni établir de plan ni "
        "inscrire au programme.",
    )

    class Meta:
        db_table = "session_suivi"
        verbose_name = "session"
        ordering = ["-date_debut"]
        constraints = [
            # Une date de clôture sur une session encore en cours signifierait
            # qu'on a clos sans changer d'état : l'incohérence serait invisible
            # à l'écran et fausserait les indicateurs de durée.
            models.CheckConstraint(
                condition=(
                    # `sorted` et non `list` : l'ordre d'itération d'un frozenset
                    # varie d'une exécution à l'autre, si bien que `makemigrations`
                    # croyait la contrainte modifiée à chaque appel et produisait
                    # une migration parasite (c'est l'origine de 0003 et 0004).
                    models.Q(etat__in=sorted(ETATS_SESSION_TERMINES))
                    | models.Q(date_cloture__isnull=True)
                ),
                name="session_en_cours_sans_date_cloture",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(etat=EtatSession.REMEDIATION, date_inscription__isnull=False)
                    | ~models.Q(etat=EtatSession.REMEDIATION)
                ),
                name="remediation_implique_date_inscription",
            ),
        ]

    def __str__(self) -> str:
        return f"Session {self.pk} — {self.identifiant_hakili}"

    # ── Décisions du cycle ───────────────────────────────────────────────────

    def _refuser_si_corpus(self) -> None:
        """Une session de corpus n'est le parcours de personne.

        Les problèmes du corpus décrivent ce qu'un humain a lu sur une copie
        d'archive ; ils ne décrivent pas la situation d'un élève à accompagner.
        Sans ce garde-fou, taguer une copie sous l'identifiant d'un élève
        réellement suivi ferait entrer ces problèmes dans son coût total, donc
        dans son palier, donc dans ce que sa famille paierait.
        """
        if self.corpus_reference:
            raise ValidationError(
                "Cette session appartient au corpus de référence (module 3) : "
                "elle sert à mesurer le diagnostic, pas à accompagner un élève. "
                "Ni plan ni inscription ne peuvent en sortir."
            )

    def calculer_palier(self) -> str:
        """Palier d'après le coût total des problèmes confirmés (protocole §7)."""
        total = self.cout_total_confirme
        if total < 8:
            return Palier.A
        if total <= 20:
            return Palier.B
        return Palier.C

    @transaction.atomic
    def etablir_le_plan(self):
        """Après T1 : fige le palier et oriente la session.

        Trois issues, et elles ne se confondent pas :
        aucun problème confirmé → l'élève sort, c'est un bon résultat ;
        palier C → orientation hors dispositif ;
        sinon → en attente de la décision d'inscription.
        """
        self._refuser_si_corpus()
        confirmes = self.problemes.filter(etat=EtatProbleme.CONFIRME).count()
        if not confirmes:
            self.palier = ""
            self.etat = EtatSession.SANS_SUITE
            self.date_cloture = timezone.localdate()
            self.save(update_fields=["palier", "etat", "date_cloture"])
            return self

        self.palier = self.calculer_palier()
        if self.palier == Palier.C:
            self.etat = EtatSession.HORS_DISPOSITIF
            self.date_cloture = timezone.localdate()
            self.save(update_fields=["palier", "etat", "date_cloture"])
        else:
            self.etat = EtatSession.ATTENTE_INSCRIPTION
            self.save(update_fields=["palier", "etat"])
        return self

    @transaction.atomic
    def inscrire(self, *, forcer: bool = False, motif: str = ""):
        """Inscrit l'élève au programme — la décision humaine du cycle.

        Bascule tous les problèmes confirmés en remédiation, avec leur transition.

        **Refuse le palier C sans décision explicite.** Proposer un parcours court
        à un élève qui cumule plus de vingt heures de lacunes garantit un échec, et
        un échec visible coûte plus cher au centre qu'un refus argumenté. `forcer`
        permet de passer outre, mais exige un motif : la décision est alors tracée
        dans les transitions, pas seulement dans la tête de celui qui l'a prise.
        """
        self._refuser_si_corpus()
        if self.etat == EtatSession.REMEDIATION:
            raise ValidationError("Cet élève est déjà inscrit au programme.")

        # `hors_dispositif` est terminal, mais c'est justement l'état où une
        # dérogation se demande : on le laisse passer jusqu'au garde-fou du
        # palier C, dont le message explique quoi faire. Le refuser ici
        # renverrait « session terminée », ce qui n'aide personne.
        if (
            self.etat in ETATS_SESSION_TERMINES
            and self.etat != EtatSession.HORS_DISPOSITIF
        ):
            raise ValidationError(
                f"Session « {self.get_etat_display()} » : elle ne peut plus "
                "recevoir d'inscription."
            )

        confirmes = list(self.problemes.filter(etat=EtatProbleme.CONFIRME))
        if not confirmes:
            raise ValidationError(
                "Aucun problème confirmé : il n'y a rien à remédier. Le test de "
                "confirmation doit avoir eu lieu avant l'inscription."
            )

        palier = self.palier or self.calculer_palier()
        if palier == Palier.C and not forcer:
            raise ValidationError(
                f"Palier C — {self.cout_total_confirme:g} h de remédiation estimées. "
                "Cet élève ne relève pas d'une remédiation courte, mais d'un "
                "accompagnement régulier. Inscrire malgré tout demande une décision "
                "explicite et un motif."
            )
        if forcer and not motif.strip():
            raise ValidationError(
                "Passer outre demande un motif : il sera conservé dans l'historique."
            )

        self.palier = palier
        self.etat = EtatSession.REMEDIATION
        self.date_inscription = timezone.localdate()
        # La session repart : une date de clôture posée par l'orientation hors
        # dispositif n'a plus lieu d'être, et la contrainte l'interdit.
        self.date_cloture = None
        self.save(
            update_fields=["palier", "etat", "date_inscription", "date_cloture"]
        )

        commentaire = f"Inscription au programme (palier {palier})"
        if forcer:
            commentaire += f" — passage outre : {motif.strip()}"
        for probleme in confirmes:
            probleme.changer_etat(
                EtatProbleme.EN_REMEDIATION, commentaire=commentaire
            )
        return self

    @transaction.atomic
    def cloturer(self):
        """Ferme le cycle après T5."""
        if self.etat in ETATS_SESSION_TERMINES:
            raise ValidationError("Cette session est déjà terminée.")
        self.etat = EtatSession.CLOSE
        self.date_cloture = timezone.localdate()
        self.save(update_fields=["etat", "date_cloture"])
        return self

    @transaction.atomic
    def abandonner(self, motif: str = ""):
        if self.etat in ETATS_SESSION_TERMINES:
            raise ValidationError("Cette session est déjà terminée.")
        self.etat = EtatSession.ABANDONNEE
        self.date_cloture = timezone.localdate()
        self.save(update_fields=["etat", "date_cloture"])
        return self

    @property
    def inscrite(self) -> bool:
        return self.etat == EtatSession.REMEDIATION

    @property
    def terminee(self) -> bool:
        return self.etat in ETATS_SESSION_TERMINES

    @property
    def cout_total_confirme(self):
        """Somme des coûts des problèmes confirmés — base du choix de palier.

        `ATT` n'a aucune ligne de coût par construction (non remédiable) et les 27
        compétences du lycée n'en ont pas non plus (volume horaire absent) :
        `cout_estime` vaut alors 0, ce qui est le comportement voulu et non une
        donnée manquante. Voir `referentiel.CoutRemediation`.
        """
        from decimal import Decimal

        total = self.problemes.filter(etat=EtatProbleme.CONFIRME).aggregate(
            total=models.Sum("cout_estime")
        )["total"]
        return total or Decimal("0")

    @property
    def cout_total_hypothese(self):
        """Somme des coûts des lacunes encore à l'état d'hypothèse (avant T1).

        Sert à donner à l'enseignant un ordre de grandeur du volume horaire dès
        le diagnostic initial, avant que le test de confirmation ne tranche
        lesquelles de ces hypothèses deviennent des problèmes confirmés.
        """
        from decimal import Decimal

        total = self.problemes.filter(etat=EtatProbleme.HYPOTHESE).aggregate(
            total=models.Sum("cout_estime")
        )["total"]
        return total or Decimal("0")


class Evaluation(models.Model):
    """Une passation (T0 à T5).

    `copy_id` relie l'évaluation au scan déjà persisté par le pipeline, au lieu de
    stocker une seconde fois le PDF et les images.

    Lien souple, pas clé étrangère — et c'est délibéré. La table `copie` appartient
    à SQLAlchemy tant que les deux ORM cohabitent : une vraie clé étrangère
    coupleraient le schéma Django à une table qu'un autre ORM peut modifier, et
    rendrait la base de test inutilisable (Django ne crée pas les tables non gérées).
    C'est le même choix que `Session.identifiant_hakili`, texte lui aussi parce que
    l'élève vit dans les Google Sheets (D-CEO-20) : quand la donnée référencée est
    hors du territoire de Django, on garde un identifiant et on documente le lien.

    Quand `copie` passera sous Django, ce champ pourra devenir une vraie clé
    étrangère — décision explicite, pas effet de bord.
    """

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="evaluations"
    )
    type = models.CharField(max_length=2, choices=TypeEvaluation.choices)
    date = models.DateField(default=timezone.localdate)
    duree_reelle = models.PositiveIntegerField(
        "durée réelle (min)",
        null=True,
        blank=True,
        help_text="Alimente l'indicateur d'écart durée estimée / réelle (module 9).",
    )
    support = models.CharField(
        max_length=50, blank=True, help_text="Ex. « scan 150 DPI », « saisie manuelle »."
    )
    copy_id = models.CharField(
        "copie associée",
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Identifiant de la copie déjà persistée par le pipeline. Vide si "
        "l'évaluation a été saisie à la main.",
    )

    numero = models.PositiveSmallIntegerField(
        "rang",
        default=1,
        help_text="Rang de cette évaluation parmi celles du même type dans la "
        "session. Le premier T3 porte 1, le suivant 2, etc.",
    )

    sujet_confirmation = models.JSONField(
        "sujet T1 généré",
        null=True,
        blank=True,
        help_text="Liste des exercices du sujet de confirmation (module 5) généré "
        "à la suite de cette évaluation T0 — numéro, énoncé, indice. Sert à la fois "
        "au PDF déjà produit et à construire le barème de la correction T1, sans "
        "rien deviner d'un sujet réextrait après coup.",
    )

    # ── Corpus de référence (module 3) ───────────────────────────────────────
    # Le corpus est l'étalon du module 4 : des copies dont les problèmes ont été
    # relevés **à la main**, pour mesurer l'écart du diagnostic automatique. Sans
    # lui, on ne saurait pas si le module 4 fonctionne — seulement qu'il produit
    # quelque chose.
    corpus_reference = models.BooleanField(
        "copie du corpus de référence",
        default=False,
        db_index=True,
        help_text="Les problèmes de cette évaluation ont été relevés par un humain "
        "et font foi. Le module 4 se mesure contre eux, il ne les écrase jamais.",
    )
    tague_par = models.CharField(
        "tagué par",
        max_length=120,
        blank=True,
        help_text="Qui a fait le relevé. Un corpus sans auteur n'est pas "
        "discutable : deux personnes ne tagueront pas tout à fait pareil, et c'est "
        "une information, pas un défaut.",
    )
    date_tagage = models.DateField("date du relevé", null=True, blank=True)

    class Meta:
        verbose_name = "évaluation"
        ordering = ["session", "date", "type", "numero"]
        constraints = [
            # Un même type peut se répéter — l'enseignant relance un test de
            # vérification tant que des lacunes persistent — mais deux évaluations
            # ne peuvent pas porter le même rang, sinon l'historique devient
            # ambigu et les indicateurs du module 9 comptent de travers.
            models.UniqueConstraint(
                fields=["session", "type", "numero"],
                name="evaluation_unique_par_rang",
            ),
            # Une copie du corpus sans auteur ni date n'est pas exploitable : on ne
            # saurait ni qui interroger sur un tagage discutable, ni à quelle
            # version du référentiel il se rapporte.
            models.CheckConstraint(
                condition=(
                    models.Q(corpus_reference=False)
                    | (~models.Q(tague_par="") & models.Q(date_tagage__isnull=False))
                ),
                name="corpus_reference_trace",
            ),
        ]

    def __str__(self) -> str:
        rang = f" ({self.numero})" if self.numero > 1 else ""
        return f"{self.type}{rang} — session {self.session_id}"

    def save(self, *args, **kwargs) -> None:
        """Attribue le rang à la création.

        Calculé ici plutôt que laissé à l'appelant : un rang oublié ferait
        échouer l'insertion sur la contrainte d'unicité, avec un message
        incompréhensible pour qui ne connaît pas le modèle.
        """
        if self._state.adding and self.session_id:
            dernier = (
                Evaluation.objects.filter(session_id=self.session_id, type=self.type)
                .order_by("-numero")
                .values_list("numero", flat=True)
                .first()
            )
            self.numero = (dernier or 0) + 1
        super().save(*args, **kwargs)

    @property
    def libelle(self) -> str:
        """« Vérification après remédiation » ou « … (2e passage) »."""
        base = self.get_type_display().split("—", 1)[-1].strip()
        if self.numero == 1:
            return base
        return f"{base} ({self.numero}e passage)"

    @property
    def copie(self) -> "Copie | None":
        """Résout la copie liée, ou None. Requête explicite plutôt que jointure
        automatique : le lien n'est pas garanti par la base."""
        if not self.copy_id:
            return None
        return Copie.objects.filter(pk=self.copy_id).first()


class Reponse(models.Model):
    """Ce que l'élève a produit sur une question, et le type d'erreur détecté.

    Pour un QCM, `code_type_erreur_detecte` vient directement de la table des
    options — aucun appel de modèle. Pour les autres formats, du module 4.
    """

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="reponses"
    )
    question = models.ForeignKey(
        "referentiel.Question", on_delete=models.PROTECT, related_name="reponses"
    )
    reponse_brute = models.TextField(
        blank=True, help_text="Transcription de la copie. Vide = sans réponse."
    )
    correcte = models.BooleanField(null=True, blank=True, help_text="Nul = pas encore corrigé.")
    type_erreur_detecte = models.ForeignKey(
        "referentiel.TypeErreur",
        on_delete=models.PROTECT,
        related_name="reponses",
        null=True,
        blank=True,
        db_column="code_type_erreur_detecte",
    )

    class Meta:
        verbose_name = "réponse"
        ordering = ["evaluation", "question"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "question"], name="reponse_unique_par_evaluation"
            ),
            # Une réponse juste ne porte pas de type d'erreur.
            models.CheckConstraint(
                condition=~models.Q(correcte=True, type_erreur_detecte__isnull=False),
                name="reponse_juste_sans_type_erreur",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.evaluation} / {self.question_id}"


class Probleme(models.Model):
    """compétence × type d'erreur — l'unité de suivi du dispositif.

    Ne jamais écrire `etat` directement : passer par `changer_etat()`, qui garantit
    l'écriture de la `Transition` correspondante. Un état modifié sans transition
    rend les indicateurs du module 9 faux sans que rien ne le signale.
    """

    #: Enchaînements permis. Un problème écarté ou clos est terminal.
    TRANSITIONS_PERMISES: dict[str, set[str]] = {
        EtatProbleme.HYPOTHESE: {EtatProbleme.CONFIRME, EtatProbleme.ECARTE},
        EtatProbleme.CONFIRME: {EtatProbleme.EN_REMEDIATION},
        EtatProbleme.EN_REMEDIATION: {EtatProbleme.RESOLU, EtatProbleme.NON_RESOLU},
        EtatProbleme.RESOLU: {EtatProbleme.REGRESSE, EtatProbleme.CLOS},
        EtatProbleme.NON_RESOLU: {EtatProbleme.EN_REMEDIATION},
        EtatProbleme.REGRESSE: {EtatProbleme.EN_REMEDIATION},
        EtatProbleme.ECARTE: set(),
        EtatProbleme.CLOS: set(),
    }

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="problemes"
    )
    competence = models.ForeignKey(
        "referentiel.Competence", on_delete=models.PROTECT, related_name="problemes"
    )
    type_erreur = models.ForeignKey(
        "referentiel.TypeErreur", on_delete=models.PROTECT, related_name="problemes"
    )
    etat = models.CharField(
        max_length=15, choices=EtatProbleme.choices, default=EtatProbleme.HYPOTHESE
    )
    cout_estime = models.DecimalField(
        "coût estimé (h)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Lu dans CoutRemediation. Vaut 0 pour ATT (non remédiable) et pour "
        "les compétences de lycée sans volume horaire — cas normaux.",
    )
    evaluation_origine = models.ForeignKey(
        Evaluation,
        on_delete=models.SET_NULL,
        related_name="problemes_reveles",
        null=True,
        blank=True,
        verbose_name="révélé par",
        help_text="La passation qui a fait apparaître ce problème. Nul pour un "
        "problème saisi hors évaluation.",
    )
    justification = models.TextField(
        "ce qui a été lu sur la copie",
        blank=True,
        help_text="La production de l'élève qui a conduit à relever ce problème. "
        "Saisie à la main pour le corpus de référence (module 3), remplie par la "
        "citation du diagnostic pour le module 4 — c'est ce qui rend un désaccord "
        "entre les deux arbitrable plutôt qu'un simple écart de comptage.",
    )
    exercices_confirmation = models.JSONField(
        "exercices du sujet T1",
        default=list,
        blank=True,
        help_text="Numéros des exercices du sujet de confirmation (module 5) qui "
        "ciblent cette hypothèse — sert à retrouver, dans la correction T1, quelles "
        "questions départagent confirmé/écarté pour ce problème précis. Vide pour un "
        "problème hors de ce circuit (corpus de référence, saisie manuelle).",
    )

    class Meta:
        verbose_name = "problème"
        verbose_name_plural = "problèmes"
        ordering = ["session", "-cout_estime"]
        constraints = [
            # Un même couple compétence × type d'erreur ne se suit qu'une fois par
            # session : deux lignes identiques compteraient double dans tous les
            # indicateurs.
            models.UniqueConstraint(
                fields=["session", "competence", "type_erreur"],
                name="probleme_unique_par_session",
            )
        ]

    def __str__(self) -> str:
        return f"{self.competence_id} × {self.type_erreur_id} [{self.etat}]"

    def clean(self) -> None:
        # `ATT` existe pour être écarté, jamais remédié (protocole §3).
        if self.type_erreur_id == "ATT" and self.etat not in {
            EtatProbleme.HYPOTHESE,
            EtatProbleme.ECARTE,
        }:
            raise ValidationError(
                {
                    "etat": "Un problème de type ATT (inattention) ne peut être "
                    "qu'en hypothèse ou écarté : il ne donne jamais lieu à remédiation."
                }
            )

    @transaction.atomic
    def changer_etat(
        self,
        nouvel_etat: str,
        *,
        evaluation: Evaluation | None = None,
        commentaire: str = "",
    ) -> "Transition":
        """Change l'état et journalise la transition — les deux ou aucun.

        Refuse un enchaînement non prévu par `TRANSITIONS_PERMISES` plutôt que de
        laisser l'historique devenir incohérent.
        """
        ancien = self.etat
        if nouvel_etat == ancien:
            raise ValidationError(f"Le problème est déjà en état « {ancien} ».")

        permis = self.TRANSITIONS_PERMISES.get(ancien, set())
        if nouvel_etat not in permis:
            attendu = ", ".join(sorted(permis)) or "aucun (état terminal)"
            raise ValidationError(
                f"Transition « {ancien} » → « {nouvel_etat} » non permise. "
                f"États atteignables : {attendu}."
            )

        self.etat = nouvel_etat
        self.full_clean()
        self.save(update_fields=["etat"])

        return Transition.objects.create(
            probleme=self,
            etat_avant=ancien,
            etat_apres=nouvel_etat,
            evaluation=evaluation,
            commentaire=commentaire,
        )


class Transition(models.Model):
    """Le cœur du dispositif : chaque changement d'état, daté.

    Les 5 indicateurs du module 9 se calculent tous depuis cette table — taux de
    résolution à T3, rétention à 45 jours et à 3 mois, taux de confirmation à T1
    (qui mesure la qualité du diagnostic, pas l'élève), écart durée estimée /
    réelle. Une transition manquante, et l'indicateur est faux en silence.

    Aucune ligne n'est modifiable après création : un historique qu'on peut
    réécrire ne prouve rien.
    """

    probleme = models.ForeignKey(
        Probleme, on_delete=models.CASCADE, related_name="transitions"
    )
    etat_avant = models.CharField(max_length=15, choices=EtatProbleme.choices)
    etat_apres = models.CharField(max_length=15, choices=EtatProbleme.choices)
    date = models.DateTimeField(default=timezone.now, db_index=True)
    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.SET_NULL,
        related_name="transitions",
        null=True,
        blank=True,
        help_text="L'évaluation qui a provoqué le changement, quand il y en a une.",
    )
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "transition"
        ordering = ["probleme", "date"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(etat_avant=models.F("etat_apres")),
                name="transition_change_etat",
            )
        ]
        indexes = [models.Index(fields=["etat_apres", "date"])]

    def __str__(self) -> str:
        return f"{self.probleme_id} : {self.etat_avant} → {self.etat_apres}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise ValidationError(
                "Une transition ne se modifie pas : l'historique doit rester fiable. "
                "Créer une nouvelle transition."
            )
        super().save(*args, **kwargs)


class Seance(models.Model):
    """La fiche que le tuteur remplit après chaque séance — cinq champs, pas plus.

    Entre T1 et T2, le tuteur observe ce qu'aucun test ne capte : blocages,
    stratégies d'évitement, réponses devinées, anxiété. Sur plusieurs semaines
    c'est le signal le plus riche du dispositif (protocole §8).

    Cinq champs et pas six : « une fiche plus longue ne sera pas remplie ». Cette
    contrainte vient du terrain, ne pas l'élargir sans en parler.
    """

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="seances"
    )
    date = models.DateField(default=timezone.localdate)
    tuteur = models.CharField(max_length=120)
    duree = models.PositiveIntegerField("durée (min)", validators=[MinValueValidator(1)])
    problemes_travailles = models.ManyToManyField(
        Probleme,
        related_name="seances",
        blank=True,
        help_text="À choisir parmi les problèmes ouverts de la session.",
    )
    blocage = models.TextField("ce qui a bloqué", blank=True)
    deblocage = models.TextField("ce qui a débloqué", blank=True)
    travail_donne = models.TextField("travail donné", blank=True)
    appreciation = models.TextField("appréciation de la séance", blank=True)

    class Meta:
        verbose_name = "séance"
        verbose_name_plural = "séances"
        ordering = ["session", "-date"]

    def __str__(self) -> str:
        return f"Séance {self.date} — session {self.session_id}"
