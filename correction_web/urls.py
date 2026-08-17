from django.urls import path

from correction_web import views

app_name = "correction_web"

urlpatterns = [
    path("a-propos/", views.a_propos, name="a_propos"),
    path("corrections/", views.liste, name="liste"),
    path("corrections/nouvelle/", views.nouvelle, name="nouvelle"),
    path("corrections/lot/", views.lot, name="lot"),
    path(
        "corrections/confirmation/<str:jeton_session>/",
        views.soumettre_confirmation,
        name="soumettre_confirmation",
    ),
    path("sujets/", views.sujets, name="sujets"),
    path("sujets/<str:bareme_id>/", views.sujet, name="sujet"),
    path("sujets/<str:bareme_id>/corrige/", views.corrige, name="corrige"),
    path("corrections/<str:jeton>/", views.suivre, name="suivre"),
    path("corrections/<str:jeton>/transcription/", views.valider_transcription, name="valider_transcription"),
    path("corrections/<str:jeton>/page/<int:page_number>/image/", views.page_image, name="page_image"),
    path("corrections/<str:jeton>/notes/", views.valider_notes, name="valider_notes"),
    path("corrections/<str:jeton>/supprimer/", views.supprimer, name="supprimer"),
]
