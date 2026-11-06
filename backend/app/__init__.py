"""Racine du package `app` — bootstrap du path vers `src/` et la racine du
dépôt, fait une seule fois ici (avant tout sous-module) plutôt que dans
`app.db` : un service importé sans passer par `app.db` en premier (ex.
`app.services.contexte`, qui importe directement `src.knowledge...`) échouait
sinon selon l'ordre d'import.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _faire_confiance_au_magasin_du_systeme() -> None:
    """Port de `manage.py::_faire_confiance_au_magasin_du_systeme` — même
    piège, même remède : un antivirus qui inspecte le HTTPS (Avast,
    Kaspersky, ESET…) fait échouer tout appel Google Sheets/LLM sur
    `CERTIFICATE_VERIFY_FAILED` parce que `certifi` (utilisé par `requests`,
    donc par `google-auth`/`gspread` et les SDK LLM) ignore la racine ajoutée
    par l'antivirus dans le magasin Windows. Facultatif à dessein : sans le
    paquet `truststore`, comportement d'origine, pas d'échec au démarrage."""
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()


_faire_confiance_au_magasin_du_systeme()
