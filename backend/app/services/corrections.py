"""Fonctions communes de `correction_web/views.py` : vérification d'accès et
dossier de dépôt des fichiers déposés — répétées par chaque écran du flux de
correction, portées une fois ici comme `app/services/eleves.py` le fait pour
`suivi_web`."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session as SQLASession

from app.models import Correction
from src.core.config import settings
from src.integrations.google_sheets import GoogleSheetsError, get_eleve_by_identifiant
from src.services.user_service import can_access_eleve

#: Mêmes bornes que côté Django.
EXTENSIONS_ACCEPTEES = {".pdf", ".jpg", ".jpeg", ".png"}
TAILLE_MAX = 50 * 1024 * 1024  # 50 Mo


def correction_autorisee(db: SQLASession, utilisateur: dict, copy_id: str) -> Correction:
    """Retrouve la correction et vérifie que l'élève est au périmètre. Le
    contrôle porte sur l'élève, pas sur qui a lancé la correction — un
    responsable doit pouvoir reprendre une copie lancée par un collègue."""
    correction = db.query(Correction).filter(Correction.copy_id == copy_id).first()
    if correction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction inconnue")
    try:
        eleve = get_eleve_by_identifiant(correction.identifiant_hakili)
    except GoogleSheetsError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Élève momentanément inaccessible") from exc
    if eleve is None or not can_access_eleve(None, utilisateur, eleve):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cette copie n'est pas dans votre périmètre.")
    return correction


def dossier_depot(copy_id: str) -> Path:
    dossier = Path(settings.runs_dir) / copy_id / "depot"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def valider_fichier(fichier: UploadFile) -> None:
    """Lève une 400 lisible plutôt que de laisser passer un format ou une
    taille non acceptée (mêmes bornes que côté Django)."""
    if Path(fichier.filename or "").suffix.lower() not in EXTENSIONS_ACCEPTEES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"« {fichier.filename} » n'est pas un format accepté ({', '.join(sorted(EXTENSIONS_ACCEPTEES))}).",
        )
    if fichier.size is not None and fichier.size > TAILLE_MAX:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"« {fichier.filename} » dépasse 50 Mo.")


def enregistrer_fichier(dossier: Path, fichier: UploadFile, prefixe: str = "") -> Path:
    destination = dossier / f"{prefixe}{Path(fichier.filename or 'fichier').name}"
    with destination.open("wb") as sortie:
        while morceau := fichier.file.read(1024 * 1024):
            sortie.write(morceau)
    return destination
