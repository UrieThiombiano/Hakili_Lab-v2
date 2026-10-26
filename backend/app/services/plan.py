"""Port de `suivi/plan.py` (Django) — le plan de remédiation : quoi
travailler, dans quel ordre, combien d'heures.

« Un problème dont un prérequis est lui-même en difficulté se traite
**après** ce prérequis, jamais avant » (protocole §3) — tri topologique sur
le graphe des prérequis, restreint aux compétences réellement en difficulté.
À égalité, on commence par le plus fondamental (compétence introduite le plus
tôt dans la scolarité). Algorithme inchangé ; seules les requêtes passent de
l'ORM Django à SQLAlchemy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session as SQLASession

from app.models import Competence, Prerequis, Probleme, Session, SignatureErreur
from app.services.session_service import _seuil_palier

#: Ordre scolaire, pour départager deux problèmes également prioritaires.
_ORDRE_NIVEAUX = ["Primaire", "6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD"]


@dataclass
class EtapePlan:
    """Un problème à traiter, avec de quoi préparer la séance."""

    probleme: Probleme
    rang: int
    cout: Decimal
    prerequis_aussi_en_difficulte: list[Competence] = field(default_factory=list)
    signatures: list[SignatureErreur] = field(default_factory=list)

    @property
    def competence(self) -> Competence:
        return self.probleme.competence

    @property
    def type_erreur(self):
        return self.probleme.type_erreur


def _niveau(competence: Competence) -> int:
    try:
        return _ORDRE_NIVEAUX.index(competence.niveau_intro)
    except ValueError:
        return len(_ORDRE_NIVEAUX)


def dependances_entre(db: SQLASession, codes: set[str]) -> dict[str, set[str]]:
    """Pour chaque compétence de `codes`, ses prérequis qui sont aussi dans
    `codes` (les seuls qui contraignent l'ordre)."""
    dependances: dict[str, set[str]] = {code: set() for code in codes}
    if not codes:
        return dependances
    for lien in db.query(Prerequis).filter(Prerequis.competence_id.in_(codes)).all():
        if lien.prerequis_id in codes:
            dependances[lien.competence_id].add(lien.prerequis_id)
    return dependances


def ordonner_competences(db: SQLASession, competences: list[Competence]) -> list[Competence]:
    """Tri topologique par couches : à chaque tour on sort les compétences
    dont aucun prérequis n'est encore à traiter ; à égalité, la plus
    fondamentale d'abord. Un cycle (la base l'interdit, mais un import mal
    formé pourrait en créer un) verse le reste tel quel plutôt que de boucler
    indéfiniment."""
    restants = {c.code: c for c in competences}
    dependances = dependances_entre(db, set(restants))
    ordonnees: list[Competence] = []
    traites: set[str] = set()

    while restants:
        prets = [code for code in restants if not (dependances[code] - traites)]
        if not prets:
            # Cycle : on verse le reste par niveau plutôt que de boucler.
            prets = list(restants)

        prets.sort(key=lambda c: (_niveau(restants[c]), c))
        for code in prets:
            ordonnees.append(restants.pop(code))
            traites.add(code)

    return ordonnees


def ordonner(db: SQLASession, problemes: list[Probleme]) -> list[Probleme]:
    """Trie les problèmes pour que chaque prérequis en difficulté vienne
    avant — tri fait au niveau de la **compétence** (les prérequis lient des
    compétences entre elles, pas des problèmes), voir `ordonner_competences`.

    Une même compétence peut porter **plusieurs** problèmes (deux types
    d'erreur différents sur la même compétence — la contrainte d'unicité en
    base est `(session, compétence, type d'erreur)`, pas `(session,
    compétence)`) : groupés par compétence pour le tri, mais aucun n'est
    perdu — un dict compétence→UN problème les aurait silencieusement fait
    disparaître.
    """
    par_code: dict[str, list[Probleme]] = {}
    for p in problemes:
        par_code.setdefault(p.competence.code, []).append(p)

    ordonnes: list[Probleme] = []
    for competence in ordonner_competences(db, [groupe[0].competence for groupe in par_code.values()]):
        groupe = par_code[competence.code]
        groupe.sort(key=lambda p: p.type_erreur_id)  # ordre stable entre les problèmes d'une même compétence
        ordonnes.extend(groupe)
    return ordonnes


def _signatures(db: SQLASession, probleme: Probleme) -> list[SignatureErreur]:
    """Ce que l'élève a probablement écrit, et ce que ça révèle — limité au
    type d'erreur diagnostiqué, pas toutes les signatures de la compétence."""
    return (
        db.query(SignatureErreur)
        .filter(
            SignatureErreur.competence_id == probleme.competence_id,
            SignatureErreur.type_erreur_id == probleme.type_erreur_id,
        )
        .limit(4)
        .all()
    )


def construire(db: SQLASession, session: Session, etats: tuple[str, ...] = ("confirme", "en_remediation")) -> dict:
    """Plan d'une session : étapes ordonnées, coût, palier.

    Par défaut, n'inclut que les problèmes **confirmés** ou déjà **en
    remédiation** — une hypothèse non vérifiée n'a rien à faire dans un plan
    de travail officiel. `etats=("hypothese",)` donne le plan *provisoire*
    (estimation avant le test de confirmation T1, non contractuelle) — voir
    `GET /api/sessions/{jeton}/plan-provisoire`.
    """
    problemes = (
        db.query(Probleme)
        .filter(Probleme.session_id == session.id, Probleme.etat.in_(etats))
        .all()
    )

    codes_en_difficulte = {p.competence.code for p in problemes}
    etapes: list[EtapePlan] = []

    liens_par_competence: dict[str, list[Prerequis]] = {}
    if problemes:
        tous_liens = (
            db.query(Prerequis)
            .filter(Prerequis.competence_id.in_(codes_en_difficulte))
            .all()
        )
        for lien in tous_liens:
            liens_par_competence.setdefault(lien.competence_id, []).append(lien)

    for rang, probleme in enumerate(ordonner(db, problemes), start=1):
        prerequis_bloquants = [
            lien.prerequis
            for lien in liens_par_competence.get(probleme.competence_id, [])
            if lien.prerequis_id in codes_en_difficulte
        ]
        etapes.append(
            EtapePlan(
                probleme=probleme,
                rang=rang,
                cout=Decimal(probleme.cout_estime),
                prerequis_aussi_en_difficulte=prerequis_bloquants,
                signatures=_signatures(db, probleme),
            )
        )

    total = sum((e.cout for e in etapes), Decimal("0"))
    return {
        "etapes": etapes,
        "total_heures": total,
        # Palier dérivé du total *de ce plan*, pas de `cout_total_confirme` —
        # correct aussi bien pour le plan officiel que pour le provisoire
        # (`etats=("hypothese",)`), qui ne doit pas se baser sur un coût
        # confirmé qu'il ne contient justement pas.
        "palier": _seuil_palier(total) if etapes else "",
        "nb_problemes": len(etapes),
        "repose_sur_estimation": any(e.probleme.competence.volume_estime for e in etapes),
    }
