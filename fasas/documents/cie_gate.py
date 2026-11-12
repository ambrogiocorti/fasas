"""
Verifica con CIE prima di aprire, scaricare o modificare i documenti (Configurazione generale, spenta per default).
Con la verifica attiva ogni pagina che mostra o cambia il contenuto di un documento passa da qui.
"""
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


def cie_gate(request, guest, document=None, next_url=None):
    """None se l'utente può procedere; altrimenti il redirect alla verifica di identità con la CIE."""
    from fasas.signatures import cie

    if cie.has_document_access(request.user, guest, document):
        return None
    params = {"next": next_url or request.get_full_path()}
    if document is not None:
        params["documento"] = document.pk
    else:
        params["ospite"] = guest.pk
    return redirect(f"{reverse('signatures:cie_access')}?{urlencode(params)}")
