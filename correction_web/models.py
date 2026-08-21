"""
État d'une correction en cours.

Pourquoi une table, et pas la session
-------------------------------------
Le pipeline dure 60 à 90 secondes et comporte **deux arrêts de validation
humaine** : la relecture de la transcription, puis le tableau de validation des
notes. Il faut donc conserver un état entre plusieurs requêtes, et il doit
survivre à un rechargement de page comme au redémarrage d'un processus.

Streamlit gardait cet état dans `session_state` (mémoire du processus) et lançait
le pipeline dans un thread. Ça ne se transpose pas : en production, plusieurs
processus servent les requêtes, et rien ne garantit que la requête suivante
tombera sur celui qui détient l'objet. Une table est la seule réponse correcte.

Le résultat du pipeline est stocké en JSON, pas en pickle : voir
`src/pipeline/serialisation.py` pour le motif.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from suivi.models import TypeEvaluation


class EtatCorrection(models.TextChoices):
    """Les états en `_EN_COURS` sont ceux où un thread travaille ; `RELECTURE` et
    `VALIDATION` sont les deux arrêts où l'on attend l'enseignant."""

    CREEE = "creee", "Créée"
    TRANSCRIPTION = "transcription", "Transcription en cours"
    RELECTURE = "relecture", "En attente de relecture de la transcription"
    CORRECTION = "correction", "Correction en cours"
    VALIDATION = "validation", "En attente de validation des notes"
    DIAGNOSTIC = "diagnostic", "Diagnostic en cours"
    TERMINEE = "terminee", "Terminée"
    ECHEC = "echec", "Échec"


#: États où un traitement tourne en arrière-plan — la page se rafraîchit.
ETATS_EN_COURS = frozenset(
    {EtatCorrection.TRANSCRIPTION, EtatCorrection.CORRECTION, EtatCorrection.DIAGNOSTIC}
)

#: États où l'on attend une action de l'enseignant.
ETATS_EN_ATTENTE = frozenset({EtatCorrection.RELECTURE, EtatCorrection.VALIDATION})


class Correction(models.Model):
    copy_id = models.CharField(max_length=255, unique=True, db_index=True)
    identifiant_hakili = models.CharField(max_length=255, db_index=True)

    # Nom et prénom recopiés à la création : ils servent aux titres de page et aux
    # noms de fichiers. Les relire dans le Sheet à chaque affichage ajouterait un
    # appel réseau, et une coupure rendrait la page inutilisable.
    # `contact_parents` n'est jamais recopié ici.
    eleve_nom = models.CharField(max_length=120, blank=True)
    eleve_prenom = models.CharField(max_length=120, blank=True)

    bareme_id = models.CharField(
        max_length=60, blank=True, help_text="Test du catalogue, vide en mode libre."
    )
    type_evaluation = models.CharField(
        max_length=2,
        choices=TypeEvaluation.choices,
        default=TypeEvaluation.T0,
        help_text="Étape du cycle de suivi que cette copie fait passer — "
        "détermine si elle produit des hypothèses (T0) ou confirme/écarte "
        "des hypothèses existantes (T1), etc.",
    )
    instructions_expert = models.TextField(blank=True)

    etat = models.CharField(
        max_length=15, choices=EtatCorrection.choices, default=EtatCorrection.CREEE
    )
    etape = models.CharField(max_length=120, blank=True, help_text="Libellé affiché.")
    progression = models.PositiveSmallIntegerField(default=0)

    resultat = models.JSONField(null=True, blank=True)
    erreurs = models.JSONField(default=list, blank=True)

    # Clé de la personne qui a lancé la correction (comptes.backends.cle_personne).
    lancee_par = models.CharField(max_length=255, blank=True)

    cree_le = models.DateTimeField(default=timezone.now, db_index=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "correction"
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return f"{self.eleve_nom} {self.eleve_prenom} — {self.get_etat_display()}"

    @property
    def en_cours(self) -> bool:
        return self.etat in ETATS_EN_COURS

    @property
    def en_attente(self) -> bool:
        return self.etat in ETATS_EN_ATTENTE

    @property
    def terminee(self) -> bool:
        return self.etat == EtatCorrection.TERMINEE

    @property
    def echouee(self) -> bool:
        return self.etat == EtatCorrection.ECHEC

    def avancer(self, *, etape: str = "", progression: int | None = None) -> None:
        """Met à jour la progression sans toucher au reste.

        Appelée depuis le thread de traitement : on écrit le minimum de champs pour
        ne pas écraser une modification faite entre-temps par une requête web.
        """
        champs = ["maj_le"]
        if etape:
            self.etape = etape
            champs.append("etape")
        if progression is not None:
            self.progression = max(0, min(100, progression))
            champs.append("progression")
        self.save(update_fields=champs)

    def echouer(self, message: str) -> None:
        self.etat = EtatCorrection.ECHEC
        self.erreurs = list(self.erreurs or []) + [message]
        self.save(update_fields=["etat", "erreurs", "maj_le"])
