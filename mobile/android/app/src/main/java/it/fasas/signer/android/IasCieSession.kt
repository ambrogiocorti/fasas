package it.fasas.signer.android

import android.nfc.TagLostException
import android.nfc.tech.IsoDep
import it.fasas.signer.CardException
import it.fasas.signer.CieSession
import it.ipzs.cieidsdk.exceptions.BlockedPinException
import it.ipzs.cieidsdk.exceptions.PinInputNotValidException
import it.ipzs.cieidsdk.exceptions.PinNotValidException
import it.ipzs.cieidsdk.nfc.Ias
import java.io.IOException

/**
 * CIE via NFC (IsoDep) con il protocollo IAS: Diffie-Hellman, DAPP, canale sicuro, VERIFY PIN (8 cifre),
 * MSE SET + INTERNAL AUTHENTICATE sul DigestInfo (la carta applica il padding PKCS#1 v1.5).
 * Usa la classe Ias della libreria MIT di PagoPA/IPZS scaricata da scripts/fetch_ias.sh (versione fissata).
 * PROTOTIPO: non collaudato con una CIE reale.
 */
class IasCieSession(private val isoDep: IsoDep) : CieSession {
    private val ias = Ias(isoDep)

    override fun open(pin: String) = guard {
        try {
            ias.startSecureChannel(pin)
        } catch (e: PinNotValidException) {
            throw CardException("pin_wrong", "PIN errato.", e.tentativi)
        } catch (e: BlockedPinException) {
            throw CardException("pin_blocked", "PIN bloccato: sbloccarlo con il PUK dall'app «CIE ID».", 0)
        } catch (e: PinInputNotValidException) {
            throw CardException("pin_wrong", "Sul telefono il PIN della CIE è completo: 8 cifre.", null)
        }
    }

    override fun readCertificate(): ByteArray = guard {
        ias.readCertCie().also { if (it.isEmpty()) throw CardException("cert_missing", "Certificato non leggibile dalla carta.") }
    }

    override fun signDigestInfo(digestInfo: ByteArray): ByteArray = guard {
        ias.sign(digestInfo) ?: throw CardException("device_error", "La carta non ha restituito la firma.")
    }

    private fun <T> guard(block: () -> T): T = try {
        block()
    } catch (e: CardException) {
        throw e
    } catch (e: TagLostException) {
        throw CardException("card_removed", "La carta è stata allontanata dal telefono: riprovare tenendola ferma.")
    } catch (e: IOException) {
        throw CardException("card_removed", "Comunicazione NFC interrotta: riprovare tenendo ferma la carta.")
    } catch (e: Exception) {
        throw CardException("device_error", "Errore nel dialogo con la CIE (${e.javaClass.simpleName}).")
    }
}
