"""
Permessi predefiniti per ruolo (sezione 2). L'amministratore può poi concedere o negare
singoli permessi a singoli utenti (sezione 26) dalla pagina «Permessi» dell'utente.
"""
from .models import Role

MANAGED_APPS = [
    "core", "accounts", "audit", "guests", "documents", "signatures", "pharmacy", "clinical", "daily",
    "protocols", "appointments", "pai", "notifications", "reports", "backups", "assessments",
    "wounds", "feedback",
]

# Consultazione della cartella: serve a chi assiste l'ospite (operatore, coordinatore, medico).
# L'amministratore di sistema non vede i dati clinici (minimizzazione, GDPR art. 5).
VIEW_CARE = [
    "guests.view_guest", "guests.view_clinicaltag", "guests.view_guestcontact", "guests.view_diagnosis",
    "guests.view_allergy", "guests.view_admissionevent",
    "documents.view_document", "signatures.view_signature",
    "clinical.view_therapy", "clinical.view_therapyadministration", "clinical.view_parametertype",
    "clinical.view_parameterreading", "clinical.view_clinicalevent", "clinical.view_restraint",
    "daily.view_diaryentry",
    "protocols.view_protocolactivation", "protocols.view_protocolactionlog",
    "pai.view_pai", "pai.view_paigoal",
    "notifications.view_notification",
    "assessments.view_assessment",
    "wounds.view_wound", "wounds.view_woundcheck", "wounds.view_dressingplan", "wounds.view_dressing",
]

# Operatore (spec. §2): registrazioni giornaliere, farmaci somministrati, eventi, parametri, diario.
# In più ciò che serve al turno: checklist, chiusura turno, azioni dei protocolli, visite da accompagnare.
OPERATOR = VIEW_CARE + [
    "daily.view_dailyrecord", "daily.view_evacuationrecord", "daily.view_checklistcheck",
    "daily.view_checklisttemplate", "daily.view_checklistitem", "daily.view_shiftassignment", "daily.view_shiftclosure",
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
    "appointments.view_appointment", "appointments.change_appointment",
    # Scale di valutazione (Barthel, Braden, PAINAD...): le compila chi assiste, come i parametri
    "assessments.add_assessment",
    # Lesioni: segnala una nuova lesione, registra rilevazioni (misure, foto) e medicazioni eseguite
    "wounds.add_wound", "wounds.add_woundcheck", "wounds.add_dressing",
    # Continuità senza rete: pacchetto del turno sul dispositivo e foglio di emergenza stampabile
    "offline.use_offline",
    # Segnalazioni del pilota: tutti possono segnalare un problema
    "feedback.add_feedback",
    # Calendario turni: consulta i propri turni, chiede ferie/permessi e cambi turno
    "staffing.view_rotamonth", "staffing.add_leaverequest", "staffing.add_shiftchange",
]

# Coordinatore sanitario (spec. §2): gestisce le cartelle, modifica i protocolli sanitari, valida le
# informazioni sanitarie, autorizza le modifiche oltre la finestra. Lavora anche in turno come l'operatore.
COORDINATOR = OPERATOR + [
    "core.edit_after_window",
    # Riapertura straordinaria di un turno chiuso (es. trascrizione del foglio di emergenza), con motivazione
    "daily.reopen_shift",
    # Firma elettronica avanzata con la propria CIE (es. PAI, consensi, verbali)
    "signatures.sign_with_cie",
    "guests.add_guest", "guests.change_guest", "guests.archive_guest", "guests.export_guest",
    "guests.add_clinicaltag", "guests.change_clinicaltag",
    "guests.add_guestcontact", "guests.change_guestcontact", "guests.add_diagnosis", "guests.change_diagnosis",
    "guests.add_allergy", "guests.change_allergy", "guests.add_admissionevent",
    "documents.add_document", "documents.change_document",
    "pharmacy.view_drug", "pharmacy.add_drug", "pharmacy.change_drug",
    "pharmacy.view_druginteraction", "pharmacy.add_druginteraction", "pharmacy.change_druginteraction",
    "pharmacy.view_stocklot", "pharmacy.add_stocklot", "pharmacy.change_stocklot", "pharmacy.view_stockmovement",
    # trascrizione delle prescrizioni del medico curante (il medico di struttura è opzionale)
    "clinical.add_therapy", "clinical.change_therapy", "clinical.validate_sos",
    "clinical.delete_therapyadministration", "clinical.delete_parameterreading", "clinical.delete_clinicalevent",
    "clinical.delete_restraint", "clinical.add_parametertype", "clinical.change_parametertype",
    "daily.delete_dailyrecord", "daily.delete_evacuationrecord", "daily.delete_diaryentry",
    "daily.add_shiftassignment", "daily.change_shiftassignment",
    "daily.add_checklisttemplate", "daily.change_checklisttemplate", "daily.add_checklistitem", "daily.change_checklistitem",
    "protocols.view_protocol", "protocols.add_protocol", "protocols.change_protocol",
    "appointments.add_appointment",
    "pai.add_pai", "pai.change_pai", "pai.approve_pai", "pai.add_paigoal", "pai.change_paigoal", "pai.delete_paigoal",
    # Scale di valutazione: annulla con motivo, sceglie le scale in uso e la frequenza
    "assessments.delete_assessment",
    "assessments.view_scalesetting", "assessments.change_scalesetting",
    # Lesioni: piano di medicazione, chiusura (guarigione), annullamento con motivo
    "wounds.add_dressingplan", "wounds.change_wound",
    "wounds.delete_wound", "wounds.delete_woundcheck", "wounds.delete_dressing",
    "reports.view_generatedreport", "reports.add_generatedreport",
    "reports.view_reportschedule", "reports.add_reportschedule", "reports.change_reportschedule",
    "reports.view_reporttemplate", "reports.add_reporttemplate", "reports.change_reporttemplate",
    # Passaggio dal cartaceo: importa anagrafiche, terapie, giacenze e documenti scansionati
    "imports.view_importbatch", "imports.add_importbatch",
    "offline.view_offlinerecord",
    # Pilota: segnalazioni ricevute e indicatori (giro farmaci, registrazioni mancanti, checklist)
    "feedback.view_feedback", "feedback.view_pilot_metrics",
    # Presenze per la rendicontazione: controlla, corregge e chiude il mese
    "billing.view_attendancemonth", "billing.add_attendancecorrection", "billing.change_attendancecorrection",
    "billing.close_attendance",
    # Pianificazione mensile dei turni del personale: calendario, ferie, cambi turno, regole
    "staffing.add_rotaentry", "staffing.change_rotaentry", "staffing.delete_rotaentry", "staffing.publish_rota",
    "staffing.view_leaverequest", "staffing.change_leaverequest", "staffing.view_shiftchange",
    "staffing.change_shiftchange", "staffing.view_rotasettings", "staffing.change_rotasettings",
    "staffing.view_staffprofile", "staffing.change_staffprofile",
]

# Medico (spec. §2): modifica le terapie, prescrive i farmaci, firma digitalmente i documenti sanitari.
# Consulta la cartella clinica, valida i farmaci SOS e autorizza le contenzioni (spec. §4);
# registra gli interventi sanitari. Non gestisce turni, magazzino, registro giornaliero o report.
DOCTOR = VIEW_CARE + [
    # Durante un'interruzione consulta terapie, allergie e contatti sul proprio dispositivo, senza registrare nulla
    "offline.view_offline_pack",
    "feedback.add_feedback",
    "core.edit_after_window",
    "guests.add_diagnosis", "guests.change_diagnosis", "guests.add_allergy", "guests.change_allergy",
    "documents.add_document",
    "pharmacy.view_drug", "pharmacy.add_drug", "pharmacy.change_drug",
    "pharmacy.view_druginteraction", "pharmacy.add_druginteraction", "pharmacy.change_druginteraction",
    "pharmacy.validate_druginteraction", "protocols.view_protocol", "protocols.validate_protocol",
    "clinical.add_therapy", "clinical.change_therapy", "clinical.validate_sos",
    "clinical.add_clinicalevent", "clinical.change_restraint",
    "signatures.sign_document", "signatures.view_signingcredential",
    "signatures.add_signingcredential", "signatures.change_signingcredential",
    "signatures.sign_with_cie",
    "assessments.add_assessment", "assessments.delete_assessment",
    "wounds.add_wound", "wounds.add_woundcheck", "wounds.add_dressingplan", "wounds.change_wound",
    "wounds.delete_wound", "wounds.delete_woundcheck", "wounds.delete_dressing",
]

# Amministratore (spec. §2): utenti, configurazione, protocolli, notifiche, audit log, backup.
# Non consulta le cartelle cliniche e non compie atti clinici.
ADMIN = [
    "accounts.view_user", "accounts.add_user", "accounts.change_user", "accounts.view_accesslog",
    "accounts.view_userpermissionoverride", "accounts.add_userpermissionoverride",
    "accounts.change_userpermissionoverride", "accounts.delete_userpermissionoverride",
    "audit.view_auditlog",
    "core.view_community", "core.change_community", "core.view_systemconfig", "core.change_systemconfig",
    "core.view_errorevent", "core.change_errorevent", "core.view_jobrun",
    "protocols.view_protocol", "protocols.add_protocol", "protocols.change_protocol",
    "notifications.view_notification", "notifications.view_notificationsetting", "notifications.change_notificationsetting",
    "backups.view_backuprecord", "backups.manage_backup",
    "reports.view_reportschedule", "reports.add_reportschedule", "reports.change_reportschedule",
    # Revoca dei dispositivi di firma (es. computer smarrito); non firma e non vede i documenti
    "signatures.manage_signer_devices",
    # Registro delle accettazioni della firma con CIE (conservazione 20 anni, copie su richiesta)
    "signatures.view_feaacceptance",
    # Pilota: riceve e gestisce le segnalazioni, vede gli indicatori
    "feedback.add_feedback", "feedback.view_feedback", "feedback.change_feedback", "feedback.view_pilot_metrics",
]

# Amministrativo (ufficio amministrativo, oltre la spec. §2): presenze per la rendicontazione, rette, prospetti
# e incassi. Vede anagrafica essenziale e giorni di presenza/assenza, non la cartella clinica.
ADMINISTRATIVE = [
    "billing.view_attendancemonth", "billing.add_attendancecorrection", "billing.change_attendancecorrection",
    "billing.close_attendance",
    "billing.view_guestfeeline", "billing.add_guestfeeline", "billing.change_guestfeeline",
    "billing.view_feestatement", "billing.add_feestatement", "billing.change_feestatement", "billing.issue_statement",
    "billing.view_feepayment", "billing.add_feepayment",
    "billing.view_billingsettings", "billing.change_billingsettings",
    "notifications.view_notification",
    # Consultazione del calendario turni (ore pianificate per le paghe)
    "staffing.view_rotamonth",
    "feedback.add_feedback",
]

ROLE_PERMISSIONS = {
    Role.OPERATOR: OPERATOR,
    Role.COORDINATOR: COORDINATOR,
    Role.DOCTOR: DOCTOR,
    Role.ADMIN: ADMIN,
    Role.ADMINISTRATIVE: ADMINISTRATIVE,
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

    from .models import User

    for user in User.objects.all():
        user.sync_role_group()
