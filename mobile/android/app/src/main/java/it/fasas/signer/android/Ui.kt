package it.fasas.signer.android

import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.animation.ValueAnimator
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.text.InputFilter
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.roundToInt

/**
 * Elementi grafici con lo stile della piattaforma FASAS (colori, raggi e icone di static/css/fasas.css):
 * schede bianche con bordo sottile su fondo grigio chiaro, blu FASAS per le azioni, tema chiaro e scuro.
 * Solo componenti Android di base: l'app non dipende da librerie esterne.
 */
internal class Ui(val context: Context) {
    fun dp(value: Number) = (value.toFloat() * context.resources.displayMetrics.density).roundToInt()
    fun color(id: Int) = context.getColor(id)

    fun rounded(fill: Int, radiusDp: Number, strokeColor: Int? = null, strokeDp: Number = 1) = GradientDrawable().apply {
        setColor(fill)
        cornerRadius = dp(radiusDp).toFloat()
        if (strokeColor != null) setStroke(dp(strokeDp), strokeColor)
    }

    fun text(value: CharSequence, sizeSp: Float = 15f, colorId: Int = R.color.fasas_text_2, bold: Boolean = false,
             center: Boolean = false) = TextView(context).apply {
        text = value
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        setTextColor(color(colorId))
        setLineSpacing(0f, 1.15f)
        if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        if (center) gravity = Gravity.CENTER_HORIZONTAL
    }

    fun label(value: String) = text(value.uppercase(), 12f, R.color.fasas_muted, bold = true).apply { letterSpacing = 0.08f }

    fun icon(resId: Int, colorId: Int, sizeDp: Int = 20) = ImageView(context).apply {
        setImageResource(resId)
        imageTintList = ColorStateList.valueOf(color(colorId))
        layoutParams = LinearLayout.LayoutParams(dp(sizeDp), dp(sizeDp))
    }

    fun column(spacingDp: Int = 0) = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        if (spacingDp > 0) {
            showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
            dividerDrawable = GradientDrawable().apply { setSize(0, dp(spacingDp)) }
        }
    }

    fun row(spacingDp: Int = 12) = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
        dividerDrawable = GradientDrawable().apply { setSize(dp(spacingDp), 0) }
    }

    fun card(paddingDp: Int = 18, spacingDp: Int = 12) = column(spacingDp).apply {
        background = rounded(color(R.color.fasas_surface), 14, color(R.color.fasas_border))
        setPadding(dp(paddingDp), dp(paddingDp), dp(paddingDp), dp(paddingDp))
    }

    fun fill(view: View, topDp: Int = 0): View {
        view.layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = dp(topDp) }
        return view
    }

    fun weight(view: View) = view.apply { layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f) }

    enum class Style { PRIMARY, SECONDARY, GHOST, DANGER }

    /** Pulsante come quelli della piattaforma: icona + testo, angoli arrotondati, effetto al tocco. */
    fun button(label: String, iconRes: Int? = null, style: Style = Style.PRIMARY, onClick: () -> Unit): View {
        val (fill, stroke, fg) = when (style) {
            Style.PRIMARY -> Triple(color(R.color.fasas_primary), null, R.color.fasas_on_primary)
            Style.SECONDARY -> Triple(color(R.color.fasas_surface), color(R.color.fasas_border), R.color.fasas_text)
            Style.GHOST -> Triple(0x00000000, null, R.color.fasas_primary)
            Style.DANGER -> Triple(0x00000000, null, R.color.fasas_danger)
        }
        val content = rounded(fill, 12, stroke)
        val mask = rounded(0xFFFFFFFF.toInt(), 12)
        val ripple = color(if (style == Style.PRIMARY) R.color.fasas_primary_pressed else R.color.fasas_surface_3)
        return row(10).apply {
            gravity = Gravity.CENTER
            background = RippleDrawable(ColorStateList.valueOf(ripple), content, mask)
            minimumHeight = dp(if (style == Style.GHOST || style == Style.DANGER) 44 else 52)
            setPadding(dp(16), dp(10), dp(16), dp(10))
            isClickable = true
            isFocusable = true
            contentDescription = label
            if (iconRes != null) addView(icon(iconRes, fg, 20))
            addView(text(label, 16f, fg, bold = true))
            setOnClickListener { onClick() }
        }
    }

    /** Campo di testo con etichetta; bordo blu quando è attivo, come i campi della piattaforma. */
    fun field(labelText: String, hintText: String, inputKind: Int = InputType.TYPE_CLASS_TEXT, mono: Boolean = false,
              initial: String = ""): Pair<View, EditText> {
        val input = EditText(context).apply {
            hint = hintText
            setText(initial)
            inputType = inputKind
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setTextColor(color(R.color.fasas_text))
            setHintTextColor(color(R.color.fasas_muted))
            if (mono) typeface = Typeface.MONOSPACE
            background = inputBackground()
            setPadding(dp(14), dp(12), dp(14), dp(12))
            isSingleLine = true
        }
        val box = column(6).apply {
            addView(text(labelText, 13f, R.color.fasas_text_2, bold = true))
            addView(fill(input))
        }
        return box to input
    }

    fun inputBackground(): Drawable = StateListDrawable().apply {
        addState(intArrayOf(android.R.attr.state_focused),
            rounded(color(R.color.fasas_surface), 10, color(R.color.fasas_primary), 2))
        addState(intArrayOf(), rounded(color(R.color.fasas_surface), 10, color(R.color.fasas_border)))
    }

    /** Campo per i PIN: cifre grandi e centrate, mai mostrate (nessun salvataggio sul telefono). */
    fun pinInput(maxDigits: Int, hintText: String) = EditText(context).apply {
        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        filters = arrayOf(InputFilter.LengthFilter(maxDigits))
        gravity = Gravity.CENTER
        hint = hintText
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 26f)
        letterSpacing = 0.4f
        typeface = Typeface.MONOSPACE
        setTextColor(color(R.color.fasas_text))
        setHintTextColor(color(R.color.fasas_muted))
        background = inputBackground()
        setPadding(dp(14), dp(14), dp(14), dp(14))
        isSingleLine = true
        importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
    }

    fun pill(value: String, fgId: Int, bgId: Int) = text(value, 12f, fgId, bold = true).apply {
        background = rounded(color(bgId), 999)
        setPadding(dp(10), dp(4), dp(10), dp(4))
    }

    /** Riquadro colorato con icona, come gli avvisi della piattaforma (info, attenzione, errore). */
    fun alert(message: String, kind: StatusPanel.Kind) = row(10).apply {
        val (fg, bg, iconRes) = StatusPanel.palette(kind)
        background = rounded(color(bg), 10)
        setPadding(dp(12), dp(10), dp(12), dp(10))
        gravity = Gravity.TOP
        addView(icon(iconRes, fg, 18))
        addView(weight(text(message, 14f, R.color.fasas_text)))
    }

    /** Icona del FASAS (linea del battito su quadrato blu), come nella barra laterale della piattaforma. */
    fun brandMark(sizeDp: Int = 44) = FrameLayout(context).apply {
        setBackgroundResource(R.drawable.brand_mark)
        layoutParams = LinearLayout.LayoutParams(dp(sizeDp), dp(sizeDp))
        addView(ImageView(context).apply {
            setImageResource(R.drawable.ic_activity)
            imageTintList = ColorStateList.valueOf(0xFFFFFFFF.toInt())
        }, FrameLayout.LayoutParams(dp(sizeDp / 2 + 2), dp(sizeDp / 2 + 2), Gravity.CENTER))
    }

    fun scroll(content: View) = ScrollView(context).apply {
        isFillViewport = true
        setBackgroundColor(color(R.color.fasas_bg))
        addView(content)
    }
}

/** Il riquadro grande in alto: cosa sta succedendo adesso, con icona, titolo e spiegazione. */
internal class StatusPanel(private val ui: Ui, private val animate: Boolean = true) {
    enum class Kind { IDLE, SETUP, WAIT_CARD, READING, SUCCESS, ERROR, WARNING }

    companion object {
        /** (colore, fondo, icona) per ogni stato, con i colori di stato della piattaforma */
        fun palette(kind: Kind) = when (kind) {
            Kind.SUCCESS -> Triple(R.color.fasas_ok, R.color.fasas_ok_soft, R.drawable.ic_check_circle)
            Kind.ERROR -> Triple(R.color.fasas_danger, R.color.fasas_danger_soft, R.drawable.ic_alert_circle)
            Kind.WARNING -> Triple(R.color.fasas_warn, R.color.fasas_warn_soft, R.drawable.ic_alert_circle)
            Kind.WAIT_CARD -> Triple(R.color.fasas_primary, R.color.fasas_primary_soft, R.drawable.ic_nfc)
            Kind.READING -> Triple(R.color.fasas_primary, R.color.fasas_primary_soft, R.drawable.ic_id_card)
            Kind.SETUP -> Triple(R.color.fasas_primary, R.color.fasas_primary_soft, R.drawable.ic_link)
            Kind.IDLE -> Triple(R.color.fasas_primary, R.color.fasas_primary_soft, R.drawable.ic_smartphone)
        }
    }

    private val badgeIcon = ImageView(ui.context)
    private val badge = FrameLayout(ui.context).apply {
        addView(badgeIcon, FrameLayout.LayoutParams(ui.dp(34), ui.dp(34), Gravity.CENTER))
    }
    private val title = ui.text("", 19f, R.color.fasas_text, bold = true, center = true)
    private val detail = ui.text("", 15f, R.color.fasas_text_2, center = true)
    private val tips = ui.text("", 13f, R.color.fasas_muted, center = true)
    private val progress = ProgressBar(ui.context, null, android.R.attr.progressBarStyleHorizontal).apply {
        isIndeterminate = true
        indeterminateTintList = ColorStateList.valueOf(ui.color(R.color.fasas_primary))
    }
    private val pulse = ObjectAnimator.ofPropertyValuesHolder(badge,
        PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.08f), PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.08f)).apply {
        duration = 900
        repeatCount = ValueAnimator.INFINITE
        repeatMode = ValueAnimator.REVERSE
    }
    var kind = Kind.IDLE
        private set

    val view: LinearLayout = ui.card(paddingDp = 22, spacingDp = 10).apply {
        gravity = Gravity.CENTER_HORIZONTAL
        addView(badge, LinearLayout.LayoutParams(ui.dp(76), ui.dp(76)).apply { bottomMargin = ui.dp(4) })
        addView(ui.fill(title))
        addView(ui.fill(detail))
        addView(ui.fill(progress))
        addView(ui.fill(tips))
    }

    fun show(kind: Kind, titleText: String, detailText: String? = null, tipsText: String? = null) {
        this.kind = kind
        val (fg, bg, iconRes) = palette(kind)
        badge.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(ui.color(bg)) }
        badgeIcon.setImageResource(iconRes)
        badgeIcon.imageTintList = ColorStateList.valueOf(ui.color(fg))
        title.text = titleText
        detail.text = detailText ?: ""
        detail.visibility = if (detailText.isNullOrEmpty()) View.GONE else View.VISIBLE
        tips.text = tipsText ?: ""
        tips.visibility = if (tipsText.isNullOrEmpty()) View.GONE else View.VISIBLE
        progress.visibility = if (kind == Kind.READING) View.VISIBLE else View.GONE
        if (kind == Kind.WAIT_CARD && animate) {
            if (!pulse.isStarted) pulse.start()
        } else {
            pulse.cancel()
            badge.scaleX = 1f
            badge.scaleY = 1f
        }
    }

    /** Aggiorna solo la spiegazione (passi della lettura) lasciando titolo e stato. */
    fun detail(detailText: String) {
        detail.text = detailText
        detail.visibility = View.VISIBLE
    }
}

internal data class Paired(val server: String, val user: String?)

/** Schermata principale: intestazione, stato, telefono abbinato (o abbinamento), azioni. */
internal class HomeScreen(private val ui: Ui, paired: Paired?, testBuild: Boolean, nfcEnabled: Boolean?,
                          animate: Boolean = true) {
    val status = StatusPanel(ui, animate)
    var onPair: (server: String, code: String) -> Unit = { _, _ -> }
    var onTestCard: () -> Unit = {}
    var onPinHelp: () -> Unit = {}
    var onUnpair: () -> Unit = {}
    lateinit var serverField: EditText
        private set

    val root: View

    init {
        val page = ui.column(14).apply { setPadding(ui.dp(20), ui.dp(24), ui.dp(20), ui.dp(28)) }
        page.addView(ui.fill(header(testBuild)))
        page.addView(ui.fill(status.view))
        if (paired == null) {
            page.addView(ui.fill(pairingCard(testBuild)))
        } else {
            page.addView(ui.fill(deviceCard(paired, nfcEnabled)))
        }
        page.addView(ui.fill(ui.button("Prova la lettura della CIE", R.drawable.ic_id_card, Ui.Style.SECONDARY) { onTestCard() }))
        page.addView(ui.fill(ui.button("Dove trovo il PIN della CIE?", R.drawable.ic_help, Ui.Style.GHOST) { onPinHelp() }))
        if (paired != null) {
            page.addView(ui.fill(ui.button("Scollega questo telefono", R.drawable.ic_log_out, Ui.Style.DANGER) { onUnpair() }))
        }
        page.addView(ui.fill(footer()))
        root = ui.scroll(page)
    }

    private fun header(testBuild: Boolean) = ui.row(12).apply {
        addView(ui.brandMark())
        addView(ui.weight(ui.column(2).apply {
            addView(ui.text("FASAS Signer", 21f, R.color.fasas_text, bold = true))
            addView(ui.text("Firma e verifica d'identità con la CIE", 13f, R.color.fasas_muted))
        }))
        if (testBuild) addView(ui.pill("Prova", R.color.fasas_warn_text, R.color.fasas_warn_soft))
    }

    private fun pairingCard(testBuild: Boolean) = ui.card().apply {
        addView(ui.text("Abbina il telefono", 17f, R.color.fasas_text, bold = true))
        addView(ui.text("Nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer» e copia qui " +
            "l'indirizzo e il codice che compaiono.", 14f))
        val (serverBox, server) = ui.field("Indirizzo del FASAS",
            if (testBuild) "http://192.168.1.20:8000/" else "https://fasas.struttura.it/",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI, initial = if (testBuild) "http://" else "https://")
        serverField = server
        val (codeBox, code) = ui.field("Codice di abbinamento", "ABCD-EFGH",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS, mono = true)
        addView(ui.fill(serverBox))
        addView(ui.fill(codeBox))
        if (testBuild) {
            addView(ui.fill(ui.alert("Versione di prova: si collega anche al FASAS sul PC della stessa Wi-Fi. " +
                "La CIE e i PIN sono quelli veri.", StatusPanel.Kind.WARNING)))
        }
        addView(ui.fill(ui.button("Abbina", R.drawable.ic_link) { onPair(server.text.toString(), code.text.toString()) }, 4))
    }

    private fun deviceCard(paired: Paired, nfcEnabled: Boolean?) = ui.card(spacingDp = 14).apply {
        addView(ui.label("Questo telefono"))
        addView(infoRow(R.drawable.ic_server, "FASAS", paired.server.removePrefix("https://").removePrefix("http://").trimEnd('/')))
        paired.user?.let { addView(infoRow(R.drawable.ic_user, "Utente", it)) }
        val nfcText = when (nfcEnabled) { true -> "attivo"; false -> "spento: attivalo nelle impostazioni"; null -> "non presente" }
        addView(infoRow(R.drawable.ic_nfc, "NFC", nfcText, if (nfcEnabled == true) R.color.fasas_ok else R.color.fasas_danger))
    }

    private fun infoRow(iconRes: Int, name: String, value: String, valueColor: Int = R.color.fasas_text) = ui.row(12).apply {
        addView(ui.icon(iconRes, R.color.fasas_muted, 20))
        addView(ui.text(name, 14f, R.color.fasas_muted).apply { minWidth = ui.dp(64) })
        addView(ui.weight(ui.text(value, 15f, valueColor, bold = true)))
    }

    private fun footer() = ui.row(10).apply {
        gravity = Gravity.TOP
        setPadding(ui.dp(4), ui.dp(4), ui.dp(4), 0)
        addView(ui.icon(R.drawable.ic_lock, R.color.fasas_muted, 16))
        addView(ui.weight(ui.text("Il PIN della carta va solo alla carta; il PIN FASAS è controllato dal FASAS. " +
            "Il telefono non conserva nessun PIN.", 12f, R.color.fasas_muted)))
    }
}

/** Contenuti dei dialoghi, con lo stesso stile delle schede. */
internal object Dialogs {
    /** Richiesta arrivata dal FASAS: cosa si fa, per quale documento e il codice da confrontare con la pagina. */
    fun request(ui: Ui, kind: String, title: String, code: String, note: String) = ui.column(12).apply {
        setPadding(ui.dp(24), ui.dp(8), ui.dp(24), ui.dp(4))
        addView(ui.label(kind))
        addView(ui.text(title, 17f, R.color.fasas_text, bold = true))
        addView(ui.column(4).apply {
            background = ui.rounded(ui.color(R.color.fasas_primary_soft), 12)
            setPadding(ui.dp(14), ui.dp(12), ui.dp(14), ui.dp(12))
            gravity = Gravity.CENTER_HORIZONTAL
            addView(ui.text("Codice di controllo", 12f, R.color.fasas_primary_text, bold = true, center = true))
            addView(ui.text(code, 28f, R.color.fasas_primary_text, bold = true, center = true).apply {
                typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
                letterSpacing = 0.12f
            })
        })
        addView(ui.text(note, 13f, R.color.fasas_muted))
    }

    /** Richiesta del PIN: eventuale errore in rosso, spiegazione e campo grande. */
    fun pin(ui: Ui, error: String?, explanation: String, maxDigits: Int, hint: String): Pair<View, EditText> {
        val input = ui.pinInput(maxDigits, hint)
        val view = ui.column(12).apply {
            setPadding(ui.dp(24), ui.dp(8), ui.dp(24), ui.dp(4))
            if (error != null) addView(ui.fill(ui.alert(error, StatusPanel.Kind.ERROR)))
            addView(ui.text(explanation, 14f))
            addView(ui.fill(input))
        }
        return view to input
    }

    /** Esito: icona grande verde o rossa, titolo e spiegazione. */
    fun result(ui: Ui, ok: Boolean, title: String, message: String) = ui.column(10).apply {
        setPadding(ui.dp(24), ui.dp(20), ui.dp(24), ui.dp(4))
        gravity = Gravity.CENTER_HORIZONTAL
        val (fg, bg, iconRes) = StatusPanel.palette(if (ok) StatusPanel.Kind.SUCCESS else StatusPanel.Kind.ERROR)
        addView(FrameLayout(ui.context).apply {
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(ui.color(bg)) }
            addView(ui.icon(iconRes, fg, 30), FrameLayout.LayoutParams(ui.dp(30), ui.dp(30), Gravity.CENTER))
        }, LinearLayout.LayoutParams(ui.dp(60), ui.dp(60)))
        addView(ui.fill(ui.text(title, 18f, R.color.fasas_text, bold = true, center = true)))
        addView(ui.fill(ui.text(message, 14f, R.color.fasas_text_2, center = true)))
    }

    /** Testo con paragrafi e punti elenco (aiuto sul PIN). */
    fun help(ui: Ui, paragraphs: List<String>) = ui.column(10).apply {
        setPadding(ui.dp(24), ui.dp(8), ui.dp(24), ui.dp(4))
        paragraphs.forEach { addView(ui.text(it, 14f)) }
    }
}
