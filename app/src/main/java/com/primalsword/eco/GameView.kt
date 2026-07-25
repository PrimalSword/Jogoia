package com.primalsword.eco

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.MotionEvent
import android.view.View
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

private data class Enemy(
    var x: Float,
    var y: Float,
    var hp: Float,
    val maxHp: Float,
    val speed: Float,
    val radius: Float,
    val type: Int,
    var phase: Float = 0f,
    var cooldown: Float = 0f
)

private data class Shot(
    var x: Float,
    var y: Float,
    var vx: Float,
    var vy: Float,
    val damage: Float,
    var life: Float,
    val hostile: Boolean
)

private data class Gem(var x: Float, var y: Float, val value: Int)
private data class Spark(var x: Float, var y: Float, var vx: Float, var vy: Float, var life: Float, val color: Int)

class GameView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val prefs = context.getSharedPreferences("eco_ruptura_clean", Context.MODE_PRIVATE)
    private val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 28)
    private val vibrator = context.getSystemService(Vibrator::class.java)

    private val enemies = mutableListOf<Enemy>()
    private val shots = mutableListOf<Shot>()
    private val gems = mutableListOf<Gem>()
    private val sparks = mutableListOf<Spark>()

    private var state = 0 // 0 menu, 1 playing, 2 upgrade, 3 dead, 4 victory
    private var playerX = 0f
    private var playerY = 0f
    private var facing = 0f
    private var touching = false
    private var touchX = 0f
    private var touchY = 0f

    private var hp = 120f
    private var maxHp = 120f
    private var moveSpeed = 0f
    private var damage = 20f
    private var fireRate = 0.48f
    private var fireTimer = 0f
    private var bulletSpeed = 0f
    private var multishot = 1
    private var magnet = 0f

    private var xp = 0
    private var nextXp = 10
    private var level = 1
    private var kills = 0
    private var collected = 0
    private var elapsed = 0f
    private var spawnTimer = 0f
    private var bossSpawned = false
    private var bossDefeated = false
    private var objective = 0
    private var objectiveTarget = 20
    private var objectiveProgress = 0
    private var best = prefs.getInt("best", 0)
    private var lastFrame = System.nanoTime()
    private var upgradeChoices = listOf<Int>()

    init {
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
                if (state == 0 || state == 3 || state == 4) {
                    startGame()
                    return true
                }
                if (state == 2) {
                    val index = (event.x / (width / 3f)).toInt().coerceIn(0, 2)
                    chooseUpgrade(index)
                    return true
                }
                touching = true
                touchX = event.x
                touchY = event.y
            }
            MotionEvent.ACTION_MOVE -> {
                touchX = event.x
                touchY = event.y
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> touching = false
        }
        return true
    }

    private fun startGame() {
        enemies.clear(); shots.clear(); gems.clear(); sparks.clear()
        state = 1
        playerX = width / 2f
        playerY = height * 0.62f
        hp = 120f
        maxHp = 120f
        moveSpeed = width * 0.80f
        damage = 20f
        fireRate = 0.48f
        fireTimer = 0f
        bulletSpeed = width * 1.65f
        multishot = 1
        magnet = width * 0.18f
        xp = 0
        nextXp = 10
        level = 1
        kills = 0
        collected = 0
        elapsed = 0f
        spawnTimer = 0.2f
        bossSpawned = false
        bossDefeated = false
        objective = 0
        objectiveTarget = 20
        objectiveProgress = 0
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 100)
    }

    override fun onDraw(canvas: Canvas) {
        val now = System.nanoTime()
        val dt = min(0.033f, (now - lastFrame) / 1_000_000_000f)
        lastFrame = now

        if (state == 1) update(dt)
        drawBackground(canvas)
        when (state) {
            0 -> drawMenu(canvas)
            1 -> drawGame(canvas)
            2 -> { drawGame(canvas); drawUpgrade(canvas) }
            3 -> { drawGame(canvas); drawDead(canvas) }
            4 -> { drawGame(canvas); drawVictory(canvas) }
        }
        postInvalidateOnAnimation()
    }

    private fun update(dt: Float) {
        elapsed += dt
        updateMovement(dt)
        updateObjective()
        updateSpawns(dt)
        updateShooting(dt)
        updateEnemies(dt)
        updateShots(dt)
        updateGems(dt)
        updateSparks(dt)
        if (hp <= 0f) die()
    }

    private fun updateMovement(dt: Float) {
        if (!touching) return
        val dx = touchX - playerX
        val dy = touchY - playerY
        val distance = hypot(dx.toDouble(), dy.toDouble()).toFloat()
        if (distance > 6f) {
            facing = atan2(dy, dx)
            playerX += dx / distance * moveSpeed * dt
            playerY += dy / distance * moveSpeed * dt
        }
        playerX = playerX.coerceIn(width * 0.06f, width * 0.94f)
        playerY = playerY.coerceIn(height * 0.14f, height * 0.92f)
    }

    private fun updateObjective() {
        objectiveProgress = when (objective) {
            0 -> kills
            1 -> collected
            2 -> elapsed.toInt()
            3 -> if (bossDefeated) 1 else 0
            else -> elapsed.toInt()
        }

        val completed = when (objective) {
            0, 1 -> objectiveProgress >= objectiveTarget
            2, 4 -> elapsed >= objectiveTarget.toFloat()
            3 -> bossDefeated
            else -> false
        }
        if (completed) advanceObjective()
    }

    private fun advanceObjective() {
        objective++
        objectiveProgress = 0
        hp = min(maxHp, hp + 30f)
        burst(playerX, playerY, Color.rgb(90, 255, 160), 22)
        safeVibrate(80, 130)

        when (objective) {
            1 -> objectiveTarget = 35
            2 -> objectiveTarget = 70
            3 -> {
                objectiveTarget = 1
                spawnBoss()
            }
            4 -> objectiveTarget = 110
            5 -> {
                state = 4
                best = max(best, elapsed.toInt())
                prefs.edit().putInt("best", best).apply()
            }
        }
    }

    private fun updateSpawns(dt: Float) {
        if (objective == 3 && bossSpawned) return
        spawnTimer -= dt
        if (spawnTimer > 0f) return

        val amount = 1 + (elapsed / 45f).toInt().coerceAtMost(2)
        repeat(amount) { spawnEnemy() }
        spawnTimer = max(0.18f, 0.70f - elapsed / 220f)
    }

    private fun spawnEnemy() {
        val edge = Random.nextInt(4)
        val position = when (edge) {
            0 -> -60f to Random.nextFloat() * height
            1 -> width + 60f to Random.nextFloat() * height
            2 -> Random.nextFloat() * width to -60f
            else -> Random.nextFloat() * width to height + 60f
        }
        val roll = Random.nextFloat()
        val type = when {
            elapsed > 65f && roll < 0.12f -> 3
            elapsed > 35f && roll < 0.30f -> 2
            elapsed > 15f && roll < 0.55f -> 1
            else -> 0
        }
        val baseHp = floatArrayOf(34f, 56f, 44f, 110f)[type]
        val radius = floatArrayOf(width * 0.034f, width * 0.048f, width * 0.042f, width * 0.064f)[type]
        val speed = floatArrayOf(width * 0.28f, width * 0.19f, width * 0.23f, width * 0.12f)[type]
        val hpValue = baseHp * (1f + elapsed / 110f)
        enemies += Enemy(position.first, position.second, hpValue, hpValue, speed, radius, type, Random.nextFloat() * 6.28f, Random.nextFloat())
    }

    private fun spawnBoss() {
        if (bossSpawned) return
        bossSpawned = true
        val bossHp = 1200f + elapsed * 8f
        enemies += Enemy(width / 2f, -width * 0.15f, bossHp, bossHp, width * 0.10f, width * 0.13f, 4, 0f, 1f)
        tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 350)
        safeVibrate(140, 200)
    }

    private fun updateShooting(dt: Float) {
        fireTimer -= dt
        if (fireTimer > 0f || enemies.isEmpty()) return
        val target = enemies.minByOrNull { distance(playerX, playerY, it.x, it.y) } ?: return
        val angle = atan2(target.y - playerY, target.x - playerX)
        facing = angle
        repeat(multishot) { index ->
            val spread = (index - (multishot - 1) / 2f) * 0.13f
            shots += Shot(
                playerX + cos(angle) * width * 0.05f,
                playerY + sin(angle) * width * 0.05f,
                cos(angle + spread) * bulletSpeed,
                sin(angle + spread) * bulletSpeed,
                damage,
                2f,
                false
            )
        }
        fireTimer = fireRate
    }

    private fun updateEnemies(dt: Float) {
        for (enemy in enemies.toList()) {
            enemy.phase += dt
            enemy.cooldown -= dt
            val dx = playerX - enemy.x
            val dy = playerY - enemy.y
            val d = max(1f, hypot(dx.toDouble(), dy.toDouble()).toFloat())

            when (enemy.type) {
                0 -> {
                    enemy.x += dx / d * enemy.speed * dt
                    enemy.y += dy / d * enemy.speed * dt
                }
                1 -> {
                    val sway = sin(enemy.phase * 5f) * width * 0.08f
                    enemy.x += (dx / d * enemy.speed - dy / d * sway) * dt
                    enemy.y += (dy / d * enemy.speed + dx / d * sway) * dt
                }
                2 -> {
                    if (enemy.cooldown <= 0f) {
                        enemy.x += dx / d * width * 0.18f
                        enemy.y += dy / d * width * 0.18f
                        enemy.cooldown = 0.85f
                    }
                }
                3 -> {
                    enemy.x += dx / d * enemy.speed * dt
                    enemy.y += dy / d * enemy.speed * dt
                    if (enemy.cooldown <= 0f) {
                        fireEnemyRing(enemy, 6)
                        enemy.cooldown = 2.1f
                    }
                }
                4 -> {
                    enemy.x += dx / d * enemy.speed * dt
                    enemy.y += dy / d * enemy.speed * dt
                    if (enemy.cooldown <= 0f) {
                        fireEnemyRing(enemy, 12)
                        enemy.cooldown = 1.25f
                    }
                }
            }

            if (d < enemy.radius + width * 0.035f) {
                hp -= when (enemy.type) {
                    4 -> 42f * dt
                    3 -> 25f * dt
                    else -> 15f * dt
                }
            }
        }
    }

    private fun fireEnemyRing(enemy: Enemy, count: Int) {
        repeat(count) { index ->
            val angle = 6.28f * index / count + enemy.phase
            shots += Shot(enemy.x, enemy.y, cos(angle) * width * 0.42f, sin(angle) * width * 0.42f, 10f, 3f, true)
        }
    }

    private fun updateShots(dt: Float) {
        for (shot in shots.toList()) {
            shot.x += shot.vx * dt
            shot.y += shot.vy * dt
            shot.life -= dt

            if (shot.hostile) {
                if (distance(shot.x, shot.y, playerX, playerY) < width * 0.045f) {
                    hp -= shot.damage
                    shots.remove(shot)
                    burst(playerX, playerY, Color.rgb(255, 90, 120), 8)
                }
            } else {
                val enemy = enemies.firstOrNull { distance(shot.x, shot.y, it.x, it.y) < it.radius + width * 0.012f }
                if (enemy != null) {
                    enemy.hp -= shot.damage
                    shots.remove(shot)
                    burst(shot.x, shot.y, Color.rgb(80, 225, 255), 4)
                    if (enemy.hp <= 0f) killEnemy(enemy)
                }
            }

            if (shot.life <= 0f || shot.x < -100f || shot.x > width + 100f || shot.y < -100f || shot.y > height + 100f) {
                shots.remove(shot)
            }
        }
    }

    private fun killEnemy(enemy: Enemy) {
        enemies.remove(enemy)
        kills++
        val value = when (enemy.type) {
            4 -> 20
            3 -> 5
            else -> 1
        }
        gems += Gem(enemy.x, enemy.y, value)
        burst(enemy.x, enemy.y, enemyColor(enemy.type), if (enemy.type == 4) 40 else 12)
        if (enemy.type == 4) {
            bossDefeated = true
            tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 450)
            safeVibrate(200, 255)
        }
    }

    private fun updateGems(dt: Float) {
        for (gem in gems.toList()) {
            val d = distance(playerX, playerY, gem.x, gem.y)
            if (d < magnet) {
                val pull = width * (0.65f + magnet / max(1f, d))
                gem.x += (playerX - gem.x) / max(1f, d) * pull * dt
                gem.y += (playerY - gem.y) / max(1f, d) * pull * dt
            }
            if (d < width * 0.05f) {
                xp += gem.value
                collected += gem.value
                gems.remove(gem)
                if (xp >= nextXp) levelUp()
            }
        }
    }

    private fun levelUp() {
        xp -= nextXp
        level++
        nextXp = (nextXp * 1.32f + 4f).toInt()
        upgradeChoices = (0..5).shuffled().take(3)
        state = 2
        safeVibrate(60, 100)
    }

    private fun chooseUpgrade(index: Int) {
        when (upgradeChoices[index]) {
            0 -> damage *= 1.30f
            1 -> fireRate = max(0.11f, fireRate * 0.82f)
            2 -> moveSpeed *= 1.18f
            3 -> multishot = (multishot + 1).coerceAtMost(6)
            4 -> { maxHp += 30f; hp += 30f }
            5 -> magnet *= 1.45f
        }
        state = 1
        tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 100)
    }

    private fun die() {
        state = 3
        best = max(best, elapsed.toInt())
        prefs.edit().putInt("best", best).apply()
        tone.startTone(ToneGenerator.TONE_PROP_NACK, 260)
        safeVibrate(180, 220)
    }

    private fun updateSparks(dt: Float) {
        for (spark in sparks) {
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            spark.vx *= 0.95f
            spark.vy *= 0.95f
            spark.life -= dt
        }
        sparks.removeAll { it.life <= 0f }
    }

    private fun burst(x: Float, y: Float, color: Int, amount: Int) {
        repeat(amount) {
            val angle = Random.nextFloat() * 6.28f
            val speed = Random.nextFloat() * width * 0.42f
            sparks += Spark(x, y, cos(angle) * speed, sin(angle) * speed, 0.3f + Random.nextFloat() * 0.5f, color)
        }
    }

    private fun safeVibrate(ms: Long, amplitude: Int) {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                vibrator?.vibrate(VibrationEffect.createOneShot(ms, amplitude))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(ms)
            }
        } catch (_: Exception) { }
    }

    private fun distance(x1: Float, y1: Float, x2: Float, y2: Float): Float =
        hypot((x1 - x2).toDouble(), (y1 - y2).toDouble()).toFloat()

    private fun enemyColor(type: Int): Int = when (type) {
        0 -> Color.rgb(255, 85, 120)
        1 -> Color.rgb(255, 175, 65)
        2 -> Color.rgb(170, 90, 255)
        3 -> Color.rgb(70, 220, 255)
        else -> Color.rgb(255, 55, 80)
    }

    private fun drawBackground(canvas: Canvas) {
        canvas.drawColor(Color.rgb(5, 7, 18))
        val offset = (elapsed * 28f) % 90f
        paint.strokeWidth = 1f
        for (i in -1..20) {
            paint.color = Color.argb(20, 60, 125, 255)
            val y = i * 90f + offset
            canvas.drawLine(0f, y, width.toFloat(), y - 110f, paint)
        }
    }

    private fun drawMenu(canvas: Canvas) {
        text(canvas, "ECO", height * 0.17f, width * 0.19f, Color.WHITE)
        text(canvas, "RUPTURA", height * 0.25f, width * 0.078f, Color.rgb(88, 230, 255))
        text(canvas, "ROGUELITE DE SOBREVIVÊNCIA TEMPORAL", height * 0.32f, width * 0.031f, Color.LTGRAY)
        drawHero(canvas, width / 2f, height * 0.51f, 0f, width * 0.14f)
        text(canvas, "TOQUE PARA INICIAR", height * 0.74f, width * 0.052f, Color.WHITE)
        text(canvas, "cumpra objetivos • evolua • derrote o núcleo", height * 0.79f, width * 0.029f, Color.GRAY)
        text(canvas, "RECORDE  ${best}s", height * 0.88f, width * 0.039f, Color.rgb(196, 92, 255))
    }

    private fun drawGame(canvas: Canvas) {
        for (gem in gems) drawDiamond(canvas, gem.x, gem.y, width * 0.018f, Color.rgb(110, 255, 160))
        for (shot in shots) {
            paint.color = if (shot.hostile) Color.rgb(255, 90, 120) else Color.rgb(88, 230, 255)
            canvas.drawCircle(shot.x, shot.y, width * 0.009f, paint)
        }
        for (enemy in enemies) drawEnemy(canvas, enemy)
        for (spark in sparks) {
            paint.color = Color.argb((spark.life * 340f).toInt().coerceIn(0, 255), Color.red(spark.color), Color.green(spark.color), Color.blue(spark.color))
            canvas.drawCircle(spark.x, spark.y, width * 0.007f, paint)
        }
        drawHero(canvas, playerX, playerY, facing, width * 0.075f)
        drawHud(canvas)
    }

    private fun drawHero(canvas: Canvas, x: Float, y: Float, angle: Float, size: Float) {
        canvas.save()
        canvas.rotate(Math.toDegrees(angle.toDouble()).toFloat() + 90f, x, y)
        val body = Path().apply {
            moveTo(x, y - size * 0.72f)
            lineTo(x - size * 0.48f, y + size * 0.50f)
            lineTo(x, y + size * 0.28f)
            lineTo(x + size * 0.48f, y + size * 0.50f)
            close()
        }
        paint.color = Color.rgb(230, 245, 255)
        canvas.drawPath(body, paint)
        paint.color = Color.rgb(28, 45, 80)
        canvas.drawCircle(x, y - size * 0.18f, size * 0.34f, paint)
        paint.color = Color.rgb(88, 230, 255)
        canvas.drawRect(x - size * 0.25f, y - size * 0.23f, x + size * 0.25f, y - size * 0.11f, paint)
        paint.color = Color.rgb(196, 92, 255)
        canvas.drawRect(x - size * 0.10f, y + size * 0.20f, x + size * 0.10f, y + size * 0.78f, paint)
        canvas.restore()
    }

    private fun drawEnemy(canvas: Canvas, enemy: Enemy) {
        paint.color = enemyColor(enemy.type)
        when (enemy.type) {
            0 -> {
                val path = Path()
                for (i in 0..5) {
                    val angle = 6.28f * i / 6f + enemy.phase
                    val radius = if (i % 2 == 0) enemy.radius else enemy.radius * 0.55f
                    val x = enemy.x + cos(angle) * radius
                    val y = enemy.y + sin(angle) * radius
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                path.close()
                canvas.drawPath(path, paint)
            }
            1 -> canvas.drawRoundRect(enemy.x - enemy.radius, enemy.y - enemy.radius * 0.55f, enemy.x + enemy.radius, enemy.y + enemy.radius * 0.55f, enemy.radius * 0.3f, enemy.radius * 0.3f, paint)
            2 -> {
                paint.style = Paint.Style.STROKE
                paint.strokeWidth = enemy.radius * 0.22f
                canvas.drawCircle(enemy.x, enemy.y, enemy.radius * 0.75f, paint)
                paint.style = Paint.Style.FILL
            }
            3 -> {
                val path = Path().apply {
                    moveTo(enemy.x, enemy.y - enemy.radius)
                    lineTo(enemy.x - enemy.radius * 0.85f, enemy.y + enemy.radius * 0.55f)
                    lineTo(enemy.x, enemy.y + enemy.radius)
                    lineTo(enemy.x + enemy.radius * 0.85f, enemy.y + enemy.radius * 0.55f)
                    close()
                }
                canvas.drawPath(path, paint)
            }
            else -> {
                paint.style = Paint.Style.STROKE
                paint.strokeWidth = enemy.radius * 0.20f
                canvas.drawCircle(enemy.x, enemy.y, enemy.radius, paint)
                canvas.drawCircle(enemy.x, enemy.y, enemy.radius * 0.62f, paint)
                paint.style = Paint.Style.FILL
            }
        }
        if (enemy.type >= 3) {
            paint.color = Color.argb(150, 0, 0, 0)
            canvas.drawRect(enemy.x - enemy.radius, enemy.y - enemy.radius * 1.35f, enemy.x + enemy.radius, enemy.y - enemy.radius * 1.18f, paint)
            paint.color = Color.rgb(110, 255, 160)
            canvas.drawRect(enemy.x - enemy.radius, enemy.y - enemy.radius * 1.35f, enemy.x - enemy.radius + 2f * enemy.radius * (enemy.hp / enemy.maxHp), enemy.y - enemy.radius * 1.18f, paint)
        }
    }

    private fun drawHud(canvas: Canvas) {
        paint.color = Color.argb(170, 5, 8, 20)
        canvas.drawRoundRect(width * 0.03f, height * 0.025f, width * 0.97f, height * 0.13f, 18f, 18f, paint)
        paint.color = Color.rgb(45, 55, 80)
        canvas.drawRoundRect(width * 0.06f, height * 0.048f, width * 0.52f, height * 0.067f, 10f, 10f, paint)
        paint.color = Color.rgb(255, 75, 110)
        canvas.drawRoundRect(width * 0.06f, height * 0.048f, width * 0.06f + width * 0.46f * (hp / maxHp), height * 0.067f, 10f, 10f, paint)
        text(canvas, "NV $level", height * 0.058f, width * 0.034f, Color.WHITE)
        text(canvas, "${elapsed.toInt()}s", height * 0.103f, width * 0.045f, Color.rgb(88, 230, 255))
        val objectiveName = when (objective) {
            0 -> "ELIMINE A HORDA"
            1 -> "COLETE FRAGMENTOS"
            2 -> "SOBREVIVA"
            3 -> "DERROTE O NÚCLEO"
            else -> "RESISTA À RUPTURA"
        }
        text(canvas, objectiveName, height * 0.155f, width * 0.033f, Color.WHITE)
        text(canvas, "$objectiveProgress / $objectiveTarget", height * 0.188f, width * 0.030f, Color.rgb(110, 255, 160))
    }

    private fun drawUpgrade(canvas: Canvas) {
        paint.color = Color.argb(225, 3, 5, 15)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        text(canvas, "ESCOLHA UMA RUPTURA", height * 0.22f, width * 0.056f, Color.WHITE)
        val names = arrayOf("POTÊNCIA", "CADÊNCIA", "IMPULSO", "DISPARO DUPLO", "VITALIDADE", "MAGNETISMO")
        for (i in 0..2) {
            val left = i * width / 3f + 12f
            val right = (i + 1) * width / 3f - 12f
            paint.color = Color.rgb(18, 28, 56)
            canvas.drawRoundRect(left, height * 0.35f, right, height * 0.68f, 24f, 24f, paint)
            paint.color = if (i == 1) Color.rgb(196, 92, 255) else Color.rgb(88, 230, 255)
            canvas.drawCircle((left + right) / 2f, height * 0.44f, width * 0.045f, paint)
            textAt(canvas, names[upgradeChoices[i]], (left + right) / 2f, height * 0.56f, width * 0.031f, Color.WHITE)
        }
    }

    private fun drawDead(canvas: Canvas) {
        paint.color = Color.argb(225, 3, 5, 15)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        text(canvas, "RUPTURA COLAPSADA", height * 0.38f, width * 0.060f, Color.WHITE)
        text(canvas, "${elapsed.toInt()}s • $kills baixas", height * 0.49f, width * 0.045f, Color.rgb(88, 230, 255))
        text(canvas, "TOQUE PARA REENTRAR", height * 0.66f, width * 0.042f, Color.WHITE)
    }

    private fun drawVictory(canvas: Canvas) {
        paint.color = Color.argb(230, 3, 5, 15)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        text(canvas, "NÚCLEO DESTRUÍDO", height * 0.38f, width * 0.062f, Color.rgb(110, 255, 160))
        text(canvas, "MISSÃO CONCLUÍDA", height * 0.49f, width * 0.046f, Color.WHITE)
        text(canvas, "TOQUE PARA NOVA INCURSÃO", height * 0.66f, width * 0.040f, Color.WHITE)
    }

    private fun drawDiamond(canvas: Canvas, x: Float, y: Float, radius: Float, color: Int) {
        val path = Path().apply {
            moveTo(x, y - radius)
            lineTo(x + radius, y)
            lineTo(x, y + radius)
            lineTo(x - radius, y)
            close()
        }
        paint.color = color
        canvas.drawPath(path, paint)
    }

    private fun text(canvas: Canvas, value: String, y: Float, size: Float, color: Int) =
        textAt(canvas, value, width / 2f, y, size, color)

    private fun textAt(canvas: Canvas, value: String, x: Float, y: Float, size: Float, color: Int) {
        paint.textAlign = Paint.Align.CENTER
        paint.textSize = size
        paint.color = color
        canvas.drawText(value, x, y, paint)
    }
}
