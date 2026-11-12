from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("segnala/", views.create, name="create"),
    path("segnalazioni/", views.feedback_list, name="list"),
    path("segnalazioni/<int:pk>/", views.handle, name="handle"),
    path("indicatori/", views.metrics_view, name="metrics"),
]
