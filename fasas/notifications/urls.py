from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("conteggio/", views.unread_count, name="count"),
    path("<int:pk>/letta/", views.mark_read, name="mark_read"),
    path("tutte-lette/", views.mark_all_read, name="mark_all_read"),
    path("impostazioni/", views.notification_settings, name="settings"),
]
