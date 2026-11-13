"""
Menu laterale costruito dai permessi dell'utente: ogni ruolo vede solo le funzioni che può usare
(spec. §2 e §26). Le sezioni senza voci visibili non vengono mostrate.
"""
from dataclasses import dataclass, field

from django.urls import reverse

from .modules import states

DASHBOARD_LABELS = {
    "operator": "Il mio turno",
    "coordinator": "Coordinamento",
    "doctor": "Area medica",
    "admin": "Gestione del sistema",
    "administrative": "Ufficio amministrativo",
    "family": "I miei cari",
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
    module: str | None = None   # modulo accendibile (fasas.core.modules): spento = voce nascosta
    exclude_roles: tuple = ()   # ruoli a cui la voce non si mostra (es. il familiare)


@dataclass
class Section:
    """Gruppo del menu. Con un titolo diventa una tendina (aperta se contiene la pagina corrente); senza titolo
    le voci restano sempre visibili. Una tendina con una sola voce visibile per l'utente si mostra come voce semplice."""
    title: str | None
    items: list = field(default_factory=list)
    icon: str = "menu"
    key: str = ""


# Raggruppato per ciò che si sta facendo: l'assistenza agli ospiti, il turno, ciò che aspetta un controllo,
# la clinica, il personale, l'archivio, l'amministrazione e il sistema.
MENU = [
    Section(None, [
        Item("Cruscotto", "dashboard", "core:dashboard", active=("core:dashboard",), exclude_roles=("family",)),
        Item("I miei cari", "heart", "families:home", "families.use_family_area", namespace="families",
             module="families"),
        Item("Ospiti", "user", "guests:list", "guests.view_guest", namespace="guests"),
    ]),
    Section("Assistenza", [
        Item("Giro farmaci", "pill", "clinical:board", "clinical.add_therapyadministration", active=("clinical:board",)),
        Item("Evacuazioni", "timer", "daily:evacuations", "daily.view_evacuationrecord", active=("daily:evacuations",)),
        Item("Attività del turno", "clock", "care:due", "care.view_caretaskcheck",
             active=("care:due", "care:check"), count="care_late", module="care"),
        Item("Medicazioni da fare", "heart", "wounds:due", "wounds.add_dressing", active=("wounds:due",),
             module="wounds"),
        Item("Valutazioni da fare", "clipboard-check", "assessments:due", "assessments.add_assessment",
             active=("assessments:due", "assessments:settings"), module="assessments"),
    ], icon="heart", key="assistenza"),
    Section("Turno", [
        Item("Checklist turno", "clipboard-check", "daily:checklist", "daily.view_checklistcheck", active=("daily:checklist",)),
        Item("Registro giornaliero", "book", "daily:register", "daily.view_dailyrecord", active=("daily:register",)),
        Item("Chiusura turni", "lock", "daily:closures", "daily.view_shiftclosure",
             active=("daily:closures", "daily:close_shift", "daily:closure_detail")),
        Item("Registro turni", "user-check", "daily:roster", "daily.view_shiftassignment", active=("daily:roster",)),
        Item("Senza rete", "wifi-off", "offline:records", "offline.use_offline", active=("offline:records",)),
    ], icon="clipboard-check", key="turno"),
    Section("Da controllare", [
        Item("SOS da validare", "shield-check", "clinical:sos_pending", "clinical.validate_sos",
             active=("clinical:sos_pending",), count="sos"),
        Item("Documenti da firmare", "pen", "documents:to_sign", ("signatures.sign_document", "signatures.sign_with_cie"),
             active=("documents:to_sign", "documents:sign", "documents:sign_cie", "signatures:cie_request")),
        Item("Protocolli attivi", "flag", "protocols:activations", "protocols.view_protocolactivation",
             active=("protocols:activations", "protocols:activation_detail"), count="protocols", module="protocols"),
        Item("Familiari", "users", "families:staff_home", "families.manage_family_area",
             active=("families:staff_home", "families:staff_guest", "families:staff_link", "families:link_create",
                     "families:link_update", "families:link_revoke"), count="families", module="families"),
        Item("Segnalazioni", "message", "feedback:list", "feedback.view_feedback", active=("feedback:list",),
             count="feedback", module="feedback"),
    ], icon="shield-check", key="controlli"),
    Section("Clinica", [
        Item("Terapie in corso", "pill", "clinical:therapy_overview", "clinical.add_therapy",
             active=("clinical:therapy_overview",)),
        Item("Appuntamenti", "calendar", "appointments:list", "appointments.view_appointment", namespace="appointments",
             module="appointments"),
        Item("Magazzino farmaci", "package", "pharmacy:stock", "pharmacy.view_stocklot",
             active=("pharmacy:stock", "pharmacy:lot_load", "pharmacy:lot_detail"), module="stock"),
    ], icon="pill", key="clinica"),
    Section("Personale", [
        Item("Calendario turni", "calendar-days", "staffing:rota", "staffing.view_rotamonth",
             active=("staffing:rota", "staffing:settings"), module="staffing"),
        Item("I miei turni", "calendar-check", "staffing:my", "staffing.add_leaverequest", active=("staffing:my",),
             module="staffing"),
        Item("Ferie e cambi turno", "check-circle", "staffing:requests", "staffing.change_leaverequest",
             active=("staffing:requests",), count="rota_requests", module="staffing"),
        Item("Scadenze del personale", "id-card", "staffing:credentials", "staffing.view_staffcredential",
             active=("staffing:credentials", "staffing:credential_create", "staffing:credential_user",
                     "staffing:credential_types", "staffing:credential_type_create", "staffing:credential_type_update"),
             count="staff_deadlines", module="staffing"),
    ], icon="users", key="personale"),
    Section("Archivio e report", [
        Item("Report", "file-text", "reports:list", "reports.view_generatedreport",
             active=("reports:list", "reports:download", "reports:guest_export"), module="reports"),
        Item("Pacchetto per l'ispezione", "clipboard", "reports:inspection", "reports.add_generatedreport",
             active=("reports:inspection",), module="reports"),
        Item("Indicatori di qualità", "activity", "reports:quality", "reports.view_quality_indicators",
             active=("reports:quality",), module="reports"),
        Item("Indicatori del pilota", "chart", "feedback:metrics", "feedback.view_pilot_metrics",
             active=("feedback:metrics",), module="feedback"),
        Item("Ricerca avanzata", "search", "search:search", "guests.view_guest", namespace="search"),
        Item("Importa dal cartaceo", "upload", "imports:home", "imports.add_importbatch", namespace="imports",
             module="imports"),
    ], icon="file-text", key="archivio"),
    Section("Rette, cassa e moduli", [
        Item("Presenze", "calendar-days", "billing:attendance", "billing.view_attendancemonth",
             active=("billing:attendance", "billing:correction"), module="billing"),
        Item("Rette", "wallet", "billing:fees", "billing.view_guestfeeline",
             active=("billing:fees", "billing:fee_create", "billing:fee_update", "billing:settings"), module="billing"),
        Item("Prospetti e incassi", "receipt", "billing:statements", "billing.view_feestatement",
             active=("billing:statements", "billing:statement"), module="billing"),
        Item("Denaro degli ospiti", "receipt", "personal:overview", "personal.view_cashmovement", namespace="personal",
             module="personal"),
        Item("Moduli degli ospiti", "clipboard", "modulistica:overview", "modulistica.view_formsubmission",
             active=("modulistica:overview", "modulistica:guest", "modulistica:guest_fill"), module="modulistica"),
    ], icon="wallet", key="amministrazione"),
    Section("Sistema", [
        Item("Utenti e permessi", "users", "accounts:user_list", "accounts.view_user",
             active=("accounts:user_list", "accounts:user_update", "accounts:user_permissions",
                     "accounts:user_create", "accounts:user_set_password")),
        Item("Configurazione", "sliders", "core:config", "core.change_systemconfig", active=("core:config",)),
        Item("Moduli", "grid", "core:modules", "core.change_systemconfig", active=("core:modules",)),
        Item("Protocolli automatici", "flag", "protocols:list", "protocols.view_protocol",
             active=("protocols:list", "protocols:create", "protocols:update"), module="protocols"),
        Item("Modulistica", "file-text", "modulistica:index", "modulistica.manage_forms",
             active=("modulistica:index", "modulistica:settings", "modulistica:create", "modulistica:edit",
                     "modulistica:preview", "modulistica:distribute"), module="modulistica"),
        Item("Impostazioni notifiche", "bell", "notifications:settings", "notifications.change_notificationsetting",
             active=("notifications:settings",)),
        Item("Report programmati", "calendar-check", "reports:schedule_list", "reports.change_reportschedule",
             active=("reports:schedule_list", "reports:schedule_create", "reports:schedule_update"), module="reports"),
        Item("Audit log", "shield", "audit:list", "audit.view_auditlog", namespace="audit"),
        Item("Log accessi", "key", "accounts:access_log", "accounts.view_accesslog", active=("accounts:access_log",)),
        Item("Backup", "database", "backups:list", "backups.manage_backup", namespace="backups"),
        Item("Dispositivi di firma", "id-card", "signatures:devices", "signatures.manage_signer_devices",
             active=("signatures:devices",)),
        Item("Pubblica l'app", "smartphone", "signatures:app_admin", "signatures.manage_signer_devices",
             active=("signatures:app_admin",)),
    ], icon="sliders", key="sistema"),
    Section(None, key="fine", items=[
        Item("Notifiche", "bell", "notifications:list", active=("notifications:list",), count="notifications"),
        Item("I miei moduli", "clipboard-check", "modulistica:mine", active=("modulistica:mine", "modulistica:fill"),
             count="forms_mine", module="modulistica", exclude_roles=("family",)),
        Item("Le mie scadenze", "calendar-check", "staffing:my_credentials", active=("staffing:my_credentials",),
             module="staffing", exclude_roles=("family",)),
        Item("Impostazioni", "sliders", "core:settings", active=("core:settings", "accounts:profile",
                                                              "accounts:password_change", "signatures:credential")),
    ]),
]


def role_of(user):
    return "admin" if user.is_superuser else user.role


def counts_for(user, unread, on):
    from fasas.clinical.models import TherapyAdministration
    from fasas.protocols.models import ProtocolActivation

    counts = {"notifications": unread}
    if user.has_perm("clinical.validate_sos"):
        counts["sos"] = TherapyAdministration.objects.filter(
            is_sos=True, validation_status=TherapyAdministration.Validation.PENDING).count()
    if on["protocols"] and user.has_perm("protocols.view_protocolactivation"):
        counts["protocols"] = ProtocolActivation.objects.filter(status__in=ProtocolActivation.OPEN_STATES).count()
    if on["feedback"] and user.has_perm("feedback.view_feedback"):
        from fasas.feedback.models import Feedback

        counts["feedback"] = Feedback.objects.filter(status=Feedback.Status.NEW).count()
    if on["care"] and user.has_perm("care.view_caretaskcheck"):
        from fasas.care.services import late_slots

        counts["care_late"] = len(late_slots()) or None
    if on["modulistica"] and role_of(user) != "family":
        from fasas.modulistica.services import pending_for

        counts["forms_mine"] = pending_for(user).count() or None
    if on["families"] and user.has_perm("families.manage_family_area"):
        from fasas.families.services import pending_visits, unread_for_staff

        counts["families"] = (unread_for_staff() + pending_visits()) or None
    if on["staffing"] and user.has_perm("staffing.view_staffcredential"):
        from fasas.staffing.credentials import matrix

        counts["staff_deadlines"] = sum(r["problems"] for r in matrix()["rows"]) or None
    if on["staffing"] and user.has_perm("staffing.change_leaverequest"):
        from fasas.staffing.views import pending_requests_count

        counts["rota_requests"] = pending_requests_count()
    return counts


def build_menu(request, unread=0):
    user = request.user
    match = request.resolver_match
    current = f"{match.namespace}:{match.url_name}" if match else ""
    namespace = match.namespace if match else ""
    on = states(getattr(request, "fasas_config", None))
    counts = counts_for(user, unread, on)
    sections = []
    for section in MENU:
        items = []
        for item in section.items:
            if item.module and not on[item.module]:
                continue
            if item.exclude_roles and role_of(user) in item.exclude_roles:
                continue
            perms = (item.perm,) if isinstance(item.perm, str) else (item.perm or ())
            if perms and not any(user.has_perm(p) for p in perms):
                continue
            label = DASHBOARD_LABELS.get(role_of(user), item.label) if item.url_name == "core:dashboard" else item.label
            items.append({
                "label": label, "icon": item.icon, "url": reverse(item.url_name),
                "active": current in item.active or (item.namespace is not None and namespace == item.namespace),
                "count": counts.get(item.count) if item.count else None,
            })
        if not items:
            continue
        if section.title and len(items) > 1:
            sections.append({"title": section.title, "icon": section.icon, "key": section.key, "items": items,
                             "open": any(i["active"] for i in items),
                             "count": sum(i["count"] or 0 for i in items) or None})
        else:  # sempre visibili, oppure una tendina con una sola voce: niente tendina
            sections.append({"title": None, "items": items, "gap": section.key == "fine"})
    return sections
