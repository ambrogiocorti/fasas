package it.fasas.signer

import java.security.MessageDigest

class CardException(val code: String, message: String, val attemptsLeft: Int? = null) : Exception(message)

/**
 * Sessione con la CIE: su Android dura finché la carta resta appoggiata al telefono (una sessione NFC).
 * L'implementazione reale (IsoDep + protocollo IAS) è nel modulo app; qui solo il contratto.
 */
interface CieSession {
    /** Canale sicuro con la carta e verifica del PIN completo (8 cifre): il PIN va solo alla carta. */
    fun open(pin: String)

    /** Certificato X.509 (DER) della carta. */
    fun readCertificate(): ByteArray

    /** Firma il DigestInfo SHA-256; la carta applica il padding PKCS#1 v1.5 (come il middleware ufficiale). */
    fun signDigestInfo(digestInfo: ByteArray): ByteArray
}

sealed class Outcome {
    data class Signed(val level: String) : Outcome()
    data class PinWrong(val attemptsLeft: Int?) : Outcome()
    /** La carta si è allontanata prima della fine: la richiesta resta aperta, basta riappoggiarla. */
    data class CardMoved(val message: String) : Outcome()
    data class Failed(val code: String, val message: String) : Outcome()
}

/**
 * Flusso per telefono: conferma e PIN prima di avvicinare la carta, poi una sessione NFC breve in cui
 * si apre il canale sicuro, si legge il certificato, il FASAS prepara il documento e la carta firma.
 * Ogni passo usa il nonce del passo precedente; il PIN non viene mai inviato al server.
 * Se la carta si allontana a metà, i passi già fatti sul server restano validi e si riprende da lì.
 */
class SigningFlow(private val api: FasasApi) {
    private var nonce: String? = null
    private var cardReported = false
    private var prepared: Prepared? = null
    private var signingReported = false

    fun accept(request: SignRequest) {
        val claimed = api.claim(request.id)
        if (claimed.getString("verify_code") != request.verifyCode) {
            api.error(request.id, claimed.getString("nonce"), "device_error")
            throw ServerException(0, "verify_code", "Il codice di controllo non coincide: firma interrotta.")
        }
        nonce = claimed.getString("nonce")
        cardReported = false
        prepared = null
        signingReported = false
    }

    /**
     * Verifica con il telefono: presa in carico e sfida da firmare con la chiave del chip sicuro del telefono,
     * che si sblocca solo con impronta, volto o PIN del telefono (lo fa l'app, non questo flusso).
     */
    fun acceptDevice(request: SignRequest): ByteArray {
        val claimed = api.claim(request.id)
        if (claimed.getString("verify_code") != request.verifyCode || !claimed.has("challenge")) {
            api.error(request.id, claimed.getString("nonce"), "device_error")
            throw ServerException(0, "verify_code", "Richiesta incoerente ricevuta dal server: verifica interrotta.")
        }
        nonce = claimed.getString("nonce")
        return Base64Codec.decode(claimed.getString("challenge"))
    }

    fun confirmDevice(request: SignRequest, signature: ByteArray): Outcome {
        val current = nonce ?: return Outcome.Failed("bad_state", "Richiesta non presa in carico.")
        return try {
            val result = api.confirm(request.id, current, signature)
            Outcome.Signed(result.optJSONObject("verification")?.optString("level") ?: "Verifica di identità")
        } catch (e: ServerException) {
            Outcome.Failed(e.code, e.message ?: e.code)
        } finally {
            nonce = null
        }
    }

    fun refuse(request: SignRequest) {
        val claimed = api.claim(request.id)
        api.error(request.id, claimed.getString("nonce"), "cancelled")
    }

    fun cancel(request: SignRequest) = abort(request, "cancelled")

    /** Chiude la richiesta sul server con un codice d'errore (es. telefono non compatibile, errore imprevisto). */
    fun abort(request: SignRequest, code: String) {
        nonce?.let { runCatching { api.error(request.id, it, code) } }
        nonce = null
    }

    fun onCard(request: SignRequest, session: CieSession, pin: String): Outcome {
        var current = nonce ?: return Outcome.Failed("bad_state", "Richiesta non presa in carico.")
        try {
            if (!cardReported) {
                current = api.state(request.id, current, "card")
                nonce = current
                cardReported = true
            }
            try {
                session.open(pin)
            } catch (e: CardException) {
                if (e.code != "pin_wrong") throw e
                current = api.state(request.id, current, "pin_wrong", e.attemptsLeft)
                nonce = current
                return Outcome.PinWrong(e.attemptsLeft)
            }
            val certificate = session.readCertificate()
            val ready = prepared ?: api.certificate(request.id, current, certificate).also {
                current = it.nonce
                nonce = current
                prepared = it
            }
            val expected = SHA256_DIGEST_INFO_PREFIX + MessageDigest.getInstance("SHA-256").digest(ready.toBeSigned)
            if (!ready.digestInfo.contentEquals(expected) || ready.verifyCode != request.verifyCode) {
                throw CardException("device_error", "Dati da firmare incoerenti ricevuti dal server: firma interrotta.")
            }
            if (!signingReported) {
                current = api.state(request.id, current, "signing")
                nonce = current
                signingReported = true
            }
            val signature = session.signDigestInfo(ready.digestInfo)
            val result = api.sign(request.id, current, signature)
            nonce = null
            return Outcome.Signed(result.optJSONObject("verification")?.optString("level") ?: "PAdES")
        } catch (e: CardException) {
            if (e.code == "card_removed") return Outcome.CardMoved(e.message ?: "Carta allontanata.")
            runCatching { api.error(request.id, current, e.code) }
            nonce = null
            return Outcome.Failed(e.code, e.message ?: e.code)
        } catch (e: ServerException) {
            nonce = null
            return Outcome.Failed(e.code, e.message ?: e.code)
        }
    }

    companion object {
        val SHA256_DIGEST_INFO_PREFIX: ByteArray = byteArrayOf(
            0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86.toByte(), 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
            0x05, 0x00, 0x04, 0x20,
        )
    }
}
