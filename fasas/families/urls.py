from django.urls import path

from . import views

app_name = "families"

urlpatterns = [
    path("", views.home, name="home"),
    path("<int:pk>/", views.guest_view, name="guest"),
    path("<int:pk>/documento/<int:share_pk>/", views.document_view, name="document"),
    path("<int:pk>/cassa/", views.cash_statement, name="cash"),
    path("<int:pk>/visita/<int:visit_pk>/annulla/", views.visit_cancel, name="visit_cancel"),
    path("gestione/", views.staff_home, name="staff_home"),
    path("gestione/ospite/<int:guest_pk>/", views.staff_guest, name="staff_guest"),
    path("gestione/collegamento/<int:pk>/", views.staff_link, name="staff_link"),
    path("gestione/collegamento/nuovo/", views.link_edit, name="link_create"),
    path("gestione/collegamento/<int:pk>/modifica/", views.link_edit, name="link_update"),
    path("gestione/collegamento/<int:pk>/revoca/", views.link_revoke, name="link_revoke"),
    path("gestione/visita/<int:pk>/decidi/", views.visit_decide, name="visit_decide"),
    path("gestione/condivisione/<int:pk>/revoca/", views.unshare, name="unshare"),
]
