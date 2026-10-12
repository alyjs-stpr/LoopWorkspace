package net.lokey.follow.core

import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class SnapshotTest {
    private val now = Instant.parse("2026-10-12T14:00:00Z").toEpochMilli()
    private fun parse(entries: String = "[]", status: String = "[]", doses: String = "[]") = NightscoutParser.parse(JSONArray(entries),JSONArray(status),JSONArray(doses),now)
    private val status = """[{"loop":{"timestamp":"2026-10-12T14:00:00Z","iob":{"timestamp":"2026-10-12T13:59:00Z","iob":-0.35},"predicted":{"startDate":"2026-10-12T14:00:00Z","values":[142,151,160]},"enacted":{"rate":0,"duration":0}}}]"""
    @Test fun sortsDeduplicatesAndUsesActualInterval() {
        val s=parse("""[{"sgv":142,"date":${now},"direction":"Flat"},{"sgv":134,"date":${now-360_000}},{"sgv":134,"date":${now-360_000}}]""")
        assertEquals(2,s.glucose.size); assertEquals(8.0,s.delta()!!.value,0.001); assertEquals(6.0,s.delta()!!.minutes,0.001)
        assertEquals(8.0/6,s.delta()!!.rate,0.001); assertEquals("→",s.arrow)
    }
    @Test fun gapsDoNotBecomeFiveMinuteDeltas() { assertNull(parse("""[{"sgv":142,"date":$now},{"sgv":134,"date":${now-900_000}}]""").delta()) }
    @Test fun preservesNegativeIobAndForecastInterval() {
        val s=parse(status=status); assertEquals(-0.35,s.iob!!.value,0.001); assertEquals("-0.35 U",s.iobText(now)); assertEquals(300_000,s.forecast[1].time-s.forecast[0].time)
        assertNull(s.activeTemp(now)); assertEquals(3,s.prediction(now).size); assertTrue(s.prediction(now+601_000).isEmpty()); assertEquals("—",s.iobText(now+601_000))
    }
    @Test fun latestLoopDoesNotReviveOlderIob() {
        val newer="""{"loop":{"timestamp":"2026-10-12T14:00:30Z"}}"""
        val s=parse(status=status.dropLast(1)+","+newer+"]"); assertNull(s.iob); assertTrue(s.forecast.isEmpty())
    }
    @Test fun oldIobAndOldForecastStayHiddenWithFreshLoop() {
        val s=parse(status=status.replace("13:59:00", "13:30:00").replace("\"startDate\":\"2026-10-12T14:00:00Z\"","\"startDate\":\"2026-10-12T13:30:00Z\""))
        assertEquals("—",s.iobText(now)); assertTrue(s.prediction(now).isEmpty())
    }
    @Test fun tempCancellationSupersedesPriorRateAndDuplicatesAreRemoved() {
        val first="""{"eventType":"Temp Basal","created_at":"2026-10-12T13:50:00Z","absolute":1.25,"duration":30,"syncIdentifier":"a"}"""
        val cancelled="""{"eventType":"Temp Basal","created_at":"2026-10-12T13:59:00Z","absolute":0,"duration":0}"""
        val s=parse(status=status,doses="[$first,$first,$cancelled]"); assertEquals(2,s.treatments.size); assertNull(s.activeTemp(now))
    }
    @Test fun suspendAndBolusAreSeparateAndZeroIsNotMissing() {
        val s=parse(status=status,doses="""[{"eventType":"Temp Basal","created_at":"2026-10-12T13:59:00Z","absolute":0,"duration":30,"reason":"suspend"},{"eventType":"Correction Bolus","created_at":"2026-10-12T13:58:00Z","insulin":2.5}]""")
        assertTrue(s.activeTemp(now)!!.suspended); assertEquals(0.0,s.activeTemp(now)!!.rate!!,0.001); assertEquals(2.5,s.treatments.first().insulin!!,0.001)
    }
    @Test fun rejectsFutureReadingsAndMissingOrWrongTypeValues() {
        val s=parse("""[{"sgv":142,"date":${now+120_000}},{"sgv":null,"date":$now},{"sgv":"142","date":$now}]"""); assertTrue(s.glucose.isEmpty())
        assertFalse(s.fresh(now+120_000,now)); assertTrue(s.fresh(now,now))
    }
    @Test fun requiresPrivateHttpsBaseUrl() {
        assertEquals("https://example.org/path",NightscoutParser.validateUrl("https://example.org/path/"))
        listOf("http://example.org","https://admin:secret@example.org","https://example.org?token=abc","https://example.org#token").forEach { assertTrue(runCatching { NightscoutParser.validateUrl(it) }.isFailure) }
    }
}
