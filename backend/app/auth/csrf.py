"""Protection CSRF — équivalent de `CsrfViewMiddleware` (Django), absent par
défaut dans une API FastAPI pure.

Le frontend est une SPA avec cookie de session `httponly` (`app/auth/deps.py`
— le navigateur l'envoie automatiquement, une page malveillante ne peut pas
le lire mais peut quand même déclencher une requête qui l'utilise). Motif
retenu, le plus courant pour ce cas : **double-submit cookie**. Un second
cookie, **lisible en JS** (donc pas `httponly`), posé en même temps que le
cookie de session ; le frontend le recopie dans un en-tête à chaque requête
mutante ; le serveur vérifie que cookie et en-tête concordent. Une page tierce
peut faire envoyer le cookie de session par le navigateur, mais ne peut ni le
lire ni lire le cookie CSRF pour recopier sa valeur dans l'en-tête (règle du
même-origine) — donc ne peut pas produire de requête valide.

Aucun état côté serveur nécessaire : contrairement au jeton de session, le
jeton CSRF n'est pas cherché en base, seule l'égalité cookie == en-tête compte.
"""
from __future__ import annotations

import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE_CSRF = "csrf_token"
HEADER_CSRF = "x-csrf-token"

#: Méthodes qui modifient l'état — les seules vérifiées, comme Django.
_METHODES_PROTEGEES = {"POST", "PUT", "PATCH", "DELETE"}


def _acces_libre() -> bool:
    """Import différé : `app.auth.deps` importe ce module (fonctions,
    au moment de l'appel) pour poser le cookie CSRF — un import au niveau
    module créerait un cycle. `acces_libre()` court-circuite déjà
    `connexion_requise`/`admin_requis` (`comptes/session.py` côté Django) ;
    sans aucune connexion, aucun cookie CSRF n'est jamais posé, donc le
    vérifier bloquerait toute action en développement sans Sheets."""
    from app.auth.deps import acces_libre

    return acces_libre()

#: Chemins exemptés : pas encore de session au moment de l'appel, donc pas
#: encore de cookie CSRF à recopier.
_CHEMINS_EXEMPTES = {"/api/auth/login"}


def generer_jeton_csrf() -> str:
    return secrets.token_urlsafe(32)


def poser_cookie_csrf(response: Response, jeton: str, *, secure: bool) -> None:
    """Cookie **non** httpOnly, délibérément : le frontend doit pouvoir le
    lire pour le recopier en en-tête (`document.cookie`)."""
    response.set_cookie(COOKIE_CSRF, jeton, httponly=False, samesite="lax", secure=secure)


class CSRFMiddleware:
    """Middleware ASGI pur (pas `BaseHTTPMiddleware`, pour éviter de
    bufferiser les corps de requête volumineux — un dépôt de copie peut
    porter plusieurs Mo de PDF) : ne lit que méthode, chemin, cookies et
    en-têtes, jamais le corps."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if request.method in _METHODES_PROTEGEES and request.url.path not in _CHEMINS_EXEMPTES and not _acces_libre():
            cookie = request.cookies.get(COOKIE_CSRF)
            entete = request.headers.get(HEADER_CSRF)
            if not cookie or not entete or not secrets.compare_digest(cookie, entete):
                reponse = JSONResponse({"detail": "Jeton CSRF manquant ou invalide."}, status_code=403)
                await reponse(scope, receive, send)
                return

        await self.app(scope, receive, send)
