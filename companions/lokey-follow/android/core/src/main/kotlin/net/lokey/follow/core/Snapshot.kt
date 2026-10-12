package net.lokey.follow.core

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import kotlin.math.roundToInt

data class Point(val time: Long, val value: Double)
data class Treatment(val time: Long, val insulin: Double?, val rate: Double?, val durationMinutes: Double, val suspended: Boolean)
data class Delta(val value: Double, val minutes: Double) { val rate get() = value / minutes }
data class Snapshot(
    val glucose: List<Point>, val direction: String, val loopTime: Long?, val iob: Point?,
    val forecast: List<Point>, val treatments: List<Treatment>, val failure: String?, val fetchedAt: Long
) {
    val latest get() = glucose.lastOrNull()
    fun fresh(time: Long?, now: Long) = time != null && now - time in -60_000..600_000
    fun delta(): Delta? {
        if (glucose.size < 2) return null
        val a = glucose[glucose.size - 2]; val b = glucose.last()
        val minutes = (b.time - a.time) / 60_000.0
        return if (minutes in 2.0..10.0) Delta(b.value - a.value, minutes) else null
    }
    fun activeTemp(now: Long): Treatment? = treatments.filter { it.rate != null && it.time <= now }.lastOrNull()
        ?.takeIf { fresh(loopTime, now) && it.durationMinutes > 0 && now < it.time + it.durationMinutes * 60_000 }
    fun prediction(now: Long) = forecast.takeIf { fresh(loopTime, now) && fresh(forecast.firstOrNull()?.time, now) && failure == null } ?: emptyList()
    fun iobText(now: Long) = iob?.takeIf { fresh(it.time, now) }?.let { "%.2f U".format(java.util.Locale.US, it.value) } ?: "—"
    fun glucoseText() = latest?.value?.roundToInt()?.toString() ?: "—"
    val arrow get() = when(direction) {
        "DoubleUp" -> "⇈"; "SingleUp" -> "↑"; "FortyFiveUp" -> "↗"; "Flat" -> "→"
        "FortyFiveDown" -> "↘"; "SingleDown" -> "↓"; "DoubleDown" -> "⇊"; else -> ""
    }
}

object NightscoutParser {
    fun validateUrl(raw: String): String {
        val uri = URI(raw.trim())
        require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null) {
            "Enter an HTTPS base URL without a token, password, or query."
        }
        return uri.toString().trimEnd('/')
    }
    fun timestamp(value: Any?): Long? = when (value) {
        is Number -> value.toLong().takeIf { it > 1_000_000_000_000 }
        is String -> runCatching { Instant.parse(value).toEpochMilli() }.getOrNull()
        else -> null
    }
    private fun number(j: JSONObject, key: String): Double? = if (j.isNull(key)) null else (j.opt(key) as? Number)?.toDouble()?.takeIf { it.isFinite() }
    private fun rows(a: JSONArray) = (0 until a.length()).mapNotNull { a.optJSONObject(it) }
    fun parse(entries: JSONArray, statuses: JSONArray, treatments: JSONArray, now: Long): Snapshot {
        val entryRows = rows(entries).filter { number(it, "sgv")?.let { v -> v in 20.0..600.0 } == true }
        val glucose = entryRows.mapNotNull { j ->
            (timestamp(j.opt("date")) ?: timestamp(j.opt("dateString")))?.let { Point(it, number(j, "sgv")!!) }
        }.filter { it.time <= now + 60_000 && it.time >= now - 86_400_000 }.distinctBy { it.time }.sortedBy { it.time }
        val direction = entryRows.firstOrNull { timestamp(it.opt("date")) == glucose.lastOrNull()?.time || timestamp(it.opt("dateString")) == glucose.lastOrNull()?.time }?.optString("direction") ?: ""
        // Select an entire newest Loop record; do not resurrect missing fields from older uploads.
        val loop = rows(statuses).mapNotNull { it.optJSONObject("loop") }
            .filter { timestamp(it.opt("timestamp"))?.let { t -> t <= now + 60_000 } == true }
            .maxByOrNull { timestamp(it.opt("timestamp"))!! }
        val loopTime = loop?.let { timestamp(it.opt("timestamp")) }
        val iob = loop?.optJSONObject("iob")?.let { j ->
            val time = timestamp(j.opt("timestamp")); val value = number(j, "iob")
            if (time != null && value != null) Point(time, value) else null
        }
        val predicted = loop?.optJSONObject("predicted")
        val start = predicted?.let { timestamp(it.opt("startDate")) }
        val values = predicted?.optJSONArray("values")
        val forecast = if (start != null && values != null) (0 until minOf(values.length(), 145)).mapNotNull { index ->
            (values.opt(index) as? Number)?.toDouble()?.takeIf { it.isFinite() && it > 0 }?.let { Point(start + index * 300_000L, it) }
        } else emptyList()
        val seen = mutableSetOf<String>()
        val doses = rows(treatments).mapNotNull { j ->
            val time = timestamp(j.opt("timestamp")) ?: timestamp(j.opt("created_at")) ?: return@mapNotNull null
            if (time > now + 60_000 || time < now - 21_600_000) return@mapNotNull null
            val type = j.optString("eventType")
            val insulin = if (type in listOf("Correction Bolus", "Meal Bolus", "Bolus", "Combo Bolus")) number(j, "insulin")?.takeIf { it >= 0 } else null
            val rate = if (type == "Temp Basal" && j.optString("temp", "absolute") == "absolute") (number(j, "absolute") ?: number(j, "rate"))?.takeIf { it >= 0 } else null
            if (insulin == null && rate == null) return@mapNotNull null
            val key = j.optString("syncIdentifier").takeIf { it.isNotBlank() } ?: "$time|$type|$insulin|$rate|${j.opt("duration")}"
            if (!seen.add(key)) return@mapNotNull null
            Treatment(time, insulin, rate, number(j, "duration") ?: 0.0, j.optString("reason") == "suspend")
        }.sortedBy { it.time }
        return Snapshot(glucose, direction, loopTime, iob, forecast, doses, loop?.optString("failureReason")?.takeIf { it.isNotBlank() }, now)
    }
}
