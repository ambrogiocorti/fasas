"""
PDF dei moduli: vuoto da compilare a mano, oppure già compilato online. Non dipende dal database (serve anche allo
script che prepara il pacchetto cartaceo). Caratteri standard PDF: le caselle sono disegnate, non sono simboli.
"""
import re
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#1F2933")
ACCENT = colors.HexColor("#1D4E89")
MUTED = colors.HexColor("#5F6B7A")
LINE = colors.HexColor("#9AA5B1")
MARGIN = 18 * mm
WIDTH = A4[0] - 2 * MARGIN - 12  # meno i margini interni (6 pt per lato) della cornice di reportlab

STYLES = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=INK,
                            alignment=TA_LEFT, spaceAfter=2 * mm),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, leading=12.4, textColor=INK, spaceAfter=2.2 * mm),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.2, leading=12.4, textColor=INK,
                             leftIndent=5 * mm, bulletIndent=1.5 * mm, spaceAfter=0.8 * mm),
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8.4, leading=10.5, textColor=INK),
    "value": ParagraphStyle("value", fontName="Helvetica", fontSize=9.2, leading=12, textColor=INK),
    "option": ParagraphStyle("option", fontName="Helvetica", fontSize=8.8, leading=11, textColor=INK),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=9.6, leading=12, textColor=ACCENT,
                              spaceBefore=2.5 * mm, spaceAfter=1 * mm),
    "help": ParagraphStyle("help", fontName="Helvetica-Oblique", fontSize=7.6, leading=9.5, textColor=MUTED),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED),
    "sign": ParagraphStyle("sign", fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED),
}


def markup(text):
    """Testo dei moduli: escape dell'HTML, poi **grassetto**."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))


def text_blocks(text):
    """Paragrafi e righe d'elenco del testo di un modulo."""
    flow = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("- ") for line in lines):
            flow += [Paragraph(markup(line.lstrip()[2:]), STYLES["bullet"], bulletText="•") for line in lines]
            flow.append(Spacer(0, 1.4 * mm))
        else:
            flow.append(Paragraph(markup(" ".join(line.strip() for line in lines)), STYLES["body"]))
    return flow


class Box(Flowable):
    """Casella da spuntare (vuota o con la crocetta)."""

    def __init__(self, checked=False, size=3.4 * mm):
        super().__init__()
        self.checked, self.size = checked, size
        self.width = self.height = size

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        c.rect(0, 0, self.size, self.size)
        if self.checked:
            c.setLineWidth(1.1)
            c.line(0.7, 0.7, self.size - 0.7, self.size - 0.7)
            c.line(0.7, self.size - 0.7, self.size - 0.7, 0.7)


def _lines(count, height=7 * mm):
    rows = [[""] for _ in range(count)]
    t = Table(rows, colWidths=[WIDTH], rowHeights=[height] * count)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE)]))
    return t


def _options(options, chosen, per_row=3):
    chosen = set(chosen if isinstance(chosen, (list, tuple)) else [chosen] if chosen else [])
    cells = [(Box(option in chosen), Paragraph(markup(option), STYLES["option"])) for option in options]
    if any(len(o) > 38 for o in options):
        per_row = 1
    elif any(len(o) > 22 for o in options):
        per_row = 2
    rows = []
    for i in range(0, len(cells), per_row):
        row = []
        for box, label in cells[i:i + per_row]:
            row += [box, label]
        row += [""] * (2 * per_row - len(row))
        rows.append(row)
    col = (WIDTH - per_row * 6 * mm) / per_row
    t = Table(rows, colWidths=[6 * mm, col] * per_row)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]))
    return t


def field_flow(field, value=None, filled=False):
    kind, label = field["kind"], markup(field["label"])
    if kind == "section":
        return [Paragraph(label, STYLES["section"])]
    if kind == "check":
        t = Table([[Box(bool(value)), Paragraph(label, STYLES["value"])]], colWidths=[6 * mm, WIDTH - 6 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (0, 0), 2.2)]))
        return [t, Spacer(0, 1.6 * mm)]
    parts = [Paragraph(label + (" *" if field.get("required") and not filled else ""), STYLES["label"])]
    if field.get("help_text") and not filled:
        parts.append(Paragraph(markup(field["help_text"]), STYLES["help"]))
    if kind in ("choice", "multi"):
        parts.append(_options(field.get("options") or [], value if filled else None))
    elif filled:
        shown = value or "—"
        parts.append(Paragraph(markup(str(shown)).replace("\n", "<br/>"), STYLES["value"]))
    else:
        parts.append(_lines(3 if kind == "textarea" else 1, 6.5 * mm))
    return [KeepTogether(parts), Spacer(0, 2.2 * mm)]


def _signatures(labels):
    if not labels:
        return []
    flow = [Spacer(0, 5 * mm)]
    place = Table([["Luogo e data", ""]], colWidths=[24 * mm, 66 * mm], rowHeights=[8 * mm], hAlign="LEFT")
    place.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, 0), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                               ("FONT", (0, 0), (0, 0), "Helvetica", 8.4), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    flow += [place, Spacer(0, 6 * mm)]
    col = (WIDTH - 10 * mm) / 2
    rows, cells = [], [Paragraph(markup(label), STYLES["sign"]) for label in labels]
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2]))
        rows += [["", "", ""], [pair[0], "", pair[1]]]
    t = Table(rows, colWidths=[col, 10 * mm, col], rowHeights=[12 * mm, 7 * mm] * (len(rows) // 2))
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]
    for r in range(0, len(rows), 2):
        style.append(("LINEBELOW", (0, r), (0, r), 0.6, INK))
        if rows[r + 1][2] != "":
            style.append(("LINEBELOW", (2, r), (2, r), 0.6, INK))
    t.setStyle(TableStyle(style))
    return flow + [KeepTogether([t])]


def _numbered_canvas(header, code_line):
    class NumberedCanvas(pdf_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            w, h = A4
            self.setFillColor(INK)
            self.setFont("Helvetica-Bold", 9)
            self.drawString(MARGIN, h - 12 * mm, (header.get("holder") or header.get("struttura") or "")[:95])
            self.setFont("Helvetica", 7.6)
            self.setFillColor(MUTED)
            sub = " · ".join(x for x in (header.get("address"), header.get("contacts")) if x)
            self.drawString(MARGIN, h - 15.5 * mm, sub[:130])
            self.drawRightString(w - MARGIN, h - 12 * mm, code_line)
            self.setStrokeColor(LINE)
            self.setLineWidth(0.5)
            self.line(MARGIN, h - 17.5 * mm, w - MARGIN, h - 17.5 * mm)
            self.drawRightString(w - MARGIN, 10 * mm, f"Pagina {self._pageNumber} di {total}")
            self.drawString(MARGIN, 10 * mm, "Modulo generato con FASAS Digitale")

    return NumberedCanvas


def render(snapshot, answers=None, meta=None):
    """snapshot: titolo, testo già con le variabili, campi, firme, intestazione. answers None = modulo vuoto."""
    filled = answers is not None
    answers = answers or {}
    meta = meta or {}
    header = snapshot.get("header", {})
    flow = [Paragraph(markup(snapshot["title"]), STYLES["title"])]
    subject = meta.get("subject") or ""
    if subject:
        flow.append(Paragraph(markup(subject), STYLES["label"]))
        flow.append(Spacer(0, 2 * mm))
    elif snapshot.get("subject_label"):
        t = Table([[snapshot["subject_label"], ""]], colWidths=[22 * mm, WIDTH - 22 * mm], rowHeights=[7 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, 0), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                               ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 8.4), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        flow += [t, Spacer(0, 3 * mm)]
    flow += text_blocks(snapshot.get("intro", ""))
    fields = snapshot.get("fields") or []
    if fields:
        flow.append(Spacer(0, 1.5 * mm))
        for field in fields:
            flow += field_flow(field, answers.get(field["key"]), filled)
    if filled and meta.get("record"):
        note = Table([[Paragraph(markup(meta["record"]), STYLES["note"])]], colWidths=[WIDTH])
        note.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, -1),
                                                                         colors.HexColor("#F4F6F8")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        flow += [Spacer(0, 2 * mm), note]
    if not filled or snapshot.get("requires_signature") or meta.get("paper_signatures"):
        flow += _signatures(snapshot.get("signatures") or [])
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=23 * mm,
                            bottomMargin=16 * mm, title=snapshot["title"], author=header.get("holder") or "")
    code_line = f"Mod. {snapshot.get('code', '')} · v{snapshot.get('version', 1)}"
    doc.build(flow, canvasmaker=_numbered_canvas(header, code_line))
    return buffer.getvalue()
