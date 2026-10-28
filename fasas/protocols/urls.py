from django.urls import path

from . import views

app_name = "protocols"

urlpatterns = [
    path("", views.activation_list, name="activations"),
    path("attivazione/<int:pk>/", views.activation_detail, name="activation_detail"),
    path("attivazione/<int:pk>/azione/", views.action_done, name="action_done"),
    path("attivazione/<int:pk>/chiudi/", views.activation_resolve, name="activation_resolve"),
    path("regole/", views.ProtocolListView.as_view(), name="list"),
    path("regole/nuova/", views.ProtocolCreateView.as_view(), name="create"),
    path("regole/<int:pk>/", views.ProtocolUpdateView.as_view(), name="update"),
]
