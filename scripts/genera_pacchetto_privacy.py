#!/usr/bin/env python3
"""
Pacchetto «privacy e moduli» per usare il FASAS in comunità, in uno zip con cartelle numerate nell'ordine d'uso:
- i documenti di governo (registro, DPIA, nomine, procedure) dai testi in docs/: Word modificabile, con i campi da
  compilare tra [parentesi quadre] evidenziati in giallo, e PDF;
- i moduli (informative, autorizzazioni, consensi, accordi, richieste) in PDF da stampare, dagli stessi testi
  predefiniti che il FASAS carica nella Modulistica (fasas/modulistica/defaults.py): nel FASAS l'amministratore li
  adatta, li pubblica e li fa compilare anche online.

    python scripts/genera_pacchetto_privacy.py [cartella_di_uscita]

Servono pandoc, LibreOffice (soffice) e python-docx. Nessun dato personale: sono modelli vuoti.
"""
import datetime
import math
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# cartella nello zip, file sorgente (relativo a docs/)
PACKAGE = [
    ("0_Leggimi", "gdpr/README.md", "00_LEGGIMI"),
    ("1_Prima_dei_dati_reali", "ADEMPIMENTI_PRIMA_DELL_AVVIO.md", None),
    ("1_Prima_dei_dati_reali", "gdpr/CHECKLIST_ATS.md", None),
    ("2_Registro_e_valutazione_impatto", "gdpr/REGISTRO_TRATTAMENTI.md", None),
    ("2_Registro_e_valutazione_impatto", "gdpr/DPIA.md", None),
    ("2_Registro_e_valutazione_impatto", "AREA_FAMILIARI_DPO.md", None),
    ("3_Nomine_e_fornitori", "gdpr/RESPONSABILI_E_NOMINE.md", None),
    ("3_Nomine_e_fornitori", "gdpr/ACCORDO_ART28_FORNITORE.md", None),
    ("4_Moduli", "MODULISTICA.md", "00_COME_SI_USANO_I_MODULI"),
    ("5_Violazioni_e_continuita", "gdpr/PROCEDURA_VIOLAZIONI.md", None),
    ("5_Violazioni_e_continuita", "SICUREZZA_FISICA_E_CONTINUITA.md", None),
    ("5_Violazioni_e_continuita", "PIANO_DI_CONTINUITA.md", None),
    ("6_Allegati_tecnici", "SICUREZZA.md", None),
    ("6_Allegati_tecnici", "BACKUP.md", None),
    ("6_Allegati_tecnici", "DISPOSITIVO_MEDICO.md", None),
    ("6_Allegati_tecnici", "FIRMA_CIE.md", None),
    ("6_Allegati_tecnici", "MODELLO_CONTRATTO_ASSISTENZA.md", None),
    ("6_Allegati_tecnici", "NOVITA_ASSISTENZA_E_FAMILIARI.md", None),
]

# moduli predefiniti in PDF (codice del modulo -> sottocartella di 4_Moduli)
FORM_FOLDERS = {
    "informativa-personale": "Personale", "autorizzazione-personale": "Personale",
    "nomina-amministratore-sistema": "Personale",
    "informativa-ospiti": "Ospiti_e_tutori", "cassa-e-oggetti": "Ospiti_e_tutori", "foto-lesioni": "Ospiti_e_tutori",
    "richiesta-diritti": "Ospiti_e_tutori",
    "informativa-familiari": "Area_familiari_solo_se_attivata", "accesso-area-familiari": "Area_familiari_solo_se_attivata",
}

LINK = re.compile(r"\[([^\]]+)\]\((?!https?://|mailto:)[^)]*\)")  # link a file del repository: resta il testo
PLACEHOLDER = re.compile(r"\[[^\[\]]{1,400}\]")
PAGE_WIDTH = 9638  # A4 con margini di 2 cm, in ventesimi di punto


def prepare(text):
    text = LINK.sub(r"\1", text)
    # i nomi dei file .md citati nel testo diventano i nomi dei documenti del pacchetto
    return re.sub(r"(?:\.\./|docs/|gdpr/)*\b([A-Z][A-Z0-9_]+)\.md\b", r"«\1»", text)


def reference_docx(workdir):
    """Stili di base di pandoc con carattere, margini e intestazioni più adatti alla stampa."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    path = workdir / "riferimento.docx"
    subprocess.run(["pandoc", "-o", str(path), "--print-default-data-file", "reference.docx"], check=True)
    doc = Document(path)
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin = section.right_margin = Cm(2)
        section.top_margin, section.bottom_margin = Cm(2), Cm(1.8)
    by_name = {s.name: s for s in doc.styles}  # nomi come li scrive pandoc («Heading 1», non «heading 1»)
    for name in ("Normal", "Body Text", "First Paragraph", "Compact", "Block Text"):
        if name in by_name:
            by_name[name].font.name, by_name[name].font.size = "Arial", Pt(10.5)
    for level, size in ((1, 16), (2, 13), (3, 11.5), (4, 11)):
        style = by_name[f"Heading {level}"]
        style.font.name, style.font.size, style.font.bold = "Arial", Pt(size), True
        style.font.color.rgb = RGBColor(0x1D, 0x4E, 0x89)
    from docx.oxml.ns import qn

    for style in doc.styles:  # i caratteri «del tema» prevalgono su quelli indicati: si tolgono
        fonts = style.element.find(qn("w:rPr") + "/" + qn("w:rFonts")) if style.element is not None else None
        if fonts is not None:
            for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                fonts.attrib.pop(qn(attr), None)
            fonts.set(qn("w:ascii"), "Arial")
            fonts.set(qn("w:hAnsi"), "Arial")
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.save(path)
    return path


def _field(paragraph, instruction):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    begin, text, end = OxmlElement("w:fldChar"), OxmlElement("w:instrText"), OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    text.set(qn("xml:space"), "preserve")
    text.text = instruction
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, text, end])
    run.font.size = paragraph.runs[0].font.size if paragraph.runs else None
    return run


def _highlight_placeholders(paragraph):
    """Divide i run che contengono [campi da compilare] ed evidenzia in giallo solo i campi."""
    import copy

    from docx.enum.text import WD_COLOR_INDEX
    from docx.text.run import Run

    for run in list(paragraph.runs):
        text = run.text
        if not PLACEHOLDER.search(text):
            continue
        pieces, last = [], 0
        for match in PLACEHOLDER.finditer(text):
            pieces += [(text[last:match.start()], False), (match.group(0), True)]
            last = match.end()
        pieces.append((text[last:], False))
        anchor = run._r
        for piece, mark in pieces:
            if not piece:
                continue
            element = copy.deepcopy(run._r)
            anchor.addnext(element)
            anchor = element
            new = Run(element, paragraph)
            new.text = piece
            if mark:
                new.font.highlight_color = WD_COLOR_INDEX.YELLOW
        run._r.getparent().remove(run._r)


def _style_table(table):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    rows = table.rows
    columns = max(len(r.cells) for r in rows)
    # larghezze proporzionali al contenuto (radice della lunghezza, con un minimo), tabella a tutta pagina
    weight, minimum = [0.0] * columns, [700] * columns
    char = 110 if columns >= 6 else 120  # larghezza media di un carattere (ventesimi di punto) col corpo usato
    for row in rows:
        for i, cell in enumerate(row.cells[:columns]):
            weight[i] = max(weight[i], math.sqrt(len(cell.text) + 8))
            longest = max((len(word) for word in cell.text.split()), default=0)
            minimum[i] = max(minimum[i], min(2600, longest * char + 260))  # nessuna parola spezzata
    # prima a ogni colonna lo spazio per la sua parola più lunga, poi il resto in proporzione al contenuto
    total, free = sum(weight) or 1, PAGE_WIDTH - sum(minimum)
    if free > 0:
        widths = [int(minimum[i] + free * weight[i] / total) for i in range(columns)]
    else:
        widths = [int(m * PAGE_WIDTH / sum(minimum)) for m in minimum]
    tbl_pr = table._tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout", "w:tblBorders"):
        for old in tbl_pr.findall(qn(tag)):
            tbl_pr.remove(old)
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:w"), str(PAGE_WIDTH))
    tbl_w.set(qn("w:type"), "dxa")
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "9AA5B1")
        borders.append(border)
    tbl_pr.extend([tbl_w, layout, borders])
    grid = table._tbl.tblGrid
    for i, col in enumerate(grid.findall(qn("w:gridCol"))):
        if i < columns:
            col.set(qn("w:w"), str(widths[i]))
    size = Pt(8.5) if columns >= 6 else Pt(9.5)
    for r, row in enumerate(rows):
        for i, cell in enumerate(row.cells[:columns]):
            cell.width = widths[i]
            tc_pr = cell._tc.get_or_add_tcPr()
            if r == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:val"), "clear")
                shade.set(qn("w:color"), "auto")
                shade.set(qn("w:fill"), "E8EEF5")
                tc_pr.append(shade)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = size
                    if r == 0:
                        run.font.bold = True


def finish_docx(path, title):
    from docx import Document
    from docx.shared import Pt

    doc = Document(path)
    for paragraph in doc.paragraphs:
        _highlight_placeholders(paragraph)
    for table in doc.tables:
        _style_table(table)
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _highlight_placeholders(paragraph)
    core = doc.core_properties
    core.title, core.author, core.comments = title, "FASAS Digitale", "Bozza da completare e far validare"
    for section in doc.sections:
        footer = section.footer.paragraphs[0]
        footer.text = ""
        lead = footer.add_run(f"FASAS Digitale – {title} – bozza da completare e far validare · pagina ")
        lead.font.size = Pt(8)
        _field(footer, "PAGE").font.size = Pt(8)
        footer.add_run(" di ").font.size = Pt(8)
        _field(footer, "NUMPAGES").font.size = Pt(8)
    doc.save(path)


def title_of(text, fallback):
    for line in text.splitlines():
        if line.startswith("# "):
            return re.sub(r"\s*[–-]\s*(bozza|modulo|modello)\b.*$", "", line[2:].strip(), flags=re.I)[:90]
    return fallback


def render_forms(target):
    """PDF da stampare dei moduli predefiniti, con le stesse funzioni che usa il FASAS (nessun database)."""
    sys.path.insert(0, str(ROOT))
    from fasas.modulistica import defaults, pdf
    from fasas.modulistica.text import default_snapshot

    count = 0
    for number, data in enumerate(defaults.TEMPLATES, start=1):
        folder = target / FORM_FOLDERS.get(data["code"], "Altri")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{number:02d}_{data['code']}.pdf").write_bytes(pdf.render(default_snapshot(data)))
        count += 1
    return count


def build(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y-%m-%d")
    zip_path = out_dir / f"FASAS_privacy_e_moduli_{stamp}.zip"
    with tempfile.TemporaryDirectory(prefix="fasas-pacchetto-") as tmp:
        work = Path(tmp)
        reference = reference_docx(work)
        staged = work / "pacchetto"
        made = []
        for folder, source, name in PACKAGE:
            src = DOCS / source
            text = src.read_text(encoding="utf-8")
            stem = name or src.stem
            target_dir = staged / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            md = work / f"{stem}.md"
            md.write_text(prepare(text), encoding="utf-8")
            docx_path = target_dir / f"{stem}.docx"
            subprocess.run(["pandoc", str(md), "-f", "gfm", "-o", str(docx_path), f"--reference-doc={reference}"],
                           check=True)
            finish_docx(docx_path, title_of(text, stem))
            made.append(docx_path)
        normalized = work / "normalizzati"
        for target_dir in sorted({p.parent for p in made}):
            docs = [str(p) for p in made if p.parent == target_dir]
            # LibreOffice riscrive i file Word in OOXML conforme (pandoc lascia piccole difformità di schema
            # che Word tollera ma che è meglio non consegnare), poi ne fa i PDF
            shutil.rmtree(normalized, ignore_errors=True)
            subprocess.run(["soffice", "--headless", "--convert-to", "docx:MS Word 2007 XML", "--outdir",
                            str(normalized), *docs], check=True, capture_output=True, timeout=600)
            for doc in docs:
                shutil.move(str(normalized / Path(doc).name), doc)
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(target_dir), *docs],
                           check=True, capture_output=True, timeout=600)
        forms = render_forms(staged / "4_Moduli")
        missing = [p for p in made if not p.with_suffix(".pdf").exists()]
        if missing:
            raise SystemExit(f"PDF non creati: {', '.join(p.name for p in missing)}")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staged.rglob("*")):
                if file.is_file():
                    archive.write(file, f"FASAS_privacy_e_moduli/{file.relative_to(staged)}")
        preview = out_dir / "anteprima"
        shutil.rmtree(preview, ignore_errors=True)
        shutil.copytree(staged, preview)
    print(f"Creato {zip_path} ({len(made)} documenti in Word e PDF, {forms} moduli in PDF)")
    return zip_path


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "pacchetto_privacy")
