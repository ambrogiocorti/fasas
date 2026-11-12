"""
Punti di controllo dell'audit log: rendono la catena verificabile anche da terzi.

La catena di hash rileva una modifica isolata, ma chi controlla il database potrebbe riscriverla tutta.
Ogni notte si salva l'impronta dell'ultima voce (testa della catena) e, se è configurata una TSA reale
(FASAS_SIGNATURE_TSA_URL), la si fa marcare temporalmente (RFC 3161): il gestore della TSA firma che
quell'impronta esisteva a quell'ora. Riscrivere la storia precedente cambia l'impronta della voce marcata
e la verifica lo rileva. La ricevuta (testo marcato + marca) si scarica e si verifica con OpenSSL;
i punti di controllo finiscono anche nei backup e nella copia fuori sede immutabile.
Senza TSA il punto di controllo resta, dichiarato «senza marca temporale»: nessuna marca simulata.
"""
import asyncio
import hashlib
import io
import logging
import zipfile

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("fasas.audit")


def anchor_message(last_entry_id, head_hash, entries):
    """Testo esatto che viene marcato: chiunque può ricalcolarne l'impronta."""
    return (f"FASAS Digitale - punto di controllo dell'audit log\n"
            f"ultima voce: {last_entry_id}\nvoci: {entries}\nimpronta della voce (SHA-256): {head_hash}\n").encode()


def timestamper():
    from fasas.signatures.providers import timestamper as signature_timestamper

    return signature_timestamper()


def request_timestamp(message):
    """Marca temporale RFC 3161 sull'impronta del messaggio. Restituisce (token DER, ora della TSA)."""
    stamper = timestamper()
    if stamper is None:
        return None, None
    content_info = asyncio.run(stamper.async_timestamp(hashlib.sha256(message).digest(), "sha256"))
    signed_data = content_info["content"]
    tst_info = signed_data["encap_content_info"]["content"].parsed
    return content_info.dump(), tst_info["gen_time"].native


def verify_timestamp(token, message):
    """
    Controlla la marca: impronta uguale al messaggio e firma della TSA integra. «affidabile» solo se il
    certificato della TSA risale alle CA configurate in FASAS_SIGNATURE_TRUST_ROOTS.
    """
    from asn1crypto import cms
    from pyhanko.sign.validation.generic_cms import validate_tst_signed_data
    from pyhanko_certvalidator import ValidationContext

    from fasas.signatures.providers import trust_roots

    content_info = cms.ContentInfo.load(bytes(token))
    roots = trust_roots()
    context = ValidationContext(trust_roots=roots, allow_fetching=False, revocation_mode="soft-fail") if roots else None

    def expected(algorithm):
        return hashlib.new(algorithm, message).digest()

    try:
        status = asyncio.run(validate_tst_signed_data(content_info["content"], context, expected))
    except Exception as exc:  # impronta diversa o firma non valida
        return {"intact": False, "trusted": False, "time": None, "error": str(exc)[:200]}
    trusted = bool(roots) and status.get("validation_path") is not None and status.get("trust_problem_indic") is None
    return {"intact": bool(status.get("intact")) and bool(status.get("valid")), "trusted": trusted,
            "time": status.get("timestamp")}


def create_checkpoint(source="job"):
    """Verifica tutta la catena, controlla i punti di controllo precedenti e ne salva uno nuovo."""
    from .models import AuditCheckpoint, AuditLog
    from .services import verify_chain

    started = timezone.now()
    ok, count, broken = verify_chain()
    rewritten = [cp.pk for cp in check_previous_checkpoints()]
    last = AuditLog.objects.order_by("-id").values("id", "hash").first()
    checkpoint = AuditCheckpoint(
        source=source, entries=count, chain_ok=ok and not rewritten, broken_at=broken,
        last_entry_id=last["id"] if last else None, head_hash=last["hash"] if last else "",
        mismatched_checkpoints=rewritten,
    )
    if checkpoint.chain_ok and last and settings.FASAS_AUDIT_TIMESTAMP:
        message = anchor_message(checkpoint.last_entry_id, checkpoint.head_hash, count)
        try:
            token, gen_time = request_timestamp(message)
        except Exception as exc:  # la TSA non risponde: si riprova la notte dopo, senza inventare nulla
            token, gen_time = None, None
            checkpoint.timestamp_error = f"{type(exc).__name__}: {exc}"[:255]
            logger.warning("Marca temporale dell'audit non ottenuta: %s", exc)
        if token:
            checkpoint.timestamp_token, checkpoint.timestamp_time = token, gen_time
            checkpoint.tsa_url = settings.FASAS_SIGNATURE_TSA_URL[:255]
    checkpoint.duration_ms = int((timezone.now() - started).total_seconds() * 1000)
    checkpoint.save()
    if not checkpoint.chain_ok:
        from fasas.notifications.services import notify

        detail = (f"la catena è interrotta alla voce #{broken}" if not ok else
                  "la storia è stata riscritta: l'impronta di voci già ancorate non corrisponde più")
        notify("audit_chain_broken", "Integrità audit log compromessa",
               f"Verifica dell'audit log: {detail}. Verificare subito il database e confrontare con i backup.",
               level="critical", dedup_key=f"audit-broken-{broken or rewritten[0]}")
        logger.error("Audit log non integro: %s", detail)
    return checkpoint


def check_previous_checkpoints():
    """Punti di controllo la cui voce ancorata oggi ha un'impronta diversa (storia riscritta o cancellata)."""
    from .models import AuditCheckpoint, AuditLog

    anchored = AuditCheckpoint.objects.filter(chain_ok=True, last_entry_id__isnull=False).order_by("id")
    current = dict(AuditLog.objects.filter(id__in=anchored.values("last_entry_id")).values_list("id", "hash"))
    return [cp for cp in anchored if current.get(cp.last_entry_id) != cp.head_hash]


def receipt_zip(checkpoint):
    """Ricevuta verificabile da terzi: testo marcato, marca temporale e istruzioni."""
    message = checkpoint.message()
    readme = (
        "Ricevuta di un punto di controllo dell'audit log di FASAS Digitale.\n\n"
        "punto-di-controllo.txt  testo esatto di cui la TSA ha marcato l'impronta SHA-256\n"
        "marca-temporale.tst     marca temporale RFC 3161 (TimeStampToken, DER)\n\n"
        "Verifica con OpenSSL (tsa-ca.pem = certificati della TSA, pubblicati dal prestatore):\n"
        "  openssl ts -verify -data punto-di-controllo.txt -in marca-temporale.tst -token_in -CAfile tsa-ca.pem\n\n"
        "Poi confrontare l'impronta con quella della stessa voce nell'audit log ripristinato o in esame:\n"
        "se la storia fosse stata riscritta, l'impronta della voce sarebbe diversa.\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("punto-di-controllo.txt", message)
        if checkpoint.timestamp_token:
            archive.writestr("marca-temporale.tst", bytes(checkpoint.timestamp_token))
        else:
            readme += "\nQuesto punto di controllo NON ha marca temporale (nessuna TSA configurata o raggiungibile).\n"
        archive.writestr("LEGGIMI.txt", readme)
    return buffer.getvalue()


def export_lines():
    """Elenco testuale dei punti di controllo, incluso nei backup e nella copia fuori sede."""
    from .models import AuditCheckpoint

    rows = ["id;data;ultima_voce;voci;impronta;integra;marca_temporale"]
    for cp in AuditCheckpoint.objects.order_by("id"):
        rows.append(f"{cp.pk};{cp.created_at.isoformat()};{cp.last_entry_id or ''};{cp.entries};{cp.head_hash};"
                    f"{'si' if cp.chain_ok else 'no'};{cp.timestamp_time.isoformat() if cp.timestamp_time else ''}")
    return "\n".join(rows) + "\n"
