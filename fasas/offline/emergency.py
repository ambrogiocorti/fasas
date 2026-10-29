"""
Foglio di emergenza stampabile: ciò che serve se mancano insieme rete e dispositivi (blackout, guasto).
Per ogni ospite: allergie, avvisi, terapie della giornata con la colonna per la sigla dell'operatore,
farmaci al bisogno con limiti, contatti di emergenza. Da stampare a inizio giornata e tenere in infermeria.
"""
from reportlab.platypus import Spacer

from fasas.clinical.models import Therapy
from fasas.clinical.services import scheduled_doses
from fasas.core.shifts import Shift, resolve_shift
from fasas.guests.services import guests_in_care
from fasas.reports.pdf import Document, p, table


def emergency_sheet(user, day=None):
    day = day or resolve_shift()[0]
    guests = list(guests_in_care().prefetch_related("allergies", "contacts"))
    doses = {}
    for code in (Shift.MORNING, Shift.AFTERNOON, Shift.NIGHT):
        for dose in scheduled_doses(day, code, guests):
            doses.setdefault(dose.guest.pk, []).append((code, dose))
    sos = {}
    for therapy in Therapy.objects.filter(status=Therapy.Status.ACTIVE, is_sos=True).select_related("drug"):
        sos.setdefault(therapy.guest_id, []).append(therapy)

    doc = Document(f"Foglio di emergenza – {day:%d/%m/%Y}", orientation="landscape", generated_by=user,
                   subtitle="Da usare solo se il sistema non è disponibile. Registrare ogni somministrazione con ora e "
                            "sigla; al ripristino riportare tutto in FASAS Digitale e conservare questo foglio.")
    width = doc.width
    for guest in guests:
        block = [p(f"{guest.last_name} {guest.first_name} · {guest.age} anni"
                   + (f" · camera {guest.room}" if guest.room else "") + f" · {guest.get_status_display()}", "h2")]
        allergies = "; ".join(f"{a.substance} ({a.get_severity_display().lower()})" for a in guest.allergies.all())
        block.append(p(f"ALLERGIE: {allergies}" if allergies else "Allergie: nessuna nota", "body"))
        alerts = [t.alert_message or t.name for t in guest.tags.all()]
        if alerts:
            block.append(p("Avvisi: " + " · ".join(alerts), "body"))
        if guest.diet or guest.diet_texture:
            block.append(p("Dieta: " + " · ".join(x for x in (guest.diet, guest.diet_texture) if x), "body"))
        rows = [(Shift(code).label, dose.time.strftime("%H:%M"), str(dose.therapy.drug), dose.therapy.dose_display,
                 dose.therapy.get_route_display(), dose.therapy.instructions or "",
                 "già registrata" if dose.done else "", "") for code, dose in doses.get(guest.pk, [])]
        if rows:
            block.append(table(["Turno", "Ora", "Farmaco", "Dose", "Via", "Istruzioni", "Stato", "Ora e sigla"], rows,
                               [width * w for w in (0.08, 0.06, 0.2, 0.09, 0.09, 0.24, 0.1, 0.14)]))
        else:
            block.append(p("Nessuna terapia programmata oggi.", "body"))
        if sos.get(guest.pk):
            sos_rows = [(str(t.drug), t.dose_display, t.sos_indication,
                         " · ".join(x for x in (f"max {t.sos_max_daily}/24h" if t.sos_max_daily else "",
                                                 f"ogni {t.sos_min_interval_hours} h" if t.sos_min_interval_hours else "")
                                    if x), "") for t in sos[guest.pk]]
            block.append(Spacer(0, 4))
            block.append(table(["Al bisogno (SOS)", "Dose", "Indicazione", "Limiti", "Ora, motivo e sigla"], sos_rows,
                               [width * w for w in (0.2, 0.1, 0.3, 0.15, 0.25)]))
        contacts = [f"{c.name} ({c.relationship or c.get_kind_display()}) {c.phone}"
                    for c in guest.contacts.all() if c.is_emergency_contact]
        if guest.general_practitioner:
            contacts.append(f"Medico curante {guest.general_practitioner} {guest.general_practitioner_phone}")
        if contacts:
            block.append(p("Contatti di emergenza: " + " · ".join(contacts), "small"))
        block.append(Spacer(0, 10))
        doc.keep(*block)
    if not guests:
        doc.text("Nessun ospite in carico.")
    return doc.build()
