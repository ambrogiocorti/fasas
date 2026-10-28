from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("ospiti", views.GuestViewSet, basename="guest")
router.register("terapie", views.TherapyViewSet, basename="therapy")
router.register("somministrazioni", views.AdministrationViewSet, basename="administration")
router.register("parametri", views.ParameterViewSet, basename="parameter")
router.register("eventi", views.EventViewSet, basename="event")
router.register("diario", views.DiaryViewSet, basename="diary")
router.register("evacuazioni", views.EvacuationViewSet, basename="evacuation")
router.register("notifiche", views.NotificationViewSet, basename="notification")

app_name = "api"

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/turno-corrente/", views.current_shift, name="current_shift"),
    path("v1/token/", views.TokenView.as_view(), name="token"),
]
