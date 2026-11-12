from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("conteggio/", views.unread_count, name="count"),
    path("<int:pk>/letta/", views.mark_read, name="mark_read"),
    path("tutte-lette/", views.mark_all_read, name="mark_all_read"),
    path("impostazioni/", views.notification_settings, name="settings"),
    path("<int:pk>/apri/", views.open_notification, name="open"),
    path("dispositivi/", views.devices, name="devices"),
    path("push/iscrivi/", views.push_subscribe, name="push_subscribe"),
    path("push/annulla/", views.push_unsubscribe, name="push_unsubscribe"),
    path("push/prova/", views.push_test, name="push_test"),
]
