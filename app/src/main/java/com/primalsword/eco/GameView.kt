package com.primalsword.eco

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.MotionEvent
import android.view.View
import kotlin.math.hypot
import kotlin.math.min

private const val CYCLE_SECONDS = 8f
private const val SAMPLE_INTERVAL = 0.05f

data class TrackPoint(val t: Float, val x: Float, val y: Float)
data class Echo(val track: List<TrackPoint>, val color: Int)

class GameView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val prefs = context.getSharedPreferences("eco_paradoxo", Context.MODE_PRIVATE)
    private val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 28)
    private val vibrator = context.getSystemService(Vibrator::class.java)

    private var state = 0 // 0 menu, 1 playing, 2 won
    private var level = prefs.getInt("level", 1).coerceAtLeast(1)
    private var cyclesUsed = 0
    private var cycleTime = 0f
    private var sampleTimer = 0f
    private var beatTimer = 0f
    private var playerX = 0f
    private var playerY = 0f
    private var targetX = 0f
    private var targetY = 0f
    private var dragging = false
    private var lastFrame = System.nanoTime()

    private val currentTrack = mutableListOf<TrackPoint>()
    private val echoes = mutableListOf<Echo>()

    init {
        isFocusable = true
        keepScreenOn = true
        paint.typeface = Typeface.create("sans", Typeface.BOLD)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        postInvalidateOnAnimation()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (state == 0 || state == 2) {
                    startLevel()
                    return true
                }
                dragging = true
                targetX = event.x
                targetY = event.y
            }
            MotionEvent.ACTION_MOVE -> {
                if (state == 1) {
                    targetX = event.x
                    targetY = event.y
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> dragging = false
        }
        return true
    }

    private fun startLevel() {
        state = 1
        cyclesUsed = 0
        echoes.clear()
        beginCycle()
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 90)
    }

    private fun beginCycle() {
        cyclesUsed++
        cycleTime = 0f
        sampleTimer = 0f
        beatTimer = 0f
        currentTrack.clear()
        playerX = width * .14f
        playerY = height * .50f
        targetX = playerX
        targetY = playerY
        dragging = false
        safeVibrate(28, 55)
    }

    private fun finishCycle() {
        if (currentTrack.isNotEmpty()) {
            val colors = intArrayOf(
                Color.rgb(196, 92, 255),
                Color.rgb(255, 96, 160),
                Color.rgb(255, 190, 70),
                Color.rgb(110, 255, 160)
            )
            echoes += Echo(currentTrack.toList(), colors[(echoes.size) % colors.size])
        }
        beginCycle()
    }

    private fun safeVibrate(ms: Long, amplitude: Int) {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                vibrator?.vibrate(VibrationEffect.createOneShot(ms, amplitude))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(ms)
            }
        } catch (_: Exception) {
            // Vibração é um bônus. Nunca deve derrubar o jogo.
        }
    }

    override fun onDraw(canvas: Canvas) {
        val now = System.nanoTime()
        val dt = min(.033f, (now - lastFrame) / 1_000_000_000f)
        lastFrame = now
        if (state == 1) update(dt)
        drawBackground(canvas)
        when (state) {
            0 -> drawMenu(canvas)
            1 -> drawGame(canvas)
            2 -> drawVictory(canvas)
        }
        postInvalidateOnAnimation()
    }

    private fun update(dt: Float) {
        cycleTime += dt
        beatTimer -= dt
        if (beatTimer <= 0f) {
            val toneId = if ((cycleTime * 2).toInt() % 4 == 0) ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_PROP_BEEP
            tone.startTone(toneId, 34)
            beatTimer = .5f
        }

        val speed = width * 2.6f
        val dx = targetX - playerX
        val dy = targetY - playerY
        val distance = hypot(dx.toDouble(), dy.toDouble()).toFloat()
        if (dragging && distance > 1f) {
            val step = min(distance, speed * dt)
            playerX += dx / distance * step
            playerY += dy / distance * step
        }
        playerX = playerX.coerceIn(width * .06f, width * .94f)
        playerY = playerY.coerceIn(height * .13f, height * .88f)

        sampleTimer -= dt
        if (sampleTimer <= 0f) {
            currentTrack += TrackPoint(cycleTime, playerX, playerY)
            sampleTimer = SAMPLE_INTERVAL
        }

        val padA = padA()
        val padB = padB()
        val aActive = actorOnPad(playerX, playerY, padA.first, padA.second) || echoes.any {
            val p = echoPosition(it, cycleTime)
            p != null && actorOnPad(p.first, p.second, padA.first, padA.second)
        }
        val bActive = actorOnPad(playerX, playerY, padB.first, padB.second) || echoes.any {
            val p = echoPosition(it, cycleTime)
            p != null && actorOnPad(p.first, p.second, padB.first, padB.second)
        }

        if (aActive && bActive) {
            val portal = portal()
            if (hypot((playerX - portal.first).toDouble(), (playerY - portal.second).toDouble()) < width * .085f) {
                win()
                return
            }
        }

        if (cycleTime >= CYCLE_SECONDS) finishCycle()
    }

    private fun win() {
        state = 2
        level++
        prefs.edit().putInt("level", level).apply()
        tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 300)
        safeVibrate(140, 160)
    }

    private fun actorOnPad(x: Float, y: Float, px: Float, py: Float): Boolean {
        return hypot((x - px).toDouble(), (y - py).toDouble()) < width * .09f
    }

    private fun echoPosition(echo: Echo, time: Float): Pair<Float, Float>? {
        if (echo.track.isEmpty()) return null
        val index = (time / SAMPLE_INTERVAL).toInt().coerceIn(0, echo.track.lastIndex)
        val p = echo.track[index]
        return p.x to p.y
    }

    private fun padA() = width * .27f to height * .34f
    private fun padB() = width * .72f to height * .67f
    private fun portal() = width * .82f to height * .25f

    private fun drawBackground(c: Canvas) {
        c.drawColor(Color.rgb(5, 7, 20))
        paint.strokeWidth = 1f
        for (i in 0..18) {
            paint.color = Color.argb(20, 88, 230, 255)
            val y = height * i / 18f
            c.drawLine(0f, y, width.toFloat(), y - 60f, paint)
        }
    }

    private fun text(c: Canvas, s: String, y: Float, size: Float, color: Int) {
        paint.textSize = size
        paint.color = color
        paint.textAlign = Paint.Align.CENTER
        c.drawText(s, width / 2f, y, paint)
    }

    private fun drawMenu(c: Canvas) {
        text(c, "ECO", height * .18f, width * .18f, Color.WHITE)
        text(c, "PARADOXO", height * .25f, width * .072f, Color.rgb(88, 230, 255))
        text(c, "SEUS FRACASSOS VIRAM ALIADOS", height * .32f, width * .034f, Color.LTGRAY)

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = width * .018f
        paint.color = Color.rgb(196, 92, 255)
        c.drawCircle(width / 2f, height * .51f, width * .12f, paint)
        paint.color = Color.rgb(88, 230, 255)
        c.drawCircle(width / 2f, height * .51f, width * .066f, paint)
        paint.style = Paint.Style.FILL

        text(c, "TOQUE PARA INICIAR", height * .72f, width * .052f, Color.WHITE)
        text(c, "arraste para mover • cada ciclo dura 8 segundos", height * .77f, width * .029f, Color.GRAY)
        text(c, "NÍVEL  $level", height * .86f, width * .040f, Color.rgb(196, 92, 255))
    }

    private fun drawGame(c: Canvas) {
        val padA = padA()
        val padB = padB()
        val portal = portal()

        drawPad(c, padA.first, padA.second, Color.rgb(88, 230, 255))
        drawPad(c, padB.first, padB.second, Color.rgb(196, 92, 255))

        val aActive = actorOnPad(playerX, playerY, padA.first, padA.second) || echoes.any {
            val p = echoPosition(it, cycleTime)
            p != null && actorOnPad(p.first, p.second, padA.first, padA.second)
        }
        val bActive = actorOnPad(playerX, playerY, padB.first, padB.second) || echoes.any {
            val p = echoPosition(it, cycleTime)
            p != null && actorOnPad(p.first, p.second, padB.first, padB.second)
        }
        val portalOpen = aActive && bActive

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = width * .018f
        paint.color = if (portalOpen) Color.rgb(110, 255, 160) else Color.rgb(70, 78, 110)
        c.drawCircle(portal.first, portal.second, width * .085f, paint)
        paint.style = Paint.Style.FILL
        if (portalOpen) {
            paint.color = Color.argb(60, 110, 255, 160)
            c.drawCircle(portal.first, portal.second, width * .075f, paint)
        }

        for (echo in echoes) {
            val p = echoPosition(echo, cycleTime) ?: continue
            paint.color = Color.argb(150, Color.red(echo.color), Color.green(echo.color), Color.blue(echo.color))
            c.drawCircle(p.first, p.second, width * .038f, paint)
        }

        paint.color = Color.rgb(240, 250, 255)
        c.drawCircle(playerX, playerY, width * .042f, paint)
        paint.color = Color.rgb(88, 230, 255)
        c.drawCircle(playerX, playerY, width * .020f, paint)

        val remaining = (CYCLE_SECONDS - cycleTime).coerceAtLeast(0f)
        text(c, "CICLO $cyclesUsed", height * .055f, width * .042f, Color.WHITE)
        text(c, String.format("%.1f", remaining), height * .10f, width * .072f,
            if (remaining < 2f) Color.rgb(255, 96, 120) else Color.rgb(88, 230, 255))
        text(c, "ECOS ${echoes.size}", height * .94f, width * .036f, Color.rgb(196, 92, 255))
        text(c, if (portalOpen) "PORTAL ABERTO" else "ATIVE OS DOIS NÚCLEOS", height * .985f, width * .030f,
            if (portalOpen) Color.rgb(110, 255, 160) else Color.LTGRAY)
    }

    private fun drawPad(c: Canvas, x: Float, y: Float, color: Int) {
        paint.color = Color.argb(45, Color.red(color), Color.green(color), Color.blue(color))
        c.drawCircle(x, y, width * .10f, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = width * .014f
        paint.color = color
        c.drawCircle(x, y, width * .072f, paint)
        paint.style = Paint.Style.FILL
    }

    private fun drawVictory(c: Canvas) {
        paint.color = Color.argb(225, 3, 5, 15)
        c.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        text(c, "PARADOXO ESTABILIZADO", height * .34f, width * .060f, Color.WHITE)
        text(c, "NÍVEL CONCLUÍDO", height * .43f, width * .090f, Color.rgb(110, 255, 160))
        text(c, "CICLOS USADOS  $cyclesUsed", height * .54f, width * .042f, Color.rgb(196, 92, 255))
        text(c, "TOQUE PARA O PRÓXIMO", height * .70f, width * .048f, Color.WHITE)
        text(c, "cada eco adiciona uma camada ao ritmo", height * .76f, width * .030f, Color.GRAY)
    }
}