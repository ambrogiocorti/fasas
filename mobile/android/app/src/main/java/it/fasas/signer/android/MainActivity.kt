package it.fasas.signer.android

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.os.Bundle
import android.provider.Settings
import android.text.InputFilter
import android.text.InputType
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import it.fasas.signer.FasasApi
import it.fasas.signer.Outcome
import it.fasas.signer.ServerException
import it.fasas.signer.SignRequest
import it.fasas.signer.SigningFlow
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * FASAS Signer per Android – PROTOTIPO NON COLLAUDATO con una CIE reale.
 * Flusso: richiesta dal FASAS → conferma (codice di controllo) → PIN di 8 cifre → «avvicina la CIE» →
 * un'unica sessione NFC (canale sicuro, certificato, firma) → esito. Il PIN non lascia il telefono.
 */
class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()   // azioni (abbinamento, presa in carico, annullamento)
    private val poller = Executors.newSingleThreadExecutor()   // attesa delle richieste: un ciclo che non si ferma
    private val polling = AtomicBoolean(false)
    private val busy = AtomicBoolean(false)
    private lateinit var status: TextView
    private var api: FasasApi? = null
    private var nfc: NfcAdapter? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)  // niente screenshot né anteprime del PIN
        nfc = NfcAdapter.getDefaultAdapter(this)
        render()
    }

    private val prefs get() = getSharedPreferences("fasas_signer", Context.MODE_PRIVATE)

    /** Versione di prova (build debug): accetta anche un FASAS in rete locale via HTTP, es. il PC dell'ufficio. */
    private val testBuild get() = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0

    private fun render() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 64, 48, 48) }
        root.addView(TextView(this).apply { text = "FASAS Signer – firma con CIE"; textSize = 22f })
        root.addView(TextView(this).apply {
            text = "Firma elettronica avanzata. Prototipo: non ancora collaudato con una CIE reale."
            setPadding(0, 8, 0, 24)
        })
        if (testBuild) {
            root.addView(TextView(this).apply {
                text = "VERSIONE DI PROVA: si collega anche a un FASAS sul PC della stessa rete Wi-Fi (http://192.168…)."
                setBackgroundColor(0xFFB00020.toInt())
                setTextColor(0xFFFFFFFF.toInt())
                setPadding(24, 16, 24, 16)
            })
        }
        status = TextView(this).apply { textSize = 16f }
        root.addView(status)
        val server = prefs.getString("server", null)
        val token = prefs.getString("token", null)
        if (server == null || token == null) {
            val serverField = EditText(this).apply {
                hint = if (testBuild) "Indirizzo del FASAS (es. http://192.168.1.20:8000/)" else "Indirizzo del FASAS (https://…)"
                setText(if (testBuild) "http://" else "https://")
            }
            val codeField = EditText(this).apply { hint = "Codice di abbinamento" }
            root.addView(serverField)
            root.addView(codeField)
            root.addView(Button(this).apply {
                text = "Abbina"
                setOnClickListener { pair(serverField.text.toString(), codeField.text.toString()) }
            })
            status.text = "Nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer»."
        } else {
            api = runCatching { FasasApi(server, token, allowLanHttp = testBuild) }.getOrNull()
            status.text = "In attesa di richieste di firma dal FASAS…"
        }
        setContentView(root)
    }

    private fun pair(server: String, code: String) = worker.execute {
        try {
            val client = FasasApi(server, allowLanHttp = testBuild)
            val data = client.pair(code.trim(), android.os.Build.MODEL ?: "Telefono")
            prefs.edit().putString("server", server.trim()).putString("token", client.token).apply()
            runOnUiThread { render(); show("Abbinato all'utente ${data.getString("user")}.") }
        } catch (e: Exception) {
            runOnUiThread { show(e.message ?: "Abbinamento non riuscito.") }
        }
    }

    override fun onResume() {
        super.onResume()
        val adapter = nfc
        if (adapter == null) {
            status.text = "Questo telefono non ha l'NFC: non può leggere la CIE."
            return
        }
        if (!adapter.isEnabled) {
            AlertDialog.Builder(this).setMessage("Attiva l'NFC per firmare con la CIE.")
                .setPositiveButton("Impostazioni") { _, _ -> startActivity(Intent(Settings.ACTION_NFC_SETTINGS)) }
                .show()
        }
        startPolling()
    }

    override fun onPause() {
        polling.set(false)
        nfc?.disableReaderMode(this)
        super.onPause()
    }

    private fun startPolling() {
        val client = api ?: return
        if (!polling.compareAndSet(false, true)) return
        poller.execute {
            runCatching {
                client.reportStatus(mapOf("middleware_found" to true, "middleware" to "IAS su NFC (prototipo)",
                    "readers" to listOf("NFC del telefono"), "nfc" to if (nfc?.isEnabled == true) "attivo" else "spento"))
            }
            while (polling.get()) {
                if (busy.get()) { Thread.sleep(1000); continue }
                try {
                    val request = client.pending(wait = 10).firstOrNull() ?: continue
                    busy.set(true)
                    runOnUiThread { confirm(client, request) }
                } catch (e: ServerException) {
                    if (e.status == 401) {
                        prefs.edit().remove("token").apply()
                        runOnUiThread { render(); show("Dispositivo revocato o non abbinato: abbinalo di nuovo.") }
                        polling.set(false)
                    } else {
                        Thread.sleep(5000)
                    }
                }
            }
        }
    }

    private fun confirm(client: FasasApi, request: SignRequest) {
        val flow = SigningFlow(client)
        val version = request.version?.let { " – versione $it" } ?: ""
        AlertDialog.Builder(this).setTitle("Richiesta di firma con CIE")
            .setMessage("${request.title}$version\n\nCodice di controllo:\n${request.verifyCode}\n\n" +
                "Firma solo se il codice coincide con quello mostrato nella pagina del FASAS.")
            .setCancelable(false)
            .setPositiveButton("Firma con CIE") { _, _ ->
                worker.execute {
                    try {
                        flow.accept(request)
                        runOnUiThread { askPin(flow, request, null) }
                    } catch (e: ServerException) {
                        runOnUiThread { finish(e.message ?: "Errore") }
                    }
                }
            }
            .setNegativeButton("Rifiuta") { _, _ -> worker.execute { runCatching { flow.refuse(request) }; busy.set(false) } }
            .show()
    }

    private fun askPin(flow: SigningFlow, request: SignRequest, message: String?) {
        val field = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            filters = arrayOf(InputFilter.LengthFilter(8))
            gravity = Gravity.CENTER
            hint = "8 cifre"
        }
        AlertDialog.Builder(this).setTitle("PIN della CIE")
            .setMessage((message?.let { "$it\n\n" } ?: "") + "Digita il PIN completo della CIE (8 cifre). Va solo alla carta.")
            .setView(field).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                if (pin.length != 8) askPin(flow, request, "Il PIN deve avere 8 cifre.") else waitForCard(flow, request, pin)
            }
            .setNegativeButton("Annulla") { _, _ -> worker.execute { flow.cancel(request); busy.set(false) } }
            .show()
    }

    private fun waitForCard(flow: SigningFlow, request: SignRequest, pin: String) {
        status.text = "Avvicina la CIE al retro del telefono e tienila ferma fino alla fine."
        val flags = NfcAdapter.FLAG_READER_NFC_A or NfcAdapter.FLAG_READER_NFC_B or
            NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK or NfcAdapter.FLAG_READER_NO_PLATFORM_SOUNDS
        nfc?.enableReaderMode(this, { tag: Tag ->
            val isoDep = IsoDep.get(tag) ?: return@enableReaderMode
            nfc?.disableReaderMode(this)
            val outcome = try {
                isoDep.connect()
                isoDep.timeout = 10_000
                flow.onCard(request, IasCieSession(isoDep), pin)
            } finally {
                runCatching { isoDep.close() }
            }
            runOnUiThread {
                when (outcome) {
                    is Outcome.Signed -> finish("Documento firmato correttamente (${outcome.level}).")
                    is Outcome.PinWrong -> askPin(flow, request,
                        "PIN errato." + (outcome.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""))
                    is Outcome.Failed -> finish("Firma non riuscita: ${outcome.message}")
                }
            }
        }, flags, null)
    }

    private fun finish(message: String) {
        status.text = "In attesa di richieste di firma dal FASAS…"
        busy.set(false)
        show(message)
    }

    private fun show(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("OK", null).show()
    }
}
