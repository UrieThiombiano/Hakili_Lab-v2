"""
Le flux de correction : dépôt de copie, transcription, relecture, correction,
validation des notes, diagnostic, rapport.

L'enchaînement reprend celui de Streamlit sans le modifier — les deux arrêts de
validation humaine sont la raison d'être du produit (D-CEO-16 : « l'IA propose,
l'enseignant décide »), pas un détail d'interface.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from src.integrations.google_sheets import GoogleSheetsError

from comptes.session import connexion_requise, utilisateur_courant
from correction_web import taches
from correction_web.models import Correction, EtatCorrection
from correction_web.serialisation import deserialiser
from suivi_web.jetons import identifiant_depuis_jeton, jeton_eleve

logger = logging.getLogger(__name__)

_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
_TAILLE_MAX = 50 * 1024 * 1024  # 50 Mo — même plafond que l'ancienne interface


def _correction_autorisee(request, jeton: str) -> Correction:
    """Retrouve la correction et vérifie que l'élève est au périmètre.

    Le contrôle porte sur l'élève, pas sur « qui a lancé la correction » : un
    responsable doit pouvoir reprendre une copie lancée par un enseignant de son
    centre. `can_access_eleve` reste la seule règle.
    """
    from src.services.user_service import can_access_eleve

    copy_id = identifiant_depuis_jeton(jeton)
    if copy_id is None:
        raise Http404("Lien invalide")

    correction = get_object_or_404(Correction, copy_id=copy_id)
    try:
        from src.integrations.google_sheets import get_eleve_by_identifiant

        eleve = get_eleve_by_identifiant(correction.identifiant_hakili)
    except GoogleSheetsError as exc:
        raise Http404("Élève momentanément inaccessible") from exc

    if eleve is None or not can_access_eleve(None, utilisateur_courant(request), eleve):
        raise PermissionDenied("Cette copie n'est pas dans votre périmètre.")
    return correction


def _dossier_depot(copy_id: str) -> Path:
    from src.core.config import settings

    dossier = Path(settings.runs_dir) / copy_id / "depot"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


@connexion_requise
def nouvelle(request):
    """Choix de l'élève et du test, dépôt de la copie.

    Accessible depuis le profil élève (`suivi_web`) avec `?eleve=<jeton>` : le
    jeton signé (`jeton_eleve`, comme partout ailleurs — D-CEO-25, jamais
    `identifiant_hakili` en clair dans une URL) verrouille l'élève pour éviter
    de le reresélectionner. `?type_evaluation=` présélectionne l'étape du
    suivi de la même façon. Un jeton absent, invalide ou hors périmètre
    retombe silencieusement sur le combobox normal — ce n'est pas une erreur
    bloquante, seulement un confort en moins.
    """
    from src.knowledge.test_registry import get_registry
    from src.services.user_service import get_accessible_eleves

    utilisateur = utilisateur_courant(request)
    try:
        eleves = get_accessible_eleves(utilisateur)
    except GoogleSheetsError as exc:
        logger.warning("[SHEETS] Liste d'élèves indisponible : %s", exc)
        messages.error(
            request, "La liste des élèves est momentanément indisponible."
        )
        eleves = []

    tests = get_registry().available_tests()

    if request.method == "POST":
        correction = _creer_correction(request, eleves, tests)
        if correction is not None:
            return redirect("correction_web:suivre", jeton=jeton_eleve(correction.copy_id))

    from suivi.models import TypeEvaluation

    eleve_preselectionne = None
    jeton_eleve_param = request.GET.get("eleve", "")
    if jeton_eleve_param:
        identifiant = identifiant_depuis_jeton(jeton_eleve_param)
        eleve_preselectionne = next(
            (e for e in eleves if e.get("identifiant_hakili") == identifiant), None
        )

    type_evaluation_preselectionnee = request.GET.get("type_evaluation", "T0")
    if type_evaluation_preselectionnee not in TypeEvaluation.values:
        type_evaluation_preselectionnee = "T0"

    return render(
        request,
        "correction_web/nouvelle.html",
        {
            "rubrique": "correction",
            "eleves": sorted(
                eleves, key=lambda e: (e.get("nom", "").upper(), e.get("prenom", ""))
            ),
            "types_evaluation": TypeEvaluation.choices,
            "type_evaluation_preselectionnee": type_evaluation_preselectionnee,
            "eleve_preselectionne": eleve_preselectionne,
            "tests": [
                {"id": tid, "label": t.label, "questions": t.total_questions}
                for tid, t in tests.items()
            ],
        },
    )


def _creer_correction(request, eleves: list[dict], tests: dict) -> Correction | None:
    """Valide le formulaire, enregistre les fichiers, lance la transcription.

    Rien n'est deviné : sans élève identifié ni test choisi, on refuse. C'est la
    règle posée en D-CEO-20 — un élève absent des Sheets bloque avant tout appel IA,
    parce qu'une copie attribuée au hasard produirait un diagnostic faux au nom d'un
    autre enfant.
    """
    identifiant = request.POST.get("eleve", "")
    eleve = next(
        (e for e in eleves if e.get("identifiant_hakili") == identifiant), None
    )
    if eleve is None:
        messages.error(request, "Sélectionnez un élève de votre périmètre.")
        return None

    bareme_id = request.POST.get("test", "")
    mode_libre = bareme_id == "libre"
    test = None if mode_libre else tests.get(bareme_id)
    if test is None and not mode_libre:
        messages.error(request, "Sélectionnez le test que l'élève a passé.")
        return None
    if mode_libre:
        # Le barème n'est pas connu à l'avance : le pipeline l'extrait de l'énoncé
        # déposé. On repart d'un barème vide, exactement comme l'ancienne interface.
        bareme_id = ""

    fichiers = request.FILES.getlist("copie")
    if not fichiers:
        messages.error(request, "Ajoutez la copie scannée de l'élève.")
        return None

    sujet_depose = request.FILES.get("sujet")
    a_verifier = list(fichiers) + ([sujet_depose] if sujet_depose else [])
    for fichier in a_verifier:
        if Path(fichier.name).suffix.lower() not in _EXTENSIONS:
            messages.error(
                request,
                f"« {fichier.name} » n'est pas un format accepté "
                f"({', '.join(sorted(_EXTENSIONS))}).",
            )
            return None
        if fichier.size > _TAILLE_MAX:
            messages.error(request, f"« {fichier.name} » dépasse 50 Mo.")
            return None

    if mode_libre and sujet_depose is None:
        messages.error(
            request,
            "En test personnalisé, ajoutez le sujet : c'est lui qui sert à établir "
            "le barème.",
        )
        return None

    # Identifiant court et lisible dans les journaux, sans donnée personnelle.
    copy_id = f"copie-{uuid.uuid4().hex[:12]}"
    dossier = _dossier_depot(copy_id)

    def _enregistrer(fichier, prefixe: str = "") -> Path:
        destination = dossier / f"{prefixe}{Path(fichier.name).name}"
        with destination.open("wb") as sortie:
            for morceau in fichier.chunks():
                sortie.write(morceau)
        return destination

    chemins = [_enregistrer(f) for f in fichiers]
    chemin_sujet = _enregistrer(sujet_depose, "sujet_") if sujet_depose else None

    from comptes.backends import cle_personne
    from comptes.session import personne_courante
    from src.models.domain import Rubric
    from suivi.models import TypeEvaluation

    type_evaluation = request.POST.get("type_evaluation", TypeEvaluation.T0)
    if type_evaluation not in TypeEvaluation.values:
        type_evaluation = TypeEvaluation.T0

    correction = Correction.objects.create(
        copy_id=copy_id,
        identifiant_hakili=identifiant,
        eleve_nom=eleve.get("nom", ""),
        eleve_prenom=eleve.get("prenom", ""),
        bareme_id=bareme_id,
        type_evaluation=type_evaluation,
        instructions_expert=request.POST.get("instructions", "").strip(),
        lancee_par=cle_personne(personne_courante(request) or {}),
    )
    rubric = (
        test.rubric
        if test
        else Rubric(subject="mathematics", total_points=0, items=[])
    )
    taches.lancer_transcription(correction, chemins, rubric, test, chemin_sujet)
    return correction


@connexion_requise
def soumettre_confirmation(request, jeton_session: str):
    """Dépôt de la copie T1 : le barème est déjà connu (module 5, sujet généré
    à la suite de T0) — l'enseignant n'a que le scan des réponses à déposer,
    ni élève ni test à choisir.

    `jeton_session` est le jeton signé de `suivi.Session` (même famille que
    `suivi_web:session_detail`/`fiche_remediation`), pas celui d'une copie :
    à ce stade aucune `Correction` n'existe encore.
    """
    from src.integrations.google_sheets import get_eleve_by_identifiant
    from src.services.user_service import can_access_eleve
    from suivi.models import EtatProbleme, Evaluation, Session, TypeEvaluation

    identifiant = identifiant_depuis_jeton(jeton_session)
    if identifiant is None:
        raise Http404("Lien invalide")
    session = get_object_or_404(Session, pk=identifiant)

    try:
        eleve = get_eleve_by_identifiant(session.identifiant_hakili)
    except GoogleSheetsError as exc:
        raise Http404("Élève momentanément inaccessible") from exc
    if eleve is None or not can_access_eleve(None, utilisateur_courant(request), eleve):
        raise PermissionDenied("Cet élève n'est pas dans votre périmètre.")

    evaluation_t0 = (
        Evaluation.objects.filter(session=session, type=TypeEvaluation.T0)
        .exclude(sujet_confirmation__isnull=True)
        .order_by("-date", "-numero")
        .first()
    )
    hypotheses_couvertes = session.problemes.filter(
        etat=EtatProbleme.HYPOTHESE
    ).exclude(exercices_confirmation=[])
    if evaluation_t0 is None or not hypotheses_couvertes.exists():
        messages.warning(
            request,
            "Aucun sujet de confirmation T1 disponible pour ce parcours — "
            "utilisez la saisie manuelle depuis l'écran de parcours.",
        )
        return redirect(
            "suivi_web:session_detail", jeton=jeton_eleve(str(session.pk))
        )

    if request.method != "POST":
        return render(
            request,
            "correction_web/soumettre_confirmation.html",
            {"rubrique": "correction", "eleve": eleve, "jeton_session": jeton_session},
        )

    fichiers = request.FILES.getlist("copie")
    if not fichiers:
        messages.error(request, "Ajoutez la copie scannée de l'élève.")
        return redirect("correction_web:soumettre_confirmation", jeton_session=jeton_session)
    for fichier in fichiers:
        if Path(fichier.name).suffix.lower() not in _EXTENSIONS:
            messages.error(
                request,
                f"« {fichier.name} » n'est pas un format accepté "
                f"({', '.join(sorted(_EXTENSIONS))}).",
            )
            return redirect("correction_web:soumettre_confirmation", jeton_session=jeton_session)
        if fichier.size > _TAILLE_MAX:
            messages.error(request, f"« {fichier.name} » dépasse 50 Mo.")
            return redirect("correction_web:soumettre_confirmation", jeton_session=jeton_session)

    copy_id = f"copie-{uuid.uuid4().hex[:12]}"
    dossier = _dossier_depot(copy_id)

    def _enregistrer(fichier) -> Path:
        destination = dossier / Path(fichier.name).name
        with destination.open("wb") as sortie:
            for morceau in fichier.chunks():
                sortie.write(morceau)
        return destination

    chemins = [_enregistrer(f) for f in fichiers]

    from comptes.backends import cle_personne
    from src.models.domain import Rubric, RubricItem

    correction = Correction.objects.create(
        copy_id=copy_id,
        identifiant_hakili=session.identifiant_hakili,
        eleve_nom=eleve.get("nom", ""),
        eleve_prenom=eleve.get("prenom", ""),
        bareme_id="",
        type_evaluation=TypeEvaluation.T1,
        lancee_par=cle_personne(utilisateur_courant(request) or {}),
    )

    exercices = sorted(evaluation_t0.sujet_confirmation, key=lambda e: e["numero"])
    rubric = Rubric(
        subject="mathematics",
        total_points=float(len(exercices)),
        items=[
            RubricItem(id=str(e["numero"]), label=e["topic"], max_score=1.0)
            for e in exercices
        ],
    )
    subject_text = "\n\n".join(
        f"Exercice {e['numero']} — {e['question']}" for e in exercices
    )
    taches.lancer_transcription(correction, chemins, rubric, None, None, subject_text)
    return redirect("correction_web:suivre", jeton=jeton_eleve(copy_id))


@connexion_requise
def suivre(request, jeton: str):
    """Page unique du flux : elle affiche l'écran correspondant à l'état courant.

    Une seule URL par copie plutôt qu'une par étape — l'enseignant peut recharger,
    fermer l'onglet et revenir : il retombe toujours au bon endroit.
    """
    correction = _correction_autorisee(request, jeton)
    taches.signaler_si_abandonnee(correction)

    resultat = deserialiser(correction.resultat) if correction.resultat else None
    contexte = {
        "rubrique": "correction",
        "correction": correction,
        "jeton": jeton,
        "resultat": resultat,
    }

    if correction.etat == EtatCorrection.RELECTURE and resultat:
        contexte["pages"] = _lignes_relecture(resultat)
        return render(request, "correction_web/relecture.html", contexte)

    if correction.etat == EtatCorrection.VALIDATION and resultat:
        contexte["questions"] = _lignes_validation(resultat)
        return render(request, "correction_web/validation.html", contexte)

    if correction.terminee and resultat:
        contexte.update(_contexte_resultats(resultat))
        return render(request, "correction_web/resultats.html", contexte)

    # En cours ou en échec : la page de progression se rafraîchit toute seule.
    return render(request, "correction_web/progression.html", contexte)


def _lignes_relecture(resultat) -> list[dict]:
    """Une page de transcription, associée à l'image scannée correspondante.

    L'ordre des images d'ingestion et celui des pages transcrites sont le même
    (chaque `page_number` vient de `enumerate()` sur les images d'ingestion,
    voir `src/api/*_client.py`) — `page_number - 1` retrouve donc directement
    l'image. `a_image` est vérifié ici plutôt que laissé au template : sans
    volume persistant, `runs/` peut avoir disparu entre la transcription et la
    relecture (voir `correction_web/serialisation.py`), et l'écran doit rester
    utilisable sans image plutôt que d'afficher une image cassée.
    """
    images = resultat.ingestion.pages if resultat.ingestion else []
    lignes = []
    for page in resultat.transcription.pages:
        chemin = images[page.page_number - 1] if 0 < page.page_number <= len(images) else None
        lignes.append({"page": page, "a_image": bool(chemin and chemin.exists())})
    return lignes


def _lignes_validation(resultat) -> list[dict]:
    """Une ligne par question : bonne réponse, réponse de l'élève, note proposée."""
    bareme = {item.id: item for item in (resultat.rubric.items if resultat.rubric else [])}
    lignes = []
    for question in resultat.grade.questions:
        item = bareme.get(question.rubric_item_id)
        lignes.append(
            {
                "id": question.rubric_item_id,
                "intitule": item.label if item else "",
                "max": item.max_score if item else 1.0,
                "bonne_reponse": question.correct_answer or "—",
                "reponse_eleve": question.observed_answer or "—",
                "note_ia": question.score,
                "commentaire": question.comment,
                "a_revoir": question.requires_review,
            }
        )
    return lignes


def _contexte_resultats(resultat) -> dict:
    grade = resultat.grade
    reussies = [q for q in grade.questions if _note_finale(q) > 0]
    ratees = [q for q in grade.questions if _note_finale(q) <= 0]
    return {
        "note": grade.final_score_on_20,
        "reussies": reussies,
        "ratees": ratees,
        "diagnostic": resultat.diagnostic,
        "a_un_rapport": bool(resultat.pdf_path),
        "a_une_remediation": bool(resultat.remediation_pdf_path),
    }


def _note_finale(question) -> float:
    from src.models.domain import TeacherDecision

    if question.teacher_decision == TeacherDecision.refused and question.teacher_score is not None:
        return question.teacher_score
    return question.score


@connexion_requise
def valider_transcription(request, jeton: str):
    """Enregistre les corrections de l'enseignant puis lance la correction."""
    correction = _correction_autorisee(request, jeton)
    if request.method != "POST" or correction.etat != EtatCorrection.RELECTURE:
        return redirect("correction_web:suivre", jeton=jeton)

    resultat = deserialiser(correction.resultat)
    for page in resultat.transcription.pages:
        corrige = request.POST.get(f"page_{page.page_number}")
        if corrige is not None and corrige != page.content:
            page.content = corrige

    from correction_web.serialisation import serialiser

    correction.resultat = serialiser(resultat)
    correction.save(update_fields=["resultat", "maj_le"])
    taches.lancer_correction(correction)
    return redirect("correction_web:suivre", jeton=jeton)


@connexion_requise
def page_image(request, jeton: str, page_number: int):
    """Sert l'image scannée d'une page, pour la relecture côte à côte.

    Lue sur disque (`runs/…/pages/`), pas en base : ce sont les images
    intermédiaires de l'ingestion, distinctes du document « scan » archivé en
    base par `src/pipeline/pipeline.py`. `_correction_autorisee` applique la
    même règle de périmètre que le reste du flux.
    """
    correction = _correction_autorisee(request, jeton)
    if not correction.resultat:
        raise Http404("Copie sans résultat")

    resultat = deserialiser(correction.resultat)
    images = resultat.ingestion.pages if resultat.ingestion else []
    if not (0 < page_number <= len(images)):
        raise Http404("Page inconnue")

    chemin = images[page_number - 1]
    if not chemin.exists():
        raise Http404("Image indisponible")

    type_contenu = "image/png" if chemin.suffix.lower() == ".png" else "image/jpeg"
    return HttpResponse(chemin.read_bytes(), content_type=type_contenu)


@connexion_requise
def valider_notes(request, jeton: str):
    """Applique les décisions de l'enseignant, calcule la note, lance le diagnostic.

    La décision humaine prime toujours sur la proposition de l'IA — c'est le cœur de
    D-CEO-16, et `CopyGrade.compute_final_score()` l'implémente déjà : on ne
    recalcule rien ici.
    """
    from src.models.domain import TeacherDecision

    correction = _correction_autorisee(request, jeton)
    if request.method != "POST" or correction.etat != EtatCorrection.VALIDATION:
        return redirect("correction_web:suivre", jeton=jeton)

    resultat = deserialiser(correction.resultat)
    bareme = {item.id: item for item in (resultat.rubric.items if resultat.rubric else [])}

    for question in resultat.grade.questions:
        decision = request.POST.get(f"decision_{question.rubric_item_id}", "accepted")
        if decision == "refused":
            question.teacher_decision = TeacherDecision.refused
            question.teacher_score = _note_saisie(
                request.POST.get(f"note_{question.rubric_item_id}"),
                maximum=bareme[question.rubric_item_id].max_score
                if question.rubric_item_id in bareme
                else 1.0,
            )
        else:
            question.teacher_decision = TeacherDecision.accepted
            question.teacher_score = None

    resultat.grade.compute_final_score()

    from correction_web.serialisation import serialiser

    correction.resultat = serialiser(resultat)
    correction.save(update_fields=["resultat", "maj_le"])
    taches.lancer_diagnostic(correction)
    return redirect("correction_web:suivre", jeton=jeton)


def _note_saisie(brut, *, maximum: float) -> float:
    """Note saisie par l'enseignant, bornée au barème.

    Une valeur illisible vaut 0 plutôt que de faire échouer la validation de toute
    la copie pour un champ mal rempli.
    """
    try:
        valeur = float(str(brut).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(valeur, maximum))


@connexion_requise
def sujet(request, bareme_id: str):
    """Sert le sujet d'un test, pour impression.

    Les élèves composent **sur le sujet** : l'enseignant doit pouvoir l'imprimer
    autant de fois qu'il a d'élèves. Le faire chercher le bon PDF ailleurs serait
    une friction inutile — et un risque de distribuer la mauvaise version.

    Réservé aux personnes connectées : un sujet d'évaluation diffusé à l'avance
    perd sa valeur diagnostique.
    """
    from src.knowledge.test_registry import get_registry

    test = get_registry().get_test(bareme_id)
    if test is None or test.sujet_pdf is None or not test.sujet_pdf.exists():
        raise Http404("Sujet indisponible")

    reponse = HttpResponse(
        test.sujet_pdf.read_bytes(), content_type="application/pdf"
    )
    disposition = "attachment" if request.GET.get("telecharger") else "inline"
    reponse["Content-Disposition"] = f'{disposition}; filename="{test.sujet_pdf.name}"'
    return reponse


@connexion_requise
def corrige(request, bareme_id: str):
    """Sert le corrigé enseignant d'un test.

    Document réservé à l'enseignant qui corrige — jamais remis à l'élève.
    Même logique d'accès que `sujet()` : réservé aux personnes connectées.
    """
    from src.knowledge.test_registry import get_registry

    test = get_registry().get_test(bareme_id)
    if test is None or test.corrige_pdf is None or not test.corrige_pdf.exists():
        raise Http404("Corrigé indisponible")

    reponse = HttpResponse(
        test.corrige_pdf.read_bytes(), content_type="application/pdf"
    )
    disposition = "attachment" if request.GET.get("telecharger") else "inline"
    reponse["Content-Disposition"] = f'{disposition}; filename="{test.corrige_pdf.name}"'
    return reponse


@connexion_requise
def sujets(request):
    """Liste des sujets imprimables et de leurs corrigés enseignant."""
    from src.knowledge.test_registry import get_registry

    return render(
        request,
        "correction_web/sujets.html",
        {
            "rubrique": "sujets",
            "tests": [
                {
                    "id": tid,
                    "label": t.label,
                    "niveaux": t.niveaux,
                    "questions": t.total_questions,
                    "imprimable": t.sujet_pdf is not None,
                    "corrige_disponible": t.corrige_pdf is not None,
                }
                for tid, t in get_registry().available_tests().items()
            ],
        },
    )


@connexion_requise
def lot(request):
    """Dépôt d'un lot de copies — une classe entière d'un coup.

    L'élève de chaque copie vient du **nom du fichier**, mis en correspondance avec
    les Sheets : une sélection manuelle pour trente copies n'aurait pas de sens.
    Mais rien n'est deviné — sans correspondance unique, la copie est écartée et
    signalée, jamais attribuée au hasard (D-CEO-20).
    """
    from src.knowledge.test_registry import get_registry
    from src.services.user_service import get_accessible_eleves

    try:
        eleves = get_accessible_eleves(utilisateur_courant(request))
    except GoogleSheetsError:
        messages.error(request, "La liste des élèves est momentanément indisponible.")
        eleves = []

    tests = get_registry().available_tests()

    if request.method == "POST":
        test = tests.get(request.POST.get("test", ""))
        fichiers = request.FILES.getlist("copies")
        if test is None:
            messages.error(request, "Sélectionnez le test que la classe a passé.")
        elif not fichiers:
            messages.error(request, "Ajoutez au moins une copie.")
        else:
            lancees, ecartees = _traiter_lot(request, fichiers, eleves, test)
            if lancees:
                messages.success(
                    request,
                    f"{lancees} copie{'s' if lancees > 1 else ''} en cours de correction. "
                    "Elles apparaîtront ici à valider une fois analysées.",
                )
            for motif in ecartees:
                messages.warning(request, motif)
            if lancees:
                return redirect("correction_web:liste")

    return render(
        request,
        "correction_web/lot.html",
        {
            "rubrique": "correction",
            "tests": [
                {"id": tid, "label": t.label, "questions": t.total_questions}
                for tid, t in tests.items()
            ],
        },
    )


def _traiter_lot(request, fichiers, eleves, test) -> tuple[int, list[str]]:
    from comptes.backends import cle_personne
    from comptes.session import personne_courante
    from src.services.identite_service import apparier_eleve_par_nom_fichier

    lancees, ecartees = 0, []
    for fichier in fichiers:
        souche = Path(fichier.name).stem

        if Path(fichier.name).suffix.lower() not in _EXTENSIONS:
            ecartees.append(f"« {fichier.name} » : format non accepté, copie écartée.")
            continue
        if fichier.size > _TAILLE_MAX:
            ecartees.append(f"« {fichier.name} » : dépasse 50 Mo, copie écartée.")
            continue

        eleve = apparier_eleve_par_nom_fichier(souche, eleves)
        if eleve is None:
            ecartees.append(
                f"« {souche} » : élève introuvable ou ambigu dans les Sheets — "
                "copie écartée. Nommez le fichier avec le nom et le prénom de l'élève."
            )
            continue

        copy_id = f"copie-{uuid.uuid4().hex[:12]}"
        dossier = _dossier_depot(copy_id)
        destination = dossier / Path(fichier.name).name
        with destination.open("wb") as sortie:
            for morceau in fichier.chunks():
                sortie.write(morceau)

        correction = Correction.objects.create(
            copy_id=copy_id,
            identifiant_hakili=eleve["identifiant_hakili"],
            eleve_nom=eleve.get("nom", ""),
            eleve_prenom=eleve.get("prenom", ""),
            bareme_id=request.POST.get("test", ""),
            instructions_expert=request.POST.get("instructions", "").strip(),
            lancee_par=cle_personne(personne_courante(request) or {}),
        )
        taches.lancer_phase_a_complete(correction, [destination], test.rubric, test)
        lancees += 1

    return lancees, ecartees


@connexion_requise
def a_propos(request):
    """Explique le cycle T0→T5 à un public non technique (parents, tuteurs)."""
    return render(request, "correction_web/a_propos.html", {"rubrique": "a_propos"})


@connexion_requise
def supprimer(request, jeton: str):
    """Supprime une copie : la Correction, et ce qui a déjà été persisté (suivi).

    Passe par `_correction_autorisee` : même règle de périmètre que le reste du
    flux (`can_access_eleve`), pas une autorisation à part. `Evaluation.copy_id`
    est un lien souple vers `Copie` (D-CEO-40, pas de clé étrangère) : une copie
    déjà exploitée par le suivi structuré devient une référence orpheline plutôt
    que de bloquer la suppression ou d'entraîner une cascade sur le suivi.
    """
    correction = _correction_autorisee(request, jeton)
    if request.method != "POST":
        return redirect("correction_web:suivre", jeton=jeton)

    import shutil

    from src.core.config import settings
    from suivi.models import Copie

    copy_id = correction.copy_id
    correction.delete()
    Copie.objects.filter(copy_id=copy_id).delete()
    shutil.rmtree(Path(settings.runs_dir) / copy_id, ignore_errors=True)

    messages.success(request, "Copie supprimée.")
    return redirect("correction_web:liste")


@connexion_requise
def liste(request):
    """Corrections récentes du périmètre de l'utilisateur."""
    from src.services.user_service import get_accessible_eleves

    try:
        identifiants = {
            e.get("identifiant_hakili")
            for e in get_accessible_eleves(utilisateur_courant(request))
        }
    except GoogleSheetsError:
        messages.error(request, "Liste des élèves momentanément indisponible.")
        identifiants = set()

    corrections = Correction.objects.filter(identifiant_hakili__in=identifiants)[:50]
    for correction in corrections:
        taches.signaler_si_abandonnee(correction)

    return render(
        request,
        "correction_web/liste.html",
        {
            "rubrique": "correction",
            "corrections": [
                {"correction": c, "jeton": jeton_eleve(c.copy_id)} for c in corrections
            ],
        },
    )
