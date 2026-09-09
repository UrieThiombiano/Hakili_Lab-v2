"""Port de `comptes/session.py` + `comptes/backends.py` (Django) — connexion
nom+PIN revalidée à chaque fois contre le Sheet personnel, casquette active,
dépendances FastAPI équivalentes à `connexion_requise`/`admin_requis`.

Ce qui ne change pas (réutilisé sans modification, comme prévu par le plan) :
`src/services/auth_service.py::authentifier`, `src/integrations/google_sheets.py`,
`src/services/identite_service.py::roles_valides_de/casquette_par_defaut/
vue_utilisateur_pour_casquette`, `src/core/roles.py::UserRole`.

Ce qui change : le cookie de session Django (signé, backend base de données
par défaut) devient un cookie portant une clé opaque aléatoire, vérifiée
contre la table `app_session` (`app/models/auth.py`) — même modèle que
Django, django.contrib.sessions n'étant pas disponible hors Django.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as SQLASession

from app.db import get_session
from app.models import AppSession
from src.core.config import settings
from src.core.roles import UserRole
from src.services.auth_service import AuthResult, authentifier
from src.services.identite_service import (
    casquette_par_defaut,
    roles_valides_de,
    vue_utilisateur_pour_casquette,
)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


COOKIE_NOM = "hakili_session"
#: Même durée que `SESSION_COOKIE_AGE` côté Django (`hakili/settings.py`).
DUREE_SESSION = timedelta(hours=8)

#: Identité de substitution en accès libre — même contenu que
#: `comptes/session.py::_PERSONNE_ACCES_LIBRE`, verrouillé sur `debug` comme
#: côté Django (jamais actif en production même si la variable y traîne).
_PERSONNE_ACCES_LIBRE = {
    "nom": "ACCÈS LIBRE",
    "prenom": "Développement",
    "role": UserRole.admin.value,
    "roles": [UserRole.admin.value],
    "pin": "",
    "email": "",
    "affectations": [],
    "centres_responsable": [],
}


def acces_libre() -> bool:
    return bool(settings.debug and settings.hakili_acces_libre)


def _serialisable(personne: dict) -> dict:
    """Même normalisation que côté Django (`comptes/session.py::_serialisable`)
    : les tuples d'affectation deviendraient des listes au prochain
    chargement JSON de toute façon — autant le faire une fois, ici."""
    copie = {cle: valeur for cle, valeur in personne.items() if not cle.startswith("_")}
    copie["affectations"] = [[centre, classe] for centre, classe in personne.get("affectations", [])]
    copie["centres_responsable"] = list(personne.get("centres_responsable", []))
    copie["roles"] = list(personne.get("roles", []))
    return copie


def ouvrir_session(db: SQLASession, response: Response, personne: dict) -> str:
    """Crée la session en base, pose le cookie, choisit la casquette de
    départ. Rend l'id de session (utile en test)."""
    roles = roles_valides_de(personne)
    session_id = secrets.token_urlsafe(32)
    db.add(
        AppSession(
            id=session_id,
            personne=_serialisable(personne),
            casquette=casquette_par_defaut(roles),
            expire_at=_maintenant() + DUREE_SESSION,
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NOM,
        session_id,
        max_age=int(DUREE_SESSION.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
    )
    # Cookie CSRF (double-submit, voir app/auth/csrf.py) — posé une seule
    # fois par session, jamais régénéré à chaque requête, comme le cookie
    # CSRF de Django.
    from app.auth.csrf import generer_jeton_csrf, poser_cookie_csrf

    poser_cookie_csrf(
        response,
        generer_jeton_csrf(),
        secure=not settings.debug,
        max_age=int(DUREE_SESSION.total_seconds()),
    )
    return session_id


def fermer_session(db: SQLASession, response: Response, session_id: str | None) -> None:
    from app.auth.csrf import COOKIE_CSRF

    if session_id:
        db.query(AppSession).filter(AppSession.id == session_id).delete()
        db.commit()
    response.delete_cookie(COOKIE_NOM)
    response.delete_cookie(COOKIE_CSRF)


def _charger(db: SQLASession, session_id: str | None) -> AppSession | None:
    if not session_id:
        return None
    ligne = db.get(AppSession, session_id)
    if ligne is None or ligne.expire_at < _maintenant():
        return None
    return ligne


def get_personne_courante(
    hakili_session: str | None = Cookie(default=None),
    db: SQLASession = Depends(get_session),
) -> dict | None:
    if acces_libre():
        return dict(_PERSONNE_ACCES_LIBRE)
    ligne = _charger(db, hakili_session)
    return dict(ligne.personne) if ligne else None


def get_casquette_courante(
    hakili_session: str | None = Cookie(default=None),
    db: SQLASession = Depends(get_session),
    personne: dict | None = Depends(get_personne_courante),
) -> str:
    if not personne:
        return ""
    if acces_libre():
        return UserRole.admin.value
    roles = roles_valides_de(personne)
    ligne = _charger(db, hakili_session)
    casquette = ligne.casquette if ligne else ""
    # Une casquette qui n'est plus dans les rôles (Sheet modifié, session
    # ancienne) est remplacée plutôt que de laisser passer un périmètre erroné.
    if casquette not in roles:
        casquette = casquette_par_defaut(roles)
        if ligne:
            ligne.casquette = casquette
            db.add(ligne)
            db.commit()
    return casquette


def changer_casquette(db: SQLASession, session_id: str | None, personne: dict | None, casquette: str) -> bool:
    """Refuse une casquette que la personne ne porte pas — sinon un
    utilisateur pourrait s'attribuer un périmètre plus large en forgeant une
    requête (même garde-fou que `comptes/session.py::changer_casquette`)."""
    if not personne or casquette not in roles_valides_de(personne):
        return False
    ligne = _charger(db, session_id)
    if not ligne:
        return False
    ligne.casquette = casquette
    db.add(ligne)
    db.commit()
    return True


def get_utilisateur_courant(
    personne: dict | None = Depends(get_personne_courante),
    casquette: str = Depends(get_casquette_courante),
) -> dict | None:
    """Dict utilisateur attendu par les fonctions de permission — porte
    `role_enum` (`src/services/identite_service.py::vue_utilisateur_pour_casquette`)."""
    if not personne:
        return None
    return vue_utilisateur_pour_casquette(personne, casquette)


def utilisateur_requis(utilisateur: dict | None = Depends(get_utilisateur_courant)) -> dict:
    """Équivalent de `connexion_requise` : 401 plutôt qu'une redirection
    (l'API n'a pas de page de connexion à rediriger vers)."""
    if utilisateur is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connexion requise.")
    return utilisateur


def admin_requis(utilisateur: dict = Depends(utilisateur_requis)) -> dict:
    """Équivalent de `admin_requis` : 403 si la casquette active n'est pas
    administrateur."""
    if not acces_libre() and utilisateur["role_enum"] != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs.")
    return utilisateur


def cle_personne(personne: dict) -> str:
    """Identique à `comptes/backends.py::cle_personne` — nom+prénom repliés,
    la même clé que celle qui regroupe les affectations d'une personne dans
    le Sheet (`google_sheets._cle_nom`)."""
    from src.integrations import google_sheets

    return google_sheets._cle_nom(personne.get("nom", ""), personne.get("prenom", ""))


def trouver_personne(cle: str) -> dict | None:
    """Identique à `comptes/backends.py::trouver_personne` — relit le Sheet
    et retrouve la personne par sa clé ; `None` si elle n'y est plus."""
    from src.integrations import google_sheets

    for personne in google_sheets.get_personnel():
        if cle_personne(personne) == cle:
            return personne
    return None


def authentifier_par_pin(cle: str, pin: str) -> AuthResult:
    """Recherche la personne dans le Sheet personnel puis compare le PIN —
    même flux que `comptes/backends.py::SheetBackend.authenticate`,
    revalidé contre le Sheet à chaque connexion."""
    return authentifier(trouver_personne(cle), pin)
