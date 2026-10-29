"""
Menu laterale costruito dai permessi dell'utente: ogni ruolo vede solo le funzioni che può usare
(spec. §2 e §26). Le sezioni senza voci visibili non vengono mostrate.
"""
from dataclasses import dataclass, field

from django.urls import reverse

DASHBOARD_LABELS = {
    "operator": "Il mio turno",
    "coordinator": "Coordinamento",
    "doctor": "Area medica",
    "admin": "Pannello di sistema",
    "administrative": "Amministrazione",
}


@dataclass
class Item:
    label: str
    icon: str
    url_name: str
    perm: str | tuple | None = None  # con una tupla basta uno dei permessi
    active: tuple = ()          # nomi di URL (namespace:nome) che rendono attiva la voce
    namespace: str | None = None  # oppure un intero namespace
    count: str | None = None    # chiave del contatore da mostrare


@dataclass
class Section:
    title: str | None
    items: list = field(default_factory=list)


MENU = [
    Section(None, [
        Item("Cruscotto", "dashboard", "core:dashboard", active=("core:dashboard",)),
        Item("Ospiti", "user", "guests:list", "guests.view_guest", namespace="guests"),
    ]),
    Section("Turno", [
        Item("Giro farmaci", "pill", "clinical:board", "clinical.add_therapyadministration", active=("clinical:board",)),
        Item("Checklist turno", "clipboard-check", "daily:checklist", "daily.view_checklistcheck", active=("daily:checklist",)),
        Item("Registro giornaliero", "book", "daily:register", "daily.view_dailyrecord", active=("daily:register",)),
        Item("Evacuazioni", "timer", "daily:evacuations", "daily.view_evacuationrecord", active=("daily:evacuations",)),
        Item("Chiusura turni", "lock", "daily:closures", "daily.view_shiftclosure",
             active=("daily:closures", "daily:close_shift", "daily:closure_detail")),
        Item("Senza rete", "wifi-off", "offline:records", "offline.use_offline", active=("offline:records",)),
        Item("Registro turni", "user-check", "daily:roster", "daily.view_shiftassignment", active=("daily:roster",)),
    ]),
    Section("Personale", [
        Item("Calendario turni", "calendar-days", "staffing:rota", "staffing.view_rotamonth",
             active=("staffing:rota", "staffing:settings")),
        Item("I miei turni", "calendar-check", "staffing:my", "staffing.add_leaverequest", active=("staffing:my",)),
        Item("Ferie e cambi turno", "check-circle", "staffing:requests", "staffing.change_leaverequest",
             active=("staffing:requests",), count="rota_requests"),
    ]),
    Section("Clinica", [
        Item("Terapie in corso", "pill", "clinical:therapy_overview", "clinical.add_therapy",
             active=("clinical:therapy_overview",)),
        Item("SOS da validare", "shield-check", "clinical:sos_pending", "clinical.validate_sos",
             active=("clinical:sos_pending",), count="sos"),
        Item("Documenti da firmare", "pen", "documents:to_sign", ("signatures.sign_document", "signatures.sign_with_cie"),
             active=("documents:to_sign", "documents:sign", "documents:sign_cie", "signatures:cie_request")),
        Item("Protocolli attivi", "flag", "protocols:activations", "protocols.view_protocolactivation",
             active=("protocols:activations", "protocols:activation_detail"), count="protocols"),
    ]),
    Section("Struttura", [
        Item("Appuntamenti", "calendar", "appointments:list", "appointments.view_appointment", namespace="appointments"),
        Item("Magazzino farmaci", "package", "pharmacy:stock", "pharmacy.view_stocklot", namespace="pharmacy"),
        Item("Report", "file-text", "reports:list", "reports.view_generatedreport", namespace="reports"),
        Item("Ricerca avanzata", "search", "search:search", "guests.view_guest", namespace="search"),
        Item("Importa dal cartaceo", "upload", "imports:home", "imports.add_importbatch", namespace="imports"),
    ]),
    Section("Amministrazione", [
        Item("Presenze", "calendar-days", "billing:attendance", "billing.view_attendancemonth",
             active=("billing:attendance", "billing:correction")),
        Item("Rette", "wallet", "billing:fees", "billing.view_guestfeeline",
             active=("billing:fees", "billing:fee_create", "billing:fee_update", "billing:settings")),
        Item("Prospetti e incassi", "receipt", "billing:statements", "billing.view_feestatement",
             active=("billing:statements", "billing:statement")),
    ]),
    Section("Sistema", [
        Item("Utenti e permessi", "users", "accounts:user_list", "accounts.view_user",
             active=("accounts:user_list", "accounts:user_update", "accounts:user_permissions",
                     "accounts:user_create", "accounts:user_set_password")),
        Item("Configurazione", "sliders", "core:config", "core.change_systemconfig", active=("core:config",)),
        Item("Protocolli automatici", "flag", "protocols:list", "protocols.view_protocol",
             active=("protocols:list", "protocols:create", "protocols:update")),
        Item("Impostazioni notifiche", "bell", "notifications:settings", "notifications.change_notificationsetting",
             active=("notifications:settings",)),
        Item("Report programmati", "calendar-check", "reports:schedule_list", "reports.change_reportschedule",
             active=("reports:schedule_list", "reports:schedule_create", "reports:schedule_update")),
        Item("Audit log", "shield", "audit:list", "audit.view_auditlog", namespace="audit"),
        Item("Log accessi", "key", "accounts:access_log", "accounts.view_accesslog", active=("accounts:access_log",)),
        Item("Backup", "database", "backups:list", "backups.manage_backup", namespace="backups"),
        Item("Dispositivi di firma", "id-card", "signatures:devices", "signatures.manage_signer_devices",
             active=("signatures:devices",)),
    ]),
    Section(None, [
        Item("Notifiche", "bell", "notifications:list", active=("notifications:list",), count="notifications"),
        Item("Impostazioni", "sliders", "core:settings", active=("core:settings", "accounts:profile",
                                                              "accounts:password_change", "signatures:credential")),
    ]),
]


def role_of(user):
    return "admin" if user.is_superuser else user.role


def counts_for(user, unread):
    from fasas.clinical.models import TherapyAdministration
    from fasas.protocols.models import ProtocolActivation

    counts = {"notifications": unread}
    if user.has_perm("clinical.validate_sos"):
        counts["sos"] = TherapyAdministration.objects.filter(
            is_sos=True, validation_status=TherapyAdministration.Validation.PENDING).count()
    if user.has_perm("protocols.view_protocolactivation"):
        counts["protocols"] = ProtocolActivation.objects.filter(status__in=ProtocolActivation.OPEN_STATES).count()
    if user.has_perm("staffing.change_leaverequest"):
        from fasas.staffing.views import pending_requests_count

        counts["rota_requests"] = pending_requests_count()
    return counts


def build_menu(request, unread=0):
    user = request.user
    match = request.resolver_match
    current = f"{match.namespace}:{match.url_name}" if match else ""
    namespace = match.namespace if match else ""
    counts = counts_for(user, unread)
    sections = []
    for section in MENU:
        items = []
        for item in section.items:
            perms = (item.perm,) if isinstance(item.perm, str) else (item.perm or ())
            if perms and not any(user.has_perm(p) for p in perms):
                continue
            label = DASHBOARD_LABELS.get(role_of(user), item.label) if item.url_name == "core:dashboard" else item.label
            items.append({
                "label": label, "icon": item.icon, "url": reverse(item.url_name),
                "active": current in item.active or (item.namespace is not None and namespace == item.namespace),
                "count": counts.get(item.count) if item.count else None,
            })
        if items:
            sections.append({"title": section.title, "items": items})
    return sections
