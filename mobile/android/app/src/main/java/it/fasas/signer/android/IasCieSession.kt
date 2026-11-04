package it.fasas.signer.android

import android.nfc.TagLostException
import android.nfc.tech.IsoDep
import it.fasas.signer.CardException
import it.fasas.signer.CieSession
import it.ipzs.cieidsdk.exceptions.BlockedPinException
import it.ipzs.cieidsdk.exceptions.NoCieException
import it.ipzs.cieidsdk.exceptions.PinInputNotValidException
import it.ipzs.cieidsdk.exceptions.PinNotValidException
import it.ipzs.cieidsdk.nfc.Ias
import java.io.IOException

/**
 * CIE via NFC (IsoDep) con il protocollo IAS: Diffie-Hellman, DAPP, canale sicuro, VERIFY PIN (8 cifre),
 * MSE SET + INTERNAL AUTHENTICATE sul DigestInfo (la carta applica il padding PKCS#1 v1.5).
 * Usa la classe Ias della libreria MIT di PagoPA/IPZS scaricata da scripts/fetch_ias.sh (versione fissata), con la
 * stessa sequenza dell'SDK ufficiale: lettura dell'ID servizi (riconosce la CIE), poi canale sicuro e PIN.
 * PROTOTIPO: non ancora collaudato con una CIE reale.
 */
class IasCieSession(isoDep: IsoDep, private val progress: (String) -> Unit = {}) : CieSession {
    private val ias = Ias(isoDep)

    /** Riconosce la CIE senza PIN (dati pubblici dei servizi): prova del collegamento NFC, nessun tentativo consumato. */
    fun check() = guard { ias.getIdServizi(); Unit }

    override fun open(pin: String) = guard {
        progress("CIE riconosciuta: verifico il PIN. Tienila ferma…")
        try {
            ias.getIdServizi()
            ias.startSecureChannel(pin)
        } catch (e: PinNotValidException) {
            throw CardException("pin_wrong", "PIN errato.", e.tentativi)
        } catch (e: BlockedPinException) {
            throw CardException("pin_blocked", "PIN bloccato: sbloccarlo con il PUK dall'app «CIE ID».", 0)
        } catch (e: PinInputNotValidException) {
            throw CardException("pin_wrong", "Sul telefono il PIN della CIE è completo: 8 cifre.", null)
        }
        progress("PIN corretto: lettura del certificato. Tienila ferma…")
    }

    override fun readCertificate(): ByteArray = guard {
        ias.readCertCie().also { if (it.isEmpty()) throw CardException("cert_missing", "Certificato non leggibile dalla carta.") }
    }

    override fun signDigestInfo(digestInfo: ByteArray): ByteArray = guard {
        progress("La carta sta firmando: tienila ferma…")
        ias.sign(digestInfo) ?: throw CardException("device_error", "La carta non ha restituito la firma.")
    }

    private fun <T> guard(block: () -> T): T = try {
        block()
    } catch (e: CardException) {
        throw e
    } catch (e: NoCieException) {
        throw CardException("not_cie", NOT_CIE)
    } catch (e: TagLostException) {
        throw CardException("card_removed", MOVED)
    } catch (e: IOException) {
        throw CardException("card_removed", MOVED)
    } catch (e: Exception) {
        throw CardException("device_error", "Errore nel dialogo con la CIE (${e.javaClass.simpleName}).")
    }

    companion object {
        const val MOVED = "La carta si è spostata durante la lettura."
        const val NOT_CIE = "La carta appoggiata non è una CIE: usa la Carta d'Identità Elettronica (quella in plastica, con il chip)."
    }
}
