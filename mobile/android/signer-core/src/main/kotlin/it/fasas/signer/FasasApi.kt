package it.fasas.signer

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Errore restituito dal FASAS (o rete assente: status 0). */
class ServerException(val status: Int, val code: String, message: String) : Exception(message)

data class SignRequest(
    val id: String, val title: String, val version: Int?, val documentSha256: String,
    val verifyCode: String, val reason: String,
)

data class Prepared(val nonce: String, val toBeSigned: ByteArray, val digestInfo: ByteArray, val verifyCode: String)

/**
 * Client delle API /api/firma/v1/ del FASAS. Il telefono contatta il server in uscita; il token del dispositivo
 * viaggia solo nell'intestazione Authorization e solo in HTTPS. HTTP è ammesso solo verso il telefono stesso e,
 * con allowLanHttp (versione di prova dell'app), verso un indirizzo IP della rete locale (es. 192.168.1.20).
 */
class FasasApi(baseUrl: String, var token: String = "", allowLanHttp: Boolean = false, private val timeoutMs: Int = 30_000) {
    private val base: String

    init {
        val url = URL(baseUrl.trim())
        val local = url.host in setOf("localhost", "127.0.0.1", "::1", "10.0.2.2")
        require(url.protocol == "https" || (url.protocol == "http" && (local || (allowLanHttp && isPrivateIpv4(url.host))))) {
            "Il FASAS va raggiunto in HTTPS: con HTTP token e firma viaggerebbero in chiaro."
        }
        base = baseUrl.trim().trimEnd('/') + "/api/firma/v1/"
    }

    companion object {
        /** 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 scritti come indirizzo numerico (non nomi a dominio). */
        fun isPrivateIpv4(host: String): Boolean {
            val parts = host.split(".").map { it.toIntOrNull() ?: return false }
            if (parts.size != 4 || parts.any { it !in 0..255 }) return false
            return parts[0] == 10 || (parts[0] == 172 && parts[1] in 16..31) || (parts[0] == 192 && parts[1] == 168)
        }
    }

    private fun call(method: String, path: String, body: JSONObject? = null, timeout: Int = timeoutMs): JSONObject {
        val connection = try {
            URL(base + path).openConnection() as HttpURLConnection
        } catch (e: IOException) {
            throw ServerException(0, "network", "FASAS non raggiungibile.")
        }
        try {
            connection.requestMethod = method
            connection.connectTimeout = timeoutMs
            connection.readTimeout = timeout
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "FASAS-Signer-Android/0.1")
            if (token.isNotEmpty()) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val status = connection.responseCode
            val stream = if (status >= 400) connection.errorStream else connection.inputStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
            val json = try { JSONObject(text) } catch (e: Exception) { JSONObject() }
            if (status >= 400) {
                throw ServerException(status, json.optString("error", "http_error"),
                    json.optString("message", "Errore del server ($status)."))
            }
            return json
        } catch (e: IOException) {
            throw ServerException(0, "network", "FASAS non raggiungibile: controllare la connessione.")
        } finally {
            connection.disconnect()
        }
    }

    fun pair(code: String, name: String, appVersion: String = "0.1"): JSONObject {
        val data = call("POST", "abbina/", JSONObject(mapOf("code" to code, "name" to name, "platform" to "android",
            "app_version" to appVersion)))
        token = data.getString("token")
        return data
    }

    fun me(): JSONObject = call("GET", "dispositivo/")

    fun reportStatus(status: Map<String, Any>) = call("POST", "dispositivo/stato/", JSONObject(status))

    fun pending(wait: Int = 10): List<SignRequest> {
        val items = call("GET", "richieste/?attesa=$wait", timeout = timeoutMs + wait * 1000).getJSONArray("requests")
        return (0 until items.length()).map { i ->
            val r = items.getJSONObject(i)
            SignRequest(r.getString("id"), r.getString("title"), if (r.isNull("version")) null else r.getInt("version"),
                r.getString("document_sha256"), r.getString("verify_code"), r.optString("reason"))
        }
    }

    fun claim(id: String): JSONObject = call("POST", "richieste/$id/prendi/")

    fun state(id: String, nonce: String, state: String, attemptsLeft: Int? = null): String {
        val body = JSONObject(mapOf("nonce" to nonce, "state" to state))
        if (attemptsLeft != null) body.put("attempts_left", attemptsLeft)
        return call("POST", "richieste/$id/stato/", body).getString("nonce")
    }

    fun certificate(id: String, nonce: String, certificate: ByteArray): Prepared {
        val r = call("POST", "richieste/$id/certificato/",
            JSONObject(mapOf("nonce" to nonce, "certificate" to Base64Codec.encode(certificate))))
        return Prepared(r.getString("nonce"), Base64Codec.decode(r.getString("to_be_signed")),
            Base64Codec.decode(r.getString("digest_info")), r.getString("verify_code"))
    }

    fun sign(id: String, nonce: String, signature: ByteArray): JSONObject =
        call("POST", "richieste/$id/firma/", JSONObject(mapOf("nonce" to nonce, "signature" to Base64Codec.encode(signature))))

    fun error(id: String, nonce: String, code: String): JSONObject =
        call("POST", "richieste/$id/errore/", JSONObject(mapOf("nonce" to nonce, "code" to code)))
}

/** java.util.Base64 è disponibile da Android 8 (API 26), il minimo dell'app. */
object Base64Codec {
    fun encode(data: ByteArray): String = java.util.Base64.getEncoder().encodeToString(data)
    fun decode(text: String): ByteArray = java.util.Base64.getDecoder().decode(text)
}
