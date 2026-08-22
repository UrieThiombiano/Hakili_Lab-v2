"""Module 7 — la fiche de travail (voir `app/services/fiche_remediation.py`).

Ne pas confondre avec `test_plan.py` (module 6, le plan chiffré d'une
session) : ces tests portent sur le contenu pédagogique d'UN problème,
catalogué indépendamment de toute session.
"""
from __future__ import annotations

import pytest

from app.models import FicheRemediation
from app.services import fiche_remediation as fiche_service
from tests.conftest import creer_probleme


class _Chunk:
    methode = {"titre": "Résoudre", "etapes": ["Étape 1", "Étape 2"]}
    retenir = ["Point à retenir"]
    exemple_resolu = "3 + 4 = 7"
    erreurs_frequentes = [{"erreur": "Confond addition et multiplication", "correction": "Relire l'énoncé"}]
    declic = "Repérer le mot-clé de l'énoncé"

    def __init__(self, exercices=None):
        self._exercices = exercices or [
            {"numero": 1, "etoiles": 1, "enonce": "1+1", "correction": "2"},
            {"numero": 2, "etoiles": 1, "enonce": "2+2", "correction": "4"},
            {"numero": 3, "etoiles": 2, "enonce": "5+5", "correction": "10"},
            {"numero": 4, "etoiles": 3, "enonce": "9+9", "correction": "18"},
        ]

    def exercices_gradues(self, repartition):
        par_etoile: dict[int, list[dict]] = {}
        for ex in self._exercices:
            par_etoile.setdefault(ex["etoiles"], []).append(ex)
        selection = []
        for etoiles in sorted(repartition):
            selection.extend(par_etoile.get(etoiles, [])[: repartition[etoiles]])
        return selection


def _patch_retriever(monkeypatch, chunk):
    monkeypatch.setattr(
        "src.knowledge.remediation_retriever.get_remediation_retriever",
        lambda: type("R", (), {"get_by_competence": staticmethod(lambda code, niveau: chunk)})(),
    )


def test_construire_contenu_sans_matiere_degrade_sans_erreur(db, referentiel_minimal, monkeypatch):
    _patch_retriever(monkeypatch, None)
    from app.models import Competence, TypeErreur

    competence = db.get(Competence, "A")
    type_erreur = db.get(TypeErreur, "CPT")

    contenu = fiche_service.construire_contenu(db, competence, type_erreur, "6eme")
    assert contenu["matiere_disponible"] is False
    assert contenu["exercices"] == []
    assert contenu["methode"] is None


def test_construire_contenu_avec_matiere(db, referentiel_minimal, monkeypatch):
    _patch_retriever(monkeypatch, _Chunk())
    from app.models import Competence, TypeErreur

    competence = db.get(Competence, "B")
    type_erreur = db.get(TypeErreur, "CPT")

    contenu = fiche_service.construire_contenu(db, competence, type_erreur, "5eme")
    assert contenu["matiere_disponible"] is True
    # Répartition 1:2, 2:2, 3:1 -> 4 exercices max ici (2 à une étoile, 1 à deux, 1 à trois)
    assert [e["numero"] for e in contenu["exercices"]] == [1, 2, 3, 4]
    assert contenu["prerequis_a_verifier"][0]["code"] == "A"  # B a A comme prérequis (referentiel_minimal)
    assert "5 exercice" not in contenu["critere_reussite"]
    assert contenu["critere_reussite"].startswith("L'élève résout seul")


def test_obtenir_ou_generer_leve_si_indisponible(db, session_suivi, monkeypatch):
    _patch_retriever(monkeypatch, None)
    probleme = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="4")

    with pytest.raises(fiche_service.ErreurFicheIndisponible):
        fiche_service.obtenir_ou_generer(db, probleme)


def test_obtenir_ou_generer_est_idempotent(db, session_suivi, monkeypatch):
    _patch_retriever(monkeypatch, _Chunk())
    probleme = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="4")

    fiche1 = fiche_service.obtenir_ou_generer(db, probleme)
    assert fiche1.version == "generee"
    assert db.query(FicheRemediation).count() == 1

    # Deuxième appel (même compétence × type d'erreur × niveau, éventuellement
    # un autre élève) : ne recrée pas de ligne, rend le même catalogue.
    fiche2 = fiche_service.obtenir_ou_generer(db, probleme)
    assert fiche2.id == fiche1.id
    assert db.query(FicheRemediation).count() == 1


def test_corriger_remplace_le_contenu_et_le_marque_corrigee(db, session_suivi, monkeypatch):
    _patch_retriever(monkeypatch, _Chunk())
    probleme = creer_probleme(db, session_suivi, competence_id="A", type_erreur_id="CPT", etat="confirme", cout="4")
    fiche = fiche_service.obtenir_ou_generer(db, probleme)

    nouveau_contenu = dict(fiche.contenu)
    nouveau_contenu["objectif"] = "Objectif réécrit par le tuteur"
    fiche_corrigee = fiche_service.corriger(db, fiche, nouveau_contenu, "Mme Traoré")

    assert fiche_corrigee.version == "corrigee"
    assert fiche_corrigee.corrigee_par == "Mme Traoré"
    assert fiche_corrigee.date_correction is not None
    assert fiche_corrigee.contenu["objectif"] == "Objectif réécrit par le tuteur"
