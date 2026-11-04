"""
Pacchetto «pronto per l'ispezione»: un unico PDF per la vigilanza (ATS/ASL) con la situazione alla data e i dati
del periodo. Riassume, non sostituisce: per ogni voce indica dove si trova il dettaglio nel FASAS.

Le sezioni dei moduli spenti (Configurazione › Moduli) non compaiono.
"""
import datetime

from django.db.models import Count, Q
from django.utils import timezone

from fasas import __version__
from fasas.core.modules import is_on


def _d(value):
    return value.strftime("%d/%m/%Y") if value else "—"


def _t(value):
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M") if value else "—"


def _pct(part, total):
    return f"{round(100 * part / total)}%" if total else "—"


def build_inspection(start, end, user=None):
    from fasas.accounts.models import AccessLog, Role, User
    from fasas.audit.models import AuditCheckpoint
    from fasas.backups.models import BackupRecord, RestoreTest
    from fasas.clinical.models import ClinicalEvent, Restraint, Therapy, TherapyAdministration
    from fasas.core.models import SystemConfig
    from fasas.documents.models import Document
    from fasas.feedback.metrics import pilot_metrics
    from fasas.guests.models import Guest
    from fasas.guests.services import guests_in_care

    from .pdf import Document as Pdf

    config = SystemConfig.get()
    community = config.community
    today = timezone.localdate()
    doc = Pdf("Pacchetto per l'ispezione", f"Situazione al {today:%d/%m/%Y} · dati del periodo {start:%d/%m/%Y} – "
              f"{end:%d/%m/%Y}", generated_by=user)

    doc.heading("Struttura", 2)
    doc.key_values([
        ("Struttura", community.name), ("Indirizzo", community.address or "—"),
        ("Codice ASL/ATS", community.asl_code or "—"), ("Telefono", community.phone or "—"),
        ("Software", f"FASAS Digitale {__version__}"),
        ("Contenuto", "Riepilogo generato dal sistema; il dettaglio è consultabile nel FASAS alle voci indicate."),
    ])

    # --- Ospiti -----------------------------------------------------------------------------------------------
    guests = list(guests_in_care().order_by("last_name", "first_name"))
    therapies = dict(Therapy.objects.filter(status=Therapy.Status.ACTIVE, guest__in=guests)
                     .values_list("guest").annotate(n=Count("pk")))
    pai_on = is_on("pai")
    active_pai = {}
    if pai_on:
        from fasas.pai.models import PAI

        active_pai = {p.guest_id: p for p in PAI.objects.filter(status=PAI.Status.ACTIVE, guest__in=guests)}
    rows = []
    for g in guests:
        row = [f"{g.last_name} {g.first_name}", _d(g.admission_date), g.get_status_display(),
               str(therapies.get(g.pk, 0)), str(g.allergies.count())]
        if pai_on:
            pai = active_pai.get(g.pk)
            if pai is None:
                row.append("SENZA PAI")
            else:
                row.append(f"v{pai.version}, revisione entro {_d(pai.review_due)}"
                           + (" (SCADUTA)" if pai.review_due < today else ""))
        rows.append(row)
    doc.heading(f"Ospiti in carico ({len(guests)})", 2)
    headers = ["Ospite", "Ingresso", "Stato", "Terapie attive", "Allergie"] + (["PAI in vigore"] if pai_on else [])
    doc.table(headers, rows, [3, 1.2, 1.4, 1, 0.9] + ([2.6] if pai_on else []))
    if pai_on:
        without = sum(1 for r in rows if r[-1] == "SENZA PAI")
        expired = sum(1 for r in rows if r[-1].endswith("(SCADUTA)"))
        doc.text(f"PAI: {len(guests) - without} ospiti con PAI in vigore, {without} senza PAI, {expired} con revisione "
                 "scaduta. Dettaglio: scheda ospite › PAI.", "small")

    # --- Terapie, somministrazioni, turni ---------------------------------------------------------------------
    totals = pilot_metrics(start, end)["totals"]
    sos = TherapyAdministration.objects.filter(is_sos=True, voided_at__isnull=True,
                                               occurred_at__date__range=(start, end))
    pending = TherapyAdministration.objects.filter(is_sos=True, voided_at__isnull=True,
                                                   validation_status=TherapyAdministration.Validation.PENDING).count()
    doc.heading("Terapie e somministrazioni nel periodo", 2)
    doc.key_values([
        ("Terapie attive oggi", str(sum(therapies.values()))),
        ("Dosi programmate (turni chiusi)", str(totals["doses_total"])),
        ("Registrate", f"{totals['doses_documented']} ({_pct(totals['doses_documented'], totals['doses_total'])})"),
        ("Non registrate alla chiusura del turno", str(totals["doses_missing"])),
        ("Registrate oltre 60 minuti dall'orario", str(totals["doses_late"])),
        ("Farmaci al bisogno (SOS) somministrati", f"{sos.count()}; da validare oggi: {pending}"),
        ("Turni chiusi", f"{totals['closed']} su {totals['expected_closures']}"),
        ("Checklist di turno completate", _pct(totals["checklist_done"], totals["checklist_total"])),
    ])
    doc.text("Dosi e checklist sono contate alla chiusura di ogni turno. Dettaglio: Report › Farmaci somministrati; "
             "Turno › Chiusura turni.", "small")

    # --- Eventi e contenzioni ---------------------------------------------------------------------------------
    events = (ClinicalEvent.objects.filter(occurred_at__date__range=(start, end), voided_at__isnull=True)
              .filter(Q(severity__in=["high", "critical"]) | Q(is_emergency=True) | Q(event_type="fall"))
              .select_related("guest").order_by("occurred_at"))
    doc.heading("Eventi rilevanti nel periodo (gravi, emergenze, cadute)", 2)
    doc.table(["Data e ora", "Ospite", "Evento", "Gravità", "Medico avvisato", "Familiari avvisati"],
              [[_t(e.occurred_at), str(e.guest), e.get_event_type_display(), e.get_severity_display(),
                "sì" if e.doctor_notified else "no", "sì" if e.family_notified else "no"] for e in events]
              or [["—", "Nessun evento", "", "", "", ""]], [1.5, 2.2, 1.8, 1, 1, 1])
    restraints = (Restraint.objects.filter(voided_at__isnull=True)
                  .filter(Q(ended_at__isnull=True) | Q(ended_at__date__gte=start)).filter(occurred_at__date__lte=end)
                  .select_related("guest", "authorized_by").order_by("occurred_at"))
    doc.heading("Contenzioni (in corso o nel periodo)", 2)
    doc.table(["Inizio", "Fine", "Ospite", "Tipo", "Autorizzata da", "Data autorizzazione"],
              [[_t(r.occurred_at), _t(r.ended_at) if r.ended_at else "in corso", str(r.guest),
                r.get_restraint_type_display(), str(r.authorized_by or r.authorizing_doctor_name or "—"),
                _d(r.authorization_date)] for r in restraints]
              or [["—", "", "Nessuna contenzione", "", "", ""]], [1.5, 1.5, 2, 1.4, 1.8, 1.2])

    # --- Moduli facoltativi -----------------------------------------------------------------------------------
    if is_on("assessments"):
        from fasas.assessments.services import due_list

        overdue = [r for r in due_list(today, [g for g in guests if g.status == Guest.Status.ACTIVE]) if r["overdue"]]
        doc.heading(f"Valutazioni (scale) scadute o mai fatte: {len(overdue)}", 2)
        if overdue:
            doc.table(["Ospite", "Scala", "Ultima", "Scadenza"],
                      [[str(r["guest"]), r["scale"].name, _d(r["last"].occurred_at if r["last"] else None),
                        _d(r["due"])] for r in overdue[:60]], [2.5, 2.5, 1.2, 1.2])
    if is_on("wounds"):
        from fasas.wounds.models import Wound

        wounds = Wound.objects.filter(status=Wound.Status.OPEN, voided_at__isnull=True).select_related("guest")
        doc.heading(f"Lesioni aperte: {wounds.count()}", 2)
        if wounds:
            doc.table(["Ospite", "Lesione", "Osservata il", "Insorgenza"],
                      [[str(w.guest), str(w), _d(timezone.localtime(w.occurred_at).date()), w.get_origin_display()]
                       for w in wounds[:60]], [2.2, 3, 1.2, 1.5])
    if is_on("stock"):
        from fasas.pharmacy.services import drug_stock_summary

        lots = [(row["drug"], lot) for row in drug_stock_summary() for lot in row["expired"]]
        doc.heading(f"Farmaci scaduti ancora in magazzino: {len(lots)}", 2)
        if lots:
            doc.table(["Farmaco", "Lotto", "Scadenza", "Quantità"],
                      [[str(drug), lot.lot_number, _d(lot.expiry_date), str(lot.quantity)] for drug, lot in lots],
                      [3, 1.5, 1.2, 1])
    if is_on("protocols"):
        from fasas.protocols.models import Protocol, ProtocolActivation

        protocols = Protocol.objects.filter(active=True).annotate(n=Count(
            "activations", filter=Q(activations__triggered_at__date__range=(start, end))))
        doc.heading("Protocolli automatici in vigore", 2)
        doc.table(["Protocollo", "Validato da", "Validato il", "Attivazioni nel periodo"],
                  [[p.name, p.validated_by or "NON VALIDATO", _d(timezone.localtime(p.validated_at).date()
                                                                if p.validated_at else None), str(p.n)]
                   for p in protocols] or [["Nessun protocollo attivo", "", "", ""]], [3, 2, 1.2, 1.3])
        still_open = ProtocolActivation.objects.filter(status__in=ProtocolActivation.OPEN_STATES).count()
        doc.text(f"Attivazioni ancora aperte oggi: {still_open}.", "small")

    documents = (Document.objects.filter(expires_on__isnull=False, expires_on__lte=today + datetime.timedelta(days=30))
                 .exclude(guest__status=Guest.Status.ARCHIVED).select_related("guest").order_by("expires_on"))
    doc.heading(f"Documenti scaduti o in scadenza entro 30 giorni: {documents.count()}", 2)
    if documents:
        doc.table(["Ospite", "Documento", "Scadenza"],
                  [[str(d.guest), d.title, _d(d.expires_on) + (" (SCADUTO)" if d.expires_on < today else "")]
                   for d in documents[:60]], [2.5, 3.5, 1.5])

    # --- Sicurezza e continuità -------------------------------------------------------------------------------
    users = User.objects.filter(is_active=True)
    by_role = dict(users.order_by().values_list("role").annotate(n=Count("pk")))
    with_2fa = users.filter(two_factor__isnull=False).count()
    last_backup = BackupRecord.objects.filter(status=BackupRecord.Status.OK).first()
    last_restore = RestoreTest.objects.first()
    checkpoint = AuditCheckpoint.objects.first()
    doc.heading("Sicurezza dei dati e continuità", 2)
    doc.key_values([
        ("Utenti attivi", ", ".join(f"{label}: {by_role.get(code, 0)}" for code, label in Role.choices)),
        ("Utenti con verifica in due passaggi", f"{with_2fa} su {users.count()}"),
        ("Accessi falliti nel periodo", str(AccessLog.objects.filter(
            timestamp__date__range=(start, end), event__in=["failed", "locked"]).count())),
        ("Ultimo backup riuscito", _t(last_backup.created_at) if last_backup else "NESSUNO"),
        ("Ultima prova di ripristino", f"{_t(last_restore.created_at)} – {last_restore.get_result_display()}"
         if last_restore else "NESSUNA"),
        ("Ultima verifica di integrità del registro delle operazioni (audit)",
         f"{_t(checkpoint.created_at)} – {'integro' if checkpoint.chain_ok else 'NON INTEGRO'}" if checkpoint
         else "NESSUNA"),
    ])
    doc.text("Il registro delle operazioni è progettato per rilevare modifiche e cancellazioni (catena di impronte "
             "verificata ogni notte); non è definito legalmente immodificabile.", "small")
    return doc.build()
