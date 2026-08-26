"""Tri topologique du plan de remédiation — port de `suivi/plan.py` (voir
`app/services/plan.py`)."""
from __future__ import annotations

from decimal import Decimal

from app.models import Competence, Prerequis
from app.services import plan as plan_service
from tests.conftest import creer_probleme


def test_ordonner_respecte_les_prerequis(db, session_suivi, referentiel_minimal):
    # B a A comme prérequis (fixture referentiel_minimal) : un problème sur B
    # doit venir après un problème sur A.
    p_b = creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT", etat="confirme", cout="4")
    p_a = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="2")

    ordonnes = plan_service.ordonner(db, [p_b, p_a])
    assert [p.competence_id for p in ordonnes] == ["A", "B"]


def test_ordonner_depart_a_egalite_par_niveau_puis_code(db, session_suivi):
    # C et D : même niveau (6eme comme A), aucun lien de prérequis -> tri par code.
    c = Competence(code="C", domaine="Activites numeriques", libelle="C", niveau_intro="6eme")
    d = Competence(code="D", domaine="Activites numeriques", libelle="D", niveau_intro="6eme")
    att = None
    from app.models import TypeErreur

    cpt = db.query(TypeErreur).filter_by(code="CPT").first()
    if cpt is None:
        cpt = TypeErreur(code="CPT", libelle="Conceptuelle", definition="", signature="", coefficient="0.7", remediable=True)
        db.add(cpt)
    db.add_all([c, d])
    db.commit()

    p_d = creer_probleme(db, session_suivi, competence_id="D", type_erreur_id="CPT", etat="confirme", cout="1")
    p_c = creer_probleme(db, session_suivi, competence_id="C", type_erreur_id="CPT", etat="confirme", cout="1")

    ordonnes = plan_service.ordonner(db, [p_d, p_c])
    assert [p.competence_id for p in ordonnes] == ["C", "D"]


def test_ordonner_ne_perd_pas_deux_problemes_sur_la_meme_competence(db, session_suivi, referentiel_minimal):
    # La contrainte d'unicité en base est (session, compétence, type
    # d'erreur), pas (session, compétence) : une compétence peut porter deux
    # problèmes distincts (ex. CPT et PRC sur A). Un tri qui groupe par
    # compétence dans un dict à une seule valeur les ferait disparaître.
    p1 = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="2")
    from app.models import TypeErreur

    db.add(TypeErreur(code="PRC", libelle="Procédurale", definition="", signature="", coefficient="0.5", remediable=True))
    db.commit()
    p2 = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="PRC", etat="confirme", cout="1")

    ordonnes = plan_service.ordonner(db, [p1, p2])
    assert {p.id for p in ordonnes} == {p1.id, p2.id}

    resultat = plan_service.construire(db, session_suivi)
    assert resultat["nb_problemes"] == 2
    assert resultat["total_heures"] == Decimal("3")


def test_construire_total_et_palier(db, session_suivi, referentiel_minimal):
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="4")
    creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT", etat="confirme", cout="4")
    # Hypothèse : ne compte pas dans le plan (le test de confirmation n'a pas tranché).
    creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="ATT", etat="hypothese", cout="0")

    resultat = plan_service.construire(db, session_suivi)
    assert resultat["nb_problemes"] == 2
    assert resultat["total_heures"] == Decimal("8")
    assert resultat["palier"] == "B"  # 8h : borne haute de A, donc B (protocole §7)


def test_construire_plan_provisoire_ne_porte_que_les_hypotheses(db, session_suivi, referentiel_minimal):
    # Un problème déjà confirmé ne doit PAS réapparaître dans le plan
    # provisoire — sinon son coût serait compté deux fois (plan officiel +
    # provisoire) si les deux étaient additionnés côté restitution.
    creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="4")
    creer_probleme(db, session_suivi, competence_id="B", type_erreur_id="CPT", etat="hypothese", cout="4")

    resultat = plan_service.construire(db, session_suivi, etats=("hypothese",))
    assert resultat["nb_problemes"] == 1
    assert [e.probleme.competence_id for e in resultat["etapes"]] == ["B"]
    assert resultat["total_heures"] == Decimal("4")
    assert resultat["palier"] == "A"  # 4h, sous le seuil — dérivé du total du plan provisoire lui-même


def test_construire_plan_provisoire_vide_ne_leve_pas(db, session_suivi, referentiel_minimal):
    resultat = plan_service.construire(db, session_suivi, etats=("hypothese",))
    assert resultat["etapes"] == []
    assert resultat["palier"] == ""
