"""Port de `suivi_web/views.py` (session_detail, confirmer_hypotheses,
trancher_evaluation, relancer, inscrire, fiche_remediation, generer_sujet) —
le parcours de remédiation d'un élève.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as SQLASession

from app.auth.deps import utilisateur_requis
from app.auth.tokens import jeton, valeur_depuis_jeton
from app.db import get_session
from app.models import Evaluation, Probleme, Session
from app.schemas import (
    EtapePlanSchema,
    InscrireRequete,
    PlanSchema,
    ProblemeSchema,
    RelancerRequete,
    SessionDetailReponse,
    TrancherReponse,
    TrancherRequete,
)
from app.services import etats, generation, plan as plan_service, session_service as svc
from app.services.eleves import eleve_autorise
from app.services.evaluations import creer_evaluation
from src.core.config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_autorisee(db: SQLASession, utilisateur: dict, jeton_session: str) -> Session:
    identifiant = valeur_depuis_jeton(jeton_session)
    if identifiant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    session = db.get(Session, int(identifiant))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session inconnue")
    eleve_autorise(utilisateur, session.identifiant_hakili)
    return session


def _problemes(db: SQLASession, session_id: int, etat: str) -> list[Probleme]:
    return db.query(Probleme).filter(Probleme.session_id == session_id, Probleme.etat == etat).all()


def _plan_schema(db: SQLASession, session: Session) -> PlanSchema:
    plan = plan_service.construire(db, session)
    return PlanSchema(
        etapes=[
            EtapePlanSchema(
                rang=e.rang,
                cout=e.cout,
                competence_id=e.probleme.competence_id,
                type_erreur_id=e.probleme.type_erreur_id,
                prerequis_bloquants=[c.code for c in e.prerequis_aussi_en_difficulte],
                signatures=[{"production_eleve": s.production_eleve, "interpretation": s.interpretation} for s in e.signatures],
            )
            for e in plan["etapes"]
        ],
        total_heures=plan["total_heures"],
        palier=plan["palier"],
        nb_problemes=plan["nb_problemes"],
        repose_sur_estimation=plan["repose_sur_estimation"],
    )


@router.get("/{jeton_session}", response_model=SessionDetailReponse)
def session_detail(
    jeton_session: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> SessionDetailReponse:
    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    sujet_t0 = (
        db.query(Evaluation)
        .filter(Evaluation.session_id == session.id, Evaluation.type == "T0", Evaluation.sujet_confirmation.isnot(None))
        .first()
    )
    hypotheses = _problemes(db, session.id, "hypothese")
    sujet_t1_disponible = bool(sujet_t0) and any(p.exercices_confirmation for p in hypotheses)

    return SessionDetailReponse(
        id=session.id,
        etat=session.etat,
        palier=session.palier,
        date_debut=session.date_debut,
        date_inscription=session.date_inscription,
        jeton=jeton_session,
        jeton_eleve=jeton(session.identifiant_hakili),
        eleve=eleve,
        plan=_plan_schema(db, session),
        cout_total_hypothese=svc.cout_total_hypothese(db, session),
        sujet_t1_disponible=sujet_t1_disponible,
        peut_inscrire=session.etat in ("attente_inscription", "hors_dispositif"),
        palier_c=session.palier == "C",
        hypotheses=[ProblemeSchema.model_validate(p) for p in hypotheses],
        ecartes=[ProblemeSchema.model_validate(p) for p in _problemes(db, session.id, "ecarte")],
        en_remediation=[ProblemeSchema.model_validate(p) for p in _problemes(db, session.id, "en_remediation")],
        resolus=[ProblemeSchema.model_validate(p) for p in _problemes(db, session.id, "resolu")],
        non_resolus=[ProblemeSchema.model_validate(p) for p in _problemes(db, session.id, "non_resolu")],
        regresses=[ProblemeSchema.model_validate(p) for p in _problemes(db, session.id, "regresse")],
    )


#: Règles de verdict par type d'évaluation — cohérentes avec
#: `etats.TRANSITIONS_PERMISES` : T3 ne fait avancer qu'un problème
#: `en_remediation` (résolu/non résolu) ; T4/T5 un problème `resolu`
#: (T4 ne connaît pas `clos`, réservé au dernier contrôle T5).
_REGLES_VERDICT = {
    "T1": {"etat_source": "hypothese", "options": {"confirme", "ecarte"}},
    "T3": {"etat_source": "en_remediation", "options": {"resolu", "non_resolu"}},
    "T4": {"etat_source": "resolu", "options": {"regresse"}},
    "T5": {"etat_source": "resolu", "options": {"regresse", "clos"}},
}


@router.post("/{jeton_session}/trancher/{type_evaluation}", response_model=TrancherReponse)
def trancher(
    jeton_session: str,
    type_evaluation: str,
    corps: TrancherRequete,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> TrancherReponse:
    """Fait passer chaque problème dans l'état source de `type_evaluation`
    vers la décision saisie (`corps.decisions[probleme_id]`), pour celles
    qui font partie des options permises. Une `Evaluation` est créée pour
    porter ces transitions (rang automatique), sans copie associée — la
    décision n'est pas issue d'une correction déposée dans l'app.

    Remplace `confirmer_hypotheses` (T1) et `trancher_evaluation` (T3-T5,
    même fonction côté Django, généralisée ici par le paramètre d'URL)."""
    regles = _REGLES_VERDICT.get(type_evaluation)
    if regles is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'évaluation invalide")

    session = _session_autorisee(db, utilisateur, jeton_session)
    problemes = _problemes(db, session.id, regles["etat_source"])
    a_traiter = {p.id: corps.decisions[p.id] for p in problemes if corps.decisions.get(p.id) in regles["options"]}

    if not a_traiter:
        return TrancherReponse(compte={}, erreurs=[])

    evaluation = creer_evaluation(db, session.id, type_evaluation)

    compte: dict[str, int] = {}
    erreurs: list[str] = []
    for probleme in problemes:
        decision = a_traiter.get(probleme.id)
        if decision is None:
            continue
        try:
            etats.changer_etat(db, probleme, decision, evaluation=evaluation)
        except etats.ErreurTransition as exc:
            erreurs.append(f"{probleme.competence_id} × {probleme.type_erreur_id} : {exc}")
            continue
        compte[decision] = compte.get(decision, 0) + 1

    db.commit()
    return TrancherReponse(compte=compte, erreurs=erreurs)


@router.post("/{jeton_session}/problemes/{probleme_id}/relancer")
def relancer(
    jeton_session: str,
    probleme_id: int,
    corps: RelancerRequete,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Relance un problème `non_resolu` ou `regresse` en remédiation — une
    décision du tuteur, jamais un effet automatique d'un contrôle. Aucune
    évaluation associée (cas déjà prévu par `Probleme.evaluation_origine`,
    nul pour un problème saisi hors évaluation)."""
    session = _session_autorisee(db, utilisateur, jeton_session)
    probleme = db.get(Probleme, probleme_id)
    if probleme is None or probleme.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problème inconnu")

    try:
        etats.changer_etat(db, probleme, "en_remediation", commentaire=corps.motif)
    except etats.ErreurTransition as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    return {"ok": True}


@router.post("/{jeton_session}/inscrire")
def inscrire(
    jeton_session: str,
    corps: InscrireRequete,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Inscrit l'élève au programme — la décision humaine du cycle. Engage
    un volume horaire et vraisemblablement une facturation."""
    session = _session_autorisee(db, utilisateur, jeton_session)
    try:
        svc.inscrire(db, session, forcer=corps.forcer, motif=corps.motif)
    except svc.ErreurSession as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    # Décompte des problèmes réellement basculés en remédiation par cet appel
    # — pas le total de la session (le message Django d'origine comptait tous
    # les problèmes, toutes causes confondues ; corrigé ici, l'API contrôlant
    # désormais le texte affiché plutôt qu'un gabarit).
    nb_en_remediation = db.query(Probleme).filter(Probleme.session_id == session.id, Probleme.etat == "en_remediation").count()
    total = svc.cout_total_confirme(db, session)
    return {"nb_problemes_en_remediation": nb_en_remediation, "cout_total_confirme": str(total)}


@router.get("/{jeton_session}/fiche")
def fiche_remediation(
    jeton_session: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Télécharge la fiche de remédiation (module 7) : le plan chiffré en
    PDF. Générée à la demande, jamais stockée — le plan bouge tant que des
    problèmes passent de confirmé à résolu, un PDF figé irait vite périmé."""
    from src.pipeline.pdf_plan_html import generate_plan_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    plan = plan_service.construire(db, session)
    if not plan["etapes"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucun problème confirmé — il n'y a pas encore de plan à exporter.")

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "fiches_remediation" / f"{uuid.uuid4().hex}.pdf"
    generate_plan_pdf(pdf_path, student_name, session, plan)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"fiche_remediation_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})


@router.get("/{jeton_session}/sujets/{type_evaluation}")
def generer_sujet(
    jeton_session: str,
    type_evaluation: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Génère à la volée le sujet T3 (vérification après remédiation) ou
    T4/T5 (contrôle de rétention), ciblé sur les problèmes réellement
    concernés. Jamais stocké — régénéré à chaque demande."""
    from src.pipeline.pdf_remediation_html import generate_remediation_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    try:
        sujet = generation.generer_sujet_verification(db, session, type_evaluation)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'évaluation invalide")

    if sujet is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rien à générer pour {type_evaluation} — aucun problème dans l'état requis, ou génération momentanément indisponible.",
        )

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "sujets_verification" / f"{uuid.uuid4().hex}.pdf"
    generate_remediation_pdf(output_path=pdf_path, copy_id=sujet.copy_id, student_name=student_name, remediation_subject=sujet)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"sujet_{type_evaluation}_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})
