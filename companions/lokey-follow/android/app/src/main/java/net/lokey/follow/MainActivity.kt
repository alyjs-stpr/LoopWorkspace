package net.lokey.follow

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.widget.*
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import net.lokey.follow.core.*
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : Activity() {
    private lateinit var repository: Repository
    private lateinit var content: LinearLayout
    private val executor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val busy = AtomicBoolean(false)
    private var snapshot: Snapshot? = null
    private var mode = "Dashboard"
    private var message = "Connect your private Nightscout site to begin."
    private var active = false
    private val purple = Color.rgb(185, 137, 255)
    private val lime = Color.rgb(116, 239, 34)
    private val periodic = object : Runnable {
        override fun run() { if (active) { render(); refresh(); handler.postDelayed(this, 60_000) } }
    }
    private val prefs by lazy { getSharedPreferences("lokey.display", MODE_PRIVATE) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repository = Repository(this); snapshot = repository.cached()
        mode = savedInstanceState?.getString("mode") ?: "Dashboard"
        val scroll = ScrollView(this).apply { setBackgroundColor(Color.rgb(17, 13, 27)); isFillViewport = true }
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(20), dp(20), dp(20)) }
        scroll.addView(content); setContentView(scroll)
        scroll.setOnApplyWindowInsetsListener { view, insets ->
            view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom); insets
        }
        render(); WidgetRefresh.schedule(this)
    }
    override fun onStart() { super.onStart(); active = true; handler.post(periodic) }
    override fun onStop() { active = false; handler.removeCallbacks(periodic); window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); super.onStop() }
    override fun onDestroy() { executor.shutdown(); super.onDestroy() }
    override fun onSaveInstanceState(outState: Bundle) { outState.putString("mode", mode); super.onSaveInstanceState(outState) }
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun text(value: String, size: Float = 18f, color: Int = Color.WHITE) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); setPadding(0, dp(6), 0, dp(6))
    }
    private fun button(title: String, action: () -> Unit) = Button(this).apply {
        text = title; isAllCaps = false; setTextColor(purple); setOnClickListener { action() }
    }
    private fun card(label: String, value: String, color: Int, detail: String = "") {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(18), dp(12), dp(18), dp(12))
            background = GradientDrawable().apply { setColor(Color.rgb(33, 26, 48)); cornerRadius = dp(20).toFloat() }
        }
        box.addView(text(label, 15f, Color.LTGRAY)); box.addView(text(value, if (mode == "Display") 40f else 30f, color))
        if (detail.isNotEmpty()) box.addView(text(detail, 13f, Color.LTGRAY))
        content.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) })
    }
    private fun time(t: Long?) = t?.let { SimpleDateFormat("h:mm a", Locale.getDefault()).format(Date(it)) } ?: "—"
    private fun refresh() {
        if (!active || repository.connection() == null || !busy.compareAndSet(false, true)) return
        val connection = repository.connection()!!
        executor.execute {
            val result = runCatching { repository.fetch(connection) }
            handler.post {
                busy.set(false)
                if (isDestroyed || repository.connection() != connection) return@post
                result.onSuccess { snapshot = it; message = "Last sync ${time(it.fetchedAt)}"; WidgetRefresh.update(this) }
                    .onFailure { message = "Unable to refresh. Check your connection or readable token. Showing saved readings, if available." }
                if (active) render()
            }
        }
    }
    private fun render() {
        content.removeAllViews()
        if (mode == "Display" && active && prefs.getBoolean("awake", true)) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        content.addView(text("LoKey Follow", 25f, purple).apply { typeface = Typeface.DEFAULT_BOLD })
        val navigation = LinearLayout(this)
        listOf("Dashboard", "Display", "Widgets").forEach { title -> navigation.addView(button(title) { mode = title; render() }, LinearLayout.LayoutParams(0, -2, 1f)) }
        content.addView(navigation)
        if (mode == "Widgets") {
            card("Your home screen", "Glucose · Dashboard", purple, "Long-press your home screen → Widgets → LoKey Follow. Choose the compact glucose widget or the larger dashboard widget; drag its edges to resize. Tap a widget to open and refresh Follow.")
            content.addView(text("Widgets show the exact reading time. Android may delay background refreshes; the open app checks every minute.", 16f))
            listOf("graph" to "Show glucose graph", "insulin" to "Show insulin history", "awake" to "Keep screen awake in Display mode").forEach { (key, label) ->
                content.addView(Switch(this).apply { text = label; setTextColor(Color.WHITE); isChecked = prefs.getBoolean(key, true)
                    setOnCheckedChangeListener { _, checked -> prefs.edit().putBoolean(key, checked).apply() } })
            }
        } else {
            val now = System.currentTimeMillis(); val s = snapshot
            val glucoseFresh = s?.fresh(s.latest?.time, now) == true
            val loopFresh = s?.fresh(s.loopTime, now) == true
            content.addView(text(if (s == null) "Waiting for data" else if (glucoseFresh) "Glucose reading ${time(s.latest?.time)}" else "STALE GLUCOSE · reading ${time(s.latest?.time)}", 14f, if (glucoseFresh) Color.LTGRAY else Color.rgb(255,181,90)))
            content.addView(text("${s?.glucoseText() ?: "—"} ${s?.arrow ?: ""}", if (mode == "Display") 96f else 76f, purple).apply { typeface = Typeface.DEFAULT_BOLD })
            content.addView(text("mg/dL", 18f, Color.LTGRAY))
            val d = if (glucoseFresh) s?.delta() else null
            card("Glucose change", d?.let { "%+.0f mg/dL in %.1f min".format(Locale.US, it.value, it.minutes) } ?: "—", purple,
                d?.let { "%+.2f mg/dL/min".format(Locale.US, it.rate) } ?: "Needs two recent readings 2–10 minutes apart.")
            card("Insulin on board · from Loop", s?.iobText(now) ?: "—", lime, "IOB timestamp ${time(s?.iob?.time)}")
            val temp = s?.activeTemp(now)
            card("Active temp basal", temp?.let { if (it.suspended) "Suspended · 0 U/hr" else "%.2f U/hr".format(Locale.US, it.rate) } ?: "—", lime, "Scheduled basal is not inferred.")
            if (prefs.getBoolean("graph", true) && s != null) {
                content.addView(text("Glucose & Loop prediction", 20f, purple))
                content.addView(GlucoseGraph(this, s), LinearLayout.LayoutParams(-1, dp(if (mode == "Display") 260 else 210)))
                val forecast = s.prediction(now).filter { it.time >= now }
                content.addView(text(forecast.lastOrNull()?.let { "Eventually ${it.value.toInt()} mg/dL · ${time(it.time)}\nPredicted low ${forecast.minOf { p -> p.value }.toInt()} mg/dL" } ?: "No current Loop prediction", 15f))
            }
            content.addView(text("Loop update ${time(s?.loopTime)}${if (!loopFresh) " · STALE" else ""}${if (s?.failure != null) " · Loop reported an error" else ""}", 14f, Color.LTGRAY))
            if (mode == "Dashboard" && prefs.getBoolean("insulin", true)) {
                content.addView(text("Insulin history · last 6 hours", 20f, lime))
                val doses = s?.treatments?.takeLast(20)?.reversed() ?: emptyList()
                if (doses.isEmpty()) content.addView(text("No uploaded treatments available.", 15f))
                doses.forEach { t -> content.addView(text("${time(t.time)}  " + if (t.insulin != null) "Bolus %.2f U".format(Locale.US, t.insulin) else if (t.durationMinutes <= 0) "Temp basal cancelled" else if (t.suspended) "Suspend" else "Temp %.2f U/hr · %.0f min".format(Locale.US, t.rate, t.durationMinutes), 16f, lime)) }
            }
        }
        content.addView(text(message, 13f, Color.LTGRAY))
        content.addView(button("Refresh") { refresh() })
        content.addView(button("Nightscout connection") { settings() })
    }
    private fun settings() {
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), 0, dp(20), 0) }
        val url = EditText(this).apply { hint = "https://your-nightscout-site"; inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI; setText(repository.connection()?.url ?: "") }
        val token = EditText(this).apply { hint = "Device's readable token"; inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD }
        stack.addView(text("Use a separate readable token for each device. Keep your administrator secret in Nightscout and Loop.", 14f)); stack.addView(url); stack.addView(token)
        AlertDialog.Builder(this).setTitle("Private Nightscout").setView(stack).setNegativeButton("Cancel", null)
            .setNeutralButton("Disconnect") { _, _ -> repository.disconnect(); snapshot = null; message = "Disconnected"; WidgetRefresh.update(this); render() }
            .setPositiveButton("Save") { _, _ ->
                runCatching { repository.save(Connection(NightscoutParser.validateUrl(url.text.toString()), token.text.toString().trim())) }
                    .onSuccess { snapshot = null; message = "Connection saved; verifying data…"; WidgetRefresh.update(this); render(); refresh() }
                    .onFailure { message = "Enter a valid HTTPS URL and a readable token."; render() }
            }.show()
    }
}
