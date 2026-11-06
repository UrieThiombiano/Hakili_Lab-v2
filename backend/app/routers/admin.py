"""Port de `suivi_web/views.py::personnel`/`statistiques` — même contenu, même
tri (comptes en défaut d'abord), mêmes messages d'indisponibilité Sheets.
`/admin/` (CRUD référentiel Django natif) reste hors scope (D-CEO-42) — ce
routeur ne couvre que la partie lecture seule déjà portée côté Django.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import acces_libre, admin_requis, utilisateur_requis
from app.db import get_session
from app.models import Copie
from app.schemas import (
    PersonnelLigne,
    PersonnelReponse,
    PreferencesModelesRequete,
    PreferencesModelesReponse,
    StatistiquesReponse,
)
from sqlalchemy.orm import Session as SQLASession
from src.core import preferences_modeles
from src.core.roles import UserRole
from src.integrations import google_sheets
from src.integrations.google_sheets import GoogleSheetsError
from src.services.identite_service import roles_valides_de

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _est_admin(utilisateur: dict) -> bool:
    return acces_libre() or utilisateur.get("role_enum") == UserRole.admin

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
                # Jamais le PIN : la ligne part telle quelle vers le navigateur.
                personne={k: v for k, v in personne.items() if k != "pin"},
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


# ── Préférences de modèles IA (D-CEO-44) ────────────────────────────────────


@router.get("/preferences-modeles", response_model=PreferencesModelesReponse)
def preferences_modeles_lire(
    utilisateur: dict = Depends(utilisateur_requis),
) -> PreferencesModelesReponse:
    """Config des fournisseurs IA par tâche. Lisible par tout utilisateur
    connecté ; seul l'administrateur peut la modifier (`modifiable`)."""
    cat = preferences_modeles.catalogue()
    return PreferencesModelesReponse(
        taches=cat["taches"],
        variantes_claude=cat["variantes_claude"],
        preferences=cat["preferences"],
        modifiable=_est_admin(utilisateur),
    )


@router.put("/preferences-modeles", response_model=PreferencesModelesReponse)
def preferences_modeles_ecrire(
    corps: PreferencesModelesRequete,
    _: dict = Depends(admin_requis),
) -> PreferencesModelesReponse:
    """Enregistre les préférences (admin uniquement). 422 si un fournisseur
    n'est pas autorisé pour la tâche ; 400 s'il n'a pas de clé API configurée."""
    demande = {
        tache: entree.model_dump() for tache, entree in corps.preferences.items()
    }
    try:
        valides = preferences_modeles.valider(demande)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    for tache, entree in valides.items():
        if not preferences_modeles.cle_presente(entree["fournisseur"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Aucune clé API configurée pour « {entree['fournisseur']} » "
                    f"(tâche « {tache} »). Renseignez-la dans .env avant de la choisir."
                ),
            )

    preferences_modeles.enregistrer(valides)
    cat = preferences_modeles.catalogue()
    return PreferencesModelesReponse(
        taches=cat["taches"],
        variantes_claude=cat["variantes_claude"],
        preferences=cat["preferences"],
        modifiable=True,
    )
