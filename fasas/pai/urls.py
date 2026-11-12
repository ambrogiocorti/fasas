from django.urls import path

from . import views

app_name = "pai"

urlpatterns = [
    path("ospite/<int:guest_pk>/", views.guest_pai, name="guest"),
    path("ospite/<int:guest_pk>/nuovo/", views.pai_create, name="create"),
    path("<int:pk>/", views.pai_detail, name="detail"),
    path("<int:pk>/modifica/", views.pai_edit, name="edit"),
    path("<int:pk>/obiettivo/", views.goal_edit, name="goal_create"),
    path("<int:pk>/obiettivo/<int:goal_pk>/", views.goal_edit, name="goal_edit"),
    path("<int:pk>/obiettivo/<int:goal_pk>/rimuovi/", views.goal_delete, name="goal_delete"),
    path("<int:pk>/obiettivo/<int:goal_pk>/verifica/", views.goal_verify, name="goal_verify"),
    path("<int:pk>/revisione/", views.pai_revise, name="revise"),
    path("<int:pk>/approva/", views.pai_activate, name="activate"),
    path("<int:pk>/pdf/", views.pai_pdf, name="pdf"),
]
