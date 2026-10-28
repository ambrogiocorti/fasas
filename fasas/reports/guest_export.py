"""
Esportazione della cartella completa dell'ospite in un unico PDF (sezione 22):
anagrafica, dati sanitari, PAI, terapie, somministrazioni, parametri, eventi, contenzioni,
diario, appuntamenti, protocolli e, in coda, i documenti allegati (PDF e immagini).
"""
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .pdf import Document


def _image_page(data, title):
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, h - 40, title[:100])
    image = ImageReader(BytesIO(data))
    iw, ih = image.getSize()
    scale = min((w - 80) / iw, (h - 100) / ih, 1)
    c.drawImage(image, 40, h - 60 - ih * scale, iw * scale, ih * scale)
    c.showPage()
    c.save()
    return buffer.getvalue()


def build_guest_folder(guest, user=None, include_documents=True, date_from=None):
    from fasas.clinical.models import ClinicalEvent, ParameterReading, Restraint, TherapyAdministration
    from fasas.daily.models import DailyRecord, DiaryEntry, EvacuationRecord
    from fasas.documents.services import read_version

    doc = Document(
        f"Cartella FASAS – {guest}",
        f"Esportazione completa del {timezone.localtime():%d/%m/%Y %H:%M}"
        + (f" · dati dal {date_from:%d/%m/%Y}" if date_from else ""),
        generated_by=user,
    )

    def since(qs, field="occurred_at"):
        return qs.filter(**{f"{field}__date__gte": date_from}) if date_from else qs

    doc.heading("1. Dati anagrafici")
    doc.key_values([
        ("Cognome e nome", f"{guest.last_name} {guest.first_name}"),
        ("Data e luogo di nascita", f"{guest.birth_date:%d/%m/%Y} {guest.birth_place}"),
        ("Codice fiscale", guest.fiscal_code),
        ("Tessera sanitaria", guest.health_card_number),
        ("Residenza", f"{guest.residence_address} {guest.residence_zip} {guest.residence_city}".strip()),
        ("Ingresso in struttura", guest.admission_date),
        ("Stato", guest.get_status_display()),
        ("Dimissione", f"{guest.discharge_date:%d/%m/%Y} – {guest.discharge_destination}" if guest.discharge_date else ""),
        ("Medico curante", f"{guest.general_practitioner} {guest.general_practitioner_phone}".strip()),
        ("Servizio inviante", guest.referring_service),
    ])
    doc.heading("Contatti, familiari e tutela legale", 2)
    doc.table(["Tipo", "Nome", "Relazione", "Telefono", "Email", "Note"],
              [[c.get_kind_display(), c.name, c.relationship, c.phone, c.email,
                f"{c.legal_reference} {c.notes}".strip()] for c in guest.contacts.all()],
              [1.2, 1.5, 1, 1.1, 1.5, 2])

    doc.heading("2. Dati sanitari")
    doc.key_values([
        ("Disabilità", guest.disability_description),
        ("Certificazioni", guest.disability_certifications),
        ("Dieta", f"{guest.diet} {guest.diet_texture}".strip()),
        ("Tag clinici", ", ".join(t.name for t in guest.tags.all())),
        ("Note cliniche", guest.clinical_notes),
    ])
    doc.heading("Diagnosi e patologie", 2)
    doc.table(["Tipo", "Descrizione", "ICD", "Data", "Attiva"],
              [[d.get_kind_display(), d.description, d.icd_code, d.diagnosed_on, d.active] for d in guest.diagnoses.all()],
              [1, 4, 1, 1, 0.7])
    doc.heading("Allergie e intolleranze", 2)
    doc.table(["Tipo", "Categoria", "Sostanza", "Reazione", "Gravità"],
              [[a.get_kind_display(), a.get_category_display(), a.substance, a.reaction, a.get_severity_display()]
               for a in guest.allergies.all()], [1, 1, 1.5, 2.5, 1])

    doc.heading("3. Piano Assistenziale Individuale")
    for pai in guest.pais.prefetch_related("goals__responsible").order_by("-version"):
        doc.heading(f"PAI v{pai.version} – {pai.get_status_display()} (revisione entro {pai.review_due:%d/%m/%Y})", 2)
        if pai.summary:
            doc.text(pai.summary)
        doc.table(["Area", "Obiettivo", "Intervento", "Responsabile", "Verifica", "Esito"],
                  [[g.get_area_display(), g.objective, g.intervention, g.responsible_display, g.verification_date,
                    g.get_outcome_display()] for g in pai.goals.all()], [1.1, 2.5, 2.8, 1.3, 1, 1])

    doc.heading("4. Terapie")
    doc.table(["Farmaco", "Dose", "Via", "Orari/SOS", "Dal", "Al", "Stato", "Prescrittore"],
              [[t.drug, t.dose_display, t.get_route_display(),
                f"SOS: {t.sos_indication}" if t.is_sos else ", ".join(t.schedule_times),
                t.start_date, t.end_date, t.get_status_display(), t.prescriber_display]
               for t in guest.therapies.select_related("drug", "prescriber").order_by("-start_date")],
              [2, 0.9, 0.9, 1.6, 0.9, 0.9, 0.8, 1.3])
    doc.heading("Somministrazioni", 2)
    doc.table(["Data/ora", "Farmaco", "Esito", "SOS – motivo", "Note", "Operatore"],
              [[a.occurred_at, a.therapy.drug, a.get_status_display(), a.sos_reason, a.notes, a.created_by]
               for a in since(TherapyAdministration.objects.filter(guest=guest)).select_related("therapy__drug", "created_by")
               .order_by("occurred_at")], [1.2, 1.8, 1, 1.8, 1.6, 1.2])

    doc.heading("5. Parametri sanitari")
    doc.table(["Data/ora", "Parametro", "Valore", "Note", "Operatore"],
              [[r.occurred_at, r.parameter_type.name, r.display_value, r.notes, r.created_by]
               for r in since(ParameterReading.objects.filter(guest=guest)).select_related("parameter_type", "created_by")
               .order_by("occurred_at")], [1.2, 1.3, 1.1, 2.5, 1.2])

    doc.heading("6. Eventi sanitari e contenzioni")
    doc.table(["Data/ora", "Tipo", "Gravità", "Descrizione", "Interventi", "Operatore"],
              [[e.occurred_at, e.get_event_type_display(), e.get_severity_display(), e.description, e.actions_taken,
                e.created_by] for e in since(ClinicalEvent.objects.filter(guest=guest)).select_related("created_by")
               .order_by("occurred_at")], [1.1, 1.2, 0.8, 2.6, 2, 1.1])
    doc.table(["Inizio", "Fine", "Tipo", "Motivo", "Autorizzazione", "Responsabile"],
              [[r.occurred_at, r.ended_at, r.get_restraint_type_display(), r.reason,
                f"{r.authorizing_doctor_display} ({r.authorization_date:%d/%m/%Y})", r.responsible_operator]
               for r in since(Restraint.objects.filter(guest=guest)).select_related("responsible_operator", "authorized_by")],
              [1.1, 1.1, 1.3, 2.4, 1.8, 1.2])

    doc.heading("7. Registro giornaliero ed evacuazioni")
    doc.table(["Data/ora", "Categoria", "Dettaglio", "Operatore"],
              [[r.occurred_at, r.get_category_display(),
                " – ".join(x for x in [r.get_meal_display(), r.get_intake_display(), r.description] if x), r.created_by]
               for r in since(DailyRecord.objects.filter(guest=guest)).select_related("created_by").order_by("occurred_at")],
              [1.2, 1.2, 4.5, 1.2])
    doc.table(["Data/ora", "Esito", "Consistenza", "Note", "Operatore"],
              [[e.occurred_at, "SI" if e.outcome else "NO", e.get_consistency_display(), e.notes, e.created_by]
               for e in since(EvacuationRecord.objects.filter(guest=guest)).select_related("created_by").order_by("occurred_at")],
              [1.2, 0.6, 1.8, 2.5, 1.2])

    doc.heading("8. Diario assistenziale")
    doc.table(["Data/ora", "Nota", "Operatore"],
              [[d.occurred_at, ("[RILEVANTE] " if d.is_relevant else "") + d.text, d.created_by]
               for d in since(DiaryEntry.objects.filter(guest=guest)).select_related("created_by").order_by("occurred_at")],
              [1.2, 6, 1.2])

    doc.heading("9. Appuntamenti sanitari")
    doc.table(["Data/ora", "Tipo", "Descrizione", "Luogo / medico", "Stato", "Esito"],
              [[a.scheduled_at, a.get_kind_display(), a.title, f"{a.location} {a.doctor}".strip(), a.get_status_display(),
                a.outcome] for a in guest.appointments.order_by("scheduled_at")], [1.1, 1.1, 1.8, 1.6, 0.9, 2.5])

    doc.heading("10. Protocolli attivati")
    doc.table(["Attivato", "Protocollo", "Motivo", "Stato", "Esito"],
              [[a.triggered_at, a.protocol.name, a.trigger_summary, a.get_status_display(), a.resolution_notes]
               for a in guest.protocol_activations.select_related("protocol").order_by("triggered_at")],
              [1.1, 1.5, 2.5, 0.9, 2.5])

    documents = list(guest.documents.prefetch_related("versions"))
    doc.heading("11. Documenti allegati")
    doc.table(["Categoria", "Titolo", "Data", "Versione", "File", "SHA-256"],
              [[d.get_category_display(), d.title, d.document_date, d.current_version.number if d.current_version else "",
                d.current_version.original_name if d.current_version else "",
                d.current_version.sha256[:16] + "…" if d.current_version else ""] for d in documents],
              [1.2, 2, 0.9, 0.7, 2, 1.4])

    main_pdf = doc.build()
    if not include_documents or not documents:
        return main_pdf

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(main_pdf)))
    for document in documents:
        version = document.current_version
        if version is None:
            continue
        try:
            data = read_version(version, user=user)
            if version.is_pdf:
                writer.append(PdfReader(BytesIO(data)), outline_item=f"Allegato: {document.title}")
            elif version.content_type.startswith("image/"):
                writer.append(PdfReader(BytesIO(_image_page(data, document.title))),
                              outline_item=f"Allegato: {document.title}")
        except Exception:  # un allegato illeggibile non deve bloccare l'esportazione: resta nell'indice
            continue
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
