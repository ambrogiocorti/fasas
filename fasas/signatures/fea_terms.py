"""
Condizioni della firma elettronica avanzata (FEA) con CIE e dichiarazione di accettazione (DPCM 22/02/2013, art. 57).

Il testo predefinito è una BOZZA da far approvare al consulente legale/DPO della struttura: con
FASAS_FEA_TERMS_FILE si indica il file di testo approvato (UTF-8), che sostituisce la bozza. Ogni versione del
testo ha un'impronta: l'accettazione registra quale testo esatto è stato firmato.
"""
import hashlib
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone

DRAFT_VERSION = "bozza-2026-10"

DRAFT_TEXT = """\
1. Che cos'è. La firma elettronica avanzata (FEA) con la Carta d'Identità Elettronica (CIE) permette di firmare
i documenti del fascicolo socio-assistenziale e sanitario gestiti da {community} con il software FASAS Digitale.
Non è una firma elettronica qualificata.

2. Dove vale. La FEA vale solo nei rapporti tra il firmatario e {community}, per i documenti gestiti con FASAS
Digitale (DPCM 22/02/2013, art. 60).

3. Come funziona. Il documento viene mostrato prima della firma. La firma si fa con la propria CIE e il proprio
PIN su FASAS Signer: il PIN non viene mai trasmesso né salvato e la chiave privata non esce dalla carta. Il
documento firmato (PAdES) contiene il certificato della CIE, che identifica il firmatario; ogni modifica
successiva alla firma è rilevabile. Le caratteristiche del sistema sono descritte nella pagina pubblica
«Caratteristiche della firma con CIE».

4. Identificazione. Il firmatario è identificato dal certificato della propria CIE, emessa dallo Stato dopo
l'identificazione in Comune, e dal codice fiscale registrato nel suo profilo FASAS, che deve coincidere.

5. Conservazione. Questa dichiarazione e il certificato che identifica il firmatario sono conservati da
{community} per almeno vent'anni. Il firmatario può ottenerne copia gratuitamente in ogni momento dalla
pagina «Firma digitale» di FASAS o chiedendola all'amministrazione.

6. Obblighi del firmatario. Custodire la CIE e il PIN, non cederli ad altri, firmare solo documenti che ha
letto, avvisare subito {community} in caso di furto o smarrimento della CIE o di uso non autorizzato.

7. Revoca. Il firmatario può revocare questa accettazione in ogni momento dalla pagina «Firma digitale»:
da quel momento non può più firmare con la CIE. Le firme già apposte restano valide.

8. Dati personali. Il trattamento dei dati è descritto nell'informativa per il personale di {community}.
"""


def terms():
    """(versione, testo) delle condizioni in uso: il file approvato se configurato, altrimenti la bozza."""
    community = _community_name()
    path = settings.FASAS_FEA_TERMS_FILE
    if path:
        text = Path(path).read_text(encoding="utf-8")
        version = Path(path).stem
    else:
        text, version = DRAFT_TEXT, DRAFT_VERSION
    return version, text.replace("{community}", community)


def is_draft():
    return not settings.FASAS_FEA_TERMS_FILE


def terms_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _community_name():
    from fasas.core.models import Community

    community = Community.default()
    return getattr(community, "name", "") or "la struttura"


def acceptance_pdf(user):
    """PDF della dichiarazione di accettazione da firmare con la CIE (nessun dato sanitario)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    version, text = terms()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("corpo", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                            bottomMargin=2 * cm, title="Accettazione delle condizioni della firma con CIE")
    story = [Paragraph("Dichiarazione di accettazione delle condizioni della firma elettronica avanzata con CIE",
                       styles["Title"])]
    if is_draft():
        story.append(Paragraph("<b>BOZZA – testo da far approvare al consulente legale della struttura.</b>", body))
    name = user.get_full_name() or user.username
    story += [
        Paragraph(f"Il/La sottoscritto/a <b>{_escape(name)}</b>, codice fiscale <b>{_escape(user.fiscal_code)}</b>, "
                  f"utente FASAS «{_escape(user.username)}», dichiara di aver letto e di accettare le seguenti "
                  "condizioni d'uso della firma elettronica avanzata con la propria CIE.", body),
        Spacer(1, 6),
    ]
    for paragraph in text.strip().split("\n\n"):
        story.append(Paragraph(_escape(" ".join(paragraph.split())), body))
    story += [
        Spacer(1, 10),
        Paragraph(f"Versione delle condizioni: {_escape(version)} · impronta SHA-256 del testo: "
                  f"{terms_sha256(text)}", body),
        Paragraph(f"Data: {timezone.localtime():%d/%m/%Y %H:%M}. Firmato con la CIE del dichiarante.", body),
    ]
    doc.build(story)
    return buffer.getvalue()


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
