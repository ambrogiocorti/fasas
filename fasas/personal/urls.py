from django.urls import path

from . import views

app_name = "personal"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("ospite/<int:guest_pk>/", views.guest_view, name="guest"),
    path("ospite/<int:guest_pk>/movimento/", views.movement_create, name="movement"),
    path("ospite/<int:guest_pk>/rendiconto/", views.statement, name="statement"),
    path("ospite/<int:guest_pk>/oggetto/", views.item_create, name="item"),
    path("movimento/<int:pk>/annulla/", views.movement_void, name="movement_void"),
    path("movimento/<int:pk>/scontrino/", views.receipt, name="receipt"),
    path("oggetto/<int:pk>/", views.item_update, name="item_update"),
]
