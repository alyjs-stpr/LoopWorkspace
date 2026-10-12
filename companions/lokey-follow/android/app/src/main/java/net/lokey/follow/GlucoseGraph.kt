package net.lokey.follow

import android.content.Context
import android.graphics.*
import android.view.View
import net.lokey.follow.core.*
import net.lokey.follow.core.Point
import java.text.SimpleDateFormat
import java.util.*

class GlucoseGraph(context: Context, private val snapshot: Snapshot) : View(context) {
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val now = System.currentTimeMillis()
        val history = snapshot.glucose.filter { it.time >= now - 10_800_000 }
        val forecast = snapshot.prediction(now).filter { it.time >= now - 300_000 }
        val all = history + forecast
        if (all.isEmpty()) return
        val start = now - 10_800_000; val end = maxOf(now + 3_600_000, all.maxOf { it.time })
        val low = minOf(70.0, all.minOf { it.value } - 10); val high = maxOf(180.0, all.maxOf { it.value } + 10)
        val left = 48f; val top = 12f; val right = width - 12f; val bottom = height - 42f
        fun x(t: Long) = left + (t-start).toFloat()/(end-start)*(right-left)
        fun y(v: Double) = bottom - ((v-low)/(high-low)).toFloat()*(bottom-top)
        val p = Paint(Paint.ANTI_ALIAS_FLAG)
        p.color = Color.argb(25,185,137,255); canvas.drawRect(left,y(180.0),right,y(70.0),p)
        listOf(70.0, 120.0, 180.0).forEach { v ->
            p.color=Color.DKGRAY; p.strokeWidth=1f; canvas.drawLine(left,y(v),right,y(v),p)
            p.color=Color.LTGRAY; p.textSize=24f; canvas.drawText(v.toInt().toString(),0f,y(v)+8,p)
        }
        p.color=Color.rgb(185,137,255); p.strokeWidth=4f; p.style=Paint.Style.STROKE
        val path = Path(); var previous: Point?=null
        history.forEach { point ->
            if (previous == null || point.time-previous!!.time > 600_000) path.moveTo(x(point.time),y(point.value)) else path.lineTo(x(point.time),y(point.value))
            previous=point
        }; canvas.drawPath(path,p)
        val predictedPath=Path(); forecast.forEachIndexed { i,point -> if(i==0) predictedPath.moveTo(x(point.time),y(point.value)) else predictedPath.lineTo(x(point.time),y(point.value)) }
        p.pathEffect=DashPathEffect(floatArrayOf(14f,10f),0f); canvas.drawPath(predictedPath,p); p.pathEffect=null
        p.style=Paint.Style.FILL; history.forEach { canvas.drawCircle(x(it.time),y(it.value),4f,p) }
        p.color=Color.LTGRAY; p.textSize=24f
        val format=SimpleDateFormat("h:mm a",Locale.getDefault())
        canvas.drawText(format.format(Date(start)),left,height-8f,p)
        val label=format.format(Date(end)); canvas.drawText(label,right-p.measureText(label),height-8f,p)
        contentDescription="Glucose history and dashed Loop prediction, mg/dL. Latest ${snapshot.glucoseText()}."
    }
}
