"""Port de `correction_web/models.py::Correction` (Django) — l'état d'une
correction en cours. Une table, pas une session : le pipeline dure 60-90 s et
comporte deux arrêts de validation humaine (relecture de transcription,
tableau de validation des notes) ; l'état doit survivre à un rechargement de
page comme à un redémarrage de process, et plusieurs workers uvicorn peuvent
servir les requêtes (même raisonnement que côté Django, transposé tel quel).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .suivi import JSONType, _utcnow_naive

#: États où un traitement tourne en arrière-plan — le client doit repoller.
ETATS_EN_COURS = frozenset({"transcription", "correction", "diagnostic"})
#: États où l'on attend une action de l'enseignant.
ETATS_EN_ATTENTE = frozenset({"relecture", "validation"})


class Correction(Base):
    __tablename__ = "correction_web_correction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    copy_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    identifiant_hakili: Mapped[str] = mapped_column(String(255), index=True)

    eleve_nom: Mapped[str] = mapped_column(String(120), default="", server_default="")
    eleve_prenom: Mapped[str] = mapped_column(String(120), default="", server_default="")

    bareme_id: Mapped[str] = mapped_column(String(60), default="", server_default="")
    type_evaluation: Mapped[str] = mapped_column(String(2), default="T0", server_default="T0")
    instructions_expert: Mapped[str] = mapped_column(Text, default="", server_default="")

    etat: Mapped[str] = mapped_column(String(15), default="creee", server_default="creee")
    etape: Mapped[str] = mapped_column(String(120), default="", server_default="")
    progression: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    resultat: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    erreurs: Mapped[list] = mapped_column(JSONType, default=list)

    lancee_par: Mapped[str] = mapped_column(String(255), default="", server_default="")

    cree_le: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive)

    @property
    def en_cours(self) -> bool:
        return self.etat in ETATS_EN_COURS

    @property
    def en_attente(self) -> bool:
        return self.etat in ETATS_EN_ATTENTE

    @property
    def terminee(self) -> bool:
        return self.etat == "terminee"

    @property
    def echouee(self) -> bool:
        return self.etat == "echec"
