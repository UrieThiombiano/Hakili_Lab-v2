"""Port de `correction_web/views.py` — dépôt de copie, transcription,
relecture, correction, validation des notes, diagnostic, rapport.

L'enchaînement reprend celui de Django sans le modifier — les deux arrêts de
validation humaine sont la raison d'être du produit (D-CEO-16), pas un
détail d'interface. Voir `app/services/taches.py` pour l'orchestration en
arrière-plan et `app/services/corrections.py` pour les fonctions communes.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session as SQLASession

from app.auth.deps import cle_personne, utilisateur_requis
from app.auth.tokens import jeton, valeur_depuis_jeton
from app.db import get_session
from app.models import Copie, Correction, Document, Session
from app.schemas import (
    CorrectionCreeReponse,
    CorrectionResume,
    CorrectionStatut,
    LotReponse,
    NotesRequete,
    TestDisponible,
    TranscriptionRequete,
)
from app.services import taches
from app.services.corrections import correction_autorisee, dossier_depot, enregistrer_fichier, valider_fichier
from app.services.diagnostic_suivi import SEUIL_CONFIRMATION_T1
from src.core.config import settings
from src.integrations.google_sheets import GoogleSheetsError
from src.models.domain import Rubric, RubricItem
from src.services.identite_service import apparier_eleve_par_nom_fichier
from src.services.user_service import get_accessible_eleves

router = APIRouter(prefix="/api/corrections", tags=["corrections"])

_TYPES_EVALUATION = {"T0", "T1", "T3", "T4", "T5"}


#: Documents lus dans l'espace de travail `runs/<copy_id>/` (clé du résultat
#: qui porte leur chemin) — jamais en base avant la sauvegarde explicite.
_FICHIERS_ESPACE_TRAVAIL = {"rapport": "pdf_path", "remediation": "remediation_pdf_path"}


def _fichier_espace_travail(correction: Correction, doc_type: str) -> Path | None:
    cle = _FICHIERS_ESPACE_TRAVAIL.get(doc_type)
    chemin = ((correction.resultat or {}).get(cle) if cle else None)
    if not chemin:
        return None
    dossier = (Path(settings.runs_dir) / correction.copy_id).resolve()
    fichier = Path(chemin)
    # Seulement un fichier rangé sous le dossier de cette copie — jamais un
    # chemin arbitraire lu dans le JSON du résultat.
    if fichier.resolve().is_relative_to(dossier) and fichier.is_file():
        return fichier
    return None


def _statut(db: SQLASession, correction: Correction) -> CorrectionStatut:
    documents = [t for t in _FICHIERS_ESPACE_TRAVAIL if _fichier_espace_travail(correction, t)]
    documents += [
        d for (d,) in db.query(Document.type).filter(Document.copy_id == correction.copy_id).all()
        if d not in documents
    ]
    # Le parcours (session) de l'élève existe dès qu'une correction a déjà
    # écrit une hypothèse (module 4) — pas forcément celle-ci, une session
    # peut en porter plusieurs. Lecture seule : on ne le crée jamais ici,
    # seul le pipeline (`diagnostic_suivi.preparer_evaluation`) le fait.
    session = (
        db.query(Session)
        .filter(Session.identifiant_hakili == correction.identifiant_hakili)
        .order_by(Session.id.desc())
        .first()
    )
    return CorrectionStatut(
        etat=correction.etat,
        etape=correction.etape,
        progression=correction.progression,
        en_cours=correction.en_cours,
        en_attente=correction.en_attente,
        terminee=correction.terminee,
        echouee=correction.echouee,
        erreurs=list(correction.erreurs or []),
        resultat=correction.resultat,
        documents=documents,
        plan_a_reprendre=taches.plan_a_reprendre(correction),
        jeton_session=jeton(str(session.id)) if session else None,
        seuil_sans_t1=(
            SEUIL_CONFIRMATION_T1
            if correction.type_evaluation == "T0" and (correction.bareme_id or "").startswith("socle_")
            else None
        ),
    )


# ── Sujets imprimables (routes littérales — avant /{jeton}) ──────────────────


@router.get("/tests", response_model=list[TestDisponible])
def tests_disponibles(utilisateur: dict = Depends(utilisateur_requis)) -> list[TestDisponible]:
    from src.knowledge.test_registry import get_registry

    return [
        TestDisponible(id=tid, label=t.label, questions=t.total_questions)
        for tid, t in get_registry().available_tests().items()
    ]


@router.get("/sujets")
def sujets(utilisateur: dict = Depends(utilisateur_requis)) -> list[dict]:
    from src.knowledge.test_registry import get_registry

    return [
        {
            "id": tid,
            "label": t.label,
            "niveaux": t.niveaux,
            "questions": t.total_questions,
            "imprimable": t.sujet_pdf is not None,
            "corrige_disponible": t.corrige_pdf is not None,
        }
        for tid, t in get_registry().available_tests().items()
    ]


@router.get("/sujets/{bareme_id}")
def sujet_pdf(bareme_id: str, telecharger: bool = Query(default=False), utilisateur: dict = Depends(utilisateur_requis)) -> Response:
    """Sert le sujet d'un test pour impression — réservé aux personnes
    connectées, un sujet diffusé à l'avance perd sa valeur diagnostique."""
    from src.knowledge.test_registry import get_registry

    test = get_registry().get_test(bareme_id)
    if test is None or test.sujet_pdf is None or not test.sujet_pdf.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sujet indisponible")
    disposition = "attachment" if telecharger else "inline"
    return Response(
        content=test.sujet_pdf.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{test.sujet_pdf.name}"'},
    )


@router.get("/sujets/{bareme_id}/corrige")
def corrige_pdf(bareme_id: str, telecharger: bool = Query(default=False), utilisateur: dict = Depends(utilisateur_requis)) -> Response:
    """Corrigé enseignant — jamais remis à l'élève."""
    from src.knowledge.test_registry import get_registry

    test = get_registry().get_test(bareme_id)
    if test is None or test.corrige_pdf is None or not test.corrige_pdf.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corrigé indisponible")
    disposition = "attachment" if telecharger else "inline"
    return Response(
        content=test.corrige_pdf.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{test.corrige_pdf.name}"'},
    )


# ── Liste des corrections récentes ────────────────────────────────────────────


@router.get("", response_model=list[CorrectionResume])
def liste(
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> list[CorrectionResume]:
    """Corrections récentes du périmètre de l'utilisateur (50 dernières)."""
    try:
        identifiants = {e.get("identifiant_hakili") for e in get_accessible_eleves(utilisateur)}
    except GoogleSheetsError:
        identifiants = set()

    corrections = (
        db.query(Correction)
        .filter(Correction.identifiant_hakili.in_(identifiants))
        .order_by(Correction.cree_le.desc())
        .limit(50)
        .all()
    )
    for correction in corrections:
        if taches.signaler_si_abandonnee(db, correction):
            db.commit()

    return [
        CorrectionResume(
            jeton=jeton(c.copy_id),
            copy_id=c.copy_id,
            eleve_nom=c.eleve_nom,
            eleve_prenom=c.eleve_prenom,
            etat=c.etat,
            etape=c.etape,
            progression=c.progression,
            cree_le=c.cree_le,
        )
        for c in corrections
    ]


# ── Dépôt d'une copie unique ───────────────────────────────────────────────────


@router.post("", response_model=CorrectionCreeReponse)
def nouvelle(
    eleve: str = Form(...),
    test: str = Form(...),  # bareme_id, ou "libre"
    type_evaluation: str = Form("T0"),
    instructions: str = Form(""),
    copie: list[UploadFile] = File(...),
    sujet: UploadFile | None = File(None),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionCreeReponse:
    """Dépôt d'une copie : choix de l'élève et du test, lancement de la
    transcription en arrière-plan. Rien n'est deviné (D-CEO-20) — un élève
    absent des Sheets bloque avant tout appel IA."""
    from src.knowledge.test_registry import get_registry

    try:
        eleves = get_accessible_eleves(utilisateur)
    except GoogleSheetsError:
        eleves = []
    eleve_trouve = next((e for e in eleves if e.get("identifiant_hakili") == eleve), None)
    if eleve_trouve is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sélectionnez un élève de votre périmètre.")

    mode_libre = test == "libre"
    test_obj = None if mode_libre else get_registry().get_test(test)
    if test_obj is None and not mode_libre:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sélectionnez le test que l'élève a passé.")
    bareme_id = "" if mode_libre else test

    if not copie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ajoutez la copie scannée de l'élève.")
    if mode_libre and sujet is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En test personnalisé, ajoutez le sujet : c'est lui qui sert à établir le barème.",
        )
    for fichier in list(copie) + ([sujet] if sujet else []):
        valider_fichier(fichier)

    if type_evaluation not in _TYPES_EVALUATION:
        type_evaluation = "T0"

    copy_id = f"copie-{uuid.uuid4().hex[:12]}"
    dossier = dossier_depot(copy_id)
    chemins = [enregistrer_fichier(dossier, f) for f in copie]
    chemin_sujet = enregistrer_fichier(dossier, sujet, "sujet_") if sujet else None

    correction = Correction(
        copy_id=copy_id,
        identifiant_hakili=eleve,
        eleve_nom=eleve_trouve.get("nom", ""),
        eleve_prenom=eleve_trouve.get("prenom", ""),
        bareme_id=bareme_id,
        type_evaluation=type_evaluation,
        instructions_expert=instructions.strip(),
        lancee_par=cle_personne(utilisateur),
    )
    db.add(correction)
    db.commit()

    rubric = test_obj.rubric if test_obj else Rubric(subject="mathematics", total_points=0, items=[])
    taches.lancer_transcription(db, correction, chemins, rubric, test_obj, chemin_sujet)
    return CorrectionCreeReponse(jeton=jeton(copy_id))


# ── Dépôt de la copie T1 (confirmation) ───────────────────────────────────────


@router.post("/confirmation/{jeton_session}", response_model=CorrectionCreeReponse)
def soumettre_confirmation(
    jeton_session: str,
    copie: list[UploadFile] = File(...),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionCreeReponse:
    """Dépôt de la copie T1 : le barème est déjà connu (module 5, sujet
    généré à la suite de T0) — l'enseignant ne dépose que le scan."""
    from app.models import Evaluation, Probleme, Session
    from app.services.eleves import eleve_autorise

    identifiant = valeur_depuis_jeton(jeton_session)
    if identifiant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    session = db.get(Session, int(identifiant))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session inconnue")
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    evaluation_t0 = (
        db.query(Evaluation)
        .filter(Evaluation.session_id == session.id, Evaluation.type == "T0", Evaluation.sujet_confirmation.isnot(None))
        .order_by(Evaluation.date.desc(), Evaluation.numero.desc())
        .first()
    )
    hypotheses_couvertes = [
        p for p in db.query(Probleme).filter(Probleme.session_id == session.id, Probleme.etat == "hypothese").all() if p.exercices_confirmation
    ]
    if evaluation_t0 is None or not hypotheses_couvertes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun sujet de confirmation T1 disponible pour ce parcours — utilisez la saisie manuelle depuis l'écran de parcours.",
        )

    if not copie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ajoutez la copie scannée de l'élève.")
    for fichier in copie:
        valider_fichier(fichier)

    copy_id = f"copie-{uuid.uuid4().hex[:12]}"
    dossier = dossier_depot(copy_id)
    chemins = [enregistrer_fichier(dossier, f) for f in copie]

    correction = Correction(
        copy_id=copy_id,
        identifiant_hakili=session.identifiant_hakili,
        eleve_nom=eleve.get("nom", ""),
        eleve_prenom=eleve.get("prenom", ""),
        bareme_id="",
        type_evaluation="T1",
        lancee_par=cle_personne(utilisateur),
    )
    db.add(correction)
    db.commit()

    exercices = sorted(evaluation_t0.sujet_confirmation, key=lambda e: e["numero"])
    rubric = Rubric(
        subject="mathematics",
        total_points=float(len(exercices)),
        items=[RubricItem(id=str(e["numero"]), label=e["topic"], max_score=1.0) for e in exercices],
    )
    subject_text = "\n\n".join(f"Exercice {e['numero']} — {e['question']}" for e in exercices)
    taches.lancer_transcription(db, correction, chemins, rubric, None, None, subject_text)
    return CorrectionCreeReponse(jeton=jeton(copy_id))


# ── Dépôt de la copie T3/T4/T5 (vérification) ─────────────────────────────────

_TYPES_VERIFICATION = {"T3", "T4", "T5"}


@router.post("/verification/{jeton_session}/{type_evaluation}", response_model=CorrectionCreeReponse)
def soumettre_verification(
    jeton_session: str,
    type_evaluation: str,
    copie: list[UploadFile] = File(...),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionCreeReponse:
    """Dépôt de la copie T3 (vérification après remédiation) ou T4/T5
    (rétention) : le barème est déjà connu — le sujet a été généré et persisté
    par `GET /sessions/{jeton_session}/sujets/{type_evaluation}`
    (`app/services/generation.py::persister_sujet_verification`). L'enseignant
    ne dépose que le scan, comme pour T1 (`soumettre_confirmation` ci-dessus)."""
    from app.models import Session

    if type_evaluation not in _TYPES_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'évaluation invalide")

    from app.services.eleves import eleve_autorise

    identifiant = valeur_depuis_jeton(jeton_session)
    if identifiant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    session = db.get(Session, int(identifiant))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session inconnue")
    eleve = eleve_autorise(utilisateur, session.identifiant_hakili)

    if session.sujet_verification_type != type_evaluation or not session.sujet_verification_exercices:
        attente = f" (un sujet {session.sujet_verification_type} est en attente — régénérez le bon avant de déposer)" if session.sujet_verification_type else ""
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aucun sujet {type_evaluation} en attente pour ce parcours — générez-le d'abord depuis l'écran de parcours.{attente}",
        )

    if not copie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ajoutez la copie scannée de l'élève.")
    for fichier in copie:
        valider_fichier(fichier)

    copy_id = f"copie-{uuid.uuid4().hex[:12]}"
    dossier = dossier_depot(copy_id)
    chemins = [enregistrer_fichier(dossier, f) for f in copie]

    correction = Correction(
        copy_id=copy_id,
        identifiant_hakili=session.identifiant_hakili,
        eleve_nom=eleve.get("nom", ""),
        eleve_prenom=eleve.get("prenom", ""),
        bareme_id="",
        type_evaluation=type_evaluation,
        lancee_par=cle_personne(utilisateur),
    )
    db.add(correction)
    db.commit()

    exercices = sorted(session.sujet_verification_exercices, key=lambda e: e["numero"])
    rubric = Rubric(
        subject="mathematics",
        total_points=float(len(exercices)),
        items=[RubricItem(id=str(e["numero"]), label=e["topic"], max_score=1.0) for e in exercices],
    )
    subject_text = "\n\n".join(f"Exercice {e['numero']} — {e['question']}" for e in exercices)
    taches.lancer_transcription(db, correction, chemins, rubric, None, None, subject_text)
    return CorrectionCreeReponse(jeton=jeton(copy_id))


# ── Suivi / relecture / validation / résultats — une seule route ─────────────


@router.get("/{jeton_copie}", response_model=CorrectionStatut)
def suivre(
    jeton_copie: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionStatut:
    """Statut courant d'une correction — le frontend branche l'écran sur
    `etat` (relecture/validation/résultats/progression), comme le faisait le
    gabarit Django avec une seule URL par copie."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    if taches.signaler_si_abandonnee(db, correction):
        db.commit()
    return _statut(db, correction)


@router.post("/{jeton_copie}/transcription", response_model=CorrectionStatut)
def valider_transcription(
    jeton_copie: str,
    corps: TranscriptionRequete,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionStatut:
    """Enregistre les corrections de l'enseignant sur la transcription puis
    lance la correction question par question."""
    from src.pipeline.serialisation import deserialiser, serialiser

    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    if correction.etat != "relecture":
        return _statut(db, correction)

    resultat = deserialiser(correction.resultat)
    for page in resultat.transcription.pages:
        corrige = corps.pages.get(page.page_number)
        if corrige is not None and corrige != page.content:
            page.content = corrige

    correction.resultat = serialiser(resultat)
    db.add(correction)
    db.commit()
    taches.lancer_correction(db, correction)
    return _statut(db, correction)


@router.get("/{jeton_copie}/fichiers/{doc_type}")
def fichier_espace_travail(
    jeton_copie: str,
    doc_type: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Rapport de correction ou plan de remédiation, lus dans l'espace de
    travail de l'analyse (pas en base : rien n'y est écrit avant « Sauvegarder »)."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    fichier = _fichier_espace_travail(correction, doc_type)
    if fichier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document inconnu")
    disposition = "attachment" if telecharger else "inline"
    return Response(
        content=fichier.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{fichier.name}"'},
    )


@router.get("/{jeton_copie}/pages/{page_number}")
def page_image(
    jeton_copie: str,
    page_number: int,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Image scannée d'une page, pour la relecture côte à côte — lue sur
    disque (`runs/…/pages/`), pas en base."""
    from src.pipeline.serialisation import deserialiser

    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    if not correction.resultat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copie sans résultat")

    resultat = deserialiser(correction.resultat)
    images = resultat.ingestion.pages if resultat.ingestion else []
    if not (0 < page_number <= len(images)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page inconnue")

    chemin = images[page_number - 1]
    if not chemin.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image indisponible")

    type_contenu = "image/png" if chemin.suffix.lower() == ".png" else "image/jpeg"
    return Response(content=chemin.read_bytes(), media_type=type_contenu)


@router.post("/{jeton_copie}/notes", response_model=CorrectionStatut)
def valider_notes(
    jeton_copie: str,
    corps: NotesRequete,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionStatut:
    """Applique les décisions de l'enseignant, calcule la note, lance le
    diagnostic. La décision humaine prime toujours sur la proposition de
    l'IA (D-CEO-16) — `CopyGrade.compute_final_score()` l'implémente déjà."""
    from src.models.domain import TeacherDecision
    from src.pipeline.serialisation import deserialiser, serialiser

    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    if correction.etat != "validation":
        return _statut(db, correction)

    resultat = deserialiser(correction.resultat)
    bareme = {item.id: item for item in (resultat.rubric.items if resultat.rubric else [])}

    for question in resultat.grade.questions:
        decision = corps.decisions.get(question.rubric_item_id)
        if decision is not None and decision.decision == "refused":
            question.teacher_decision = TeacherDecision.refused
            maximum = bareme[question.rubric_item_id].max_score if question.rubric_item_id in bareme else 1.0
            question.teacher_score = _note_saisie(decision.note, maximum=maximum)
        else:
            question.teacher_decision = TeacherDecision.accepted
            question.teacher_score = None

    resultat.grade.compute_final_score()

    correction.resultat = serialiser(resultat)
    db.add(correction)
    db.commit()
    taches.lancer_diagnostic(db, correction)
    return _statut(db, correction)


@router.post("/{jeton_copie}/plan", response_model=CorrectionStatut)
def reprendre_plan(
    jeton_copie: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> CorrectionStatut:
    """Termine un plan de remédiation resté incomplet : seules les sections
    manquantes sont rédigées, sans refaire l'analyse."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)
    if correction.en_cours:
        return _statut(db, correction)
    if not taches.plan_a_reprendre(correction):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Aucun plan de remédiation à reprendre pour cette copie.")
    taches.lancer_reprise_plan(db, correction)
    return _statut(db, correction)


def _note_saisie(brut, *, maximum: float) -> float:
    try:
        valeur = float(str(brut).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(valeur, maximum))


@router.delete("/{jeton_copie}")
def supprimer(
    jeton_copie: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Supprime une copie : la `Correction`, et ce qui a déjà été persisté
    par le suivi (`Copie`, en cascade `Document`)."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    correction = correction_autorisee(db, utilisateur, copy_id)

    db.delete(correction)
    copie = db.get(Copie, copy_id)
    if copie is not None:
        db.delete(copie)
    db.commit()
    shutil.rmtree(Path(settings.runs_dir) / copy_id, ignore_errors=True)
    return {"ok": True}


# ── Dépôt en lot ───────────────────────────────────────────────────────────────


@router.post("/lot", response_model=LotReponse)
def lot(
    test: str = Form(...),
    instructions: str = Form(""),
    copies: list[UploadFile] = File(...),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> LotReponse:
    """Dépôt d'une classe entière d'un coup — l'élève de chaque copie vient
    du nom du fichier, mis en correspondance avec les Sheets. Rien n'est
    deviné : sans correspondance unique, la copie est écartée et signalée."""
    from src.knowledge.test_registry import get_registry

    try:
        eleves = get_accessible_eleves(utilisateur)
    except GoogleSheetsError:
        eleves = []

    test_obj = get_registry().get_test(test)
    if test_obj is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sélectionnez le test que la classe a passé.")
    if not copies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ajoutez au moins une copie.")

    lancees = 0
    ecartees: list[str] = []
    for fichier in copies:
        souche = Path(fichier.filename or "").stem

        if Path(fichier.filename or "").suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            ecartees.append(f"« {fichier.filename} » : format non accepté, copie écartée.")
            continue
        if fichier.size is not None and fichier.size > 50 * 1024 * 1024:
            ecartees.append(f"« {fichier.filename} » : dépasse 50 Mo, copie écartée.")
            continue

        eleve = apparier_eleve_par_nom_fichier(souche, eleves)
        if eleve is None:
            ecartees.append(f"« {souche} » : élève introuvable ou ambigu dans les Sheets — copie écartée. Nommez le fichier avec le nom et le prénom de l'élève.")
            continue

        copy_id = f"copie-{uuid.uuid4().hex[:12]}"
        dossier = dossier_depot(copy_id)
        destination = enregistrer_fichier(dossier, fichier)

        correction = Correction(
            copy_id=copy_id,
            identifiant_hakili=eleve["identifiant_hakili"],
            eleve_nom=eleve.get("nom", ""),
            eleve_prenom=eleve.get("prenom", ""),
            bareme_id=test,
            instructions_expert=instructions.strip(),
            lancee_par=cle_personne(utilisateur),
        )
        db.add(correction)
        db.commit()
        taches.lancer_phase_a_complete(db, correction, [destination], test_obj.rubric, test_obj)
        lancees += 1

    return LotReponse(lancees=lancees, ecartees=ecartees)
