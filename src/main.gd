extends Node2D

const SAVE_PATH := "user://eco_save.json"
const W := 720.0
const H := 1280.0
const PLAYER_X := 150.0
const TOP := 160.0
const BOTTOM := 1120.0

var state := "menu"
var player_y := H / 2.0
var velocity := 0.0
var polarity := 1.0
var score := 0.0
var best := 0
var shards := 0
var speed := 285.0
var spawn_timer := 0.0
var pulse := 0.0
var shake := 0.0
var obstacles: Array[Dictionary] = []
var particles: Array[Dictionary] = []
var echoes: Array[Dictionary] = []
var current_run: Array[Vector2] = []
var previous_run: Array[Vector2] = []
var sample_timer := 0.0
var rng := RandomNumberGenerator.new()

func _ready() -> void:
	rng.randomize()
	load_game()
	set_process(true)
	queue_redraw()

func _process(delta: float) -> void:
	pulse += delta
	shake = maxf(0.0, shake - delta * 18.0)
	update_particles(delta)
	if state == "playing":
		update_game(delta)
	queue_redraw()

func _unhandled_input(event: InputEvent) -> void:
	var pressed := false
	if event is InputEventScreenTouch:
		pressed = event.pressed
	elif event is InputEventMouseButton:
		pressed = event.pressed and event.button_index == MOUSE_BUTTON_LEFT
	if not pressed:
		return
	if state == "menu" or state == "gameover":
		start_game()
	else:
		flip()

func start_game() -> void:
	state = "playing"
	player_y = H / 2.0
	velocity = -180.0
	polarity = -1.0
	score = 0.0
	speed = 285.0
	spawn_timer = 0.55
	obstacles.clear()
	particles.clear()
	current_run.clear()
	sample_timer = 0.0
	spawn_obstacle(860.0)

func flip() -> void:
	polarity *= -1.0
	velocity = 480.0 * polarity
	shake = 4.0
	burst(Vector2(PLAYER_X, player_y), 10)

func update_game(delta: float) -> void:
	score += delta * 10.0
	speed = minf(560.0, 285.0 + score * 1.35)
	velocity += 1150.0 * polarity * delta
	velocity = clampf(velocity, -760.0, 760.0)
	player_y += velocity * delta

	if player_y < TOP + 25.0 or player_y > BOTTOM - 25.0:
		die()
		return

	spawn_timer -= delta
	if spawn_timer <= 0.0:
		spawn_obstacle(W + 90.0)
		spawn_timer = maxf(0.62, 1.22 - score / 550.0) + rng.randf_range(-0.08, 0.10)

	for obstacle in obstacles:
		obstacle.x -= speed * delta
		if not obstacle.passed and obstacle.x < PLAYER_X:
			obstacle.passed = true
			shards += 1
			burst(Vector2(PLAYER_X + 35.0, player_y), 5)
		if collide_obstacle(obstacle):
			die()
			return
	obstacles = obstacles.filter(func(o): return o.x > -100.0)

	sample_timer -= delta
	if sample_timer <= 0.0:
		current_run.append(Vector2(score, player_y))
		sample_timer = 0.08

func spawn_obstacle(x_pos: float) -> void:
	var gap := maxf(245.0, 350.0 - score * 0.42)
	var center := rng.randf_range(TOP + gap * 0.58, BOTTOM - gap * 0.58)
	obstacles.append({"x": x_pos, "center": center, "gap": gap, "passed": false})

func collide_obstacle(o: Dictionary) -> bool:
	if absf(o.x - PLAYER_X) > 48.0:
		return false
	var radius := 22.0
	return player_y - radius < o.center - o.gap / 2.0 or player_y + radius > o.center + o.gap / 2.0

func die() -> void:
	state = "gameover"
	shake = 13.0
	burst(Vector2(PLAYER_X, clampf(player_y, TOP, BOTTOM)), 34)
	var final_score := int(score)
	if final_score > best:
		best = final_score
	previous_run = current_run.duplicate()
	save_game()

func burst(pos: Vector2, amount: int) -> void:
	for i in amount:
		var angle := rng.randf_range(0.0, TAU)
		var force := rng.randf_range(70.0, 310.0)
		particles.append({
			"p": pos,
			"v": Vector2(cos(angle), sin(angle)) * force,
			"life": rng.randf_range(0.25, 0.75),
			"size": rng.randf_range(2.0, 7.0)
		})

func update_particles(delta: float) -> void:
	for p in particles:
		p.p += p.v * delta
		p.v *= 0.96
		p.life -= delta
	particles = particles.filter(func(p): return p.life > 0.0)

func ghost_y_at(run_score: float) -> float:
	if previous_run.is_empty():
		return -100.0
	var index := int(run_score / 0.8)
	if index >= 0 and index < previous_run.size():
		return previous_run[index].y
	return -100.0

func _draw() -> void:
	var offset := Vector2(rng.randf_range(-shake, shake), rng.randf_range(-shake, shake)) if shake > 0.0 else Vector2.ZERO
	draw_set_transform(offset)
	draw_background()
	if state == "menu":
		draw_menu()
	else:
		draw_world()
		if state == "gameover":
			draw_game_over()
	draw_set_transform(Vector2.ZERO)

func draw_background() -> void:
	draw_rect(Rect2(0, 0, W, H), Color("07091a"))
	for i in range(14):
		var y := fmod(float(i * 101) + pulse * (8.0 + i), H)
		var alpha := 0.035 + float(i % 3) * 0.012
		draw_line(Vector2(0, y), Vector2(W, y - 80), Color(0.3, 0.7, 1.0, alpha), 1.0)
	var glow := 80.0 + sin(pulse * 1.8) * 8.0
	draw_circle(Vector2(W * 0.82, H * 0.18), glow, Color(0.35, 0.1, 0.8, 0.08))
	draw_circle(Vector2(W * 0.18, H * 0.82), glow * 1.3, Color(0.0, 0.85, 0.8, 0.05))

func draw_menu() -> void:
	center_text("ECO", 180, 104, Color("eaf6ff"))
	center_text("ÚLTIMO TOQUE", 275, 32, Color("58e6ff"))
	center_text("VOCÊ JOGA CONTRA O SEU PASSADO", 350, 22, Color(0.7, 0.78, 0.9))

	var c := Vector2(W / 2.0, 600.0)
	draw_circle(c, 95.0 + sin(pulse * 2.2) * 7.0, Color(0.2, 0.85, 1.0, 0.08))
	draw_circle(c, 42.0, Color("58e6ff"))
	draw_circle(c, 20.0, Color("07101d"))
	draw_arc(c, 66.0, -PI * 0.8, PI * 0.8, 48, Color("c45cff"), 8.0)

	center_text("TOQUE PARA INICIAR", 790, 30, Color("ffffff"))
	center_text("toque durante a partida para inverter a queda", 844, 20, Color(0.55, 0.64, 0.76))
	center_text("RECORDE  %06d" % best, 1015, 24, Color("c45cff"))
	center_text("FRAGMENTOS  %d" % shards, 1058, 20, Color("58e6ff"))

func draw_world() -> void:
	draw_line(Vector2(0, TOP), Vector2(W, TOP), Color("253354"), 3.0)
	draw_line(Vector2(0, BOTTOM), Vector2(W, BOTTOM), Color("253354"), 3.0)

	var gy := ghost_y_at(score)
	if gy > 0.0:
		draw_circle(Vector2(PLAYER_X, gy), 20.0, Color(0.76, 0.36, 1.0, 0.20))
		draw_arc(Vector2(PLAYER_X, gy), 30.0, 0, TAU, 24, Color(0.76, 0.36, 1.0, 0.25), 3.0)

	for o in obstacles:
		var x: float = o.x
		var top_h: float = o.center - o.gap / 2.0 - TOP
		var bottom_y: float = o.center + o.gap / 2.0
		draw_rect(Rect2(x - 30.0, TOP, 60.0, top_h), Color("18284b"))
		draw_rect(Rect2(x - 30.0, bottom_y, 60.0, BOTTOM - bottom_y), Color("18284b"))
		draw_rect(Rect2(x - 35.0, o.center - o.gap / 2.0 - 10.0, 70.0, 10.0), Color("58e6ff"))
		draw_rect(Rect2(x - 35.0, o.center + o.gap / 2.0, 70.0, 10.0), Color("c45cff"))

	var player := Vector2(PLAYER_X, player_y)
	draw_circle(player, 34.0 + sin(pulse * 8.0) * 2.0, Color(0.35, 0.9, 1.0, 0.10))
	draw_circle(player, 22.0, Color("eaf6ff"))
	draw_circle(player, 10.0, Color("58e6ff") if polarity < 0 else Color("c45cff"))
	var tail_dir := -signf(velocity)
	draw_line(player, player + Vector2(-42.0, tail_dir * 18.0), Color(0.35, 0.9, 1.0, 0.45), 8.0)

	for p in particles:
		draw_circle(p.p, p.size, Color(0.35, 0.9, 1.0, clampf(p.life * 1.8, 0.0, 1.0)))

	draw_string(ThemeDB.fallback_font, Vector2(36, 80), "%06d" % int(score), HORIZONTAL_ALIGNMENT_LEFT, -1, 40, Color("ffffff"))
	draw_string(ThemeDB.fallback_font, Vector2(W - 210, 72), "ECO %06d" % best, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("c45cff"))

func draw_game_over() -> void:
	draw_rect(Rect2(0, 0, W, H), Color(0.01, 0.015, 0.04, 0.68))
	center_text("SINAL PERDIDO", 430, 45, Color("ffffff"))
	center_text("%06d" % int(score), 535, 76, Color("58e6ff"))
	center_text("seu próximo inimigo acaba de nascer", 635, 22, Color(0.75, 0.65, 0.95))
	center_text("TOQUE PARA REESCREVER", 790, 28, Color("ffffff"))
	center_text("RECORDE  %06d" % best, 850, 20, Color(0.6, 0.7, 0.85))

func center_text(text: String, y: float, size: int, color: Color) -> void:
	var width := ThemeDB.fallback_font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	draw_string(ThemeDB.fallback_font, Vector2((W - width) / 2.0, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)

func save_game() -> void:
	var data := {"best": best, "shards": shards}
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(data))

func load_game() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if not file:
		return
	var parsed = JSON.parse_string(file.get_as_text())
	if parsed is Dictionary:
		best = int(parsed.get("best", 0))
		shards = int(parsed.get("shards", 0))
