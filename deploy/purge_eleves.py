"""Purge des données d'élèves — changement de cohorte (nouveau Sheet élèves).

Supprime TOUT ce qui est rattaché à un élève (copies, documents, corrections,
parcours de suivi) et garde le reste : référentiel, fiches de remédiation
(génériques, par compétence × type d'erreur — jamais par élève), sessions de
connexion. Les fichiers de `runs/` sont nettoyés à part (voir
nouvelle_cohorte.sh).

Usage (dans le conteneur, depuis la racine du dépôt sur l'hôte) :
    docker exec -i hakili python - compter     < deploy/purge_eleves.py
    docker exec -i hakili python - sauvegarder < deploy/purge_eleves.py > sauvegarde.json
    docker exec -i hakili python - purger      < deploy/purge_eleves.py
En local : `python deploy/purge_eleves.py compter` depuis Hakili_Lab/.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

if Path("/app/backend").is_dir():
    _RACINE = Path("/app")
else:
    _RACINE = Path(__file__).resolve().parent.parent
    os.chdir(_RACINE)  # `.env` et `sqlite:///dev.db` sont relatifs à la racine
sys.path[:0] = [str(_RACINE / "backend"), str(_RACINE)]

from sqlalchemy import inspect, text  # noqa: E402

from app.db import engine  # noqa: E402

# Ordre enfants → parents : on ne s'appuie pas sur ON DELETE CASCADE (SQLite
# ne l'applique pas sans PRAGMA foreign_keys).
TABLES_ELEVES = [
    "suivi_seance_problemes_travailles",
    "suivi_seance",
    "suivi_transition",
    "suivi_probleme",
    "suivi_reponse",
    "suivi_evaluation",
    "session_suivi",
    "document",
    "copie",
    "correction_web_correction",
]


def _tables_presentes() -> list[str]:
    existantes = set(inspect(engine).get_table_names())
    return [t for t in TABLES_ELEVES if t in existantes]


def _serialiser(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"b64": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def compter() -> None:
    with engine.connect() as c:
        for t in _tables_presentes():
            n = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:<36} {n}", file=sys.stderr)


def sauvegarder() -> None:
    sortie: dict[str, list[dict]] = {}
    with engine.connect() as c:
        for t in _tables_presentes():
            lignes = c.execute(text(f"SELECT * FROM {t}")).mappings().all()
            sortie[t] = [{k: _serialiser(v) for k, v in l.items()} for l in lignes]
    json.dump(sortie, sys.stdout, ensure_ascii=False)


def purger() -> None:
    with engine.begin() as c:  # une seule transaction : tout ou rien
        for t in _tables_presentes():
            n = c.execute(text(f"DELETE FROM {t}")).rowcount
            print(f"  {t:<36} {n} ligne(s) supprimée(s)", file=sys.stderr)


if __name__ == "__main__":
    # La sauvegarde contient des symboles mathématiques (⊂, ≤…) : sous
    # Windows, stdout est en cp1252 par défaut.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    actions = {"compter": compter, "sauvegarder": sauvegarder, "purger": purger}
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in actions:
        sys.exit(f"Action attendue : {' | '.join(actions)}")
    actions[action]()
