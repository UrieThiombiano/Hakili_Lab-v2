"""Port de `suivi_web/views.py` (accueil, profil élève, document, suppression
de copie) — voir `app/services/eleves.py` pour les fonctions communes
(accès, copies par élève) réutilisées ici comme côté Django.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as SQLASession

from app.auth.deps import get_utilisateur_courant, utilisateur_requis
from app.auth.tokens import jeton, valeur_depuis_jeton
from app.db import get_session
from app.models import Copie, Correction, Document, Evaluation, Probleme, Session
from app.schemas import (
    AccueilReponse,
    CopieEntree,
    DocumentResume,
    EleveDetailReponse,
    EleveLigne,
    PointCourbe,
    ProblemeHypothese,
    SessionResume,
)
from app.services.eleves import copies_par_eleve, eleve_autorise, eleves_accessibles, type_reel
from src.core.config import settings
from src.core.tendance import calculer_tendance
from src.services.identite_service import filtrer_par_recherche, nom_fichier_document

router = APIRouter(prefix="/api/eleves", tags=["eleves"])

#: Ordre d'affichage des documents — même ordre que `suivi_web/views.py`.
_DOC_ORDRE = ["scan", "rapport", "sujet_confirmation"]
_DOC_LIBELLES = {
    "scan": "Copie de l'élève",
    "rapport": "Rapport d'analyse",
    "sujet_confirmation": "Sujet de confirmation (T1)",
}


@router.get("", response_model=AccueilReponse)
def accueil(
    q: str = Query(default=""),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> AccueilReponse:
    """Liste des élèves du périmètre, avec leur tendance (`src/core/tendance.py`,
    seuil 1.0) — élèves en baisse d'abord."""
    eleves = eleves_accessibles(utilisateur)
    lignes: list[EleveLigne] = []
    en_baisse = 0

    if eleves:
        eleves = filtrer_par_recherche(eleves, q, lambda e: f"{e.get('prenom', '')} {e.get('nom', '')}")
        par_eleve = copies_par_eleve(db, eleves)

        brut: list[tuple[str, EleveLigne]] = []
        for eleve in eleves:
            copies = par_eleve.get(eleve.get("identifiant_hakili", ""), [])
            tendance = calculer_tendance(copies)
            notes = [c.notes_finales for c in copies if c.notes_finales is not None]
            brut.append(
                (
                    tendance,
                    EleveLigne(
                        eleve=eleve,
                        jeton=jeton(eleve.get("identifiant_hakili", "")),
                        tendance=tendance,
                        nb_copies=len(copies),
                        derniere_note=notes[-1] if notes else None,
                    ),
                )
            )
            if tendance == "regresse":
                en_baisse += 1

        # Les élèves en baisse d'abord — ce qu'un responsable doit voir en premier.
        ordre = {"regresse": 0, "stagne": 1, "progresse": 2, "insuffisant": 3}
        brut.sort(key=lambda item: ordre.get(item[0], 9))
        lignes = [ligne for _, ligne in brut]

    return AccueilReponse(lignes=lignes, en_baisse=en_baisse, lecture_impossible=eleves is None)


@router.get("/{jeton_eleve}", response_model=EleveDetailReponse)
def eleve_detail(
    jeton_eleve: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> EleveDetailReponse:
    """Profil d'un élève : tendance, copies chronologiques et leurs
    documents, courbe de progression, sessions T0→T5 en cours."""
    identifiant = valeur_depuis_jeton(jeton_eleve)
    if identifiant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    eleve = eleve_autorise(utilisateur, identifiant)

    copies = (
        db.query(Copie)
        .filter(Copie.identifiant_hakili == identifiant)
        .order_by(Copie.date_soumission.desc())
        .all()
    )
    evaluations_par_copie = {
        e.copy_id: e
        for e in db.query(Evaluation)
        .filter(Evaluation.copy_id.in_([c.copy_id for c in copies]))
        .order_by(Evaluation.numero)
        .all()
    }

    entrees: list[CopieEntree] = []
    for copie in copies:
        documents = sorted(
            (d for d in db.query(Document).filter(Document.copy_id == copie.copy_id).all() if d.type != "remediation"),
            key=lambda d: _DOC_ORDRE.index(d.type) if d.type in _DOC_ORDRE else 9,
        )
        evaluation = evaluations_par_copie.get(copie.copy_id)
        libelle_rapport = _DOC_LIBELLES["rapport"]
        if evaluation:
            libelle_rapport += f" {evaluation.type}"
            if evaluation.numero > 1:
                libelle_rapport += f" ({evaluation.numero})"
        entrees.append(
            CopieEntree(
                copy_id=copie.copy_id,
                jeton=jeton(copie.copy_id),
                classe=copie.classe,
                date_soumission=copie.date_soumission,
                notes_finales=copie.notes_finales,
                documents=[
                    DocumentResume(
                        type=doc.type,
                        libelle=libelle_rapport if doc.type == "rapport" else _DOC_LIBELLES.get(doc.type, doc.type),
                    )
                    for doc in documents
                ],
            )
        )

    tendance = calculer_tendance(copies)
    notes = [c.notes_finales for c in copies if c.notes_finales is not None]
    notees = sorted((c for c in copies if c.notes_finales is not None), key=lambda c: c.date_soumission)
    courbe = [PointCourbe(date=c.date_soumission, note=c.notes_finales) for c in notees]

    sessions = db.query(Session).filter(Session.identifiant_hakili == identifiant).all()
    parcours = [
        SessionResume(
            id=s.id,
            jeton=jeton(str(s.id)),
            etat=s.etat,
            hypotheses=[
                ProblemeHypothese(
                    id=p.id, competence_id=p.competence_id, type_erreur_id=p.type_erreur_id, justification=p.justification
                )
                for p in db.query(Probleme).filter(Probleme.session_id == s.id, Probleme.etat == "hypothese").all()
            ],
        )
        for s in sessions
    ]

    return EleveDetailReponse(
        eleve=eleve,
        entrees=entrees,
        tendance=tendance,
        nb_copies=len(copies),
        derniere_note=notes[-1] if notes else None,
        courbe=courbe,
        parcours=parcours,
        jeton_nouvelle_analyse=jeton(identifiant),
    )


@router.get("/documents/{jeton_copie}/{doc_type}")
def document(
    jeton_copie: str,
    doc_type: str,
    telecharger: bool = Query(default=False),
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> Response:
    """Sert un document (scan/rapport/sujet). Le droit d'accès est revérifié
    ici — pas seulement sur la page qui affiche le lien — sinon une URL
    devinée suffirait à récupérer la copie d'un élève d'un autre centre."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")

    copie = db.get(Copie, copy_id)
    if copie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copie inconnue")

    eleve = eleve_autorise(utilisateur, copie.identifiant_hakili)

    doc = db.query(Document).filter(Document.copy_id == copy_id, Document.type == doc_type).first()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document inconnu")

    donnees = bytes(doc.fichier)
    mime, extension = type_reel(donnees)
    nom = nom_fichier_document(nom=eleve.get("nom", ""), prenom=eleve.get("prenom", ""), doc_type=doc_type, date=copie.date_soumission)

    disposition = "attachment" if telecharger else "inline"
    return Response(
        content=donnees,
        media_type=mime,
        headers={"Content-Disposition": f'{disposition}; filename="{nom}.{extension}"'},
    )


def _fichiers_du_document(copy_id: str, doc_type: str, correction: Correction | None) -> list[Path]:
    """Copies disque d'un document dans `runs/<copy_id>/` — à retirer avec la
    ligne `document`, sinon le fichier reste sur le serveur après suppression."""
    dossier = Path(settings.runs_dir) / copy_id
    if doc_type == "scan":
        return [dossier / "depot", dossier / "pages"]
    if doc_type == "sujet_confirmation":
        return [dossier / "sujet_confirmation.pdf"]
    cle = {"rapport": "pdf_path", "remediation": "remediation_pdf_path"}.get(doc_type)
    chemin = ((correction.resultat if correction else None) or {}).get(cle or "")
    # Seulement un fichier rangé sous le dossier de cette copie — jamais un
    # chemin arbitraire lu dans le JSON du résultat.
    if chemin and Path(chemin).resolve().is_relative_to(dossier.resolve()):
        return [Path(chemin)]
    return []


@router.delete("/documents/{jeton_copie}/{doc_type}")
def supprimer_document(
    jeton_copie: str,
    doc_type: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Supprime un document produit pour une copie (scan, rapport, sujet…)
    sans toucher à la copie ni à sa note. Le plan de remédiation et le rapport
    diagnostique ne passent pas ici : ils ne sont jamais stockés, seulement
    générés à la demande depuis le suivi."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    copie = db.get(Copie, copy_id)
    if copie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copie inconnue")
    eleve_autorise(utilisateur, copie.identifiant_hakili)

    docs = db.query(Document).filter(Document.copy_id == copy_id, Document.type == doc_type).all()
    if not docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document inconnu")
    correction = db.query(Correction).filter(Correction.copy_id == copy_id).first()
    for doc in docs:
        db.delete(doc)
    db.commit()

    for chemin in _fichiers_du_document(copy_id, doc_type, correction):
        if chemin.is_dir():
            shutil.rmtree(chemin, ignore_errors=True)
        else:
            chemin.unlink(missing_ok=True)
    return {"ok": True}


@router.delete("/copies/{jeton_copie}")
def supprimer_copie(
    jeton_copie: str,
    db: SQLASession = Depends(get_session),
    utilisateur: dict = Depends(utilisateur_requis),
) -> dict:
    """Supprime une copie depuis le profil élève — copie, documents en
    cascade, fichiers de `runs/` si présents. `Evaluation.copy_id` n'étant
    pas une clé étrangère, une copie déjà exploitée par le suivi structuré
    devient une référence orpheline plutôt que de bloquer la suppression
    (même choix que côté Django).

    Supprime aussi la `Correction` associée si elle existe — miroir de
    `correction_web/views.py::supprimer` (une copie affichée ici peut ne pas
    en avoir une : `/api/corrections` ne remonte que les 50 dernières du
    périmètre, alors que le profil élève montre tout l'historique)."""
    copy_id = valeur_depuis_jeton(jeton_copie)
    if copy_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien invalide")
    copie = db.get(Copie, copy_id)
    if copie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copie inconnue")
    eleve_autorise(utilisateur, copie.identifiant_hakili)

    correction = db.query(Correction).filter(Correction.copy_id == copy_id).first()
    if correction is not None:
        db.delete(correction)
    db.delete(copie)
    db.commit()
    shutil.rmtree(Path(settings.runs_dir) / copy_id, ignore_errors=True)
    return {"ok": True}
