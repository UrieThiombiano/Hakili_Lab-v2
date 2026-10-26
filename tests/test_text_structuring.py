"""
Tests du découpage positionnel des textes LLM (text_structuring).

Les cas "exo_*" reproduisent les défauts réels observés dans le sujet de
remédiation généré pour la copie sandwidi_emrys (39 exercices, ≥10 touchés) :
deux systèmes de numérotation entrelacés dans une même chaîne, produits par
les LLM malgré le contrat de format des prompts.

Invariants vérifiés :
  1. les marqueurs sont des frontières positionnelles — les numéros portés
     par le LLM (redémarrages, entrelacements) sont ignorés ;
  2. aucun marqueur source ne survit dans l'intro ni dans les items — la
     seule numérotation visible est régénérée par le template.
"""
import re


from src.pipeline.pdf_remediation_html import _split_question
from src.pipeline.pdf_report_html import _action_html
from src.pipeline.text_structuring import split_numbered_items

# Aucun marqueur résiduel : "(1)" nulle part, ni "2." / "3)" en tête d'item
_INLINE_MARKER = re.compile(r"\(\d{1,2}\)\s")
_LEAD_MARKER = re.compile(r"^\d{1,2}[.)]\s")


def _assert_no_residual_numbering(intro: str, items: list[str]) -> None:
    assert not _INLINE_MARKER.search(intro), f"marqueur inline dans l'intro : {intro!r}"
    assert not _LEAD_MARKER.match(intro), f"marqueur en tête d'intro : {intro!r}"
    for it in items:
        assert not _LEAD_MARKER.match(it), f"marqueur en tête d'item : {it!r}"
        assert not _INLINE_MARKER.search(it), f"marqueur inline dans l'item : {it!r}"


# ── Cas réels — sujet de remédiation sandwidi_emrys ───────────────────────────

EXO_4 = (
    "Un instrument de mesure affiche la valeur 0,0307 mètre. "
    "(1) Écris cette valeur en lettres en précisant chaque rang. "
    "(2) Convertis cette valeur en millimètres (1 m = 1000 mm) et écris le résultat en lettres. "
    "(3) Un second instrument affiche 'zéro virgule zéro trois cent sept' — est-ce la même valeur ?\n"
    "1. Justifie en comparant les rangs décimaux."
)

EXO_8 = (
    "Deux élèves décomposent le nombre 73,906.\n"
    "1. Élève A écrit : partie entière = 73, partie décimale = 0,906.\n"
    "2. Élève B écrit : partie entière = 73, partie décimale = 906. "
    "(1) Laquelle des deux décompositions est correcte ?\n"
    "3. Justifie en vérifiant par addition. "
    "(2) Décompose toi-même le nombre 15,048 en partie entière et partie décimale. "
    "(3) Encadre la partie décimale entre deux fractions de dénominateur 1000."
)

EXO_15 = (
    "Dans un stade, trois tribunes contiennent respectivement 8 756, 5 489 et 3 675 spectateurs. "
    "(1) Calcule le nombre total de spectateurs en posant l'addition en colonnes "
    "avec toutes les retenues apparentes. "
    "(2) La capacité totale du stade est 19 000 places.\n"
    "1. Calcule le nombre de places vides. "
    "(3) Vérifie la cohérence de tes deux résultats par une addition finale."
)

EXO_22 = (
    "Un rectangle est divisé en 20 parties égales.\n"
    "1. On colorie 13 parties en bleu et 4 parties en rouge. "
    "(1) Quelle fraction du rectangle est bleue ? "
    "(2) Quelle fraction est rouge ? "
    "(3) Quelle fraction n'est ni bleue ni rouge ? "
    "(4) Vérifie que la somme des trois fractions vaut 1."
)

EXO_29 = (
    "Un article coûtait 4 500 F CFA.\n"
    "1. Son prix a augmenté à 5 400 F CFA. "
    "(1) Calcule l'augmentation en valeur absolue. "
    "(2) Calcule le taux d'augmentation en pourcentage (par rapport au prix initial). "
    "(3) Un second article a subi une augmentation de 12%.\n"
    "2. Son nouveau prix est 2 240 F CFA.\n"
    "3. Calcule son prix initial."
)


def test_exo4_deux_systemes_fusionnes_en_une_seule_liste():
    intro, tasks = _split_question(EXO_4)
    assert intro == "Un instrument de mesure affiche la valeur 0,0307 mètre."
    assert len(tasks) == 4
    assert tasks[0].startswith("Écris cette valeur en lettres")
    assert tasks[1].startswith("Convertis cette valeur en millimètres (1 m = 1000 mm)")
    assert tasks[2].startswith("Un second instrument affiche")
    assert tasks[3] == "Justifie en comparant les rangs décimaux."
    _assert_no_residual_numbering(intro, tasks)


def test_exo8_sequences_entrelacees_ordre_de_lecture():
    intro, tasks = _split_question(EXO_8)
    assert intro == "Deux élèves décomposent le nombre 73,906."
    assert [t.split()[0] for t in tasks] == [
        "Élève", "Élève", "Laquelle", "Justifie", "Décompose", "Encadre",
    ]
    _assert_no_residual_numbering(intro, tasks)


def test_exo15_marqueur_intercale():
    intro, tasks = _split_question(EXO_15)
    assert intro.startswith("Dans un stade")
    assert len(tasks) == 4
    assert tasks[1] == "La capacité totale du stade est 19 000 places."
    assert tasks[2] == "Calcule le nombre de places vides."
    _assert_no_residual_numbering(intro, tasks)


def test_exo22_liste_dans_une_tache():
    intro, tasks = _split_question(EXO_22)
    assert intro == "Un rectangle est divisé en 20 parties égales."
    assert len(tasks) == 5
    assert tasks[0].startswith("On colorie 13 parties")
    assert tasks[4].startswith("Vérifie que la somme")
    _assert_no_residual_numbering(intro, tasks)


def test_exo29_numero_final_reutilise():
    intro, tasks = _split_question(EXO_29)
    assert intro == "Un article coûtait 4 500 F CFA."
    assert len(tasks) == 6
    assert tasks[-1] == "Calcule son prix initial."
    assert tasks[3] == "Un second article a subi une augmentation de 12%."
    _assert_no_residual_numbering(intro, tasks)


# ── Format nominal du contrat de prompt (non-régression) ─────────────────────

def test_format_contractuel_contexte_puis_liste():
    text = (
        "On donne le nombre D = 58,307.\n"
        "1. Identifie et écris la partie entière de D.\n"
        "2. Identifie et écris la partie décimale de D.\n"
        "3. Vérifie ta décomposition en calculant la somme."
    )
    intro, tasks = _split_question(text)
    assert intro == "On donne le nombre D = 58,307."
    assert len(tasks) == 3
    _assert_no_residual_numbering(intro, tasks)


def test_liste_sans_contexte_enonce_vide():
    text = "1. Calcule 4 768 + 2 594.\n2. Vérifie par une estimation arrondie."
    intro, tasks = _split_question(text)
    assert intro == ""
    assert len(tasks) == 2


def test_style_inline_parentheses_pur():
    text = (
        "On considère P = 9,75 et Q = 0,309. (1) Décompose P et Q. "
        "(2) Calcule P + Q. (3) Décompose le résultat."
    )
    intro, tasks = _split_question(text)
    assert intro == "On considère P = 9,75 et Q = 0,309."
    assert len(tasks) == 3
    _assert_no_residual_numbering(intro, tasks)


# ── Fallback verbes d'action (texte sans aucun marqueur) ─────────────────────

def test_fallback_verbes_sans_marqueurs():
    text = (
        "Un père a 3 fois l'âge de son fils et la somme de leurs âges est 48 ans. "
        "Calculer l'âge de chacun. Vérifier le résultat."
    )
    intro, tasks = _split_question(text)
    assert intro.startswith("Un père")
    assert len(tasks) == 2
    assert tasks[0].startswith("Calculer")


# ── Gardes anti-faux-positifs ─────────────────────────────────────────────────

def test_reference_num_geo_non_decoupee():
    text = "Reprendre Num. 4a (5537 + 319). Faire poser l'addition en colonnes :\n1. écrire les deux nombres alignés à droite\n2. additionner colonne par colonne en notant chaque retenue\n3. vérifier le résultat par une estimation arrondie."
    intro, steps = split_numbered_items(text)
    assert "Num. 4a" in intro
    assert len(steps) == 3


def test_reference_exercice_apres_saut_de_ligne():
    text = "Voir l'exercice.\n2. n'est pas un début de liste ici."
    intro, items = split_numbered_items(text)
    assert items == []


def test_parenthese_mesure_non_marqueur():
    intro, items = split_numbered_items(
        "Convertis en millimètres (1 m = 1000 mm) puis en centimètres."
    )
    assert items == []


def test_annee_non_marqueur():
    intro, items = split_numbered_items(
        "La population était de 12 500 habitants en 2020. 15 000 habitants aujourd'hui."
    )
    assert items == []


def test_marqueur_isole_non_initial_ignore():
    intro, items = split_numbered_items(
        "Le reste du disque. (3) est une notation, pas une liste."
    )
    assert items == []


def test_marqueur_isole_initial_accepte():
    intro, items = split_numbered_items("Contexte du problème. 1. Fais ce calcul complet.")
    assert intro == "Contexte du problème."
    assert items == ["Fais ce calcul complet."]


# ── Rapport de correction : _action_html ──────────────────────────────────────

def test_action_html_liste_numerotee():
    html = str(_action_html(
        "Séquence en 3 temps :\n1. ancrage concret sur la métaphore financière\n"
        "2. dérivation de la règle abstraite avec l'élève\n"
        "3. exercices de confirmation en deux étapes séparées."
    ))
    assert html.count("<li>") == 3
    assert "Séquence en 3 temps" in html
    assert "1." not in re.sub(r"</?ol[^>]*>|</?li>|</?p>", "", html)


def test_action_html_numerotation_hybride():
    html = str(_action_html(
        "Reprendre la méthode : (1) poser le calcul ; (2) vérifier chaque retenue.\n"
        "1. Refaire avec 3 exemples."
    ))
    assert html.count("<li>") == 3
    assert "(1)" not in html and "(2)" not in html


def test_action_html_prose_sans_liste():
    html = str(_action_html(
        "Faire verbaliser l'élève sur un exemple concret avant d'abstraire la règle."
    ))
    assert "<li>" not in html


def test_paragraphs_liste_numerotee_rendue_en_ol():
    from src.pipeline.pdf_report_html import _paragraphs
    html = str(_paragraphs(
        "L'élève confond deux règles. Pour corriger :\n"
        "1. faire verbaliser la règle d'addition\n"
        "2. opposer un contre-exemple de multiplication."
    ))
    assert html.count("<li>") == 2
    assert "1." not in re.sub(r"</?ol[^>]*>|</?li>|</?p>", "", html)


# ── Titres de série élève (_series_title) ─────────────────────────────────────

# Les 8 libellés réels du document sandwidi_emrys (weaknesses du diagnostic)
SERIES_REELLES = {
    "Lecture précise des rangs décimaux au-delà des centièmes : confusion sur le rang "
    "des unités de mille-millièmes — Num. 2":
        "Lecture précise des rangs décimaux au-delà des centièmes",
    "Décomposition d'un nombre décimal en partie entière et partie décimale : réponse "
    "conceptuelle sans valeurs numériques — Num. 3a":
        "Décomposition d'un nombre décimal en partie entière et partie décimale",
    "Calcul posé d'une addition entière : erreur de retenue produisant 5 846 au lieu de "
    "5 856 — Num. 4a":
        "Calcul posé d'une addition entière",
    "Division décimale : résultat 73,63 au lieu de 72,87 — erreur dans la procédure de "
    "division posée — Num. 7":
        "Division décimale",
    "Identification d'une fraction d'une quantité : choix de la mauvaise option (7/16 au "
    "lieu de 9/16) — Num. 9":
        "Identification d'une fraction d'une quantité",
    "Calcul d'un pourcentage : formule inversée (30 × 6 / 100 au lieu de 6 / 30 × 100) — Num. 15":
        "Calcul d'un pourcentage",
    "Tracé d'une droite passant par deux points donnés : absence de réponse — Geo. 2":
        "Tracé d'une droite passant par deux points donnés",
    "Tracé d'un segment et placement de son milieu : absence de réponse — Geo. 4":
        "Tracé d'un segment et placement de son milieu",
}


def test_series_title_libelles_reels():
    from src.pipeline.pdf_remediation_html import _series_title
    for topic, attendu in SERIES_REELLES.items():
        assert _series_title(topic) == attendu


def test_series_title_jamais_de_vocabulaire_diagnostic():
    from src.pipeline.pdf_remediation_html import _series_title
    for topic in SERIES_REELLES:
        title = _series_title(topic)
        for interdit in ("au lieu de", "Num.", "Geo.", "Q_", "l'élève", "absence de réponse"):
            assert interdit not in title, f"{interdit!r} dans le titre {title!r}"


def test_series_title_id_brut_et_sans_deux_points():
    from src.pipeline.pdf_remediation_html import _series_title
    assert _series_title(
        "Règle d'inversion du sens dans les inéquations non acquise — Q_NUM_11"
    ) == "Règle d'inversion du sens dans les inéquations non acquise"


def test_series_title_libelle_court_inchange():
    from src.pipeline.pdf_remediation_html import _series_title
    assert _series_title("Division décimale") == "Division décimale"


# ── Sujet T1 du 2026-10-17 : listes de valeurs mal numérotées ────────────────

def test_liste_de_valeurs_numerotation_collee():
    intro, items = _split_question(
        "Pour chacun des nombres suivants, indique le plus petit ensemble.\n1. -7 2. 9/4\n2. sqrt(25)"
    )
    assert intro == "Pour chacun des nombres suivants, indique le plus petit ensemble."
    assert items == ["-7", "9/4", "sqrt(25)"]


def test_liste_de_valeurs_apres_fin_de_phrase():
    intro, items = _split_question(
        "Indique l'ensemble, en justifiant si nécessaire. 1. 5/8 2. 7/12\n1. sqrt(11)\n2. -3"
    )
    assert intro == "Indique l'ensemble, en justifiant si nécessaire."
    assert items == ["5/8", "7/12", "sqrt(11)", "-3"]


def test_nombre_nu_apres_point_et_operateur_ne_sont_pas_des_marqueurs():
    assert _split_question("Calcule A = 3. 5 élèves sont là.")[1] == []
    _, items = _split_question("On donne x = 2.\n1. Calcule 3x + 2. 5 est-il solution ?\n2. Conclus.")
    assert items == ["Calcule 3x + 2. 5 est-il solution ?", "Conclus."]


def test_series_title_sans_type_d_erreur():
    from src.pipeline.pdf_remediation_html import _series_title
    assert _series_title("Vecteurs : egalite et somme × Connaissance non disponible") == "Vecteurs"
    assert _series_title("Pourcentages × Connaissance non disponible") == "Pourcentages"


def test_coordonnees_entre_parentheses_ne_sont_pas_des_marqueurs():
    intro, items = _split_question(
        "On considère les points P(-3 ; 1) et Q(2 ; -4). Un point R a pour image S(-1 ; 2)."
        "\n1. Détermine les coordonnées du point R."
    )
    assert intro == "On considère les points P(-3 ; 1) et Q(2 ; -4). Un point R a pour image S(-1 ; 2)."
    assert items == ["Détermine les coordonnées du point R."]
