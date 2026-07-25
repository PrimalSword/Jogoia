package com.primalsword.eco

import android.content.Context
import android.graphics.*
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

data class Gate(var x: Float, val center: Float, val gap: Float, var passed: Boolean = false)
data class EchoPoint(val score: Float, val y: Float)

class GameView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val prefs = context.getSharedPreferences("eco_save", Context.MODE_PRIVATE)
    private val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 35)
    private val vibrator = context.getSystemService(Vibrator::class.java)
    private val gates = mutableListOf<Gate>()
    private val run = mutableListOf<EchoPoint>()
    private var previous = mutableListOf<EchoPoint>()
    private var state = 0 // 0 menu, 1 playing, 2 game over
    private var playerY = 0f
    private var velocity = 0f
    private var gravity = -1f
    private var score = 0f
    private var best = prefs.getInt("best", 0)
    private var shards = prefs.getInt("shards", 0)
    private var spawn = 0f
    private var sample = 0f
    private var lastFrame = System.nanoTime()

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
        if (event.action != MotionEvent.ACTION_DOWN) return true
        if (state != 1) startGame() else flip()
        return true
    }

    private fun startGame() {
        state = 1
        playerY = height * .5f
        velocity = -420f
        gravity = -1f
        score = 0f
        spawn = .4f
        sample = 0f
        gates.clear()
        run.clear()
        gates += newGate(width * 1.15f)
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 60)
    }

    private fun flip() {
        gravity *= -1f
        velocity = gravity * 950f
        tone.startTone(ToneGenerator.TONE_PROP_ACK, 35)
        if (android.os.Build.VERSION.SDK_INT >= 26) vibrator?.vibrate(VibrationEffect.createOneShot(18, 70))
    }

    private fun die() {
        state = 2
        previous = run.toMutableList()
        best = max(best, score.toInt())
        prefs.edit().putInt("best", best).putInt("shards", shards).apply()
        tone.startTone(ToneGenerator.TONE_PROP_NACK, 130)
        if (android.os.Build.VERSION.SDK_INT >= 26) vibrator?.vibrate(VibrationEffect.createOneShot(90, 120))
    }

    private fun newGate(x: Float): Gate {
        val gap = max(height * .20f, height * (.30f - score / 6000f))
        val margin = height * .14f + gap / 2
        return Gate(x, Random.nextFloat() * (height - margin * 2) + margin, gap)
    }

    override fun onDraw(canvas: Canvas) {
        val now = System.nanoTime()
        val dt = min(.033f, (now - lastFrame) / 1_000_000_000f)
        lastFrame = now
        if (state == 1) update(dt)
        drawBackground(canvas)
        if (state == 0) drawMenu(canvas) else drawGame(canvas)
        postInvalidateOnAnimation()
    }

    private fun update(dt: Float) {
        score += dt * 10f
        val speed = min(width * 1.05f, width * (.42f + score / 900f))
        velocity += gravity * height * 1.65f * dt
        velocity = velocity.coerceIn(-height * .95f, height * .95f)
        playerY += velocity * dt
        val top = height * .09f
        val bottom = height * .91f
        if (playerY < top || playerY > bottom) return die()

        spawn -= dt
        if (spawn <= 0f) {
            gates += newGate(width * 1.1f)
            spawn = max(.58f, 1.18f - score / 520f)
        }
        for (g in gates) {
            g.x -= speed * dt
            if (!g.passed && g.x < width * .21f) { g.passed = true; shards++ }
            if (abs(g.x - width * .21f) < width * .055f &&
                (playerY < g.center - g.gap / 2 || playerY > g.center + g.gap / 2)) return die()
        }
        gates.removeAll { it.x < -width * .15f }
        sample -= dt
        if (sample <= 0f) { run += EchoPoint(score, playerY); sample = .08f }
    }

    private fun drawBackground(c: Canvas) {
        c.drawColor(Color.rgb(7, 9, 26))
        paint.strokeWidth = 1f
        for (i in 0..14) {
            paint.color = Color.argb(22, 88, 230, 255)
            val y = height * i / 14f
            c.drawLine(0f, y, width.toFloat(), y - 45f, paint)
        }
    }

    private fun text(c: Canvas, s: String, y: Float, size: Float, color: Int) {
        paint.textSize = size
        paint.color = color
        paint.textAlign = Paint.Align.CENTER
        c.drawText(s, width / 2f, y, paint)
    }

    private fun drawMenu(c: Canvas) {
        text(c, "ECO", height * .19f, width * .18f, Color.WHITE)
        text(c, "ÚLTIMO TOQUE", height * .25f, width * .055f, Color.rgb(88,230,255))
        text(c, "VOCÊ JOGA CONTRA O SEU PASSADO", height * .31f, width * .029f, Color.LTGRAY)
        paint.color = Color.rgb(88,230,255)
        c.drawCircle(width/2f, height*.50f, width*.095f, paint)
        paint.color = Color.rgb(7,9,26)
        c.drawCircle(width/2f, height*.50f, width*.048f, paint)
        text(c, "TOQUE PARA INICIAR", height * .69f, width * .052f, Color.WHITE)
        text(c, "toque para inverter a gravidade", height * .74f, width * .030f, Color.GRAY)
        text(c, "RECORDE  %06d".format(best), height * .84f, width * .040f, Color.rgb(196,92,255))
        text(c, "FRAGMENTOS  $shards", height * .88f, width * .034f, Color.rgb(88,230,255))
    }

    private fun drawGame(c: Canvas) {
        val top = height * .09f
        val bottom = height * .91f
        paint.color = Color.rgb(37,51,84)
        paint.strokeWidth = 4f
        c.drawLine(0f, top, width.toFloat(), top, paint)
        c.drawLine(0f, bottom, width.toFloat(), bottom, paint)
        for (g in gates) {
            paint.color = Color.rgb(24,40,75)
            c.drawRect(g.x-width*.045f, top, g.x+width*.045f, g.center-g.gap/2, paint)
            c.drawRect(g.x-width*.045f, g.center+g.gap/2, g.x+width*.045f, bottom, paint)
        }
        val ghost = previous.getOrNull((score/.8f).toInt())
        if (ghost != null) {
            paint.color = Color.argb(80,196,92,255)
            c.drawCircle(width*.21f, ghost.y, width*.032f, paint)
        }
        paint.color = if (gravity < 0) Color.rgb(88,230,255) else Color.rgb(196,92,255)
        c.drawCircle(width*.21f, playerY, width*.034f, paint)
        text(c, "%06d".format(score.toInt()), height*.065f, width*.060f, Color.WHITE)
        if (state == 2) {
            paint.color = Color.argb(190,4,6,18)
            c.drawRect(0f,0f,width.toFloat(),height.toFloat(),paint)
            text(c,"SINAL PERDIDO",height*.38f,width*.070f,Color.WHITE)
            text(c,"%06d".format(score.toInt()),height*.49f,width*.13f,Color.rgb(88,230,255))
            text(c,"TOQUE PARA REESCREVER",height*.64f,width*.045f,Color.WHITE)
            text(c,"seu próximo inimigo acaba de nascer",height*.70f,width*.030f,Color.LTGRAY)
        }
    }
}
