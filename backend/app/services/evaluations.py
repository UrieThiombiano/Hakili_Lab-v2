"""Port de `Evaluation.save()` (`suivi/models.py`, Django) — attribution du
rang (`numero`) à la création. Calculé ici plutôt que laissé à l'appelant :
un rang oublié ferait échouer l'insertion sur `evaluation_unique_par_rang`
avec un message incompréhensible pour qui ne connaît pas le modèle.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session as SQLASession

from app.models import Evaluation


def creer_evaluation(db: SQLASession, session_id: int, type_evaluation: str, **kwargs) -> Evaluation:
    dernier = (
        db.query(func.max(Evaluation.numero))
        .filter(Evaluation.session_id == session_id, Evaluation.type == type_evaluation)
        .scalar()
    )
    evaluation = Evaluation(session_id=session_id, type=type_evaluation, numero=(dernier or 0) + 1, **kwargs)
    db.add(evaluation)
    db.flush()
    return evaluation
