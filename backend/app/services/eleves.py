"""Port des fonctions communes de `suivi_web/views.py` : liste accessible,
copies par élève, et la vérification d'accès (`_eleve_autorise`) répétée par
chaque écran du parcours (D-CEO-32 : un centre d'encadrement, tout le monde
autorisé voit tout le monde — le vrai contrôle est `get_accessible_eleves`/
`can_access_eleve`, réutilisées telles quelles, jamais dupliquées).
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as SQLASession

from app.models import Copie
from src.integrations.google_sheets import GoogleSheetsError, get_eleve_by_identifiant
from src.services.user_service import can_access_eleve, get_accessible_eleves

logger = logging.getLogger(__name__)


def eleves_accessibles(utilisateur: dict) -> list[dict] | None:
    """`None` signale une lecture impossible — distinct d'une liste vide
    (« aucun élève dans le périmètre »)."""
    try:
        return get_accessible_eleves(utilisateur)
    except GoogleSheetsError as exc:
        logger.warning("[SHEETS] Lecture des élèves impossible : %s", exc)
        return None


def copies_par_eleve(db: SQLASession, eleves: list[dict]) -> dict[str, list[Copie]]:
    """Copies de tous les élèves du périmètre, en une seule requête (pas de
    N+1)."""
    identifiants = [e.get("identifiant_hakili", "") for e in eleves]
    if not identifiants:
        return {}
    par_identifiant: dict[str, list[Copie]] = {i: [] for i in identifiants}
    for copie in db.query(Copie).filter(Copie.identifiant_hakili.in_(identifiants)).all():
        par_identifiant.setdefault(copie.identifiant_hakili, []).append(copie)
    return par_identifiant


def eleve_autorise(utilisateur: dict, identifiant: str) -> dict:
    """Retrouve l'élève et vérifie le droit d'accès, ou lève 404 / 403.

    404 quand l'élève n'existe pas, 403 quand il existe mais hors périmètre —
    ne pas confondre les deux (sinon la différence de code renseigne déjà sur
    l'existence d'un élève dans un autre centre)."""
    try:
        eleve = get_eleve_by_identifiant(identifiant)
    except GoogleSheetsError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Élève momentanément inaccessible") from exc

    if eleve is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Élève inconnu")

    if not can_access_eleve(None, utilisateur, eleve):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cet élève n'est pas dans votre périmètre.")
    return eleve


def type_reel(donnees: bytes) -> tuple[str, str]:
    """Type MIME réel d'un document stocké en base, d'après ses premiers
    octets (le scan peut être PDF ou photo selon ce qui a été déposé)."""
    if donnees[:4] == b"%PDF":
        return "application/pdf", "pdf"
    if donnees[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if donnees[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    return "application/octet-stream", "bin"
