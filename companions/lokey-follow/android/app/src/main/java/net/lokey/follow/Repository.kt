package net.lokey.follow

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import net.lokey.follow.core.NightscoutParser
import net.lokey.follow.core.Snapshot
import org.json.JSONArray
import org.json.JSONObject
import java.net.URL
import java.net.HttpURLConnection
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.time.Instant

data class Connection(val url: String, val token: String)
class Repository(context: Context) {
    companion object { private val keyLock = Any(); private val connectionLock = Any() }
    private val preferences = context.getSharedPreferences("lokey.private", Context.MODE_PRIVATE)
    private fun key(): SecretKey = synchronized(keyLock) {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("lokey.follow", null) as? SecretKey)?.let { return@synchronized it }
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("lokey.follow", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    private fun encrypt(raw: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        return Base64.encodeToString(cipher.iv + cipher.doFinal(raw.toByteArray()), Base64.NO_WRAP)
    }
    private fun decrypt(raw: String): String {
        val bytes = Base64.decode(raw, Base64.NO_WRAP)
        return Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12))) }
            .doFinal(bytes.copyOfRange(12, bytes.size)).toString(Charsets.UTF_8)
    }
    fun connection(): Connection? = runCatching {
        val raw = preferences.getString("connection", null) ?: return null
        val j = JSONObject(decrypt(raw)); Connection(j.getString("url"), j.getString("token"))
    }.getOrNull()
    fun save(connection: Connection) {
        NightscoutParser.validateUrl(connection.url)
        require(connection.token.isNotBlank() && !connection.token.contains('\n') && !connection.token.contains('\r'))
        synchronized(connectionLock) { preferences.edit().putString("connection", encrypt(JSONObject().put("url", connection.url).put("token", connection.token).toString())).remove("cache").commit() }
    }
    fun disconnect() { synchronized(connectionLock) { preferences.edit().remove("connection").remove("cache").commit() } }
    private fun get(c: Connection, path: String): JSONArray {
        val request = URL(c.url + path).openConnection() as HttpURLConnection
        try {
            request.instanceFollowRedirects = false; request.connectTimeout = 15_000; request.readTimeout = 15_000
            request.setRequestProperty("API-SECRET", c.token); request.setRequestProperty("Accept", "application/json")
            require(request.responseCode == 200) { if (request.responseCode in listOf(401,403)) "Check the readable token." else "Nightscout request failed." }
            val body = request.inputStream.bufferedReader().use { it.readText() }
            require(body.length < 4_000_000) { "Nightscout response too large." }
            return JSONArray(body)
        } finally { request.disconnect() }
    }
    fun fetch(c: Connection = connection() ?: error("Connect Nightscout first.")): Snapshot {
        val now = System.currentTimeMillis()
        val entries = get(c, "/api/v1/entries/sgv.json?count=1000&find%5Bdate%5D%5B%24gte%5D=${now - 86_400_000}")
        val status = get(c, "/api/v1/devicestatus.json?count=100")
        val doses = get(c, "/api/v1/treatments.json?count=1000&find%5Bcreated_at%5D%5B%24gte%5D=${Instant.ofEpochMilli(now - 21_600_000)}")
        val raw = JSONObject().put("entries", entries).put("statuses", status).put("treatments", doses).put("fetchedAt", now)
        // Discard an in-flight response after a disconnect/account change.
        synchronized(connectionLock) { if (connection() == c) preferences.edit().putString("cache", encrypt(raw.toString())).commit() }
        return NightscoutParser.parse(entries, status, doses, now)
    }
    fun cached(): Snapshot? = runCatching {
        val raw = preferences.getString("cache", null) ?: return null
        val j = JSONObject(decrypt(raw))
        NightscoutParser.parse(j.getJSONArray("entries"), j.getJSONArray("statuses"), j.getJSONArray("treatments"), j.getLong("fetchedAt"))
    }.getOrNull()
}
