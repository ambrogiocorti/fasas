package it.fasas.signer.android

import android.nfc.TagLostException
import android.nfc.tech.IsoDep
import it.fasas.signer.CardException
import it.fasas.signer.NisCardData
import java.io.ByteArrayOutputStream
import java.io.IOException

/**
 * CIE senza il suo PIN, con il protocollo «NIS» del Ministero dell'Interno (stessi comandi dell'SDK ufficiale
 * italia/cie-nis-java-sdk, licenza BSD-3): si leggono il NIS (EF 1001), la chiave pubblica dell'autenticazione
 * interna (EF 1005) e, alla registrazione, il SOD firmato dal Ministero (EF 1006); poi la carta firma con la sua
 * chiave privata la sfida del FASAS (INTERNAL AUTHENTICATE), così dimostra di essere originale. Nessun PIN.
 * PROTOTIPO: non ancora collaudato con una CIE reale.
 */
class NisSession(private val isoDep: IsoDep, private val progress: (String) -> Unit = {}) {

    private class Response(val data: ByteArray, val sw: Int) {
        val sw1 get() = sw shr 8
        val sw2 get() = sw and 0xFF
    }

    fun read(challenge: ByteArray, withSod: Boolean): NisCardData = guard {
        progress("CIE rilevata: lettura in corso, tienila ferma…")
        transmit(hex("00A4040C0DA0000000308000000009816001"))  // applicazione IAS (come l'SDK ufficiale)
        selectCie()
        val nis = readFile(0x1001)
        if (nis.isEmpty()) throw CardException("not_cie", IasCieSession.NOT_CIE)
        val kpub = readFile(0x1005)
        progress("La carta conferma di essere originale…")
        val response = internalAuthenticate(challenge)
        val sod = if (withSod) {
            selectCie()
            readFile(0x1006).also { if (it.isEmpty()) throw CardException("cert_missing", "Dati firmati della carta non leggibili.") }
        } else null
        NisCardData(nis, kpub, response, sod)
    }

    private fun selectCie() = command(hex("00A4040C06A00000000039"))

    /** MSE SET sulla chiave dell'autenticazione interna (0x83), poi INTERNAL AUTHENTICATE con la sfida. */
    private fun internalAuthenticate(challenge: ByteArray): ByteArray {
        command(hex("002241A406800102840183"))
        val response = command(byteArrayOf(0x00, 0x88.toByte(), 0x00, 0x00, challenge.size.toByte()) + challenge)
        if (response.isEmpty()) throw CardException("device_error", "La carta non ha risposto alla sfida.")
        return response
    }

    private fun readFile(id: Int): ByteArray {
        command(byteArrayOf(0x00, 0xA4.toByte(), 0x02, 0x04, 0x02, (id shr 8).toByte(), id.toByte()))
        val out = ByteArrayOutputStream()
        var offset = 0
        while (offset < 0x8000) {
            val head = byteArrayOf(0x00, 0xB0.toByte(), (offset shr 8).toByte(), offset.toByte())
            var r = transmit(head + byteArrayOf(0x00))  // fino a 256 byte
            if (r.sw1 == 0x6C) r = transmit(head + byteArrayOf(r.sw2.toByte()))  // lunghezza esatta indicata dalla carta
            if (r.sw1 == 0x61) r = getResponse(r)
            when {
                r.sw == 0x9000 && r.data.isNotEmpty() -> { out.write(r.data); offset += r.data.size }
                r.sw == 0x6282 -> { out.write(r.data); break }  // fine del file prima dei byte chiesti
                else -> break  // 0x6B00: oltre la fine del file
            }
        }
        return out.toByteArray()
    }

    /** Comando che deve riuscire (9000, anche dopo GET RESPONSE); altrimenti la carta non è una CIE. */
    private fun command(apdu: ByteArray): ByteArray {
        var r = transmit(apdu)
        if (r.sw1 == 0x61) r = getResponse(r)
        if (r.sw != 0x9000) throw CardException("not_cie", IasCieSession.NOT_CIE)
        return r.data
    }

    private fun getResponse(first: Response): Response {
        val out = ByteArrayOutputStream().apply { write(first.data) }
        var r = first
        while (r.sw1 == 0x61) {
            r = transmit(byteArrayOf(0x00, 0xC0.toByte(), 0x00, 0x00, r.sw2.toByte()))
            out.write(r.data)
        }
        return Response(out.toByteArray(), r.sw)
    }

    private fun transmit(apdu: ByteArray): Response {
        val raw = isoDep.transceive(apdu)
        if (raw.size < 2) throw IOException("risposta incompleta")
        val sw = ((raw[raw.size - 2].toInt() and 0xFF) shl 8) or (raw[raw.size - 1].toInt() and 0xFF)
        return Response(raw.copyOfRange(0, raw.size - 2), sw)
    }

    private fun <T> guard(block: () -> T): T = try {
        block()
    } catch (e: CardException) {
        throw e
    } catch (e: TagLostException) {
        throw CardException("card_removed", IasCieSession.MOVED)
    } catch (e: IOException) {
        throw CardException("card_removed", IasCieSession.MOVED)
    } catch (e: Exception) {
        throw CardException("device_error", "Errore nel dialogo con la CIE (${e.javaClass.simpleName}).")
    }

    private fun hex(text: String) = ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
}
