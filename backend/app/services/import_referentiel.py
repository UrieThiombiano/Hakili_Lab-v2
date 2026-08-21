"""Port de `referentiel/management/commands/importer_referentiel.py` —
importe `Referentiel_Socle_v0.xlsx` dans les tables SQLAlchemy. Même
algorithme, même stratégie d'écriture, même contrôle d'intégrité **avant**
toute écriture (un code inconnu fait échouer tout l'import, rien n'est écrit
à moitié). Voir le fichier d'origine pour la justification complète de
chaque choix ; ce module ne répète que ce que le code doit faire.

Deux stratégies d'écriture, reprises telles quelles :
- `TypeErreur`, `Competence`, `Question` sont mises à jour, jamais
  supprimées (le suivi des élèves pointe dessus).
- `Prerequis`, `CoutRemediation`, `SignatureErreur`, `OptionQcm` sont
  remplacées en bloc (rien ne pointe vers elles).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as SQLASession

from app.models import (
    Competence,
    CoutRemediation,
    OptionQcm,
    Prerequis,
    Question,
    SignatureErreur,
    TypeErreur,
)
from app.services.couts import VOLUME_REPLI_LYCEE, arrondir_heures, cout_remediation

_ONGLETS = (
    "01_Types_erreur",
    "02_Competences",
    "04_Questions",
    "05_Grille_diagnostic",
    "06_Distracteurs",
    "08_Cout_remediation",
)

_DIVISEUR_BAREME = Decimal(3)


class ErreurImport(ValueError):
    """Référence inconnue dans le classeur — aucune écriture n'a eu lieu."""


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _oui(valeur) -> bool:
    return _texte(valeur).upper() in {"OUI", "YES", "TRUE", "1"}


def _decimal(valeur) -> Decimal | None:
    brut = _texte(valeur)
    if not brut or brut.lower().startswith("non disponible"):
        return None
    try:
        return Decimal(brut.replace(",", "."))
    except Exception:
        return None


@dataclass
class RapportImport:
    a_blanc: bool = False
    lignes_lues: dict[str, int] = field(default_factory=dict)
    n_types: int = 0
    n_competences: int = 0
    n_prerequis: int = 0
    n_couts: int = 0
    n_couts_estimes: int = 0
    n_questions: int = 0
    n_signatures: int = 0
    n_options: int = 0
    n_qcm_avec_reponse: int = 0
    n_sans_corrige: int = 0


def lire_onglets(chemin: Path) -> dict[str, list]:
    wb = openpyxl.load_workbook(chemin, data_only=True, read_only=True)
    try:
        return {nom: list(wb[nom].iter_rows(values_only=True))[1:] for nom in _ONGLETS}
    except KeyError as exc:
        raise ErreurImport(f"Onglet manquant dans le classeur : {exc}") from exc
    finally:
        wb.close()


def verifier_integrite(onglets: dict[str, list]) -> None:
    """Échoue avant toute écriture si un code est inconnu — contrôler
    d'abord évite d'écrire la moitié du référentiel puis d'échouer."""
    codes_types = {_texte(r[0]) for r in onglets["01_Types_erreur"] if _texte(r[0])}
    codes_comp = {_texte(r[0]) for r in onglets["02_Competences"] if _texte(r[0])}
    erreurs: list[str] = []

    for ligne in onglets["04_Questions"]:
        for col, role in ((6, "principale"), (7, "secondaire")):
            code = _texte(ligne[col])
            if code and code not in codes_comp:
                erreurs.append(f"04_Questions {_texte(ligne[0])}/{_texte(ligne[1])} : compétence {role} « {code} » inconnue")

    for ligne in onglets["05_Grille_diagnostic"]:
        if (code := _texte(ligne[2])) and code not in codes_comp:
            erreurs.append(f"05_Grille_diagnostic : compétence « {code} » inconnue")
        if (code := _texte(ligne[3])) and code not in codes_types:
            erreurs.append(f"05_Grille_diagnostic : type d'erreur « {code} » inconnu")

    for ligne in onglets["06_Distracteurs"]:
        if (code := _texte(ligne[5])) and code not in codes_types:
            erreurs.append(f"06_Distracteurs : type d'erreur « {code} » inconnu")

    for ligne in onglets["08_Cout_remediation"]:
        if (code := _texte(ligne[0])) and code not in codes_comp:
            erreurs.append(f"08_Cout_remediation : compétence « {code} » inconnue")
        if (code := _texte(ligne[3])) and code not in codes_types:
            erreurs.append(f"08_Cout_remediation : type d'erreur « {code} » inconnu")

    if erreurs:
        apercu = "\n  ".join(erreurs[:15])
        reste = f"\n  … et {len(erreurs) - 15} autres" if len(erreurs) > 15 else ""
        raise ErreurImport(f"{len(erreurs)} référence(s) inconnue(s) dans le classeur :\n  {apercu}{reste}\n\nAucune écriture effectuée.")


def _importer_types_erreur(db: SQLASession, lignes: list) -> int:
    n = 0
    for r in lignes:
        code = _texte(r[0])
        if not code:
            continue
        obj = db.get(TypeErreur, code)
        if obj is None:
            obj = TypeErreur(code=code)
            db.add(obj)
        obj.libelle = _texte(r[1])
        obj.definition = _texte(r[2])
        obj.signature = _texte(r[3])
        obj.exemple = _texte(r[4])
        obj.coefficient = _decimal(r[5]) or Decimal(0)
        obj.remediable = _oui(r[6])
        n += 1
    db.flush()
    return n


def _importer_competences(db: SQLASession, lignes: list) -> tuple[int, int]:
    n = 0
    liens: list[tuple[str, str]] = []
    for r in lignes:
        code = _texte(r[0])
        if not code:
            continue

        volume = _decimal(r[8])
        estime = volume is None
        if estime:
            volume = VOLUME_REPLI_LYCEE

        obj = db.get(Competence, code)
        if obj is None:
            obj = Competence(code=code)
            db.add(obj)
        obj.domaine = _texte(r[1])
        obj.libelle = _texte(r[2])
        obj.description = _texte(r[3])
        obj.niveau_intro = _texte(r[4])
        obj.chapitre_intro = _texte(r[5])
        obj.transversale = _oui(r[6])
        obj.volume_horaire = volume
        obj.source_volume = _texte(r[9])
        obj.volume_estime = estime
        n += 1

        for prereq in (p.strip() for p in _texte(r[7]).split(";")):
            if prereq:
                liens.append((code, prereq))
    db.flush()

    connus = {c for c, in db.execute(select(Competence.code))}
    inconnus = {p for _, p in liens if p not in connus}
    if inconnus:
        raise ErreurImport(f"Prérequis pointant vers des compétences inexistantes : {sorted(inconnus)}")

    db.execute(delete(Prerequis))
    db.flush()
    liens_uniques = {(c, p) for c, p in liens if c != p}
    db.add_all([Prerequis(competence_id=c, prerequis_id=p) for c, p in liens_uniques])
    db.flush()
    return n, len(liens_uniques)


def _importer_couts(db: SQLASession, lignes: list) -> tuple[int, int]:
    db.execute(delete(CoutRemediation))
    db.flush()

    objets: list[CoutRemediation] = [
        CoutRemediation(
            competence_id=_texte(r[0]),
            type_erreur_id=_texte(r[3]),
            cout_heures=arrondir_heures(_decimal(r[6]) or Decimal("0.5")),
            derivation=_texte(r[7]),
            estime=False,
        )
        for r in lignes
        if _texte(r[0]) and _texte(r[3])
    ]
    officiels = len(objets)

    deja = {(o.competence_id, o.type_erreur_id) for o in objets}
    remediables = db.execute(select(TypeErreur).where(TypeErreur.coefficient > 0)).scalars().all()
    competences_estimees = db.execute(select(Competence).where(Competence.volume_estime.is_(True))).scalars().all()
    for competence in competences_estimees:
        for type_erreur in remediables:
            if (competence.code, type_erreur.code) in deja:
                continue
            objets.append(
                CoutRemediation(
                    competence_id=competence.code,
                    type_erreur_id=type_erreur.code,
                    cout_heures=cout_remediation(competence.volume_horaire, type_erreur.coefficient),
                    derivation=f"estimation : {competence.volume_horaire:g} h (repli) x {type_erreur.coefficient}",
                    estime=True,
                )
            )

    db.add_all(objets)
    db.flush()
    return officiels, len(objets) - officiels


def _importer_questions(db: SQLASession, lignes: list) -> int:
    n = 0
    for r in lignes:
        niveau, code = _texte(r[0]), _texte(r[1])
        if not (niveau and code):
            continue
        bareme_classeur = _decimal(r[3]) or Decimal(0)
        secondaire = _texte(r[7]) or None

        obj = db.execute(select(Question).where(Question.niveau_test == niveau, Question.code_question == code)).scalar_one_or_none()
        if obj is None:
            obj = Question(niveau_test=niveau, code_question=code)
            db.add(obj)
        obj.partie = _texte(r[2])
        obj.format = _texte(r[4])
        obj.bareme = bareme_classeur / _DIVISEUR_BAREME
        obj.bareme_classeur = bareme_classeur
        obj.code_local = _texte(r[5])
        obj.competence_id = _texte(r[6])
        obj.competence_secondaire_id = secondaire
        obj.objet = _texte(r[8])
        n += 1
    db.flush()
    return n


def _importer_signatures(db: SQLASession, lignes: list) -> int:
    db.execute(delete(SignatureErreur))
    db.flush()

    index = {(q.niveau_test, q.code_question): q.id for q in db.execute(select(Question)).scalars().all()}
    objets: list[SignatureErreur] = []
    orphelines: list[str] = []
    for r in lignes:
        cle = (_texte(r[0]), _texte(r[1]))
        if cle not in index:
            orphelines.append(f"{cle[0]}/{cle[1]}")
            continue
        objets.append(
            SignatureErreur(
                question_id=index[cle],
                competence_id=_texte(r[2]),
                type_erreur_id=_texte(r[3]),
                production_eleve=_texte(r[4]),
                interpretation=_texte(r[5]),
            )
        )
    if orphelines:
        raise ErreurImport(f"{len(orphelines)} signature(s) rattachée(s) à une question inexistante : {sorted(set(orphelines))[:10]}")

    db.add_all(objets)
    db.flush()
    return len(objets)


def _importer_options(db: SQLASession, lignes: list) -> tuple[int, int]:
    """Écrit les options ET remplit `Question.reponse_attendue` pour les
    QCM — c'est ce qui rend un QCM corrigeable sans appel de modèle."""
    db.execute(delete(OptionQcm))
    db.flush()

    questions = {(q.niveau_test, q.code_question): q for q in db.execute(select(Question)).scalars().all()}

    objets: list[OptionQcm] = []
    bonnes: dict[str, list[str]] = {}
    for r in lignes:
        cle = (_texte(r[0]), _texte(r[1]))
        question = questions.get(cle)
        if question is None:
            raise ErreurImport(f"06_Distracteurs : option rattachée à une question inexistante {cle}")
        correcte = _oui(r[4])
        objets.append(
            OptionQcm(
                question_id=question.id,
                lettre=_texte(r[2]),
                texte=_texte(r[3]),
                correcte=correcte,
                type_erreur_id=None if correcte else (_texte(r[5]) or None),
                erreur="" if correcte else _texte(r[6]),
            )
        )
        if correcte:
            bonnes.setdefault(f"{cle[0]}/{cle[1]}", []).append(_texte(r[2]))

    db.add_all(objets)
    db.flush()

    ambigues = [cle for cle, lettres in bonnes.items() if len(lettres) != 1]
    if ambigues:
        raise ErreurImport(f"{len(ambigues)} QCM sans bonne réponse unique — un QCM doit en avoir exactement une : {ambigues[:10]}")

    for cle, lettres in bonnes.items():
        niveau, code = cle.split("/", 1)
        questions[(niveau, code)].reponse_attendue = lettres[0]
    db.flush()

    return len(objets), len(bonnes)


def importer(db: SQLASession, chemin: Path, *, a_blanc: bool = False) -> RapportImport:
    """Importe le classeur dans la base. Transaction unique : une erreur
    d'intégrité annule tout, comme côté Django (`transaction.atomic`)."""
    onglets = lire_onglets(chemin)
    verifier_integrite(onglets)

    rapport = RapportImport(a_blanc=a_blanc, lignes_lues={nom: len(lignes) for nom, lignes in onglets.items()})
    if a_blanc:
        return rapport

    try:
        rapport.n_types = _importer_types_erreur(db, onglets["01_Types_erreur"])
        rapport.n_competences, rapport.n_prerequis = _importer_competences(db, onglets["02_Competences"])
        rapport.n_couts, rapport.n_couts_estimes = _importer_couts(db, onglets["08_Cout_remediation"])
        rapport.n_questions = _importer_questions(db, onglets["04_Questions"])
        rapport.n_signatures = _importer_signatures(db, onglets["05_Grille_diagnostic"])
        rapport.n_options, rapport.n_qcm_avec_reponse = _importer_options(db, onglets["06_Distracteurs"])
    except Exception:
        db.rollback()
        raise

    db.commit()
    rapport.n_sans_corrige = db.execute(select(Question).where(Question.reponse_attendue == "")).scalars().all().__len__()
    return rapport
