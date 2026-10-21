"""Port SQLAlchemy de `suivi/models.py` (Django) — le suivi d'un élève, du
premier test au dernier contrôle de rétention.

Deux points de conception hérités tels quels (voir `suivi/models.py`, docstring
d'origine, pour le détail) :

1. **`Transition` est le cœur du dispositif.** Aucun changement d'état de
   `Probleme` ne doit se faire sans y écrire une ligne datée. Ici, ça passe
   par `app/services/etats.py::changer_etat()`, jamais par une écriture directe
   de `Probleme.etat`.
2. **L'identité de l'élève n'est pas ici.** `identifiant_hakili` est un champ
   texte, jamais une clé étrangère (D-CEO-20) — ne pas recréer de table élève.

Comme dans `referentiel.py`, les noms de table/colonne/contrainte reproduisent
ceux que Django génère (`session_suivi`, `copie`, `document` sont des
`db_table` explicites côté Django ; les autres suivent la convention par
défaut `<app>_<modele>`), pour que l'adoption du schéma existant sur Neon
(Phase 4 du plan) reste vérifiable colonne à colonne.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone


def _utcnow_naive() -> datetime:
    """UTC naïf — cohérent avec `DateTime` (colonnes naïves) plutôt que
    `datetime.utcnow()`, dépréciée."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .referentiel import Competence, TypeErreur  # noqa: F401 (résolution des relationships en string)

#: JSON générique en test (SQLite, colonne texte) ; `jsonb` sur Postgres —
#: c'est ce que Django `JSONField` génère nativement sur Postgres, donc ce
#: qui existe déjà sur Neon pour `Evaluation.sujet_confirmation` et
#: `Probleme.exercices_confirmation`.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Copie(Base):
    """Une copie corrigée — produite et persistée par le pipeline
    (`src/pipeline/depot.py`, `DepotCopies`). Passée sous Django le
    2026-08-05 (D-CEO-40) ; ici sous SQLAlchemy à nouveau, cette fois côté
    FastAPI — la table elle-même ne change pas."""

    __tablename__ = "copie"

    copy_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    identifiant_hakili: Mapped[str] = mapped_column(String(255))
    classe: Mapped[str] = mapped_column(String(50))
    annee_scolaire: Mapped[str] = mapped_column(String(50))
    date_soumission: Mapped[date] = mapped_column(Date, default=date.today)
    notes_finales: Mapped[float | None] = mapped_column(Float, nullable=True)


class Document(Base):
    """Un fichier attaché à une copie (scan/rapport/sujet/remédiation),
    stocké en base (`bytea`) — pas de volume persistant garanti côté
    hébergeur. Servi par jeton signé, jamais par une URL en clair (D-CEO-25)."""

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    copy_id: Mapped[str] = mapped_column(
        "copy_id", ForeignKey("copie.copy_id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(50))
    fichier: Mapped[bytes] = mapped_column(LargeBinary)
    date_creation: Mapped[date] = mapped_column(Date, default=date.today)

    copie: Mapped["Copie"] = relationship()


#: États terminaux d'une session — le parcours ne reprend pas depuis là.
#: Triés (comme côté Django, voir le commentaire de `session_en_cours_sans_date_cloture`
#: dans `suivi/models.py`) pour qu'un `CheckConstraint` généré ne varie jamais
#: d'une exécution à l'autre.
ETATS_SESSION_TERMINES = frozenset({"abandonnee", "close", "hors_dispositif", "sans_suite"})


class Session(Base):
    """Le parcours complet d'un élève (T0→T5), environ sept mois. Nommée
    `Session` côté Python mais `session_suivi` en base — pour ne pas se
    confondre avec la table de session d'authentification, dans la même base."""

    __tablename__ = "session_suivi"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifiant_hakili: Mapped[str] = mapped_column(String(255), index=True)
    date_debut: Mapped[date] = mapped_column(Date, default=date.today)
    palier: Mapped[str] = mapped_column(String(1), default="", server_default="")
    etat: Mapped[str] = mapped_column(String(20), default="diagnostic", server_default="diagnostic")
    date_inscription: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_cloture: Mapped[date | None] = mapped_column(Date, nullable=True)
    corpus_reference: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    #: Sujet T3/T4/T5 généré mais pas encore déposé — porté par la session
    #: plutôt que par une `Evaluation` (qui n'existe pas encore à cet instant,
    #: contrairement à T1 qui se pose sur l'évaluation T0 déjà écrite).
    #: Régénérer avant dépôt écrase simplement ces deux champs, sans créer de
    #: rang fantôme (voir `app/services/generation.py::persister_sujet_verification`).
    sujet_verification_type: Mapped[str | None] = mapped_column(String(2), nullable=True)
    sujet_verification_exercices: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)

    problemes: Mapped[list["Probleme"]] = relationship(back_populates="session")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="session")

    __table_args__ = (
        CheckConstraint(
            "etat IN ('abandonnee','close','hors_dispositif','sans_suite') "
            "OR date_cloture IS NULL",
            name="session_en_cours_sans_date_cloture",
        ),
        CheckConstraint(
            "(etat = 'remediation' AND date_inscription IS NOT NULL) "
            "OR etat <> 'remediation'",
            name="remediation_implique_date_inscription",
        ),
    )

    @property
    def inscrite(self) -> bool:
        return self.etat == "remediation"

    @property
    def terminee(self) -> bool:
        return self.etat in ETATS_SESSION_TERMINES


class Evaluation(Base):
    """Une passation T0 à T5. `copy_id` est un lien souple (texte, pas FK) vers
    `copie.copy_id` — même choix que `Session.identifiant_hakili`, documenté
    dans `suivi/models.py`."""

    __tablename__ = "suivi_evaluation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session_suivi.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(2))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    duree_reelle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support: Mapped[str] = mapped_column(String(50), default="", server_default="")
    copy_id: Mapped[str] = mapped_column(String(255), default="", server_default="", index=True)
    numero: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    sujet_confirmation: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    corpus_reference: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    tague_par: Mapped[str] = mapped_column(String(120), default="", server_default="")
    date_tagage: Mapped[date | None] = mapped_column(Date, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="evaluations")

    __table_args__ = (
        UniqueConstraint("session_id", "type", "numero", name="evaluation_unique_par_rang"),
        CheckConstraint(
            "corpus_reference = false OR (tague_par <> '' AND date_tagage IS NOT NULL)",
            name="corpus_reference_trace",
        ),
        CheckConstraint("duree_reelle IS NULL OR duree_reelle >= 0", name="evaluation_duree_reelle_positive"),
        CheckConstraint("numero >= 0", name="evaluation_numero_positif"),
    )


class Reponse(Base):
    """Ce que l'élève a produit sur une question, et le type d'erreur détecté.
    Pour un QCM, vient directement d'`OptionQcm` — aucun appel de modèle."""

    __tablename__ = "suivi_reponse"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("suivi_evaluation.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("referentiel_question.id", ondelete="RESTRICT"))
    reponse_brute: Mapped[str] = mapped_column(Text, default="", server_default="")
    correcte: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    type_erreur_detecte_id: Mapped[str | None] = mapped_column(
        "code_type_erreur_detecte",
        ForeignKey("referentiel_typeerreur.code", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("evaluation_id", "question_id", name="reponse_unique_par_evaluation"),
        CheckConstraint(
            "NOT (correcte = true AND code_type_erreur_detecte IS NOT NULL)",
            name="reponse_juste_sans_type_erreur",
        ),
    )


class Probleme(Base):
    """compétence × type d'erreur — l'unité de suivi. Ne jamais écrire `etat`
    directement : passer par `app/services/etats.py::changer_etat()`."""

    __tablename__ = "suivi_probleme"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session_suivi.id", ondelete="CASCADE"))
    competence_id: Mapped[str] = mapped_column(ForeignKey("referentiel_competence.code", ondelete="RESTRICT"))
    type_erreur_id: Mapped[str] = mapped_column(ForeignKey("referentiel_typeerreur.code", ondelete="RESTRICT"))
    etat: Mapped[str] = mapped_column(String(15), default="hypothese", server_default="hypothese")
    cout_estime: Mapped[str] = mapped_column(Numeric(5, 2), default=0, server_default="0")
    evaluation_origine_id: Mapped[int | None] = mapped_column(
        ForeignKey("suivi_evaluation.id", ondelete="SET NULL"), nullable=True
    )
    justification: Mapped[str] = mapped_column(Text, default="", server_default="")
    exercices_confirmation: Mapped[list] = mapped_column(JSONType, default=list)
    #: Pendant de `exercices_confirmation` pour T3/T4/T5 — numéros d'exercice
    #: du sujet de vérification actuellement en attente ciblant ce problème.
    #: Champ séparé pour ne rien risquer sur le circuit T1 en production.
    exercices_verification: Mapped[list] = mapped_column(JSONType, default=list)

    session: Mapped["Session"] = relationship(back_populates="problemes")
    competence: Mapped["Competence"] = relationship()
    type_erreur: Mapped["TypeErreur"] = relationship()
    transitions: Mapped[list["Transition"]] = relationship(back_populates="probleme", order_by="Transition.date")

    __table_args__ = (
        UniqueConstraint("session_id", "competence_id", "type_erreur_id", name="probleme_unique_par_session"),
        CheckConstraint("cout_estime >= 0", name="probleme_cout_estime_positif"),
    )


class Transition(Base):
    """Chaque changement d'état de `Probleme`, daté — source des 5
    indicateurs du module 9. **Jamais modifiable après création** : voir
    `app/services/etats.py`, aucune fonction d'update n'est exposée."""

    __tablename__ = "suivi_transition"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    probleme_id: Mapped[int] = mapped_column(ForeignKey("suivi_probleme.id", ondelete="CASCADE"))
    etat_avant: Mapped[str] = mapped_column(String(15))
    etat_apres: Mapped[str] = mapped_column(String(15))
    date: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)
    evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("suivi_evaluation.id", ondelete="SET NULL"), nullable=True
    )
    commentaire: Mapped[str] = mapped_column(Text, default="", server_default="")

    probleme: Mapped["Probleme"] = relationship(back_populates="transitions")

    __table_args__ = (
        CheckConstraint("etat_avant <> etat_apres", name="transition_change_etat"),
        Index("suivi_transition_etat_apres_date_idx", "etat_apres", "date"),
    )


seance_problemes_travailles = Table(
    "suivi_seance_problemes_travailles",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("seance_id", ForeignKey("suivi_seance.id", ondelete="CASCADE")),
    Column("probleme_id", ForeignKey("suivi_probleme.id", ondelete="CASCADE")),
    UniqueConstraint("seance_id", "probleme_id", name="suivi_seance_problemes_travailles_unique"),
)


class FicheRemediation(Base):
    """Une fiche de travail (module 7) — une séance prête à l'emploi pour le
    tuteur : méthode, exemple résolu, exercices gradués, critère de réussite.
    Cataloguée par couple **compétence × type d'erreur × niveau**, pas par
    élève ni par session : deux élèves avec le même problème reçoivent la
    même fiche (guide-v2.md, module 7, « le catalogue »). Assemblée par
    `app/services/fiche_remediation.py` à partir de `RemediationRetriever`
    (D-CEO-41) — jamais par appel de modèle.

    Ne pas confondre avec le plan (`app/services/plan.py`, module 6) : le
    plan dit *quoi* travailler et dans quel ordre pour une session donnée: la
    fiche dit *comment* travailler un problème donné, un contenu réutilisable
    entre sessions (voir D-CEO-43, qui corrige une confusion de nommage entre
    les deux)."""

    __tablename__ = "suivi_fiche_remediation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competence_id: Mapped[str] = mapped_column(ForeignKey("referentiel_competence.code", ondelete="CASCADE"))
    type_erreur_id: Mapped[str] = mapped_column(ForeignKey("referentiel_typeerreur.code", ondelete="CASCADE"))
    #: `NiveauTest` (ex. `2ndeC`) — une même compétence peut être remédiée
    #: différemment selon le niveau auquel l'élève la rencontre.
    niveau: Mapped[str] = mapped_column(String(10))
    contenu: Mapped[dict] = mapped_column(JSONType)
    #: `generee` : produite par `construire_contenu()`, jamais retouchée.
    #: `corrigee` : un tuteur l'a corrigée — ce contenu fait foi, et
    #: `obtenir_ou_generer()` ne le régénère plus jamais automatiquement.
    version: Mapped[str] = mapped_column(String(10), default="generee", server_default="generee")
    date_generation: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
    corrigee_par: Mapped[str] = mapped_column(String(120), default="", server_default="")
    date_correction: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    competence: Mapped["Competence"] = relationship()
    type_erreur: Mapped["TypeErreur"] = relationship()

    __table_args__ = (
        UniqueConstraint("competence_id", "type_erreur_id", "niveau", name="fiche_remediation_unique_par_couple"),
        CheckConstraint("version IN ('generee', 'corrigee')", name="fiche_remediation_version_valide"),
        CheckConstraint(
            "version = 'generee' OR (corrigee_par <> '' AND date_correction IS NOT NULL)",
            name="fiche_remediation_correction_tracee",
        ),
    )


class Seance(Base):
    """La fiche que le tuteur remplit après chaque séance — cinq champs, pas
    plus (« une fiche plus longue ne sera pas remplie », protocole §8)."""

    __tablename__ = "suivi_seance"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session_suivi.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    tuteur: Mapped[str] = mapped_column(String(120))
    duree: Mapped[int] = mapped_column(Integer)
    blocage: Mapped[str] = mapped_column(Text, default="", server_default="")
    deblocage: Mapped[str] = mapped_column(Text, default="", server_default="")
    travail_donne: Mapped[str] = mapped_column(Text, default="", server_default="")
    appreciation: Mapped[str] = mapped_column(Text, default="", server_default="")

    problemes_travailles: Mapped[list["Probleme"]] = relationship(secondary=seance_problemes_travailles)

    __table_args__ = (
        CheckConstraint("duree >= 1", name="seance_duree_minimum"),
    )

