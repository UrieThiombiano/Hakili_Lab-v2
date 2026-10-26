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
