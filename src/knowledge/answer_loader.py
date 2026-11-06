"""
AnswerLoader — charge les corrigés officiels Hakili Lab et les formate
en bloc texte injecté dans le prompt de correction.

Fonctionnement :
  1. Charge corrige_test_*.yaml depuis data/knowledge/ au démarrage.
  2. get_official_answers(test_id) → bloc texte prêt à injecter dans le prompt.
  3. Si le test_id est absent ou le fichier introuvable → retourne "" (pas de crash).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent.parent.parent / "data" / "knowledge"


class OfficialAnswer:
    """Réponse officielle pour une question donnée."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.reponse: str = data.get("reponse", "")
        self.solution: str = (data.get("solution") or "").strip()
        # Points de la question au corrigé enseignant (barèmes socle) — le
        # barème « 1 pt pour… ; 1 pt pour… » de `solution` s'y rapporte.
        self.points: float | None = data.get("points")

    def to_text(self) -> str:
        entete = f"{self.id} ({self.points:g} pt{'s' if self.points > 1 else ''} au corrigé)" if self.points else self.id
        lines = [f"{entete} → {self.reponse}"]
        if self.solution:
            for line in self.solution.splitlines():
                lines.append(f"   {line}")
        return "\n".join(lines)


class AnswerLoader:
    """
    Singleton — chargé une seule fois par session.

    Utilisation :
        loader = get_answer_loader()
        answers_text = loader.get_official_answers("socle_6eme")
    """

    def __init__(self) -> None:
        self._answers: dict[str, list[OfficialAnswer]] = {}
        self._load_all()

    def _load_all(self) -> None:
        corrige_files = list(_KB_DIR.glob("corrige_test_*.yaml"))
        if not corrige_files:
            logger.debug("Aucun corrigé au format historique (corrige_test_*.yaml) — normal depuis le retrait des anciens tests.")
        for path in corrige_files:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                test_id = raw.get("meta", {}).get("test_id", path.stem)
                all_answers: list[OfficialAnswer] = []
                for section in ("questions_numeriques", "questions_geometriques"):
                    for item in raw.get(section, []):
                        all_answers.append(OfficialAnswer(item))
                self._answers[test_id] = all_answers
                logger.info(
                    "Corrigé chargé : %s (%d réponses officielles)",
                    test_id, len(all_answers),
                )
            except Exception as exc:
                logger.error("Erreur lecture corrigé %s : %s", path.name, exc)

        # Barèmes v2 (data/knowledge/bareme_socle_*.yaml, générés par
        # scripts/generer_baremes_socle.py) — structure plate `questions` avec
        # `code`/`reponse_attendue`/`solution`, corrigé complet pour les QCM
        # (depuis le classeur) et partiel pour le reste (arbitrage B, saisi à
        # la main dans corriges_socle.yaml puis fusionné à la génération).
        for path in _KB_DIR.glob("bareme_socle_*.yaml"):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or "questions" not in raw:
                    continue
                test_id = raw.get("meta", {}).get("test_id", path.stem)
                all_answers = []
                for q in raw.get("questions", []):
                    reponse = (q.get("reponse_attendue") or "").strip()
                    if not reponse:
                        continue  # pas encore de corrigé (arbitrage B) — rien à injecter
                    if q.get("format") == "qcm" and q.get("options"):
                        option = next(
                            (o for o in q["options"] if str(o.get("lettre")) == reponse),
                            None,
                        )
                        if option and option.get("texte"):
                            reponse = f"{reponse}) {option['texte']}"
                    all_answers.append(OfficialAnswer({
                        "id": q.get("code", ""),
                        "reponse": reponse,
                        "solution": q.get("solution", ""),
                        "points": q.get("bareme_classeur"),
                    }))
                self._answers[test_id] = all_answers
                logger.info(
                    "Corrigé v2 chargé : %s (%d réponses officielles)",
                    test_id, len(all_answers),
                )
            except Exception as exc:
                logger.error("Erreur lecture barème v2 %s : %s", path.name, exc)

    def get_official_answers(self, test_id: str) -> str:
        """
        Retourne un bloc texte formaté pour injection dans le prompt de correction.
        Retourne "" si le test_id est inconnu (pas de crash, pipeline continue).
        """
        answers = self._answers.get(test_id)
        if not answers:
            return ""

        lines = [
            "## Corrigé officiel",
            "",
            "Ces réponses officielles te donnent le CONCEPT ou la VALEUR attendue pour chaque question.",
            "Ton rôle : vérifier si l'élève a démontré qu'il connaît ce concept ou a trouvé cette valeur —",
            "PAS vérifier si l'élève a écrit exactement la même chose que le corrigé.",
            "",
            "La forme du corrigé (notation formelle, ordre des termes, présentation compacte) est",
            "une convention de rédaction, pas un gabarit à reproduire mot pour mot.",
            "Un élève qui écrit la bonne réponse en prose, avec une notation différente, ou dans un",
            "ordre différent, a QUAND MÊME trouvé — accorde le point.",
            "",
            "Quand une entrée contient « Barème : … », ce barème répartit les points de la question",
            "entre plusieurs critères (démarche, résultat, conclusion) : note critère par critère,",
            "selon la section « Barème détaillé par critère » des consignes. Un résultat juste sans",
            "la démarche exigée n'obtient que les critères portant sur ce résultat.",
            "",
        ]
        for ans in answers:
            lines.append(ans.to_text())
            lines.append("")

        return "\n".join(lines)

    def get_answer_map(self, test_id: str) -> dict[str, str]:
        """Retourne {question_id: reponse_courte} pour un test donné."""
        answers = self._answers.get(test_id)
        if not answers:
            return {}
        return {a.id: a.reponse for a in answers}

    def available_tests(self) -> list[str]:
        return list(self._answers.keys())


# ── Singleton module-level ────────────────────────────────────────────────────

_loader: AnswerLoader | None = None


def get_answer_loader() -> AnswerLoader:
    global _loader
    if _loader is None:
        _loader = AnswerLoader()
    return _loader
