"""Port SQLAlchemy de `referentiel/models.py` (Django) — le référentiel et la
banque de questions, importés du classeur, jamais saisis à la main (sauf
`Question.reponse_attendue`/`solution`, voir plus bas).

Fidélité délibérée aux noms de table/colonne/contrainte Django
----------------------------------------------------------------
Les noms de table (`referentiel_typeerreur`, etc.), les colonnes de clé
étrangère (`<champ>_id`) et les noms de contraintes (`prerequis_unique`,
`option_type_erreur_coherent`, ...) reproduisent exactement ceux que Django
génère. Ce n'est pas un souci d'esthétique : le plan de migration (Phase 4)
prévoit qu'Alembic **adopte** le schéma existant sur Neon sans le recréer,
comme `suivi/migrations/0007_copie_document_sous_django.py` l'a déjà fait une
fois pour l'ancien SQLAlchemy. Un nom qui diverge dès le départ rendrait cette
adoption bien plus dure à vérifier.

Comme en Django, les `choices` (domaine, niveau_test, format, partie) ne sont
**pas** des contraintes de base — Django ne les traduit pas en `CHECK`
(`docs/v2_roadmap.md`, module 1 : « CheckConstraint Django, pas Enum Postgres
natif »). Seules les contraintes explicitement déclarées dans `Meta.constraints`
du modèle Django deviennent des `CheckConstraint`/`UniqueConstraint` ici.
"""
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Domaine(str, enum.Enum):
    """Les 8 domaines de l'onglet 02_Competences — validation applicative
    uniquement (voir docstring du module)."""

    NUMERIQUE = "Activites numeriques"
    ALGEBRE = "Calcul litteral et algebre"
    GEOMETRIE = "Activites geometriques"
    MESURES = "Mesures et grandeurs"
    FONCTIONS = "Fonctions et applications"
    DONNEES = "Donnees, proportionnalite, statistique"
    SUITES = "Suites et raisonnement"
    TRIGONOMETRIE = "Trigonometrie"


class NiveauTest(str, enum.Enum):
    SIXIEME = "6eme"
    CINQUIEME = "5eme"
    QUATRIEME = "4eme"
    TROISIEME = "3eme"
    SECONDE_C = "2ndeC"
    PREMIERE_D = "1ereD"
    TERMINALE_D = "tleD"


class FormatQuestion(str, enum.Enum):
    QCM = "qcm"
    COURT = "court"
    REDIGE = "redige"
    CONSTRUCTION = "construction"


class Partie(str, enum.Enum):
    A = "A"
    B = "B"


class TypeErreur(Base):
    """Les 7 types d'erreur. Liste FERMÉE (protocole-v2.md §3) — `ATT` a un
    coefficient 0 et n'a jamais de ligne dans `CoutRemediation`."""

    __tablename__ = "referentiel_typeerreur"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    libelle: Mapped[str] = mapped_column(String(100))
    definition: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(Text)
    exemple: Mapped[str] = mapped_column(Text, default="", server_default="")
    coefficient: Mapped[str] = mapped_column(Numeric(4, 2))
    remediable: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (
        CheckConstraint("coefficient >= 0 AND coefficient <= 1", name="typeerreur_coefficient_borne"),
    )


class Competence(Base):
    """Les 101 compétences canoniques. `volume_estime` signale les 27 de
    lycée dont le volume horaire est une valeur de repli (`app/services/couts.py`)."""

    __tablename__ = "referentiel_competence"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    domaine: Mapped[str] = mapped_column(String(60))
    libelle: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    niveau_intro: Mapped[str] = mapped_column(String(20))
    chapitre_intro: Mapped[str] = mapped_column(String(100), default="", server_default="")
    transversale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    volume_horaire: Mapped[str | None] = mapped_column(Numeric(5, 2), nullable=True)
    source_volume: Mapped[str] = mapped_column(String(120), default="", server_default="")
    volume_estime: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (
        Index("referentiel_competence_domaine_idx", "domaine"),
        Index("referentiel_competence_niveau_intro_idx", "niveau_intro"),
    )


class Prerequis(Base):
    """Graphe des prérequis directs — parcouru par `app/services/plan.py`
    (tri topologique) pour ordonner le plan de remédiation."""

    __tablename__ = "referentiel_prerequis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competence_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="CASCADE")
    )
    prerequis_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="CASCADE")
    )

    competence: Mapped["Competence"] = relationship(foreign_keys=[competence_id])
    prerequis: Mapped["Competence"] = relationship(foreign_keys=[prerequis_id])

    __table_args__ = (
        UniqueConstraint("competence_id", "prerequis_id", name="prerequis_unique"),
        # Une compétence prérequis d'elle-même créerait une boucle infinie au
        # parcours du graphe (app/services/plan.py).
        CheckConstraint("competence_id <> prerequis_id", name="prerequis_pas_reflexif"),
    )


class CoutRemediation(Base):
    """Coût horaire précalculé par couple compétence × type d'erreur — 606
    lignes (101 compétences × 6 types remédiables ; `ATT` n'y figure jamais).
    Formule et bornes : `app/services/couts.py`."""

    __tablename__ = "referentiel_coutremediation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competence_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="CASCADE")
    )
    type_erreur_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_typeerreur.code", ondelete="CASCADE")
    )
    cout_heures: Mapped[str] = mapped_column(Numeric(4, 2))
    derivation: Mapped[str] = mapped_column(String(200), default="", server_default="")
    estime: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("competence_id", "type_erreur_id", name="cout_unique_par_couple"),
    )


class Question(Base):
    """Les 280 questions des 7 tests d'entrée. `bareme` sur 20 (D-CEO-26) ;
    `reponse_attendue`/`solution` vides pour 209 questions — le seul champ
    de tout le référentiel qu'un humain édite directement (arbitrage B)."""

    __tablename__ = "referentiel_question"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_question: Mapped[str] = mapped_column(String(10))
    niveau_test: Mapped[str] = mapped_column(String(10))
    partie: Mapped[str] = mapped_column(String(1))
    format: Mapped[str] = mapped_column(String(15))
    bareme: Mapped[str] = mapped_column(Numeric(8, 6))
    bareme_classeur: Mapped[str] = mapped_column(Numeric(4, 1))
    code_local: Mapped[str] = mapped_column(String(10), default="", server_default="")
    competence_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="RESTRICT")
    )
    competence_secondaire_id: Mapped[str | None] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="RESTRICT"), nullable=True
    )
    objet: Mapped[str] = mapped_column(Text)
    reponse_attendue: Mapped[str] = mapped_column(Text, default="", server_default="")
    solution: Mapped[str] = mapped_column(Text, default="", server_default="")

    competence: Mapped["Competence"] = relationship(foreign_keys=[competence_id])

    __table_args__ = (
        UniqueConstraint("niveau_test", "code_question", name="question_unique_par_test"),
        Index("referentiel_question_niveau_test_partie_idx", "niveau_test", "partie"),
        Index("referentiel_question_competence_id_idx", "competence_id"),
    )

    @property
    def a_corrige(self) -> bool:
        return bool(self.reponse_attendue)


class SignatureErreur(Base):
    """Les 1031 signatures : ce qu'on lit sur la copie, et la lacune que ça
    révèle — matière du module 4 (le modèle reconnaît, il ne devine pas)."""

    __tablename__ = "referentiel_signatureerreur"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("referentiel_question.id", ondelete="CASCADE")
    )
    competence_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_competence.code", ondelete="RESTRICT")
    )
    type_erreur_id: Mapped[str] = mapped_column(
        ForeignKey("referentiel_typeerreur.code", ondelete="RESTRICT")
    )
    production_eleve: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str] = mapped_column(Text)

    question: Mapped["Question"] = relationship()

    __table_args__ = (
        Index("referentiel_signatureerreur_type_erreur_id_idx", "type_erreur_id"),
    )


class OptionQcm(Base):
    """Les 284 options de QCM — diagnostic mécanique, aucun appel de modèle
    (guide-v2.md, module 4). `option_type_erreur_coherent` est l'invariant
    qui rend ça possible : une bonne réponse ne révèle jamais d'erreur."""

    __tablename__ = "referentiel_optionqcm"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("referentiel_question.id", ondelete="CASCADE")
    )
    lettre: Mapped[str] = mapped_column(String(2))
    texte: Mapped[str] = mapped_column(Text)
    correcte: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    type_erreur_id: Mapped[str | None] = mapped_column(
        ForeignKey("referentiel_typeerreur.code", ondelete="RESTRICT"), nullable=True
    )
    erreur: Mapped[str] = mapped_column(Text, default="", server_default="")

    __table_args__ = (
        UniqueConstraint("question_id", "lettre", name="option_unique_par_question"),
        CheckConstraint(
            "(correcte = true AND type_erreur_id IS NULL) "
            "OR (correcte = false AND type_erreur_id IS NOT NULL)",
            name="option_type_erreur_coherent",
        ),
    )
