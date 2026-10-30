package vn.tms.location

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Định vị bằng LocationManager của Android (GPS/mạng), không cần Google Play Services.
 * Dùng dự phòng khi expo-location (Fused Location) không chạy được trên máy.
 * Quyền vị trí do expo-location xin trước khi gọi.
 */
class TmsLocationModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("TmsLocation")

    // Trả vị trí mới nhất trong `timeoutMs`; hết giờ thì trả vị trí đã biết gần nhất (có thể null).
    AsyncFunction("getCurrentPosition") { timeoutMs: Int, promise: Promise ->
      getCurrentPosition(timeoutMs.toLong(), promise)
    }
  }

  @SuppressLint("MissingPermission")
  private fun getCurrentPosition(timeoutMs: Long, promise: Promise) {
    val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
      .filter { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
    val lastKnown = providers
      .mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
      .maxByOrNull { it.elapsedRealtimeNanos }
    if (providers.isEmpty()) {
      promise.resolve(lastKnown?.let(::toMap))
      return
    }

    val done = AtomicBoolean(false)
    val handler = Handler(Looper.getMainLooper())
    lateinit var listener: LocationListener
    val finish = { location: Location? ->
      if (done.compareAndSet(false, true)) {
        manager.removeUpdates(listener)
        handler.removeCallbacksAndMessages(null)
        promise.resolve((location ?: lastKnown)?.let(::toMap))
      }
    }
    listener = LocationListener { location -> finish(location) }
    handler.postDelayed({ finish(null) }, timeoutMs)
    try {
      for (provider in providers) {
        manager.requestLocationUpdates(provider, 0L, 0f, listener, Looper.getMainLooper())
      }
    } catch (e: SecurityException) {
      if (done.compareAndSet(false, true)) {
        handler.removeCallbacksAndMessages(null)
        promise.reject("E_LOCATION_PERMISSION", "Chưa cấp quyền vị trí", e)
      }
    }
  }

  private fun toMap(location: Location): Map<String, Any?> {
    val ageMs = (SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos) / 1_000_000
    @Suppress("DEPRECATION")
    val mocked = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) location.isMock else location.isFromMockProvider
    return mapOf(
      "latitude" to location.latitude,
      "longitude" to location.longitude,
      "accuracy" to if (location.hasAccuracy()) location.accuracy.toDouble() else null,
      "timestamp" to location.time.toDouble(),
      "ageMs" to ageMs.toDouble(),
      "provider" to location.provider,
      "mocked" to mocked,
    )
  }
}
