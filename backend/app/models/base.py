"""Base déclarative SQLAlchemy — miroir de `referentiel/models.py` + `suivi/models.py`
(Django) portés dans le cadre de la migration FastAPI (voir
`C:\\Users\\Urie\\.claude\\plans\\majestic-nibbling-anchor.md`).

Une seule Base pour les deux domaines (référentiel + suivi) : ce sont deux
apps Django distinctes mais une seule base Postgres (Neon), donc un seul
schéma Alembic — pas de raison de les séparer ici.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
