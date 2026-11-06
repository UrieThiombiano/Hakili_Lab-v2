"""`DepotFastAPI` — implémentation SQLAlchemy du contrat `DepotCopies` de
`src/pipeline/depot.py` (4 méthodes : `creer_copie`, `ajouter_document`,
`maj_notes`, `maj_classe`). Miroir direct de `correction_web/depot.py`
(`DepotDjango`) — mêmes quatre gestes, mêmes garanties de rejouabilité
(`ajouter_document` remplace plutôt qu'empile, comme là-bas et pour la même
raison : le pipeline retry une écriture après un refus de connexion Neon, et
une seconde tentative ne doit ni recréer la copie ni dupliquer le document).

`src/pipeline/` ne sait pas que ce module existe — il appelle seulement
`depot()` (voir `src/pipeline/depot.py`), qui rend l'instance installée par
`app/main.py` au démarrage. Aucune ligne de `src/` ne change.
"""
from __future__ import annotations

from sqlalchemy.orm import Session as SQLASession

from app.models import Copie, Document


class DepotFastAPI:
    def __init__(self, session_factory) -> None:
        # Une factory, pas une session ouverte une fois pour toutes : le
        # pipeline peut être invoqué depuis un thread de tâche de fond
        # (BackgroundTasks) distinct du thread de la requête qui l'a lancé —
        # chaque appel a besoin de sa propre session SQLAlchemy.
        self._session_factory = session_factory

    def creer_copie(
        self, *, copy_id: str, identifiant_hakili: str, classe: str, annee_scolaire: str
    ) -> None:
        db: SQLASession = self._session_factory()
        try:
            existe = db.get(Copie, copy_id)
            if existe is None:
                db.add(
                    Copie(
                        copy_id=copy_id,
                        identifiant_hakili=identifiant_hakili,
                        classe=classe,
                        annee_scolaire=annee_scolaire,
                    )
                )
                db.commit()
        finally:
            db.close()

    def ajouter_document(self, *, copy_id: str, type_document: str, contenu: bytes) -> None:
        db: SQLASession = self._session_factory()
        try:
            db.query(Document).filter(
                Document.copy_id == copy_id, Document.type == type_document
            ).delete(synchronize_session=False)
            db.add(Document(copy_id=copy_id, type=type_document, fichier=contenu))
            db.commit()
        finally:
            db.close()

    def maj_notes(self, *, copy_id: str, notes_finales: float | None) -> None:
        db: SQLASession = self._session_factory()
        try:
            db.query(Copie).filter(Copie.copy_id == copy_id).update(
                {"notes_finales": notes_finales}, synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

    def maj_classe(self, *, copy_id: str, classe: str) -> None:
        db: SQLASession = self._session_factory()
        try:
            db.query(Copie).filter(Copie.copy_id == copy_id).update(
                {"classe": classe}, synchronize_session=False
            )
            db.commit()
        finally:
            db.close()
