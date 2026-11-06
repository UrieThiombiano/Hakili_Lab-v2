"""
TestRegistry — Catalogue des tests standards Hakili Lab.

Pour chaque test pré-défini, charge automatiquement :
  - L'énoncé (texte extrait du fichier DOCX dans data/Documents/)
  - Le barème Rubric (construit depuis le YAML data/knowledge/bareme_socle_*.yaml)
  - Le bareme_id RAG correspondant

Utilisation dans le pipeline :
    registry = get_registry()
    test = registry.get_test("socle_6eme")
    rubric      = test.rubric        # Rubric Pydantic prêt à l'emploi
    subject_text = test.subject_text  # Texte de l'énoncé
    bareme_id    = test.bareme_id

Tests retirés
-------------
Les tests antérieurs à la batterie du 2026-10-16 (6 tests v1 et sujets longs
d'août) ne sont plus au catalogue ; leurs fichiers restent dans l'historique git.
Le mécanisme `archive: True` (chargé, résolu par get_test(), mais non proposé)
reste disponible pour retirer un test dont des copies corrigées dépendent.

    available_tests()  -> tests proposables pour une NOUVELLE correction
    all_tests()        -> tous les tests, archivés compris (historique)
    get_test(id)       -> résout n'importe quel test, archivé ou non
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.knowledge.answer_loader import get_answer_loader

if TYPE_CHECKING:
    from src.models.domain import Rubric

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_DOCS_DIR = _ROOT / "data" / "Documents"
_CORRIGES_DIR = _DOCS_DIR / "corriges"
_KB_DIR = _ROOT / "data" / "knowledge"

# ── Catalogue des tests Hakili ────────────────────────────────────────────────
#
# Seuls les 7 tests diagnostiques livrés le 2026-10-16 (batterie allégée) sont
# au catalogue. Les tests antérieurs (v1 de juin-juillet, sujets longs d'août)
# ont été retirés à la demande du commanditaire : aucune correction en base ne
# s'y rapportait. `archive: True` reste supporté pour un retrait futur.

_TEST_CATALOG: dict[str, dict] = {
    # ── Tests v2 — actifs ─────────────────────────────────────────────────────
    # Batterie allégée du 2026-10-06 (les sujets du 2026-08-12 étaient trop
    # longs : les élèves ne finissaient pas). Barèmes générés par
    # scripts/generer_baremes_socle.py depuis data/referentiel/Referentiel_Urie_v1.xlsx
    # et les corrigés transcrits des PDF enseignant (data/knowledge/corriges_socle.yaml) :
    # barème automatique et corrigé imprimé portent désormais les mêmes questions.
    # `label` et `niveaux` sont laissés vides : ils sont lus dans le `meta` du
    # YAML (titre, classe) pour éviter de dupliquer la même information.
    #
    # Pas de DOCX : les sujets sont des PDF dont les mathématiques sont dessinées
    # en vectoriel, donc non extractibles en texte. Ce n'est pas bloquant — dans
    # ce format l'élève compose SUR le sujet, donc la copie scannée porte déjà
    # l'énoncé imprimé que l'IA transcrit.
    **{
        f"socle_{niveau}": {
            "label": "",
            "description": (
                "Batterie allégée (oct. 2026) · automatismes, savoir-faire, "
                "3 ou 4 problèmes · corrigé complet"
            ),
            "niveaux": "",
            "docx_filename": "",
            "bareme_yaml": f"bareme_socle_{niveau}.yaml",
            "corrige_yaml": "",
            # Le sujet PDF sert à l'IMPRESSION, pas à l'extraction de texte : ses
            # mathématiques sont vectorielles (voir docs/harmonisation_donnees.md
            # §3bis). L'enseignant doit pouvoir l'imprimer depuis l'application.
            "sujet_pdf": f"Test_diagnostique_entree_{niveau}.pdf",
            # Corrigé enseignant imprimable, aligné sur bareme_socle_*.yaml.
            "corrige_pdf": f"corriges/Corrige_test_diagnostique_entree_{niveau}.pdf",
        }
        for niveau in ("6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD", "tleD")
    },
}


@dataclass
class HakiliTest:
    """Test Hakili pré-chargé — prêt à injecter dans run_single_copy()."""
    bareme_id: str
    label: str
    description: str
    niveaux: str
    subject_text: str
    rubric: "Rubric"  # type: ignore[type-arg]
    total_questions: int
    official_answers: str = ""  # Corrigé officiel formaté pour injection dans le prompt
    archive: bool = False       # True = plus proposé pour une nouvelle correction
    sujet_pdf: Path | None = None  # sujet imprimable, None si absent
    corrige_pdf: Path | None = None  # corrigé enseignant imprimable, None si absent
    # {code question: format} — vide pour les tests archivés. Le format décide
    # de ce que le diagnostic contraint peut faire d'une réponse : un QCM se
    # tranche sans modèle, une construction géométrique ne se diagnostique pas.
    formats: dict[str, str] = field(default_factory=dict)


def _extract_docx_text(docx_path: Path) -> str:
    """Extrait le texte brut d'un fichier DOCX (tous paragraphes non vides)."""
    try:
        import docx  # python-docx
        doc = docx.Document(str(docx_path))
        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                lines.append(text)
        # Inclure aussi les tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and text not in lines:
                        lines.append(text)
        return "\n".join(lines)
    except ImportError:
        logger.error("python-docx non installé — impossible d'extraire l'énoncé DOCX.")
        return ""
    except Exception as exc:
        logger.error("Erreur extraction DOCX %s : %s", docx_path.name, exc)
        return ""


def _build_rubric_from_yaml(bareme_yaml_path: Path) -> tuple["Rubric", int, dict]:
    """
    Construit un objet Rubric Pydantic à partir d'un fichier de barème YAML.

    Deux formats sont acceptés :

    - **v2** (`bareme_socle_*.yaml`, généré par `scripts/generer_baremes_socle.py`) :
      liste plate `questions`, clés `code` / `objet` / `bareme`. Structure plate parce
      que les 7 domaines du référentiel (N, L, G, D, F, M, S, T) ne rentrent pas dans
      un découpage numérique/géométrique.
    - **Ancien** (`bareme_test_*.yaml`, tests archivés) : sections
      `questions_numeriques` / `questions_geometriques`, clés `id` / `enonce_court` /
      `points_originaux`. Conservé pour la relecture de l'historique.

    Retourne (rubric, total_questions, meta).
    """
    from src.models.domain import Rubric, RubricItem

    try:
        raw = yaml.safe_load(bareme_yaml_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Erreur lecture barème YAML %s : %s", bareme_yaml_path.name, exc)
        return Rubric(subject="mathematics", total_points=0, items=[]), 0, {}

    meta = raw.get("meta", {}) or {}
    items: list[RubricItem] = []

    if "questions" in raw:  # format v2
        for q in raw.get("questions", []):
            qid = q.get("code", "")
            if qid:
                max_score = float(q.get("bareme", 0.0))
                points = float(q.get("bareme_classeur") or 0.0)
                # Partie A : tout ou rien (règle 2 des corrigés). Parties B et C :
                # notées critère par critère, au demi-point près du corrigé.
                if points <= 0 or q.get("partie") == "A":
                    pas = max_score
                else:
                    pas = max_score / (2 * points)
                items.append(
                    RubricItem(
                        id=qid,
                        label=q.get("objet", "") or qid,
                        max_score=max_score,
                        points_corrige=points or None,
                        score_step=round(pas, 6),
                    )
                )
    else:  # format ancien
        for section in ("questions_numeriques", "questions_geometriques"):
            for q in raw.get(section, []):
                qid = q.get("id", "")
                label = q.get("enonce_court", qid)
                pts = float(q.get("points_originaux", 1.0))
                if qid:
                    items.append(RubricItem(id=qid, label=label, max_score=pts))

    # Format de chaque question (qcm / court / redige / construction). Seuls les
    # barèmes v2 le portent — il vient du classeur, et c'est la même valeur
    # que porte `referentiel.Question.format` en base.
    meta["formats"] = {
        q["code"]: q["format"]
        for q in (raw.get("questions") or [])
        if q.get("code") and q.get("format")
    }

    total_pts = float(meta.get("total_possible") or sum(i.max_score for i in items))
    rubric = Rubric(subject="mathematics", total_points=total_pts, items=items)
    return rubric, len(items), meta


class TestRegistry:
    """
    Singleton — chargé une fois en début de session.

    Charge et met en cache les tests Hakili (énoncés + barèmes).
    """

    def __init__(self) -> None:
        self._tests: dict[str, HakiliTest] = {}
        self._load_all()

    def _load_all(self) -> None:
        for test_id, cfg in _TEST_CATALOG.items():
            docx_filename = cfg.get("docx_filename", "")
            docx_path = (_DOCS_DIR / docx_filename) if docx_filename else None
            yaml_path = _KB_DIR / cfg["bareme_yaml"]

            archive = bool(cfg.get("archive", False))
            if docx_path is None:
                logger.info("Test '%s' — pas de DOCX (énoncé absent).", test_id)
            elif not docx_path.exists():
                # Pour un test archivé, l'absence du DOCX est normale : les sujets
                # ont été refaits et les anciens fichiers retirés. Le signaler comme
                # un avertissement laisserait croire à une installation cassée.
                niveau = logger.info if archive else logger.warning
                niveau(
                    "Test '%s' — DOCX absent%s : %s",
                    test_id,
                    " (archivé, attendu)" if archive else "",
                    docx_path.name,
                )
            if not yaml_path.exists():
                logger.warning(
                    "Test '%s' — barème YAML introuvable : %s", test_id, yaml_path
                )
                continue

            subject_text = (
                _extract_docx_text(docx_path)
                if docx_path is not None and docx_path.exists()
                else ""
            )
            sujet_pdf_nom = cfg.get("sujet_pdf", "")
            sujet_pdf = (_DOCS_DIR / sujet_pdf_nom) if sujet_pdf_nom else None
            if sujet_pdf is not None and not sujet_pdf.exists():
                logger.warning(
                    "Test '%s' — sujet PDF introuvable : %s (impression indisponible)",
                    test_id, sujet_pdf.name,
                )
                sujet_pdf = None

            corrige_pdf_nom = cfg.get("corrige_pdf", "")
            corrige_pdf = (_DOCS_DIR / corrige_pdf_nom) if corrige_pdf_nom else None
            if corrige_pdf is not None and not corrige_pdf.exists():
                logger.warning(
                    "Test '%s' — corrigé PDF introuvable : %s (correction papier indisponible)",
                    test_id, corrige_pdf.name,
                )
                corrige_pdf = None

            rubric, total, bareme_meta = _build_rubric_from_yaml(yaml_path)

            # Chargement du corrigé officiel
            official_answers = get_answer_loader().get_official_answers(test_id)

            # Les tests v2 laissent label/niveaux vides dans le catalogue :
            # la valeur fait autorité dans le `meta` du barème, pas ici.
            label = cfg["label"] or str(bareme_meta.get("titre") or test_id)
            niveaux = cfg["niveaux"] or str(bareme_meta.get("classe") or "")

            self._tests[test_id] = HakiliTest(
                bareme_id=test_id,
                label=label,
                description=cfg["description"],
                niveaux=niveaux,
                subject_text=subject_text,
                rubric=rubric,
                total_questions=total,
                official_answers=official_answers,
                archive=archive,
                sujet_pdf=sujet_pdf,
                corrige_pdf=corrige_pdf,
                formats=bareme_meta.get("formats") or {},
            )
            corrige_status = f"corrigé {len(official_answers)} chars" if official_answers else "sans corrigé"
            logger.info(
                "Test chargé : %s (%d questions, énoncé %d chars, %s)%s",
                test_id, total, len(subject_text), corrige_status,
                " [ARCHIVÉ]" if cfg.get("archive") else "",
            )

    def available_tests(self) -> dict[str, HakiliTest]:
        """Tests proposables pour une NOUVELLE correction — sans les archivés."""
        return {tid: t for tid, t in self._tests.items() if not t.archive}

    def all_tests(self) -> dict[str, HakiliTest]:
        """Tous les tests chargés, archivés compris — relecture de l'historique."""
        return dict(self._tests)

    def get_test(self, test_id: str) -> HakiliTest | None:
        """Résout n'importe quel test, archivé ou non — l'historique en dépend."""
        return self._tests.get(test_id)

    @property
    def ids(self) -> list[str]:
        """Identifiants de tous les tests chargés, archivés compris."""
        return list(self._tests.keys())


# ── Singleton module-level ────────────────────────────────────────────────────

_registry: TestRegistry | None = None


def get_registry() -> TestRegistry:
    global _registry
    if _registry is None:
        _registry = TestRegistry()
    return _registry
