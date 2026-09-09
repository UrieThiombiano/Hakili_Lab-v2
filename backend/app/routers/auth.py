"""Port de `comptes/views.py` — connexion nom+PIN, déconnexion, casquette.

`GET /api/auth/personnel` remplace la liste déroulante déjà triée
côté template Django ; `POST /api/auth/login` remplace la vue `connexion`
(POST) ; `POST /api/auth/casquette` remplace `choisir_casquette` ; `GET
/api/auth/me` remplace le processeur de contexte `contexte_utilisateur`
(consommé par React au lieu d'être injecté dans chaque gabarit).
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as SQLASession

from app.auth.deps import (
    acces_libre,
    changer_casquette,
    cle_personne,
    fermer_session,
    get_casquette_courante,
    get_personne_courante,
    ouvrir_session,
)
from app.db import get_session
from src.core.config import settings
from src.integrations import google_sheets
from src.integrations.google_sheets import GoogleSheetsError
from src.services.identite_service import LIBELLES_CASQUETTE, roles_valides_de

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PersonneListe(BaseModel):
    cle: str
    libelle: str


class ConnexionRequete(BaseModel):
    cle: str
    pin: str


class ConnexionErreur(HTTPException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": code, "message": message})


@router.get("/personnel", response_model=list[PersonneListe])
def liste_personnel() -> list[PersonneListe]:
    """Le Sheet peut être injoignable — même distinction que côté Django
    entre coupure réseau et erreur de configuration (`GoogleSheetsError`)."""
    try:
        personnel = google_sheets.get_personnel()
    except GoogleSheetsError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La liste du personnel est momentanément indisponible. Réessayez dans un instant.",
        )
    personnel = sorted(personnel, key=lambda p: (p.get("nom", "").upper(), p.get("prenom", "")))
    return [
        PersonneListe(cle=cle_personne(p), libelle=f"{p.get('nom', '')} {p.get('prenom', '')}".strip())
        for p in personnel
    ]


@router.post("/login")
def login(
    corps: ConnexionRequete,
    response: Response,
    db: SQLASession = Depends(get_session),
) -> dict:
    from app.auth.deps import authentifier_par_pin

    if not corps.cle:
        raise ConnexionErreur("nom_absent", "Veuillez sélectionner votre nom dans la liste.")

    resultat = authentifier_par_pin(corps.cle, corps.pin)
    if resultat.personne is None:
        raise ConnexionErreur(
            "personne_absente", "Ce nom n'est plus dans le Sheet du personnel — contactez le docteur."
        )
    if resultat.status == "pin_absent":
        raise ConnexionErreur("pin_absent", "Aucun code PIN n'a été configuré pour ce compte — contactez le docteur.")
    if resultat.status == "pin_incorrect":
        raise ConnexionErreur("pin_incorrect", "Code incorrect.")

    roles = roles_valides_de(resultat.personne)
    if not roles:
        raise ConnexionErreur(
            "role_inconnu",
            f"Rôle non reconnu dans le Sheet ({resultat.personne.get('role', '')!r}) — contactez le docteur.",
        )

    ouvrir_session(db, response, resultat.personne)
    return {
        "nom": resultat.personne.get("nom", ""),
        "prenom": resultat.personne.get("prenom", ""),
    }


@router.post("/logout")
def logout(
    response: Response,
    db: SQLASession = Depends(get_session),
    hakili_session: str | None = Cookie(default=None),
) -> dict:
    fermer_session(db, response, hakili_session)
    return {"ok": True}


@router.get("/me")
def me(
    response: Response,
    personne: dict | None = Depends(get_personne_courante),
    casquette: str = Depends(get_casquette_courante),
    hakili_session: str | None = Cookie(default=None),
    csrf_token: str | None = Cookie(default=None),
) -> dict:
    # Auto-réparation : une session ouverte avant que le cookie CSRF n'ait un
    # `Max-Age` (ou dont le cookie de session navigateur a été perdu à la
    # fermeture) se retrouve « connectée » mais sans jeton CSRF — toute action
    # mutante répond alors 403. `me()` est appelé à chaque chargement de la
    # SPA : c'est le bon endroit pour reposer le cookie manquant.
    if personne and hakili_session and not csrf_token and not acces_libre():
        from app.auth.csrf import generer_jeton_csrf, poser_cookie_csrf
        from app.auth.deps import DUREE_SESSION

        poser_cookie_csrf(
            response,
            generer_jeton_csrf(),
            secure=not settings.debug,
            max_age=int(DUREE_SESSION.total_seconds()),
        )

    if not personne:
        return {"acces_libre": acces_libre(), "personne": None}
    roles = roles_valides_de(personne)
    return {
        "acces_libre": acces_libre(),
        "personne": personne,
        "casquette": casquette,
        "casquettes_possibles": [{"valeur": r, "libelle": LIBELLES_CASQUETTE.get(r, r)} for r in roles],
    }


class CasquetteRequete(BaseModel):
    casquette: str


@router.post("/casquette")
def casquette(
    corps: CasquetteRequete,
    db: SQLASession = Depends(get_session),
    personne: dict | None = Depends(get_personne_courante),
    hakili_session: str | None = Cookie(default=None),
) -> dict:
    """En POST seulement, comme côté Django : un changement de périmètre ne
    doit pas pouvoir arriver par un simple lien cliqué ailleurs."""
    if not changer_casquette(db, hakili_session, personne, corps.casquette):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ce rôle ne vous est pas attribué.")
    return {"casquette": corps.casquette}
