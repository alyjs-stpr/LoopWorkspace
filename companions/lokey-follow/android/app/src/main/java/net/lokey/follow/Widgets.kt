package net.lokey.follow

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import androidx.work.*
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

open class GlucoseWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) { WidgetRefresh.schedule(context); WidgetRefresh.update(context) }
}
class DashboardWidget : GlucoseWidget()
class WidgetWorker(context: Context, parameters: WorkerParameters) : Worker(context, parameters) {
    override fun doWork(): Result {
        return try { val repo=Repository(applicationContext); if(repo.connection()!=null) repo.fetch(); WidgetRefresh.update(applicationContext); Result.success() }
        catch (_: Exception) { WidgetRefresh.update(applicationContext); Result.retry() }
    }
}
object WidgetRefresh {
    fun schedule(context: Context) {
        val task=PeriodicWorkRequestBuilder<WidgetWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("lokey-follow",ExistingPeriodicWorkPolicy.KEEP,task)
    }
    fun update(context: Context) {
        val manager=AppWidgetManager.getInstance(context); val s=Repository(context).cached(); val now=System.currentTimeMillis()
        listOf(GlucoseWidget::class.java,DashboardWidget::class.java).forEach { type ->
            manager.getAppWidgetIds(ComponentName(context,type)).forEach { id ->
                val view=RemoteViews(context.packageName,if(type==DashboardWidget::class.java) R.layout.widget_dashboard else R.layout.widget_glucose)
                view.setTextViewText(R.id.glucose,"${s?.glucoseText() ?: "—"} ${s?.arrow ?: ""}")
                val stamp=s?.latest?.time?.let { SimpleDateFormat("MMM d, h:mm a",Locale.getDefault()).format(Date(it)) } ?: "No reading"
                view.setTextViewText(R.id.reading_time,"Reading: $stamp\nSnapshot · tap to refresh")
                view.setTextViewText(R.id.status,if(s?.fresh(s.latest?.time,now)==true) "mg/dL" else "STALE / NO DATA")
                if(type==DashboardWidget::class.java) {
                    view.setTextViewText(R.id.iob,"IOB ${s?.iobText(now) ?: "—"}")
                    val delta=if(s?.fresh(s.latest?.time,now)==true) s.delta() else null
                    view.setTextViewText(R.id.delta,delta?.let { "%+.0f in %.1f min".format(Locale.US,it.value,it.minutes) } ?: "Delta —")
                }
                view.setOnClickPendingIntent(R.id.widget_root,PendingIntent.getActivity(context,id,Intent(context,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
                manager.updateAppWidget(id,view)
            }
        }
    }
}
