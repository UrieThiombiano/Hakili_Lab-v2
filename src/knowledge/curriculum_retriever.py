"""
CurriculumRetriever — base de connaissance RAG sur les curriculums officiels.

Fonctionnement :
  1. Charge tous les fichiers YAML de data/knowledge/curriculum_*.yaml au démarrage.
  2. Index les chunks par leur `id` (ex: "5e_NUM_Ch3_L1").
  3. À la correction, les barèmes YAML (bareme_test_*.yaml) indiquent les chunk_ids
     liés à chaque question. Les chunks des questions échouées sont récupérés
     et injectés dans le prompt diagnostic.

Format d'un chunk YAML :
  id, classe, domaine, chapitre, lecon, savoir, savoir_faire[], prerequis_ids[],
  mots_cles[], erreurs_frequentes[]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent.parent.parent / "data" / "knowledge"


def _coerce_str(item: Any) -> str:
    """Convertit un item YAML en chaîne.

    PyYAML parse `- texte : formule` (espace-deux-points-espace) en dict
    au lieu de string. Cette fonction reconstruit la chaîne attendue.
    """
    if isinstance(item, dict):
        parts = [f"{k} : {v}" if v is not None else str(k) for k, v in item.items()]
        return " ".join(parts)
    return str(item)


class CurriculumChunk:
    """Un chunk = une leçon du programme officiel."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.classe: str = data["classe"]
        self.domaine: str = data.get("domaine", "")
        self.chapitre: str = data.get("chapitre", "")
        self.lecon: str = data.get("lecon", "")
        self.savoir: str = data.get("savoir", "")
        self.savoir_faire: list[str] = [_coerce_str(x) for x in data.get("savoir_faire", [])]
        self.prerequis_ids: list[str] = data.get("prerequis_ids", [])
        self.mots_cles: list[str] = data.get("mots_cles", [])
        self.erreurs_frequentes: list[str] = [_coerce_str(x) for x in data.get("erreurs_frequentes", [])]

    def to_context_text(self) -> str:
        """Texte injecté dans le prompt diagnostic pour ce chunk."""
        lines = [
            f"[{self.id}] {self.classe} — {self.chapitre} : {self.lecon}",
            f"  Savoir : {self.savoir}",
        ]
        if self.savoir_faire:
            lines.append("  Savoir-faire :")
            for sf in self.savoir_faire:
                lines.append(f"    • {sf}")
        if self.erreurs_frequentes:
            lines.append("  Erreurs fréquentes :")
            for ef in self.erreurs_frequentes:
                lines.append(f"    ⚠ {ef}")
        return "\n".join(lines)

    def to_gap_text(self) -> str:
        """Texte court pour identifier une compétence non maîtrisée."""
        return (
            f"[{self.id}] {self.classe}/{self.domaine} — "
            f"'{self.lecon}' ({self.chapitre})"
        )


class BaremeQuestion:
    """Mapping entre une question du test et ses chunk_ids de compétences."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.enonce_court: str = data.get("enonce_court", "")
        self.niveau_programme: list[str] = data.get("niveau_programme", [])
        self.competences_cibles: list[str] = data.get("competences_cibles", [])
        self.chunk_ids: list[str] = data.get("chunk_ids", [])
        self.lacune_type: str = data.get("lacune_type", "")


class CurriculumRetriever:
    """
    Singleton chargé une fois au démarrage du pipeline.

    Utilisation :
        retriever = CurriculumRetriever()
        context = retriever.get_diagnostic_context(
            failed_question_ids=["Q_NUM_07", "Q_NUM_10"],
            bareme_id="socle_6eme",
        )
    """

    def __init__(self) -> None:
        self._chunks: dict[str, CurriculumChunk] = {}
        self._baremes: dict[str, dict[str, BaremeQuestion]] = {}
        self._load_curriculum()
        self._load_baremes()

    def _load_curriculum(self) -> None:
        curriculum_files = list(_KB_DIR.glob("curriculum_*.yaml"))
        if not curriculum_files:
            logger.warning("Aucun fichier curriculum_*.yaml trouvé dans %s", _KB_DIR)
            return
        for path in curriculum_files:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    logger.warning("%s : format YAML inattendu (pas une liste)", path.name)
                    continue
                for item in data:
                    chunk = CurriculumChunk(item)
                    self._chunks[chunk.id] = chunk
                logger.info("Curriculum chargé : %s (%d leçons)", path.name, len(data))
            except Exception as exc:
                logger.error("Erreur lecture %s : %s", path.name, exc)
        logger.info("Base de connaissance : %d chunks curriculum au total", len(self._chunks))

    def _load_baremes(self) -> None:
        bareme_files = list(_KB_DIR.glob("bareme_test_*.yaml"))
        if not bareme_files:
            logger.debug("Aucun barème historique (bareme_test_*.yaml) — les tests du référentiel passent par l'ancrage du référentiel.")
            return
        for path in bareme_files:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                meta = raw.get("meta", {})
                test_id = meta.get("test_id", path.stem)
                questions: dict[str, BaremeQuestion] = {}
                for section_key in ("questions_numeriques", "questions_geometriques"):
                    for q in raw.get(section_key, []):
                        bq = BaremeQuestion(q)
                        questions[bq.id] = bq
                self._baremes[test_id] = questions
                logger.info("Barème chargé : %s (%d questions)", test_id, len(questions))
            except Exception as exc:
                logger.error("Erreur lecture %s : %s", path.name, exc)

    # ── API publique ──────────────────────────────────────────────────────────

    def get_chunk(self, chunk_id: str) -> CurriculumChunk | None:
        return self._chunks.get(chunk_id)

    def get_chunks_for_question(
        self, question_id: str, bareme_id: str
    ) -> list[CurriculumChunk]:
        bareme = self._baremes.get(bareme_id, {})
        bq = bareme.get(question_id)
        if bq is None:
            return []
        chunks = []
        for cid in bq.chunk_ids:
            chunk = self._chunks.get(cid)
            if chunk:
                chunks.append(chunk)
            else:
                logger.debug("chunk_id '%s' référencé dans %s mais absent du KB", cid, bareme_id)
        return chunks

    def get_diagnostic_context(
        self,
        failed_question_ids: list[str],
        bareme_id: str,
    ) -> str:
        """
        Construit le bloc de contexte curricula à injecter dans le prompt diagnostic.

        Retourne une chaîne vide si :
          - le barème n'existe pas (test sans RAG, ex : test 6e avec primaire)
          - aucun chunk_id n'est associé aux questions échouées
        """
        if bareme_id not in self._baremes:
            return ""

        seen_chunk_ids: set[str] = set()
        context_blocks: list[str] = []

        for q_id in failed_question_ids:
            chunks = self.get_chunks_for_question(q_id, bareme_id)
            for chunk in chunks:
                if chunk.id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.id)
                    context_blocks.append(chunk.to_context_text())

        if not context_blocks:
            return ""

        header = (
            "## Compétences du programme officiel liées aux questions échouées\n\n"
            "Les compétences ci-dessous sont extraites du programme officiel "
            "du Ministère de l'Éducation du Burkina Faso. "
            "Utilise-les pour identifier précisément les leçons non maîtrisées "
            "et formuler un diagnostic ancré sur les compétences officielles.\n"
        )
        return header + "\n\n".join(context_blocks)

    def get_competency_gaps(
        self,
        failed_question_ids: list[str],
        bareme_id: str,
    ) -> list[dict[str, str]]:
        """
        Retourne la liste des lacunes de compétence (chunk_id + texte court)
        pour les questions échouées — utilisé pour enrichir DiagnosticResult.
        """
        if bareme_id not in self._baremes:
            return []

        seen: set[str] = set()
        gaps: list[dict[str, str]] = []

        for q_id in failed_question_ids:
            chunks = self.get_chunks_for_question(q_id, bareme_id)
            for chunk in chunks:
                if chunk.id not in seen:
                    seen.add(chunk.id)
                    gaps.append({
                        "chunk_id": chunk.id,
                        "classe": chunk.classe,
                        "domaine": chunk.domaine,
                        "chapitre": chunk.chapitre,
                        "lecon": chunk.lecon,
                        "savoir_faire": chunk.savoir_faire,
                        "erreurs_frequentes": chunk.erreurs_frequentes,
                        "description": chunk.to_gap_text(),
                    })
        return gaps
