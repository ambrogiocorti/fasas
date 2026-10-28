"""
Permessi predefiniti per ruolo (sezione 2). L'amministratore può poi concedere o negare
singoli permessi a singoli utenti (sezione 26) dalla pagina «Permessi» dell'utente.
"""
from .models import Role

MANAGED_APPS = [
    "core", "accounts", "audit", "guests", "documents", "signatures", "pharmacy", "clinical", "daily",
    "protocols", "appointments", "pai", "notifications", "reports", "backups",
]

VIEW_CLINICAL = [
    "guests.view_guest", "guests.view_clinicaltag", "guests.view_guestcontact", "guests.view_diagnosis",
    "guests.view_allergy", "guests.view_admissionevent",
    "documents.view_document", "signatures.view_signature",
    "pharmacy.view_drug", "pharmacy.view_druginteraction", "pharmacy.view_stocklot", "pharmacy.view_stockmovement",
    "clinical.view_therapy", "clinical.view_therapyadministration", "clinical.view_parametertype",
    "clinical.view_parameterreading", "clinical.view_clinicalevent", "clinical.view_restraint",
    "daily.view_dailyrecord", "daily.view_evacuationrecord", "daily.view_diaryentry", "daily.view_checklistcheck",
    "daily.view_checklisttemplate", "daily.view_checklistitem", "daily.view_shiftassignment", "daily.view_shiftclosure",
    "protocols.view_protocol", "protocols.view_protocolactivation", "protocols.view_protocolactionlog",
    "appointments.view_appointment", "pai.view_pai", "pai.view_paigoal",
    "notifications.view_notification",
]

OPERATOR = VIEW_CLINICAL + [
    "documents.add_document",
    "clinical.add_therapyadministration", "clinical.change_therapyadministration",
    "clinical.add_parameterreading", "clinical.change_parameterreading",
    "clinical.add_clinicalevent", "clinical.change_clinicalevent",
    "clinical.add_restraint", "clinical.change_restraint",
    "daily.add_dailyrecord", "daily.change_dailyrecord",
    "daily.add_evacuationrecord", "daily.change_evacuationrecord",
    "daily.add_diaryentry", "daily.change_diaryentry",
    "daily.add_checklistcheck", "daily.change_checklistcheck", "daily.delete_checklistcheck",
    "daily.close_shift",
    "protocols.change_protocolactivation", "protocols.add_protocolactionlog",
    "appointments.change_appointment",
]

COORDINATOR = OPERATOR + [
    "core.edit_after_window",
    "guests.add_guest", "guests.change_guest", "guests.archive_guest", "guests.export_guest",
    "guests.add_clinicaltag", "guests.change_clinicaltag",
    "guests.add_guestcontact", "guests.change_guestcontact", "guests.add_diagnosis", "guests.change_diagnosis",
    "guests.add_allergy", "guests.change_allergy", "guests.add_admissionevent",
    "documents.change_document",
    "pharmacy.add_drug", "pharmacy.change_drug", "pharmacy.add_druginteraction", "pharmacy.change_druginteraction",
    "pharmacy.add_stocklot", "pharmacy.change_stocklot",
    # trascrizione delle prescrizioni del medico curante (nelle comunità senza medico interno)
    "clinical.add_therapy", "clinical.change_therapy", "clinical.validate_sos",
    "clinical.delete_therapyadministration", "clinical.delete_parameterreading", "clinical.delete_clinicalevent",
    "clinical.delete_restraint", "clinical.add_parametertype", "clinical.change_parametertype",
    "daily.delete_dailyrecord", "daily.delete_evacuationrecord", "daily.delete_diaryentry",
    "daily.add_shiftassignment", "daily.change_shiftassignment",
    "daily.add_checklisttemplate", "daily.change_checklisttemplate", "daily.add_checklistitem", "daily.change_checklistitem",
    "protocols.add_protocol", "protocols.change_protocol",
    "appointments.add_appointment",
    "pai.add_pai", "pai.change_pai", "pai.approve_pai", "pai.add_paigoal", "pai.change_paigoal", "pai.delete_paigoal",
    "reports.view_generatedreport", "reports.add_generatedreport",
    "reports.view_reportschedule", "reports.add_reportschedule", "reports.change_reportschedule",
]

DOCTOR = VIEW_CLINICAL + [
    "core.edit_after_window",
    "guests.add_diagnosis", "guests.change_diagnosis", "guests.add_allergy", "guests.change_allergy",
    "documents.add_document",
    "pharmacy.add_drug", "pharmacy.change_drug", "pharmacy.add_druginteraction", "pharmacy.change_druginteraction",
    "clinical.add_therapy", "clinical.change_therapy", "clinical.validate_sos",
    "clinical.add_parameterreading", "clinical.add_clinicalevent", "clinical.change_clinicalevent",
    "clinical.add_restraint", "clinical.change_restraint",
    "daily.add_diaryentry",
    "signatures.sign_document", "signatures.add_signingcredential", "signatures.change_signingcredential",
    "pai.approve_pai", "pai.change_paigoal",
    "protocols.change_protocolactivation", "protocols.add_protocolactionlog",
    "reports.view_generatedreport", "reports.add_generatedreport",
]

# L'amministratore gestisce il sistema: utenti, configurazione, protocolli, notifiche, audit, backup.
# Non prescrive, non firma e non valida atti clinici.
ADMIN_EXCLUDED = {
    "clinical.add_therapy", "clinical.change_therapy", "clinical.validate_sos", "signatures.sign_document",
    "pai.approve_pai",
}

ROLE_PERMISSIONS = {
    Role.OPERATOR: OPERATOR,
    Role.COORDINATOR: COORDINATOR,
    Role.DOCTOR: DOCTOR,
}


def setup_role_groups(stdout=None):
    from django.contrib.auth.models import Group, Permission

    def perm_objects(names):
        found = []
        for name in names:
            app_label, codename = name.split(".")
            perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if perm is None:
                if stdout:
                    stdout.write(f"  permesso non trovato: {name}")
                continue
            found.append(perm)
        return found

    for role, names in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=Role(role).label)
        group.permissions.set(perm_objects(sorted(set(names))))
    admin_group, _ = Group.objects.get_or_create(name=Role.ADMIN.label)
    admin_perms = Permission.objects.filter(content_type__app_label__in=MANAGED_APPS + ["authtoken"])
    admin_group.permissions.set([
        p for p in admin_perms if f"{p.content_type.app_label}.{p.codename}" not in ADMIN_EXCLUDED
    ])

    from .models import User

    for user in User.objects.all():
        user.sync_role_group()
