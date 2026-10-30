from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("accesso/entra/", views.LoginView.as_view(), name="login"),
    path("accesso/esci/", views.LogoutView.as_view(), name="logout"),
    path("accesso/verifica/", views.otp_verify, name="otp_verify"),
    path("accesso/attiva-verifica/", views.otp_setup, name="otp_setup"),
    path("profilo/sicurezza/", views.security, name="security"),
    path("profilo/", views.ProfileView.as_view(), name="profile"),
    path("profilo/tema/", views.set_theme, name="set_theme"),
    path("profilo/password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("utenti/", views.UserListView.as_view(), name="user_list"),
    path("utenti/nuovo/", views.UserCreateView.as_view(), name="user_create"),
    path("utenti/<int:pk>/", views.UserUpdateView.as_view(), name="user_update"),
    path("utenti/<int:pk>/password/", views.user_set_password, name="user_set_password"),
    path("utenti/<int:pk>/permessi/", views.user_permissions, name="user_permissions"),
    path("utenti/<int:pk>/verifica/", views.user_reset_2fa, name="user_reset_2fa"),
    path("log-accessi/", views.AccessLogListView.as_view(), name="access_log"),
]
