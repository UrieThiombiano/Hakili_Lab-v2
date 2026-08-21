"""Port de `suivi_web/views.py::personnel`/`statistiques` — même contenu, même
tri (comptes en défaut d'abord), mêmes messages d'indisponibilité Sheets.
`/admin/` (CRUD référentiel Django natif) reste hors scope (D-CEO-42) — ce
routeur ne couvre que la partie lecture seule déjà portée côté Django.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import admin_requis
from app.db import get_session
from app.models import Copie
from app.schemas import PersonnelLigne, PersonnelReponse, StatistiquesReponse
from sqlalchemy.orm import Session as SQLASession
from src.integrations import google_sheets
from src.integrations.google_sheets import GoogleSheetsError
from src.services.identite_service import roles_valides_de

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ORDRE_ETAT = {"regresse": 0, "stagne": 1, "progresse": 2}


@router.get("/personnel", response_model=PersonnelReponse)
def personnel(_: dict = Depends(admin_requis)) -> PersonnelReponse:
    """Qui a accès à la plateforme — lecture seule, rien n'est modifiable ici
    (l'ajout/retrait se fait dans le Sheet, D-CEO-21/25)."""
    try:
        personnes = google_sheets.get_personnel()
    except GoogleSheetsError:
        return PersonnelReponse(lignes=[], probleme=0, lecture_impossible=True)

    lignes: list[PersonnelLigne] = []
    probleme = 0
    for personne in personnes:
        roles = roles_valides_de(personne)
        a_un_code = bool(str(personne.get("pin") or "").strip())

        if not roles:
            etat, libelle = "regresse", f"Rôle non reconnu : « {personne.get('role', '')} »"
        elif not a_un_code:
            etat, libelle = "stagne", "Aucun code d'accès — ne peut pas se connecter"
        else:
            etat, libelle = "progresse", "Accès actif"

        if etat != "progresse":
            probleme += 1

        centres = sorted({c for c, _ in personne.get("affectations", []) if c}) or ["—"]
        lignes.append(
            PersonnelLigne(
                personne=personne,
                roles=", ".join(roles) or "—",
                centres=", ".join(centres),
                etat=etat,
                libelle=libelle,
            )
        )

    lignes.sort(key=lambda l: (_ORDRE_ETAT.get(l.etat, 9), l.personne.get("nom", "")))
    return PersonnelReponse(lignes=lignes, probleme=probleme, lecture_impossible=False)


@router.get("/statistiques", response_model=StatistiquesReponse)
def statistiques(
    db: SQLASession = Depends(get_session),
    _: dict = Depends(admin_requis),
) -> StatistiquesReponse:
    """Élèves, centres et copies — mêmes chiffres que côté Django. Les
    centres sont dérivés des Sheets (`get_centres_derives`), jamais d'une
    liste figée (D-CEO-25)."""
    nb_copies: int | None
    try:
        nb_copies = db.query(Copie).count()
    except Exception:  # noqa: BLE001
        nb_copies = None

    eleves: list | None = None
    centres: list[str] = []
    suspects: list[str] = []
    try:
        eleves = google_sheets.get_eleves()
        derives = google_sheets.get_centres_derives()
        centres = sorted(infos["canonique"] for infos in derives.values())
        suspects = sorted(infos["canonique"] for infos in derives.values() if infos["suspect"])
    except GoogleSheetsError:
        pass

    return StatistiquesReponse(
        nb_eleves=len(eleves) if eleves is not None else None,
        nb_centres=len(centres),
        nb_copies=nb_copies,
        centres=centres,
        centres_suspects=suspects,
    )
