"""Allegati fotografati o scansionati (scontrini, attestati): PDF così com'è, foto ridotte e senza dati EXIF."""
from io import BytesIO

from .models import SystemConfig


class UploadError(ValueError):
    pass


def clean_pdf_or_photo(uploaded, max_side=1800):
    """Restituisce (byte, tipo): il PDF invariato oppure la foto JPEG/PNG ricompressa in JPEG, senza EXIF (posizione)."""
    limit_mb = SystemConfig.get().max_upload_mb
    if uploaded.size > limit_mb * 1024 * 1024:
        raise UploadError(f"Il file supera la dimensione massima di {limit_mb} MB.")
    head = uploaded.read(5)
    uploaded.seek(0)
    if head == b"%PDF-":
        return uploaded.read(), "application/pdf"
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(uploaded)
        if image.format not in ("JPEG", "PNG"):
            raise UploadError("Formato non ammesso: foto JPEG o PNG, oppure PDF.")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side))
        output = BytesIO()
        image.convert("RGB").save(output, "JPEG", quality=82)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise UploadError("Il file non è un'immagine o un PDF leggibile.") from None
    return output.getvalue(), "image/jpeg"
