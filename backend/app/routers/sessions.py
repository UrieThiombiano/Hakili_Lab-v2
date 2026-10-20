"""Port de `suivi_web/views.py` (session_detail, confirmer_hypotheses,
trancher_evaluation, relancer, inscrire, plan_remediation, generer_sujet) —
le parcours de remédiation d'un élève.

Les endpoints `problemes/{probleme_id}/fiche` (module 7 — la fiche de
travail d'UN problème) s'ajoutent à ceux déjà là ; ne pas les confondre avec
`{jeton_session}/plan` (module 6 — le plan chiffré de toute la session), qui
s'appelait `/fiche` jusqu'à D-CEO-43 et créait la même confusion de nommage
dans l'API que dans le code."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as SQLASession

from app.auth.deps import utilisateur_requis
from app.auth.tokens import jeton, valeur_depuis_jeton
from app.db import get_session
from app.models import Document, Evaluation, FicheRemediation, Probleme, Session, SignatureErreur
from app.schemas import (
    EtapePlanSchema,
    FicheRemediationCorrection,
    InscrireRequete,
    PlanSchema,
    ProblemeSchema,
    RelancerRequete,
    SessionDetailReponse,
    TrancherReponse,
    TrancherRequete,
)
from app.services import etats, fiche_remediation as fiche_service, generation, plan as plan_service, session_service as svc
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


def _interpretation_generale(db: SQLASession, competence_id: str, type_erreur_id: str) -> str:
    """La lacune que révèle ce couple compétence × type d'erreur, indépendamment
    de la question qui l'a signalée — même logique que `plan.py::_signatures`,
    une seule signature suffit ici (pas de fiche de séance à préparer)."""
    signature = (
        db.query(SignatureErreur)
        .filter(SignatureErreur.competence_id == competence_id, SignatureErreur.type_erreur_id == type_erreur_id)
        .first()
    )
    return signature.interpretation if signature else ""


def _probleme_schema(db: SQLASession, p: Probleme) -> ProblemeSchema:
    return ProblemeSchema(
        id=p.id,
        competence_id=p.competence_id,
        competence_libelle=p.competence.libelle,
        type_erreur_id=p.type_erreur_id,
        etat=p.etat,
        cout_estime=p.cout_estime,
        justification=p.justification,
        interpretation=_interpretation_generale(db, p.competence_id, p.type_erreur_id),
    )


def _plan_schema(db: SQLASession, session: Session, etats: tuple[str, ...] = ("confirme", "en_remediation")) -> PlanSchema:
    plan = plan_service.construire(db, session, etats=etats)
    return PlanSchema(
        etapes=[
            EtapePlanSchema(
                rang=e.rang,
                probleme_id=e.probleme.id,
                cout=e.cout,
                competence_id=e.probleme.competence_id,
                competence_libelle=e.competence.libelle,
                type_erreur_id=e.probleme.type_erreur_id,
                prerequis_bloquants=[{"code": c.code, "libelle": c.libelle} for c in e.prerequis_aussi_en_difficulte],
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
        # Le plus récent d'abord — même ordre que `soumettre_confirmation`
        # (corrections.py) : sans lui, `.first()` rendait le T0 le plus
        # ancien à avoir un sujet, pas celui qui a produit les hypothèses
        # actuellement ouvertes (une session peut avoir plusieurs T0).
        .order_by(Evaluation.date.desc(), Evaluation.numero.desc())
        .first()
    )
    hypotheses = _problemes(db, session.id, "hypothese")
    sujet_t1_disponible = bool(sujet_t0) and any(p.exercices_confirmation for p in hypotheses)
    # Lien direct vers le PDF du sujet T1 (document "sujet_confirmation" de
    # la copie T0 qui l'a généré) — sans lui, l'enseignant voit « Déposer la
    # copie T1 » sans jamais avoir pu obtenir le sujet à faire passer.
    # Seulement si le PDF existe encore : l'enseignant peut l'avoir supprimé
    # (les exercices restent dans `sujet_confirmation`, le dépôt T1 marche).
    pdf_t1_present = bool(sujet_t0) and (
        db.query(Document.id).filter(Document.copy_id == sujet_t0.copy_id, Document.type == "sujet_confirmation").first() is not None
    )
    sujet_t1_jeton_copie = jeton(sujet_t0.copy_id) if pdf_t1_present else None

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
        plan_provisoire=_plan_schema(db, session, etats=("hypothese",)),
        cout_total_hypothese=svc.cout_total_hypothese(db, session),
        sujet_t1_disponible=sujet_t1_disponible,
        sujet_t1_jeton_copie=sujet_t1_jeton_copie,
        peut_inscrire=session.etat in ("attente_inscription", "hors_dispositif"),
        palier_c=session.palier == "C",
        hypotheses=[_probleme_schema(db, p) for p in hypotheses],
        ecartes=[_probleme_schema(db, p) for p in _problemes(db, session.id, "ecarte")],
        en_remediation=[_probleme_schema(db, p) for p in _problemes(db, session.id, "en_remediation")],
        resolus=[_probleme_schema(db, p) for p in _problemes(db, session.id, "resolu")],
        non_resolus=[_probleme_schema(db, p) for p in _problemes(db, session.id, "non_resolu")],
        regresses=[_probleme_schema(db, p) for p in _problemes(db, session.id, "regresse")],
    )


#: Règles de verdict par type d'évaluation — cohérentes avec
#: `etats.TRANSITIONS_PERMISES` : T3 ne fait avancer qu'un problème
#: `en_remediation` (résolu/non résolu) ; T4/T5 un problème `resolu`
#: (T4 ne connaît pas `clos`, réservé au dernier contrôle T5). `etat_source`
#: pour T3/T4/T5 vient de `generation.ETAT_CIBLE` — même valeur que celle qui
#: filtre les problèmes lors de la génération du sujet, pour ne pas faire
#: diverger les deux (une seule source de vérité sur « quel état ce type
#: d'évaluation vérifie »).
_REGLES_VERDICT = {
    "T1": {"etat_source": "hypothese", "options": {"confirme", "ecarte"}},
    "T3": {"etat_source": generation.ETAT_CIBLE["T3"], "options": {"resolu", "non_resolu"}},
    "T4": {"etat_source": generation.ETAT_CIBLE["T4"], "options": {"regresse"}},
    "T5": {"etat_source": generation.ETAT_CIBLE["T5"], "options": {"regresse", "clos"}},
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


@router.get("/{jeton_session}/plan")
def plan_remediation(
    jeton_session: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Télécharge le plan de remédiation (module 6) en PDF : quoi travailler,
    dans quel ordre, combien d'heures. Générée à la demande, jamais stockée —
    le plan bouge tant que des problèmes passent de confirmé à résolu, un PDF
    figé irait vite périmé.

    Anciennement `/fiche` : renommé pour ne plus se confondre avec la vraie
    fiche de travail du module 7 (`/problemes/{probleme_id}/fiche`
    ci-dessous), qui décrit comment travailler UN problème — voir D-CEO-43."""
    from src.pipeline.pdf_plan_html import generate_plan_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    plan = plan_service.construire(db, session)
    if not plan["etapes"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucun problème confirmé — il n'y a pas encore de plan à exporter.")

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "plans_remediation" / f"{uuid.uuid4().hex}.pdf"
    generate_plan_pdf(pdf_path, student_name, session, plan)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"plan_remediation_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})


@router.get("/{jeton_session}/plan-provisoire")
def plan_provisoire(
    jeton_session: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Télécharge une estimation provisoire du plan de remédiation, à partir
    des lacunes encore à l'état d'hypothèse — **avant** le test de
    confirmation T1, donc non contractuelle. Contrairement à `/plan`, ne
    refuse jamais faute de problème : aucune hypothèse ouverte est un état
    normal juste après T0, pas une erreur."""
    from src.pipeline.pdf_plan_html import generate_plan_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    plan = plan_service.construire(db, session, etats=("hypothese",))

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "plans_remediation" / f"{uuid.uuid4().hex}.pdf"
    generate_plan_pdf(pdf_path, student_name, session, plan, provisoire=True)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"plan_provisoire_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})


@router.get("/{jeton_session}/rapport-diagnostique")
def rapport_diagnostique(
    jeton_session: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Télécharge le rapport diagnostique des lacunes (module 9) : l'état
    des lieux complet de la session — hypothèses, confirmées, écartées,
    résolues — construit à partir du diagnostic structuré (module 4), pas
    du texte libre. Contrairement à `/plan`, a du sens même sans aucun
    problème (juste après T0, ou une session entièrement résolue)."""
    from app.services import diagnostic_rapport
    from src.pipeline.pdf_diagnostic_html import generate_diagnostic_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    rapport = diagnostic_rapport.construire(db, session)

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "rapports_diagnostiques" / f"{uuid.uuid4().hex}.pdf"
    generate_diagnostic_pdf(pdf_path, student_name, rapport)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"rapport_diagnostique_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})


def _probleme_confirme(db: SQLASession, session: Session, probleme_id: int) -> Probleme:
    probleme = db.get(Probleme, probleme_id)
    if probleme is None or probleme.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problème inconnu")
    if probleme.etat not in ("confirme", "en_remediation"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fiche de travail n'est disponible que pour un problème confirmé.",
        )
    return probleme


@router.get("/{jeton_session}/problemes/{probleme_id}/fiche")
def fiche_travail(
    jeton_session: str,
    probleme_id: int,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Télécharge la fiche de travail (module 7) d'UN problème confirmé : une
    séance prête à l'emploi pour le tuteur — méthode, exemple résolu,
    exercices gradués corrigés, critère de réussite. Cataloguée par couple
    compétence × type d'erreur × niveau (`app/services/fiche_remediation.py`)
    : deux élèves avec le même problème téléchargent le même document."""
    from src.pipeline.pdf_fiche_travail_html import generate_fiche_travail_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve_autorise(utilisateur, session.identifiant_hakili)
    probleme = _probleme_confirme(db, session, probleme_id)

    try:
        fiche = fiche_service.obtenir_ou_generer(db, probleme)
    except fiche_service.ErreurFicheIndisponible as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    pdf_path = Path(settings.runs_dir) / "fiches_travail" / f"{uuid.uuid4().hex}.pdf"
    generate_fiche_travail_pdf(pdf_path, fiche)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"fiche_travail_{probleme.competence_id}_{probleme.type_erreur_id}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})


@router.patch("/{jeton_session}/problemes/{probleme_id}/fiche")
def corriger_fiche_travail(
    jeton_session: str,
    probleme_id: int,
    corps: FicheRemediationCorrection,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Enregistre la correction d'un tuteur — cette version remplace la
    version générée dans le catalogue (guide-v2.md, module 7 :
    « versionnement »). La fiche doit déjà exister (avoir été générée au
    moins une fois via le GET ci-dessus) ; ce endpoint ne crée pas de fiche
    pour un couple que `remediation/` ne couvre pas encore."""
    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve_autorise(utilisateur, session.identifiant_hakili)
    probleme = _probleme_confirme(db, session, probleme_id)

    fiche = (
        db.query(FicheRemediation)
        .filter(
            FicheRemediation.competence_id == probleme.competence_id,
            FicheRemediation.type_erreur_id == probleme.type_erreur_id,
            FicheRemediation.niveau == probleme.competence.niveau_intro,
        )
        .first()
    )
    if fiche is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune fiche générée pour ce problème — télécharger la fiche au moins une fois avant de la corriger.",
        )

    contenu = corps.model_dump()
    contenu.update({
        "competence_code": fiche.competence_id,
        "competence_libelle": probleme.competence.libelle,
        "type_erreur_code": fiche.type_erreur_id,
        "type_erreur_libelle": probleme.type_erreur.libelle,
        "niveau": fiche.niveau,
        "matiere_disponible": True,
    })
    tuteur = f"{utilisateur.get('nom', '')} {utilisateur.get('prenom', '')}".strip() or "tuteur"
    fiche_service.corriger(db, fiche, contenu, tuteur)
    return {"ok": True, "version": fiche.version, "corrigee_par": fiche.corrigee_par}


def _type_sujet_courant(
    hypotheses: list[Probleme], en_remediation: list[Probleme], resolus: list[Probleme]
) -> str | None:
    """Le type d'évaluation qui correspond au profil actuel de l'élève :
    hypothèses ouvertes → T1 (confirmation), remédiation en cours → T3
    (vérification), problèmes résolus → T4 (rétention). `None` s'il n'y a
    rien à évaluer."""
    if hypotheses:
        return "T1"
    if en_remediation:
        return "T3"
    if resolus:
        return "T4"
    return None


@router.get("/{jeton_session}/sujet-test")
def generer_sujet_test(
    jeton_session: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Génère « un sujet de test » adapté au profil **actuel** de l'élève :
    le type (T1/T3/T4) est choisi selon l'état de ses lacunes, et le sujet est
    régénéré à chaque appel à partir des problèmes concernés à cet instant.
    Raccourci de `/sujets/{type}` pour l'enseignant qui veut juste « tester
    l'élève maintenant » sans choisir le type lui-même."""
    session = _session_autorisee(db, utilisateur, jeton_session)
    type_evaluation = _type_sujet_courant(
        _problemes(db, session.id, "hypothese"),
        _problemes(db, session.id, "en_remediation"),
        _problemes(db, session.id, "resolu"),
    )
    if type_evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucune lacune à évaluer pour l'instant — ni hypothèse ouverte, ni problème en remédiation ou résolu.",
        )
    return generer_sujet(jeton_session, type_evaluation, telecharger, db, utilisateur)


@router.get("/{jeton_session}/sujets/{type_evaluation}")
def generer_sujet(
    jeton_session: str,
    type_evaluation: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Génère à la volée le sujet de confirmation T1 (discrimine chaque
    hypothèse), de vérification T3 (après remédiation) ou de rétention T4/T5,
    ciblé sur les problèmes réellement concernés. Jamais mis en cache —
    régénéré à chaque demande, donc toujours aligné sur le profil courant."""
    from src.pipeline.pdf_remediation_html import generate_remediation_pdf

    session = _session_autorisee(db, utilisateur, jeton_session)
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    if type_evaluation == "T1":
        resultat = generation.generer_sujet_confirmation(db, session)
        if resultat is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucune hypothèse ouverte à confirmer, ou génération momentanément indisponible.",
            )
        sujet, hypotheses = resultat
        # Acte officiel « ce sujet est celui donné à l'élève » : persisté pour
        # le diagnostic automatique au dépôt de la copie T1.
        student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
        generation.persister_sujet_confirmation(db, session, sujet, hypotheses, student_name)
    else:
        try:
            sujet = generation.generer_sujet_verification(db, session, type_evaluation)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'évaluation invalide")

        if sujet is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rien à générer pour {type_evaluation} — aucun problème dans l'état requis, ou génération momentanément indisponible.",
            )

        # Ce téléchargement est l'acte officiel « ce sujet est celui donné à
        # l'élève » — il est donc persisté comme sujet en attente de dépôt, pour
        # que la copie corrigée puisse être diagnostiquée automatiquement
        # (module 5, suite). Régénérer avant dépôt remplace simplement l'ancien.
        generation.persister_sujet_verification(db, session, type_evaluation, sujet)

    student_name = f"{eleve.get('nom', '')} {eleve.get('prenom', '')}".strip()
    pdf_path = Path(settings.runs_dir) / "sujets_verification" / f"{uuid.uuid4().hex}.pdf"
    generate_remediation_pdf(output_path=pdf_path, copy_id=sujet.copy_id, student_name=student_name, remediation_subject=sujet)
    donnees = pdf_path.read_bytes()
    pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if telecharger else "inline"
    nom = f"sujet_{type_evaluation}_{eleve.get('nom', 'eleve')}".replace(" ", "_")
    return Response(content=donnees, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{nom}.pdf"'})
