"""
Parseur des livrets de remédiation (`remediation/<niveau>/modules_c/M*.md`,
en dehors de ce dépôt — voir `_REMEDIATION_DIR`).

Pourquoi ce module
-------------------
Le module 5 (sujet de confirmation T1) et le futur module 7 (fiches de
remédiation) ont besoin d'une matière pédagogique calibrée par niveau, sans
laquelle le LLM génère des exercices à l'aveugle (voir `remediation_retriever
.py` pour la suite de la chaîne). `remediation/` porte 79 modules rédigés
selon un gabarit fixe et vérifié uniforme (`_gabarit/GABARIT_CONDENSE.md`,
vérifié identique tête de fichier à tête de fichier sur les 79) : ce parseur
en extrait une structure exploitable, sans jamais réécrire le texte source.

Ce que ce parseur ne fait pas
------------------------------
Il ne classe pas les leçons par compétence canonique — c'est le rôle de
`scripts/rapprocher_remediation.py` (rapprochement, jugement pédagogique,
séparé de l'extraction mécanique faite ici). Un module qui ne respecte pas le
gabarit sur un point précis dégrade la donnée correspondante (liste vide,
champ `None`) plutôt que de faire échouer tout le fichier — sauf sur les
sections invariantes (numéro et titre de module, présence d'au moins une
leçon et d'au moins un exercice), où un module qui ne les fournit pas trahit
un vrai problème de source et doit être vu, pas absorbé en silence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# `Hakili_Lab/src/knowledge/remediation_parser.py` -> remonter à `HAKILI-V2/`
_ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION_DIR = _ROOT / "remediation"

NIVEAUX = ["6eme", "5eme", "4eme", "3eme", "2ndeC", "1ereD", "TleD"]

CORRIGES_MARK = "<!-- ===== CORRIGES ===== -->"

_RE_MODULE_HEADER = re.compile(r"^##\s*MODULE\s*(\d+)\s*:\s*(.+?)\s*$", re.M)
_RE_LECON_HEADER = re.compile(r"^##\s*(\d+\.\d+)\s+(.+?)\s*$", re.M)
_RE_SECTION_HEADER = re.compile(r"^##\s+.+$", re.M)
_RE_EXERCICE = re.compile(
    r"\*\*Exercice\s*(\d+)\.\*\*\s*(★{1,3})\s*(.+?)(?=\n\*\*Exercice\s*\d+\.\*\*|\Z)",
    re.S,
)
_RE_CORRIGE_EXERCICE = re.compile(
    r"\*\*Exercice\s*(\d+)\.\*\*\s*(.+?)(?=\n\*\*Exercice\s*\d+\.\*\*|\Z)", re.S
)
_RE_DIAGNOSTIC_Q = re.compile(r"\*\*D(\d)\.\*\*\s*(.+?)(?=\s*\*\*D\d\.\*\*|\n\n|\Z)", re.S)
_RE_DIAGNOSTIC_REP = re.compile(r"D(\d)\s*:\s*(.+?)(?=\s+D\d\s*:|\s*$)", re.S)
_RE_FIGURE = re.compile(r"\[SVG:\s*([^\]]+?)\]")
_RE_ERREUR_FREQ = re.compile(
    r"-\s*\*\*Erreur fréquente\s*:\*\*\s*(.+?)\*\*Correction\s*:\*\*\s*(.+?)"
    r"(?=\n-\s*\*\*Erreur fréquente|\Z)",
    re.S,
)


def _fold_blank(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _slice(text: str, start_pat: re.Pattern, *, from_end_of_match: bool = True) -> tuple[str, int, int]:
    """Retourne (texte, début, fin) de la section commençant au 1er match de
    `start_pat`, jusqu'au prochain `## ` de même niveau ou la fin du texte."""
    m = start_pat.search(text)
    if not m:
        return "", -1, -1
    start = m.end() if from_end_of_match else m.start()
    nxt = _RE_SECTION_HEADER.search(text, m.end())
    end = nxt.start() if nxt else len(text)
    return text[start:end].strip(), start, end


@dataclass
class ErreurFrequente:
    erreur: str
    correction: str


@dataclass
class Lecon:
    numero: str
    titre: str
    retenir: list[str] = field(default_factory=list)
    methode_titre: str | None = None
    methode_etapes: list[str] = field(default_factory=list)
    exemple_resolu: str | None = None
    erreurs_frequentes: list[ErreurFrequente] = field(default_factory=list)
    declic: str | None = None
    figures: list[str] = field(default_factory=list)


@dataclass
class Exercice:
    numero: int
    etoiles: int
    enonce: str
    correction: str = ""


@dataclass
class Module:
    niveau: str
    numero: int
    titre: str
    pourquoi: str = ""
    diagnostic: list[tuple[str, str]] = field(default_factory=list)
    lecons: list[Lecon] = field(default_factory=list)
    exercices: list[Exercice] = field(default_factory=list)
    fiche_revision: list[str] = field(default_factory=list)
    trouve_erreur: list[tuple[str, str]] = field(default_factory=list)
    source_path: str = ""


def _parse_pourquoi(corps: str) -> str:
    m = re.search(
        r"\*Pourquoi ce module\s*\?\*\s*(.+?)(?=\n\n##\s*DIAGNOSTIC EXPRESS)", corps, re.S
    )
    return _fold_blank(m.group(1)) if m else ""


def _parse_diagnostic(corps: str) -> list[tuple[str, str]]:
    bloc, start, end = _slice(corps, re.compile(r"^##\s*DIAGNOSTIC EXPRESS\s*$", re.M))
    if not bloc:
        return []
    questions = {num: _fold_blank(q) for num, q in _RE_DIAGNOSTIC_Q.findall(bloc)}
    m_rep = re.search(r"\*\*Corrigés\.\*\*\s*(.+)", bloc)
    reponses: dict[str, str] = {}
    if m_rep:
        reponses = {num: r.strip().rstrip(".") for num, r in _RE_DIAGNOSTIC_REP.findall(m_rep.group(1))}
    return [
        (questions[n], reponses.get(n, ""))
        for n in sorted(questions, key=int)
    ]


def _parse_lecon_bloc(numero: str, titre: str, bloc: str) -> Lecon:
    lecon = Lecon(numero=numero, titre=titre.strip())

    m = re.search(
        r">\s*####\s*📖\s*CE QU'IL FAUT RETENIR\s*\n(.+?)(?=\n>\s*####|\n\n[^>]|\Z)", bloc, re.S
    )
    if m:
        lecon.retenir = [
            _fold_blank(ligne.lstrip("> ").lstrip("- ").strip())
            for ligne in m.group(1).splitlines()
            if ligne.strip().startswith(">") and "-" in ligne[:6]
        ]

    m = re.search(
        r">\s*####\s*MÉTHODE\s*:\s*(.+?)\n(.+?)(?=\n>\s*####|\n\n[^>]|\Z)", bloc, re.S
    )
    if m:
        lecon.methode_titre = m.group(1).strip()
        lecon.methode_etapes = [
            re.sub(r"^\d+\.\s*", "", ligne.lstrip("> ").strip())
            for ligne in m.group(2).splitlines()
            if re.match(r">\s*\d+\.", ligne)
        ]

    m = re.search(
        # Arrêt devant N'IMPORTE QUEL sous-titre en bloc-citation qui suit
        # (« DÉCLIC » ou « ⚠ ATTENTION », selon lequel des deux vient en
        # premier dans la leçon) — s'arrêter seulement devant "⚠" avalait le
        # bloc DÉCLIC entier quand il précédait ATTENTION, corrigé D-CEO-43.
        r"\*\*Exemple résolu\.\*\*\s*(.+?)(?=\n>\s*####|\n\n##|\Z)", bloc, re.S
    )
    if m:
        lecon.exemple_resolu = _fold_blank(m.group(1))

    m = re.search(
        r">\s*####\s*⚠\s*ATTENTION\s*!\s*\n(.+?)(?=\n>\s*####|\n\n[^>]|\Z)", bloc, re.S
    )
    if m:
        attention_lines = "\n".join(
            ligne.strip().lstrip(">").strip()
            for ligne in m.group(1).splitlines()
            if ligne.strip().lstrip(">").strip()
        )
        for erreur, correction in _RE_ERREUR_FREQ.findall(attention_lines):
            lecon.erreurs_frequentes.append(
                ErreurFrequente(erreur=_fold_blank(erreur), correction=_fold_blank(correction))
            )

    # Même correctif qu'« Exemple résolu » ci-dessus, dans l'autre sens :
    # DÉCLIC doit s'arrêter avant ATTENTION quand ATTENTION le suit.
    m = re.search(r">\s*####\s*DÉCLIC\s*:\s*(.+?)\n(.+?)(?=\n>\s*####|\n\n[^>]|\Z)", bloc, re.S)
    if m:
        corps_declic = " ".join(
            ligne.lstrip("> ").strip()
            for ligne in m.group(2).splitlines()
            if ligne.strip().startswith(">") and ligne.lstrip("> ").strip()
        )
        lecon.declic = _fold_blank(f"{m.group(1).strip()} — {corps_declic}")

    lecon.figures = _RE_FIGURE.findall(bloc)
    return lecon


def _parse_lecons(corps: str) -> list[Lecon]:
    headers = list(_RE_LECON_HEADER.finditer(corps))
    lecons = []
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(corps)
        # une leçon s'arrête aussi au prochain "## " qui n'est pas "## n.x"
        section_end = _RE_SECTION_HEADER.search(corps, start)
        if section_end and section_end.start() < end and not _RE_LECON_HEADER.match(corps, section_end.start()):
            end = section_end.start()
        lecons.append(_parse_lecon_bloc(h.group(1), h.group(2), corps[start:end]))
    return lecons


def _parse_exercices(corps: str, corrections: dict[int, str]) -> list[Exercice]:
    bloc, _, _ = _slice(corps, re.compile(r"^##\s*EXERCICES\s*\(Module\s*\d+\)\s*$", re.M))
    if not bloc:
        return []
    exercices = []
    for num, etoiles, enonce in _RE_EXERCICE.findall(bloc):
        n = int(num)
        exercices.append(
            Exercice(
                numero=n,
                etoiles=len(etoiles),
                enonce=_fold_blank(enonce),
                correction=corrections.get(n, ""),
            )
        )
    return exercices


def _parse_corrections(corrige_bloc: str) -> dict[int, str]:
    return {int(num): _fold_blank(txt) for num, txt in _RE_CORRIGE_EXERCICE.findall(corrige_bloc)}


def _parse_fiche_revision(corps: str) -> list[str]:
    bloc, _, _ = _slice(corps, re.compile(r"^##\s*FICHE DE RÉVISION\s*\(Module\s*\d+\)\s*$", re.M))
    if not bloc:
        return []
    # Deux gabarits coexistent : une notion par paragraphe (ligne blanche
    # entre chaque) ou une notion par ligne simple (1ereD/TleD) — on force
    # une frontière devant chaque nouvelle notion en gras avant de découper.
    bloc = re.sub(r"\n(?=\*\*)", "\n\n", bloc)
    return [_fold_blank(p) for p in re.split(r"\n\n+", bloc) if p.strip()]


def _parse_trouve_erreur(corps: str) -> list[tuple[str, str]]:
    bloc, _, _ = _slice(corps, re.compile(r"^##\s*✗\s*TROUVE L'ERREUR\s*\(Module\s*\d+\)\s*$", re.M))
    if not bloc:
        return []
    lignes = []
    for ligne in bloc.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("|") or set(ligne.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue
        cols = [c.strip() for c in ligne.strip("|").split("|")]
        if len(cols) >= 2 and "✗ faux" not in cols[0].lower():
            lignes.append((cols[0], cols[1]))
    return lignes


def parse_module_file(path: Path, niveau: str) -> Module:
    texte = path.read_text(encoding="utf-8")
    if CORRIGES_MARK in texte:
        corps, corrige_bloc = texte.split(CORRIGES_MARK, 1)
    else:
        corps, corrige_bloc = texte, ""

    m = _RE_MODULE_HEADER.search(corps)
    if not m:
        raise ValueError(f"{path} : en-tête '## MODULE n : titre' introuvable")
    numero, titre = int(m.group(1)), m.group(2).strip()

    corrections = _parse_corrections(corrige_bloc)
    exercices = _parse_exercices(corps, corrections)
    lecons = _parse_lecons(corps)
    if not lecons:
        raise ValueError(f"{path} : aucune leçon '## n.x' trouvée")
    if not exercices:
        raise ValueError(f"{path} : aucun exercice trouvé")

    return Module(
        niveau=niveau,
        numero=numero,
        titre=titre,
        pourquoi=_parse_pourquoi(corps),
        diagnostic=_parse_diagnostic(corps),
        lecons=lecons,
        exercices=exercices,
        fiche_revision=_parse_fiche_revision(corps),
        trouve_erreur=_parse_trouve_erreur(corps),
        source_path=str(path.relative_to(_ROOT)),
    )


def parse_niveau(niveau: str) -> list[Module]:
    dossier = _REMEDIATION_DIR / niveau / "modules_c"
    fichiers = sorted(dossier.glob("M*.md"))
    if not fichiers:
        raise ValueError(f"Aucun module trouvé dans {dossier}")
    return [parse_module_file(f, niveau) for f in fichiers]


# ── Cartographie des lacunes (PLAN_Livret_Remediation_<classe>.md) ─────────

@dataclass
class LacuneCartographie:
    lacune: str
    module: str
    bloque_en: str


def parse_plan_livret(niveau: str) -> list[LacuneCartographie]:
    """Table « Cartographie des lacunes » du PLAN, quand il existe.

    N'existe que pour 2ndeC, 3eme, 4eme, 5eme dans l'édition actuelle — absent
    ailleurs, retourne une liste vide plutôt que d'échouer.
    """
    candidats = list((_REMEDIATION_DIR / niveau).glob("PLAN_Livret_Remediation_*.md"))
    if not candidats:
        return []
    texte = candidats[0].read_text(encoding="utf-8")
    m = re.search(
        r"##\s*2\.\s*Cartographie des lacunes.*?\n(.+?)(?=\n##\s*3\.)", texte, re.S
    )
    if not m:
        return []
    lignes = []
    for ligne in m.group(1).splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("|") or set(ligne.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue
        cols = [c.strip() for c in ligne.strip("|").split("|")]
        if len(cols) >= 4 and cols[0] != "#":
            lignes.append(LacuneCartographie(lacune=cols[1], module=cols[2], bloque_en=cols[3]))
    return lignes


# ── Positionnement (tête de Livret_Remediation_<classe>.md) ────────────────

@dataclass
class QuestionPositionnement:
    numero: str
    module: str


def parse_positionnement(niveau: str) -> list[QuestionPositionnement]:
    candidats = list((_REMEDIATION_DIR / niveau).glob(f"Livret_Remediation_{niveau}*.md"))
    candidats = [c for c in candidats if c.suffix == ".md"]
    if not candidats:
        return []
    texte = candidats[0].read_text(encoding="utf-8")
    m = re.search(r"\*\*Grille d'orientation\*\*\s*\n(.+?)(?=\n---|\Z)", texte, re.S)
    if not m:
        return []
    resultat = []
    for ligne in m.group(1).splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("|") or set(ligne.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue
        cols = [c.strip() for c in ligne.strip("|").split("|")]
        if len(cols) >= 2 and "questions ratées" not in cols[0].lower():
            resultat.append(QuestionPositionnement(numero=cols[0], module=cols[1]))
    return resultat
