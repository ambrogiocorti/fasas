from django.urls import path

from . import views

app_name = "wounds"

urlpatterns = [
    path("ospite/<int:guest_pk>/", views.guest_wounds, name="guest"),
    path("ospite/<int:guest_pk>/nuova/", views.wound_create, name="create"),
    path("<int:pk>/", views.wound_detail, name="detail"),
    path("<int:pk>/rilevazione/", views.check_create, name="check"),
    path("<int:pk>/piano/", views.plan_create, name="plan"),
    path("<int:pk>/medicazione/", views.dressing_create, name="dressing"),
    path("<int:pk>/medicazione/fatta/", views.dressing_quick, name="dressing_quick"),
    path("<int:pk>/chiudi/", views.wound_close, name="close"),
    path("<int:pk>/annulla/", views.WoundVoidView.as_view(), name="void"),
    path("rilevazione/<int:pk>/annulla/", views.WoundCheckVoidView.as_view(), name="check_void"),
    path("medicazione/<int:pk>/annulla/", views.DressingVoidView.as_view(), name="dressing_void"),
    path("da-fare/", views.due_overview, name="due"),
]
