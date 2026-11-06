"""Espace de travail d'une analyse : scans supprimés en fin d'analyse, rapport
et plan servis depuis `runs/<copy_id>/` sans écriture en base."""
from types import SimpleNamespace

from app.routers.corrections import _fichier_espace_travail
from app.services.taches import _supprimer_scans
from src.core.config import settings


def test_fin_d_analyse_supprime_les_scans_et_garde_les_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runs_dir", str(tmp_path))
    dossier = tmp_path / "c1"
    for sous in ("depot", "pages"):
        (dossier / sous).mkdir(parents=True)
        (dossier / sous / "p1.png").write_bytes(b"x")
    (dossier / "rapport_correction.pdf").write_bytes(b"%PDF")

    _supprimer_scans("c1")

    assert not (dossier / "depot").exists() and not (dossier / "pages").exists()
    assert (dossier / "rapport_correction.pdf").exists()


def test_fichier_espace_travail_refuse_un_chemin_hors_du_dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runs_dir", str(tmp_path))
    dossier = tmp_path / "c1"
    dossier.mkdir()
    rapport = dossier / "rapport_correction.pdf"
    rapport.write_bytes(b"%PDF")
    ailleurs = tmp_path / "secret.pdf"
    ailleurs.write_bytes(b"%PDF")

    correction = SimpleNamespace(copy_id="c1", resultat={"pdf_path": str(rapport), "remediation_pdf_path": str(ailleurs)})

    assert _fichier_espace_travail(correction, "rapport") == rapport
    assert _fichier_espace_travail(correction, "remediation") is None
    assert _fichier_espace_travail(correction, "scan") is None


def test_sauvegarder_ecrit_copie_note_documents_et_hypotheses_une_seule_fois(db, tmp_path, monkeypatch):
    from app.models import Copie, Correction, Document
    from app.services import taches
    from src.models.domain import IngestionResult
    from src.pipeline.pipeline import PipelineResult
    from src.pipeline.serialisation import serialiser

    monkeypatch.setattr(settings, "runs_dir", str(tmp_path))
    dossier = tmp_path / "c1"
    dossier.mkdir()
    rapport, plan = dossier / "rapport_correction.pdf", dossier / "plan_remediation.pdf"
    rapport.write_bytes(b"%PDF-rapport")
    plan.write_bytes(b"%PDF-plan")
    resultat = PipelineResult(
        copy_id="c1", student_name="Amale",
        ingestion=IngestionResult(copy_id="c1", total_pages=0, pages=[], output_dir=dossier),
        classe="3eme", pdf_path=rapport, remediation_pdf_path=plan,
    )
    correction = Correction(copy_id="c1", identifiant_hakili="e1", etat="terminee", resultat=serialiser(resultat))
    db.add(correction)
    db.commit()

    ecritures = []
    monkeypatch.setattr(taches, "_ecrire_hypotheses_module4", lambda *a, **k: ecritures.append(a))

    taches.sauvegarder(db, correction)
    taches.sauvegarder(db, correction)

    copie = db.get(Copie, "c1")
    assert copie.classe == "3eme" and copie.identifiant_hakili == "e1"
    assert sorted(d.type for d in db.query(Document).filter_by(copy_id="c1")) == ["rapport", "remediation"]
    assert len(ecritures) == 1
