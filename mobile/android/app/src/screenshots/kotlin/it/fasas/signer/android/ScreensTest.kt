package it.fasas.signer.android

import android.view.View
import android.view.ViewGroup
import android.content.res.ColorStateList
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import com.android.resources.Density
import com.android.resources.NightMode
import org.junit.Rule
import org.junit.Test

/** Schermate dell'app disegnate senza telefono (Paparazzi), per controllarne l'aspetto in chiaro e in scuro. */
abstract class ScreensTest(night: Boolean) {
    @get:Rule
    val paparazzi = Paparazzi(
        deviceConfig = DeviceConfig.PIXEL_5.copy(
            screenWidth = 590, screenHeight = 1280, xdpi = 240, ydpi = 240, density = Density.HIGH,
            nightMode = if (night) NightMode.NIGHT else NightMode.NOTNIGHT, softButtons = false,
        ),
        theme = "Theme.Fasas",
        showSystemUi = false,
    )

    private val ui get() = Ui(paparazzi.context)

    private fun home(paired: Boolean, test: Boolean = false) = HomeScreen(ui,
        if (paired) Paired("https://casarosa-fasas.duckdns.org/", "Carlo Coordinatore") else null, test, true, animate = false)

    /** Il contenuto di un dialogo dentro un riquadro come quello vero, su fondo scurito. */
    private fun asDialog(content: View, title: String? = null): View {
        val u = ui
        val box = u.column(4).apply {
            setBackgroundResource(R.drawable.dialog_background)
            setPadding(0, u.dp(28), 0, u.dp(20))
            if (title != null) addView(u.text(title, 20f, R.color.fasas_text, bold = true).apply {
                setPadding(u.dp(40), 0, u.dp(40), u.dp(4))
            })
            addView(content)
            addView(u.text("Annulla        Avanti", 15f, R.color.fasas_primary, bold = true).apply {
                setPadding(u.dp(40), u.dp(16), u.dp(40), 0)
                gravity = android.view.Gravity.END
            })
        }
        return FrameLayout(u.context).apply {
            setBackgroundColor(0x99000000.toInt())
            addView(box, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                android.view.Gravity.CENTER))
        }
    }

    @Test fun pairing() = paparazzi.snapshot(home(paired = false, test = true).apply {
        status.show(StatusPanel.Kind.SETUP, "Abbina il telefono al FASAS",
            "Serve una volta sola: poi le richieste di firma e di verifica compaiono qui da sole.")
    }.root, "abbinamento")

    @Test fun ready() = paparazzi.snapshot(home(paired = true).apply {
        status.show(StatusPanel.Kind.IDLE, "Pronto", "In attesa di richieste dal FASAS. Quando dal FASAS avvii una " +
            "firma o una verifica, la richiesta compare qui.")
    }.root, "pronto")

    @Test fun update() = paparazzi.snapshot(home(paired = true).apply {
        status.show(StatusPanel.Kind.IDLE, "Pronto", "In attesa di richieste dal FASAS.")
        showUpdate("0.3") {}
    }.root, "aggiornamento")

    @Test fun waitingForCard() = paparazzi.snapshot(home(paired = true).apply {
        status.show(StatusPanel.Kind.WAIT_CARD, "Avvicina la CIE", "Appoggia la carta al retro del telefono e tienila " +
            "ferma fino alla fine. Non serve il suo PIN.", "Togli la cover. Appoggia la carta al centro del retro, " +
            "vicino alla fotocamera, e spostala lentamente finché il telefono vibra; poi non muoverla.")
    }.root, "avvicina-la-cie")

    @Test fun reading() = paparazzi.snapshot(home(paired = true).apply {
        status.show(StatusPanel.Kind.READING, "CIE rilevata", "La carta conferma di essere originale…")
    }.root, "lettura")

    @Test fun request() = paparazzi.snapshot(asDialog(Dialogs.request(ui, "Verifica di identità",
        "Per aprire: Relazione clinica di prova", "K7QM-2HXA", "Conferma solo se il codice coincide con quello " +
            "mostrato nella pagina del FASAS. Ti verrà chiesto il PIN FASAS.")), "richiesta")

    @Test fun pin() = paparazzi.snapshot(asDialog(Dialogs.pin(ui, "PIN FASAS errato. Tentativi rimasti: 4.",
        "Il PIN che hai scelto nel FASAS al primo accesso: non è il PIN della carta né quello del telefono.", 8,
        "6-8 cifre").first, "PIN FASAS"), "pin-fasas")

    /**
     * Icona dell'app: i due livelli dell'icona adattiva sovrapposti a mano (il simulatore di Paparazzi non disegna le
     * icone adattive; sul telefono la forma la sceglie il launcher) e la versione monocromatica di Android 13+.
     */
    @Test fun icon() = paparazzi.snapshot(ui.row(28).apply {
        val u = ui
        setPadding(u.dp(24), u.dp(24), u.dp(24), u.dp(24))
        setBackgroundColor(u.color(R.color.fasas_bg))
        gravity = android.view.Gravity.TOP
        addView(FrameLayout(context).apply {
            setBackgroundResource(R.drawable.ic_launcher_background)
            addView(ImageView(context).apply { setImageResource(R.drawable.ic_launcher_foreground) },
                FrameLayout.LayoutParams(u.dp(108), u.dp(108)))
        }, LinearLayout.LayoutParams(u.dp(108), u.dp(108)))
        addView(FrameLayout(context).apply {
            background = u.rounded(0xFFD6E4F5.toInt(), 48)
            addView(ImageView(context).apply {
                setImageResource(R.drawable.ic_launcher_monochrome)
                imageTintList = ColorStateList.valueOf(0xFF1D3B5C.toInt())
                scaleX = 1.5f; scaleY = 1.5f
            }, FrameLayout.LayoutParams(u.dp(96), u.dp(96)))
        }, LinearLayout.LayoutParams(u.dp(96), u.dp(96)))
    }, "icona")

    @Test fun result() = paparazzi.snapshot(asDialog(Dialogs.result(ui, true, "Identità verificata",
        "Torna al FASAS: il documento si apre.")), "esito")
}

class LightScreensTest : ScreensTest(night = false)

class DarkScreensTest : ScreensTest(night = true)
