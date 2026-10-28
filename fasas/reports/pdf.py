"""Generazione PDF con ReportLab (nessuna dipendenza di sistema)."""
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1e3a5f")
MUTED = colors.HexColor("#5b6472")
GRID = colors.HexColor("#c9d1dc")
ZEBRA = colors.HexColor("#f3f6f9")

_styles = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("t", parent=_styles["Title"], fontSize=17, textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4),
    "h1": ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=13, textColor=ACCENT, spaceBefore=10, spaceAfter=4),
    "h2": ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, textColor=ACCENT, spaceBefore=6, spaceAfter=3),
    "body": ParagraphStyle("b", parent=_styles["BodyText"], fontSize=9, leading=12),
    "small": ParagraphStyle("s", parent=_styles["BodyText"], fontSize=7.5, leading=9.5, textColor=MUTED),
    "cell": ParagraphStyle("c", parent=_styles["BodyText"], fontSize=7.5, leading=9.5),
    "cellb": ParagraphStyle("cb", parent=_styles["BodyText"], fontSize=7.5, leading=9.5, fontName="Helvetica-Bold",
                            textColor=colors.white),
}


def p(text, style="body"):
    """Paragrafo con testo utente sempre escapato."""
    text = "" if text is None else str(text)
    return Paragraph(escape(text).replace("\n", "<br/>"), STYLES[style])


def fmt(value):
    if value is None or value == "":
        return "—"
    if hasattr(value, "tzinfo") and hasattr(value, "hour"):
        return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Sì" if value else "No"
    return str(value)


def table(headers, rows, col_widths=None, available_width=None):
    data = [[p(h, "cellb") for h in headers]]
    data += [[p(fmt(c), "cell") for c in row] for row in rows]
    if not rows:
        data.append([p("Nessun dato nel periodo.", "cell")] + [""] * (len(headers) - 1))
    if col_widths is None and available_width:
        col_widths = [available_width / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    if not rows:
        style.append(("SPAN", (0, 1), (-1, 1)))
    t.setStyle(TableStyle(style))
    return t


def key_values(pairs, width):
    data = [[p(k, "small"), p(fmt(v))] for k, v in pairs]
    t = Table(data, colWidths=[width * 0.3, width * 0.7])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


class Document:
    """Documento PDF con intestazione della comunità, piè di pagina e numerazione."""

    def __init__(self, title, subtitle="", orientation="portrait", generated_by=None):
        from fasas.core.models import Community

        self.title = title
        self.subtitle = subtitle
        self.pagesize = landscape(A4) if orientation == "landscape" else A4
        self.margin = 14 * mm
        self.width = self.pagesize[0] - 2 * self.margin
        self.story = []
        self.community = Community.default()
        self.generated_by = generated_by
        self.generated_at = timezone.localtime()

    def add(self, *flowables):
        self.story.extend(flowables)

    def heading(self, text, level=1):
        self.story.append(p(text, "h1" if level == 1 else "h2"))

    def text(self, value, style="body"):
        self.story.append(p(value, style))

    def table(self, headers, rows, col_widths=None):
        if col_widths:
            total = sum(col_widths)
            col_widths = [self.width * w / total for w in col_widths]
        self.story.append(table(headers, rows, col_widths, self.width))
        self.story.append(Spacer(0, 4 * mm))

    def key_values(self, pairs):
        self.story.append(key_values(pairs, self.width))
        self.story.append(Spacer(0, 3 * mm))

    def keep(self, *flowables):
        self.story.append(KeepTogether(list(flowables)))

    def page_break(self):
        self.story.append(PageBreak())

    def _decorate(self, canvas, doc):
        canvas.saveState()
        w, h = self.pagesize
        canvas.setFillColor(ACCENT)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(self.margin, h - 9 * mm, self.community.name[:90])
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - self.margin, h - 9 * mm, "FASAS - Fascicolo Socio Assistenziale Sanitario")
        canvas.setStrokeColor(GRID)
        canvas.line(self.margin, h - 10.5 * mm, w - self.margin, h - 10.5 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        footer = f"Generato il {self.generated_at:%d/%m/%Y %H:%M}"
        if self.generated_by:
            footer += f" da {self.generated_by}"
        footer += " - Documento contenente dati sanitari riservati (GDPR art. 9)"
        canvas.drawString(self.margin, 8 * mm, footer)
        canvas.drawRightString(w - self.margin, 8 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    def build(self):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=self.pagesize, leftMargin=self.margin, rightMargin=self.margin,
            topMargin=15 * mm, bottomMargin=14 * mm, title=self.title, author=self.community.name,
        )
        story = [p(self.title, "title")]
        if self.subtitle:
            story.append(p(self.subtitle, "small"))
        story.append(Spacer(0, 4 * mm))
        doc.build(story + self.story, onFirstPage=self._decorate, onLaterPages=self._decorate)
        return buffer.getvalue()


def pai_pdf(pai):
    from fasas.pai.models import PAIGoal

    guest = pai.guest
    doc = Document(
        f"Piano Assistenziale Individuale - v{pai.version}",
        f"{guest} - nato/a il {guest.birth_date:%d/%m/%Y} - CF {guest.fiscal_code}",
    )
    doc.key_values([
        ("Stato", pai.get_status_display()),
        ("In vigore dal", pai.valid_from),
        ("Revisione entro", pai.review_due),
        ("Approvato da", pai.approved_by),
        ("Partecipanti", pai.participants),
    ])
    if pai.summary:
        doc.heading("Sintesi e bisogni rilevati", 2)
        doc.text(pai.summary)
    goals = list(pai.goals.select_related("responsible"))
    for code, label in PAIGoal.Area.choices:
        area_goals = [g for g in goals if g.area == code]
        doc.heading(label)
        doc.table(
            ["Obiettivo", "Intervento", "Responsabile", "Verifica", "Indicatori", "Esito"],
            [[g.objective, g.intervention, g.responsible_display, g.verification_date, g.indicators,
              g.get_outcome_display()] for g in area_goals],
            col_widths=[3, 3.5, 1.6, 1.2, 1.8, 1.2],
        )
    doc.add(Spacer(0, 12 * mm))
    doc.table(["Firma coordinatore", "Firma medico", "Firma ospite / tutore"], [["", "", ""]])
    return doc.build()
