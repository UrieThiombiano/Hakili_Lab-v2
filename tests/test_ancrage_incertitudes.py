"""Rattachement des doutes de transcription au texte (`⟦…⟧`) — src/pipeline/ancrage_incertitudes.py."""

from src.models.domain import PageTranscription, TranscriptionResult
from src.pipeline.ancrage_incertitudes import ancrer_contenu, ancrer_incertitudes


def test_fragment_maths_sans_guillemets_espaces_differents():
    # Cas réel (copie SOUBEIGA, page 2) : le modèle cite sans guillemets,
    # sans espaces, en anglais — et n'a posé aucun marqueur dans content.
    content = "L2 F = 9x² - 5²\nF = (3x - 5)(3x + 5)\nL3 7x - 4x = 9 + 3"
    doute = (
        "The student wrote (9x-5)(9x+5) in the image, but the formula is 9x²-25. "
        "Re-reading the image: it is (3x-5)(3x+5)."
    )
    assert ancrer_contenu(content, [doute]) == (
        "L2 F = 9x² - 5²\nF = ⟦(3x - 5)(3x + 5)⟧\nL3 7x - 4x = 9 + 3"
    )


def test_passage_entre_guillemets():
    content = "MN = AC − BA / MN − BM\nDonc MN = 4"
    doute = '"MN = AC - BA / MN - BM" : ligne confuse, recopie de Thalès'
    assert ancrer_contenu(content, [doute]) == "⟦MN = AC − BA / MN − BM⟧\nDonc MN = 4"


def test_doute_sans_passage_reste_au_bandeau():
    content = "800x + 15 000 ≤ 38 000"
    doute = "Le symbole de comparaison est ambigu, ressemble à un 7 barré."
    assert ancrer_contenu(content, [doute]) == content


def test_token_court_non_ancre():
    content = "AB = 25\nAC = 25"
    assert ancrer_contenu(content, ['"25" : lu 25 ou 26']) == content


def test_marqueur_existant_non_double():
    content = "x = ⟦(3x - 5)⟧ + 1"
    assert ancrer_contenu(content, ['"(3x - 5)" : 3 ou 9']) == content


def test_ancrer_incertitudes_toutes_les_pages():
    t = TranscriptionResult(
        copy_id="c",
        global_quality="good",
        pages=[
            PageTranscription(page_number=1, content="a = 2(x+1)", uncertainties=['"2(x+1)" : 2 ou Z'], confidence=0.9),
            PageTranscription(page_number=2, content="b = 3", confidence=1.0),
        ],
    )
    out = ancrer_incertitudes(t)
    assert out.pages[0].content == "a = ⟦2(x+1)⟧"
    assert out.pages[1].content == "b = 3"
