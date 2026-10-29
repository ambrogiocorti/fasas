from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.utils import timezone

from fasas.audit.models import AppendOnlyQuerySet, ImmutableRecordError


class Role(models.TextChoices):
    ADMIN = "admin", "Amministratore"
    COORDINATOR = "coordinator", "Coordinatore sanitario"
    OPERATOR = "operator", "Operatore"
    DOCTOR = "doctor", "Medico"
    ADMINISTRATIVE = "administrative", "Amministrativo"


class User(AbstractUser):
    class Theme(models.TextChoices):
        AUTO = "auto", "Automatico (scuro di notte)"
        LIGHT = "light", "Chiaro"
        DARK = "dark", "Scuro"

    role = models.CharField("ruolo", max_length=20, choices=Role.choices, default=Role.OPERATOR)
    community = models.ForeignKey(
        "core.Community", verbose_name="comunità", on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
    fiscal_code = models.CharField("codice fiscale", max_length=16, blank=True)
    phone = models.CharField("telefono", max_length=50, blank=True)
    qualification = models.CharField("qualifica", max_length=100, blank=True, help_text="Es. OSS, Educatore, Infermiere")
    professional_register = models.CharField(
        "iscrizione albo/ordine", max_length=100, blank=True, help_text="Obbligatorio per i medici che firmano"
    )
    theme = models.CharField("tema interfaccia", max_length=10, choices=Theme.choices, default=Theme.AUTO)

    class Meta:
        verbose_name = "utente"
        verbose_name_plural = "utenti"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_role_group()

    def sync_role_group(self):
        role_groups = Group.objects.filter(name__in=Role.labels)
        wanted = Group.objects.filter(name=self.get_role_display()).first()
        current = set(self.groups.filter(pk__in=role_groups).values_list("pk", flat=True))
        if wanted is not None and current == {wanted.pk}:
            return
        self.groups.remove(*role_groups)
        if wanted is not None:
            self.groups.add(wanted)
        self.clear_permission_cache()

    def clear_permission_cache(self):
        for attr in ("_fasas_perm_cache", "_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.__dict__.pop(attr, None)

    @property
    def is_admin(self):
        return self.is_superuser or self.role == Role.ADMIN

    @property
    def is_coordinator(self):
        return self.role == Role.COORDINATOR

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR


class UserPermissionOverride(models.Model):
    """Permesso granulare: concede o nega a un singolo utente un permesso rispetto al suo ruolo."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permission_overrides")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")
    allow = models.BooleanField("concesso", help_text="Se disattivo il permesso viene negato anche se previsto dal ruolo")

    class Meta:
        verbose_name = "permesso personalizzato"
        verbose_name_plural = "permessi personalizzati"
        constraints = [models.UniqueConstraint(fields=["user", "permission"], name="unique_user_permission_override")]

    def __str__(self):
        return f"{self.user} {'+' if self.allow else '−'} {self.permission.codename}"


class AccessLog(models.Model):
    """Log accessi (sezione 20). Come l'audit log è in sola aggiunta."""

    class Event(models.TextChoices):
        LOGIN = "login", "Accesso"
        LOGOUT = "logout", "Uscita"
        FAILED = "failed", "Accesso fallito"
        LOCKED = "locked", "Accesso bloccato"
        TIMEOUT = "timeout", "Sessione scaduta"

    timestamp = models.DateTimeField("data e ora", default=timezone.now, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="access_logs")
    username = models.CharField("nome utente", max_length=150, db_index=True)
    event = models.CharField("evento", max_length=10, choices=Event.choices)
    ip_address = models.CharField("IP", max_length=64, blank=True)
    user_agent = models.TextField("user agent", blank=True)
    device = models.CharField("dispositivo", max_length=120, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = "accesso"
        verbose_name_plural = "log accessi"
        ordering = ["-timestamp"]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.timestamp:%d/%m/%Y %H:%M} {self.username} {self.get_event_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableRecordError("Il log accessi non può essere modificato.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("Il log accessi non può essere cancellato.")
