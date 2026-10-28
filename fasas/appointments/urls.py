from django.urls import path

from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.appointment_list, name="list"),
    path("nuovo/", views.AppointmentCreateView.as_view(), name="create"),
    path("<int:pk>/", views.AppointmentDetailView.as_view(), name="detail"),
    path("<int:pk>/modifica/", views.AppointmentUpdateView.as_view(), name="update"),
    path("<int:pk>/esito/", views.appointment_outcome, name="outcome"),
    path("ospite/<int:guest_pk>/", views.guest_appointments, name="guest_list"),
]
