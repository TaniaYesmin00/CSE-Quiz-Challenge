"""CSE Quiz Challenge - a desktop multiple-choice quiz game built with Pygame.

Run with:  python main.py
All game rules live in quiz_logic.py; this file only handles drawing and input.
"""
from __future__ import annotations

import array
import math
import random
import sqlite3
import sys

import pygame

import database
import quiz_logic as ql

WIDTH, HEIGHT = 1000, 680
FPS = 60
FEEDBACK_SECONDS = 1.5

# ------------------------------ palette ------------------------------------ #
BG_TOP = (10, 14, 34)
BG_BOTTOM = (26, 18, 56)
PANEL = (24, 32, 62)
PANEL2 = (33, 44, 80)
BORDER = (60, 78, 124)
WHITE = (242, 246, 255)
MUTED = (160, 174, 206)
DIM = (96, 111, 150)
CYAN = (78, 220, 230)
PURPLE = (157, 117, 255)
GREEN = (85, 220, 151)
RED = (255, 105, 125)
YELLOW = (255, 211, 105)
DIFF_COLORS = {"Easy": GREEN, "Medium": YELLOW, "Hard": RED}
GRADE_COLORS = {"S": YELLOW, "A": GREEN, "B": CYAN, "C": MUTED}


# ------------------------------ small helpers ------------------------------ #
def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def make_gradient(width, height, top, bottom):
    surf = pygame.Surface((width, height))
    for y in range(height):
        pygame.draw.line(surf, mix(top, bottom, y / max(1, height - 1)), (0, y), (width, y))
    return surf


def make_font(size, bold=False):
    return pygame.font.SysFont("segoeui,helveticaneue,arial,dejavusans", size, bold=bold)


def wrap_text(text, font, max_width):
    lines, line = [], ""
    for word in str(text).split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


# ------------------------------ sound -------------------------------------- #
class Sfx:
    """Tiny synthesised sound effects (no audio files needed). Fails silently."""

    def __init__(self):
        self.enabled = True
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 1, 512)
            rate, fmt, channels = pygame.mixer.get_init()
            if fmt != -16:
                raise pygame.error("unsupported mixer format")
            self.rate, self.channels = rate, channels
            self.sounds = {
                "click": self._tone([(720, 0.05)], 0.25),
                "correct": self._tone([(523, 0.09), (659, 0.09), (784, 0.16)], 0.3),
                "wrong": self._tone([(220, 0.16), (165, 0.26)], 0.3),
                "tick": self._tone([(980, 0.03)], 0.18),
                "win": self._tone([(523, 0.10), (659, 0.10), (784, 0.10), (1047, 0.30)], 0.3),
                "lose": self._tone([(392, 0.15), (330, 0.15), (262, 0.35)], 0.3),
            }
        except (pygame.error, NotImplementedError, TypeError, ValueError):
            self.sounds = {}

    def _tone(self, notes, volume):
        data = array.array("h")
        for freq, seconds in notes:
            count = int(self.rate * seconds)
            for i in range(count):
                envelope = min(1.0, i / 200.0, (count - i) / 400.0)
                value = int(32767 * volume * envelope * math.sin(2 * math.pi * freq * i / self.rate))
                for _ in range(self.channels):
                    data.append(value)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def play(self, name):
        if self.enabled and name in self.sounds:
            self.sounds[name].play()


# ------------------------------ the game ----------------------------------- #
class QuizGame:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("CSE Quiz Challenge")
        self._set_icon()
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.sfx = Sfx()

        self.f_small = make_font(15)
        self.f_body = make_font(21)
        self.f_med = make_font(27, True)
        self.f_q = make_font(27, True)
        self.f_q_small = make_font(22, True)
        self.f_big = make_font(54, True)
        self.f_huge = make_font(96, True)
        self._text_cache = {}
        self._shadow_cache = {}
        self._grad_cache = {}

        self.questions = ql.load_questions()
        self.categories = ql.list_categories(self.questions)
        try:
            self.db = database.Database()
        except (sqlite3.Error, OSError):
            self.db = None  # e.g. read-only folder: guest mode still works
        self.user = None
        self.dash = None
        self.guest_best = 0
        self.save_note = ""
        self.auth_mode = "login"
        self.auth_fields = {"username": "", "password": "", "confirm": ""}
        self.auth_focus = "username"
        self.auth_error = "" if self.db else "Database unavailable - guest mode only"
        self.round_filters = ("All", "All")

        self.bg = make_gradient(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)
        self.fade_surface = pygame.Surface((WIDTH, HEIGHT))
        self.fade_surface.fill(BG_TOP)
        self.flash_surface = pygame.Surface((WIDTH, HEIGHT))
        self.particles = [
            {
                "x": random.uniform(0, WIDTH),
                "y": random.uniform(0, HEIGHT),
                "r": random.choice((1, 1, 2, 2, 3)),
                "v": random.uniform(8, 26),
                "p": random.uniform(0, 6.28),
            }
            for _ in range(46)
        ]
        self.confetti = []
        self.popups = []

        self.state = "auth"
        self.running = True
        self.difficulty = "All"
        self.category = "All"
        self.round = None
        self.display_score = 0.0
        self.feedback = ""
        self.feedback_color = WHITE
        self.feedback_time = 0.0
        self.new_best = False
        self.review_index = 0
        self.fade = 255.0
        self.flash = 0.0
        self.flash_color = GREEN
        self.shake = 0.0
        self.time = 0.0
        self.dt = 0.0
        self.hover = {}
        self.buttons = []
        self._next_buttons = []
        self._hand_cursor = False
        self.last_tick_second = None

    # ----------------------------- setup helpers --------------------------- #
    def _set_icon(self):
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.rect(icon, (36, 28, 90), (0, 0, 64, 64), border_radius=16)
        pygame.draw.rect(icon, CYAN, (0, 0, 64, 64), 4, border_radius=16)
        pygame.draw.circle(icon, CYAN, (30, 30), 14, 5)
        pygame.draw.line(icon, PURPLE, (39, 39), (50, 50), 6)
        pygame.display.set_icon(icon)

    def set_state(self, state):
        self.state = state
        self.fade = 255.0
        self.sfx.play("click")

    # ----------------------------- drawing primitives ---------------------- #
    def text(self, value, x, y, font=None, color=WHITE, anchor="topleft"):
        font = font or self.f_body
        key = (str(value), id(font), color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 600:
                self._text_cache.clear()
            surf = font.render(str(value), True, color)
            self._text_cache[key] = surf
        rect = surf.get_rect(**{anchor: (x, y)})
        self.screen.blit(surf, rect)
        return rect

    def shadow(self, rect, radius, color=(0, 0, 0), spread=16, strength=90, offset=(0, 6)):
        rect = pygame.Rect(rect)
        key = (rect.w, rect.h, radius, color, spread, strength)
        surf = self._shadow_cache.get(key)
        if surf is None:
            surf = pygame.Surface((rect.w + spread * 2, rect.h + spread * 2), pygame.SRCALPHA)
            for i in range(spread, 0, -1):
                alpha = int(strength * (1 - i / spread) ** 2)
                pygame.draw.rect(
                    surf,
                    (*color, alpha),
                    (spread - i, spread - i, rect.w + i * 2, rect.h + i * 2),
                    border_radius=radius + i,
                )
            self._shadow_cache[key] = surf
        self.screen.blit(surf, (rect.x - spread + offset[0], rect.y - spread + offset[1]))

    def card(self, rect, fill=PANEL, radius=20, border=BORDER, shadow=True):
        rect = pygame.Rect(rect)
        if shadow:
            self.shadow(rect, radius)
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        if border:
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=radius)

    def gradient_rect(self, rect, c1, c2, radius):
        rect = pygame.Rect(rect)
        key = (rect.w, rect.h, c1, c2, radius)
        surf = self._grad_cache.get(key)
        if surf is None:
            surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            for x in range(rect.w):
                pygame.draw.line(surf, mix(c1, c2, x / max(1, rect.w - 1)), (x, 0), (x, rect.h))
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, rect.w, rect.h), border_radius=radius)
            surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self._grad_cache[key] = surf
        self.screen.blit(surf, rect)

    def pill(self, label, x, y, color, anchor="topleft"):
        surf = self.f_small.render(label, True, color)
        rect = surf.get_rect()
        rect.inflate_ip(22, 10)
        setattr(rect, anchor, (x, y))
        pygame.draw.rect(self.screen, mix(PANEL, color, 0.16), rect, border_radius=rect.h // 2)
        pygame.draw.rect(self.screen, mix(PANEL, color, 0.55), rect, 1, border_radius=rect.h // 2)
        self.screen.blit(surf, surf.get_rect(center=rect.center))
        return rect

    def heart(self, cx, cy, size, color):
        r = size * 0.27
        pygame.draw.circle(self.screen, color, (cx - size * 0.25, cy - size * 0.12), r)
        pygame.draw.circle(self.screen, color, (cx + size * 0.25, cy - size * 0.12), r)
        pygame.draw.polygon(
            self.screen,
            color,
            [(cx - size * 0.50, cy - size * 0.02), (cx + size * 0.50, cy - size * 0.02), (cx, cy + size * 0.50)],
        )

    def check_icon(self, cx, cy, color):
        pygame.draw.lines(self.screen, color, False, [(cx - 9, cy), (cx - 3, cy + 7), (cx + 9, cy - 7)], 4)

    def cross_icon(self, cx, cy, color):
        pygame.draw.line(self.screen, color, (cx - 7, cy - 7), (cx + 7, cy + 7), 4)
        pygame.draw.line(self.screen, color, (cx - 7, cy + 7), (cx + 7, cy - 7), 4)

    def bolt_icon(self, cx, cy, color):
        pts = [(cx + 3, cy - 10), (cx - 6, cy + 2), (cx - 1, cy + 2), (cx - 4, cy + 10), (cx + 6, cy - 3), (cx + 1, cy - 3)]
        pygame.draw.polygon(self.screen, color, pts)

    def arrow_icon(self, cx, cy, color, direction=1):
        d = direction
        pygame.draw.line(self.screen, color, (cx - 9 * d, cy), (cx + 7 * d, cy), 3)
        pygame.draw.lines(self.screen, color, False, [(cx + 1 * d, cy - 7), (cx + 8 * d, cy), (cx + 1 * d, cy + 7)], 3)

    # ----------------------------- widgets --------------------------------- #
    def hover_amount(self, key, hovered):
        cur = self.hover.get(key, 0.0)
        cur += ((1.0 if hovered else 0.0) - cur) * min(1.0, self.dt * 16)
        self.hover[key] = cur
        return cur

    def button(self, key, label, rect, action, fill=PANEL2, border=BORDER, color=WHITE, font=None,
               gradient=None, enabled=True, icon=None):
        rect = pygame.Rect(rect)
        hovered = enabled and rect.collidepoint(pygame.mouse.get_pos())
        h = self.hover_amount(key, hovered)
        draw_rect = rect.move(0, int(-2 * h))
        self.shadow(draw_rect, 14, spread=12, strength=70 + int(40 * h))
        if gradient:
            self.gradient_rect(draw_rect, gradient[0], gradient[1], 14)
            if h > 0.02:
                pygame.draw.rect(self.screen, mix(gradient[1], WHITE, 0.6), draw_rect, 2, border_radius=14)
        else:
            body = mix(fill, WHITE, 0.07 * h) if enabled else mix(fill, BG_TOP, 0.5)
            pygame.draw.rect(self.screen, body, draw_rect, border_radius=14)
            edge = mix(border, CYAN, h) if enabled else mix(border, BG_TOP, 0.5)
            pygame.draw.rect(self.screen, edge, draw_rect, 2, border_radius=14)
        label_color = color if enabled else DIM
        font = font or self.f_body
        if icon:
            width = font.size(label)[0]
            self.text(label, draw_rect.centerx - 14, draw_rect.centery, font, label_color, "center")
            icon(draw_rect.centerx + width // 2 + 4, draw_rect.centery, label_color)
        else:
            self.text(label, draw_rect.centerx, draw_rect.centery, font, label_color, "center")
        if enabled:
            self._next_buttons.append((rect, action))

    def chips(self, items, selected, setter, y, max_width, prefix):
        font = self.f_small
        widths = [font.size(i)[0] + 30 for i in items]
        rows, row, row_w = [], [], 0
        for item, w in zip(items, widths):
            if row and row_w + w + 10 > max_width:
                rows.append((row, row_w))
                row, row_w = [], 0
            row.append((item, w))
            row_w += w + (10 if row_w else 0)
        if row:
            rows.append((row, row_w))
        for row, row_w in rows:
            x = WIDTH // 2 - row_w // 2
            for item, w in row:
                active = item == selected
                self.button(
                    f"{prefix}{item}", item, (x, y, w, 34), lambda v=item: setter(v),
                    fill=mix(PANEL2, PURPLE, 0.35) if active else PANEL2,
                    border=CYAN if active else BORDER, color=CYAN if active else WHITE, font=font,
                )
                x += w + 10
            y += 42
        return y

    # ----------------------------- game actions ---------------------------- #
    def set_difficulty(self, value):
        self.difficulty = value

    def set_category(self, value):
        self.category = value

    def start_round(self):
        self.round = ql.build_round(self.questions, self.difficulty, self.category)
        self.round_filters = (self.difficulty, self.category)
        self.save_note = ""
        self.display_score = 0.0
        self.feedback = ""
        self.feedback_time = 0.0
        self.new_best = False
        self.popups.clear()
        self.confetti.clear()
        self.last_tick_second = None
        self.set_state("quiz")

    def go_menu(self):
        """MAIN MENU button: the dashboard for players, the setup screen for guests."""
        self.set_state("dashboard" if self.user else "menu")

    def go_setup(self):
        self.set_state("menu")

    def go_back(self):
        if not self.user:
            self.auth_focus = "username"
        self.set_state("dashboard" if self.user else "auth")

    def current_best(self):
        if self.user and self.dash:
            return self.dash["stats"]["high_score"]
        return self.guest_best

    def refresh_dash(self):
        try:
            uid = self.user["id"]
            self.dash = {
                "stats": self.db.user_stats(uid),
                "recent": self.db.recent_games(uid, 5),
                "board": self.db.leaderboard(5),
            }
        except sqlite3.Error:
            self.dash = {"stats": {"games_played": 0, "high_score": 0, "best_streak": 0,
                                   "total_correct": 0, "accuracy": 0}, "recent": [], "board": []}
            self.save_note = "Could not read the database"

    # ----- accounts
    def set_auth_mode(self, mode):
        self.auth_mode = mode
        self.auth_error = ""
        self.auth_focus = "username"
        self.sfx.play("click")

    def focus_field(self, key):
        self.auth_focus = key

    def auth_field_order(self):
        return ["username", "password"] + (["confirm"] if self.auth_mode == "register" else [])

    def submit_auth(self):
        if not self.db:
            self.auth_error = "Database unavailable - play as guest"
            return
        fields = self.auth_fields
        try:
            if self.auth_mode == "register":
                if fields["password"] != fields["confirm"]:
                    raise database.AuthError("Passwords do not match")
                user = self.db.register(fields["username"], fields["password"])
            else:
                user = self.db.authenticate(fields["username"], fields["password"])
        except database.AuthError as exc:
            self.auth_error = str(exc)
            self.sfx.play("wrong")
            return
        except sqlite3.Error:
            self.auth_error = "Database error - please try again"
            self.sfx.play("wrong")
            return
        self.user = user
        self.auth_fields = {"username": "", "password": "", "confirm": ""}
        self.auth_focus, self.auth_error = "username", ""
        self.refresh_dash()
        self.set_state("dashboard")
        self.sfx.play("correct")

    def play_as_guest(self):
        self.user, self.dash = None, None
        self.set_state("menu")

    def logout(self):
        self.user, self.dash, self.round = None, None, None
        self.auth_mode, self.auth_error, self.auth_focus = "login", "", "username"
        self.set_state("auth")

    def auth_key(self, key, char):
        order = self.auth_field_order()
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_TAB:
            self.auth_focus = order[(order.index(self.auth_focus) + 1) % len(order)] if self.auth_focus in order else order[0]
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.submit_auth()
        elif key == pygame.K_BACKSPACE:
            self.auth_fields[self.auth_focus] = self.auth_fields[self.auth_focus][:-1]
        elif char and char.isprintable():
            focus = self.auth_focus
            if focus == "username":
                if not (char.isascii() and (char.isalnum() or char == "_")):
                    return
                limit = 16
            else:
                limit = database.MAX_PASSWORD_LENGTH
            if len(self.auth_fields[focus]) < limit:
                self.auth_fields[focus] += char
                self.auth_error = ""

    def submit(self, choice):
        r = self.round
        if not r or r.locked or self.state != "quiz":
            return
        result = r.answer(choice)
        self.feedback_time = 0.0
        if result.correct:
            self.feedback = f"Correct!  +{result.points} points"
            self.feedback_color = GREEN
            self.flash, self.flash_color = 0.6, GREEN
            self.popups.append({"text": f"+{result.points}", "x": 500.0, "y": 92.0, "life": 1.0, "color": GREEN})
            self.sfx.play("correct")
        else:
            if result.timed_out:
                self.feedback = "Time is up! The correct answer is highlighted."
            else:
                self.feedback = "Not quite - the correct answer is highlighted."
            self.feedback_color = RED
            self.flash, self.flash_color = 0.8, RED
            self.shake = 1.0
            self.sfx.play("wrong")

    def next_question(self):
        r = self.round
        if r is None:
            return
        if r.finished:
            self.finish_round()
        else:
            r.advance()
            self.feedback = ""
            self.last_tick_second = None

    def finish_round(self):
        r = self.round
        self.new_best = r.score > self.current_best()
        if self.user:
            try:
                self.db.record_game(
                    self.user["id"], score=r.score, correct=r.correct_count, answered=r.answered,
                    total=r.total, best_streak=r.best_streak, grade=r.grade,
                    difficulty=self.round_filters[0], category=self.round_filters[1],
                )
                self.refresh_dash()
            except sqlite3.Error:
                self.save_note = "Could not save this game to the database"
        else:
            self.guest_best = max(self.guest_best, r.score)
        self.review_index = 0
        self.set_state("results")
        if self.new_best or r.grade in ("S", "A"):
            self.spawn_confetti()
            self.sfx.play("win")
        else:
            self.sfx.play("lose" if r.lives <= 0 else "click")

    def spawn_confetti(self):
        colors = (CYAN, PURPLE, GREEN, YELLOW, RED, WHITE)
        for _ in range(110):
            self.confetti.append({
                "x": random.uniform(0, WIDTH), "y": random.uniform(-260, -10),
                "vx": random.uniform(-40, 40), "vy": random.uniform(60, 220),
                "w": random.randint(5, 10), "h": random.randint(3, 6), "c": random.choice(colors),
            })

    def use_fifty(self):
        if self.state == "quiz" and self.round and self.round.use_fifty_fifty():
            self.sfx.play("click")

    def toggle_pause(self):
        if self.state == "quiz":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "quiz"

    # ----------------------------- update ---------------------------------- #
    def update(self, dt):
        self.time += dt
        self.fade = max(0.0, self.fade - dt * 1100)
        self.flash = max(0.0, self.flash - dt * 1.8)
        self.shake = max(0.0, self.shake - dt * 2.2)
        for p in self.particles:
            p["y"] -= p["v"] * dt
            if p["y"] < -6:
                p["y"], p["x"] = HEIGHT + 6, random.uniform(0, WIDTH)
        for c in self.confetti:
            c["vy"] += 260 * dt
            c["x"] += c["vx"] * dt
            c["y"] += c["vy"] * dt
        self.confetti = [c for c in self.confetti if c["y"] < HEIGHT + 20]
        for p in self.popups:
            p["y"] -= 38 * dt
            p["life"] -= dt * 0.9
        self.popups = [p for p in self.popups if p["life"] > 0]

        if self.state == "quiz" and self.round:
            r = self.round
            if not r.locked:
                if r.tick(dt):
                    self.submit(-1)
                else:
                    second = int(r.time_left)
                    if r.time_left <= 5 and second != self.last_tick_second:
                        self.last_tick_second = second
                        self.sfx.play("tick")
            else:
                self.feedback_time += dt
                if self.feedback_time >= FEEDBACK_SECONDS:
                    self.next_question()
            self._approach_score(dt, 8)
        elif self.state == "results" and self.round:
            self._approach_score(dt, 5)

    def _approach_score(self, dt, speed):
        target = self.round.score
        self.display_score += (target - self.display_score) * min(1.0, dt * speed)
        if abs(target - self.display_score) < 1:
            self.display_score = float(target)

    # ----------------------------- drawing --------------------------------- #
    def draw_background(self):
        self.screen.blit(self.bg, (0, 0))
        for x, y, r in [(70, 90, 110), (930, 110, 150), (910, 610, 110), (110, 600, 80)]:
            pygame.draw.circle(self.screen, (30, 40, 82), (x, y), r, 2)
            pygame.draw.circle(self.screen, (24, 32, 68), (x, y), r + 14, 1)
        for p in self.particles:
            twinkle = 0.5 + 0.5 * math.sin(self.time * 1.4 + p["p"])
            color = (int(34 + 46 * twinkle), int(48 + 70 * twinkle), int(92 + 90 * twinkle))
            pygame.draw.circle(self.screen, color, (int(p["x"]), int(p["y"])), p["r"])

    def field(self, key, label, rect, secret=False):
        rect = pygame.Rect(rect)
        value = self.auth_fields[key]
        focused = self.auth_focus == key
        h = self.hover_amount(f"field_{key}", rect.collidepoint(pygame.mouse.get_pos()))
        self.text(label, rect.x + 2, rect.y - 8, self.f_small, DIM, "bottomleft")
        pygame.draw.rect(self.screen, mix(BG_TOP, PANEL, 0.7), rect, border_radius=12)
        edge = CYAN if focused else mix(BORDER, CYAN, 0.5 * h)
        pygame.draw.rect(self.screen, edge, rect, 2, border_radius=12)
        shown = "*" * len(value) if secret else value
        self.text(shown, rect.x + 14, rect.centery, self.f_body, WHITE, "midleft")
        if focused and int(self.time * 2) % 2 == 0:
            cx = rect.x + 16 + self.f_body.size(shown)[0]
            pygame.draw.line(self.screen, CYAN, (cx, rect.centery - 11), (cx, rect.centery + 11), 2)
        self._next_buttons.append((rect, lambda k=key: self.focus_field(k)))

    def draw_auth(self):
        register = self.auth_mode == "register"
        self.text("CSE QUIZ CHALLENGE", 500, 70, self.f_med, CYAN, "center")
        self.text("Create a profile to save your scores, or jump in as a guest.", 500, 104, self.f_small, MUTED, "center")
        base = 400 if register else 330
        card_h = base + 190 - 140
        self.card((300, 140, 400, card_h), radius=26)
        for i, (mode, label) in enumerate((("login", "LOG IN"), ("register", "REGISTER"))):
            active = self.auth_mode == mode
            self.button(f"tab_{mode}", label, (322 + i * 180, 160, 166, 40), lambda m=mode: self.set_auth_mode(m),
                        fill=mix(PANEL2, PURPLE, 0.35) if active else PANEL2,
                        border=CYAN if active else BORDER, color=CYAN if active else WHITE, font=self.f_small)
        self.field("username", "USERNAME", (330, 244, 340, 46))
        self.field("password", "PASSWORD", (330, 316, 340, 46), secret=True)
        if register:
            self.field("confirm", "CONFIRM PASSWORD", (330, 388, 340, 46), secret=True)
        if self.auth_error:
            self.text(self.auth_error, 500, base + 40, self.f_small, RED, "center")
        elif register:
            self.text("3-16 letters, numbers or _   |   password 4+ characters", 500, base + 40, self.f_small, DIM, "center")
        self.button("submit", "CREATE ACCOUNT" if register else "LOG IN", (330, base + 62, 340, 52), self.submit_auth,
                    gradient=(mix(CYAN, PURPLE, 0.15), PURPLE), font=self.f_body, enabled=self.db is not None)
        self.button("guest", "Play as guest (scores not saved)", (330, base + 126, 340, 38), self.play_as_guest,
                    font=self.f_small, color=MUTED)
        self.text("TAB next field   |   ENTER submit   |   ESC quit", 500, 662, self.f_small, DIM, "center")

    def draw_dashboard(self):
        user, dash = self.user, self.dash
        st = dash["stats"]
        # Header
        pygame.draw.circle(self.screen, mix(PANEL, PURPLE, 0.45), (72, 66), 32)
        pygame.draw.circle(self.screen, PURPLE, (72, 66), 32, 3)
        self.text(user["username"][0].upper(), 72, 66, self.f_med, WHITE, "center")
        self.text(f"Welcome back, {user['username']}!", 122, 40, self.f_med, WHITE)
        self.text(f"Member since {user['created_at'][:10]}", 122, 78, self.f_small, MUTED)
        self.button("logout", "LOG OUT", (846, 40, 120, 40), self.logout, font=self.f_small)

        # Stat cards
        cards = [("BEST SCORE", st["high_score"], YELLOW), ("GAMES PLAYED", st["games_played"], CYAN),
                 ("BEST STREAK", st["best_streak"], PURPLE), ("ACCURACY", f"{st['accuracy']}%", GREEN)]
        for i, (label, value, color) in enumerate(cards):
            rect = pygame.Rect(34 + i * 239, 124, 215, 92)
            self.card(rect, radius=18)
            pygame.draw.rect(self.screen, color, (rect.x + 16, rect.y + 18, 4, 56), border_radius=2)
            self.text(label, rect.x + 34, rect.y + 16, self.f_small, DIM)
            self.text(value, rect.x + 34, rect.y + 40, self.f_med, color)

        # Recent games
        self.card((34, 240, 590, 290), radius=20)
        self.text("RECENT GAMES", 58, 258, self.f_small, MUTED)
        if dash["recent"]:
            for x, label in ((58, "DATE"), (190, "SCORE"), (290, "GRADE"), (370, "CORRECT"), (470, "MODE")):
                self.text(label, x, 288, self.f_small, DIM)
            for i, g in enumerate(dash["recent"]):
                y = 318 + i * 41
                pygame.draw.line(self.screen, (44, 58, 98), (58, y - 6), (600, y - 6), 1)
                self.text(g["played_at"][5:16].replace("-", "/"), 58, y, self.f_small, MUTED)
                self.text(g["score"], 190, y - 2, self.f_body, YELLOW)
                self.text(g["grade"], 290, y - 2, self.f_body, GRADE_COLORS.get(g["grade"], WHITE))
                self.text(f"{g['correct']} / {g['answered']}", 370, y, self.f_small, WHITE)
                mode = g["difficulty"] if g["category"] == "All" else g["category"]
                self.text(mode, 470, y, self.f_small, MUTED)
        else:
            self.text("No games yet - play your first round!", 329, 390, self.f_body, MUTED, "center")

        # Leaderboard
        self.card((648, 240, 318, 290), radius=20)
        self.text("LEADERBOARD", 672, 258, self.f_small, MUTED)
        if dash["board"]:
            for i, row in enumerate(dash["board"]):
                y = 292 + i * 44
                me = row["username"].lower() == user["username"].lower()
                if me:
                    pygame.draw.rect(self.screen, mix(PANEL, CYAN, 0.18), (662, y - 8, 290, 38), border_radius=10)
                rank_color = (YELLOW, MUTED, (205, 140, 90))[i] if i < 3 else DIM
                self.text(f"{i + 1}", 680, y + 11, self.f_body, rank_color, "midleft")
                self.text(row["username"], 716, y + 11, self.f_body, CYAN if me else WHITE, "midleft")
                self.text(row["best"], 940, y + 11, self.f_body, YELLOW, "midright")
        else:
            self.text("Be the first on the board!", 807, 390, self.f_body, MUTED, "center")

        pulse = 1.0 + 0.015 * math.sin(self.time * 3)
        w, h = int(300 * pulse), int(58 * pulse)
        self.button("play_now", "PLAY NOW", (500 - w // 2, 560, w, h), self.go_setup,
                    gradient=(mix(CYAN, PURPLE, 0.15), PURPLE), font=self.f_med, icon=self.arrow_icon)
        note = self.save_note or "ENTER play   |   ESC quit   |   M sound   |   F11 fullscreen"
        self.text(note, 500, 656, self.f_small, YELLOW if self.save_note else DIM, "center")

    def draw_menu(self):
        self.button("back", "BACK", (30, 26, 100, 40), self.go_back, font=self.f_small)
        who = self.user["username"] if self.user else "Guest"
        self.pill(f"PLAYER: {who.upper()}", 970, 32, CYAN if self.user else MUTED, "topright")
        glow = 0.5 + 0.5 * math.sin(self.time * 2)
        self.text("CSE", 500, 74, self.f_big, mix(CYAN, WHITE, 0.25 * glow), "center")
        title = self.text("QUIZ CHALLENGE", 500, 132, self.f_big, WHITE, "center")
        if int(self.time * 1.6) % 2 == 0:  # blinking terminal cursor
            pygame.draw.rect(self.screen, CYAN, (title.right + 8, title.bottom - 14, 26, 6), border_radius=2)
        self.text("Think fast. Learn more. Level up your CSE skills.", 500, 184, self.f_body, MUTED, "center")

        self.card((165, 216, 670, 356), radius=26)
        self.text("DIFFICULTY", 500, 244, self.f_small, DIM, "center")
        self.chips(list(ql.DIFFICULTIES), self.difficulty, self.set_difficulty, 262, 600, "d:")
        self.text("CATEGORY", 500, 322, self.f_small, DIM, "center")
        self.chips(self.categories, self.category, self.set_category, 342, 620, "c:")

        pulse = 1.0 + 0.015 * math.sin(self.time * 3)
        w, h = int(300 * pulse), int(58 * pulse)
        self.button("start", "START QUIZ", (500 - w // 2, 446, w, h), self.start_round,
                    gradient=(mix(CYAN, PURPLE, 0.15), PURPLE), font=self.f_med, icon=self.arrow_icon)

        matches = ql.count_matching(self.questions, self.difficulty, self.category)
        if matches == 0:
            note, note_color = "No questions match - all questions will be used", YELLOW
        else:
            note, note_color = f"{min(matches, ql.ROUND_LENGTH)} questions in this round", MUTED
        self.text(note, 500, 530, self.f_small, note_color, "center")

        if self.user and self.dash:
            st = self.dash["stats"]
            stats = [("BEST SCORE", st["high_score"], YELLOW), ("GAMES", st["games_played"], WHITE),
                     ("BEST STREAK", st["best_streak"], CYAN), ("ACCURACY", f"{st['accuracy']}%", GREEN)]
            for i, (label, value, color) in enumerate(stats):
                x = 245 + i * 170
                self.text(label, x, 598, self.f_small, DIM, "center")
                self.text(value, x, 624, self.f_med, color, "center")
        else:
            self.text("Playing as a guest - scores are not saved", 500, 600, self.f_body, MUTED, "center")
            self.text("Log in from the BACK screen to keep your progress", 500, 626, self.f_small, DIM, "center")
        self.text("ESC back   |   P pause   |   M sound   |   F11 fullscreen", 500, 662, self.f_small, DIM, "center")

    def draw_quiz(self, interactive=True):
        r = self.round
        q = r.current
        mouse = pygame.mouse.get_pos()

        # Header
        self.text("CSE QUIZ CHALLENGE", 34, 22, self.f_med, CYAN)
        self.text(f"QUESTION {r.index + 1} / {r.total}", 34, 70, self.f_small, MUTED)
        self.text("SCORE", 500, 22, self.f_small, DIM, "midtop")
        self.text(int(round(self.display_score)), 500, 40, self.f_med, YELLOW, "midtop")
        for i in range(ql.STARTING_LIVES):
            self.heart(966 - i * 34, 38, 26, RED if i < r.lives else (52, 46, 84))
        if r.streak >= 2:
            self.bolt_icon(838, 74, YELLOW)
            self.text(f"x{r.streak} STREAK", 850, 74, self.f_small, YELLOW, "midleft")
        for p in self.popups:
            surf = self.f_med.render(p["text"], True, p["color"])
            surf.set_alpha(int(255 * max(0.0, min(1.0, p["life"]))))
            self.screen.blit(surf, surf.get_rect(center=(int(p["x"]), int(p["y"]))))

        # Progress bar
        pygame.draw.rect(self.screen, (40, 52, 90), (34, 100, 932, 8), border_radius=4)
        done = r.index + (1 if r.locked else 0)
        if done:
            self.gradient_rect((34, 100, max(8, int(932 * done / r.total)), 8), CYAN, PURPLE, 4)

        # Question card
        self.card((34, 128, 932, 156), radius=20)
        self.pill(q["category"].upper(), 56, 146, PURPLE)
        self.pill(q["difficulty"].upper(), 944, 146, DIFF_COLORS.get(q["difficulty"], MUTED), "topright")
        font = self.f_q
        lines = wrap_text(q["question"], font, 868)
        if len(lines) > 3:
            font = self.f_q_small
            lines = wrap_text(q["question"], font, 868)
        for i, line in enumerate(lines[:4]):
            self.text(line, 58, 188 + i * (font.get_linesize() + 1), font, WHITE)

        # Timer
        ratio = max(0.0, r.time_left / ql.QUESTION_SECONDS)
        timer_color = GREEN if ratio > 0.5 else YELLOW if ratio > 0.25 else RED
        pygame.draw.rect(self.screen, (40, 52, 90), (34, 302, 880, 10), border_radius=5)
        if ratio > 0:
            pygame.draw.rect(self.screen, timer_color, (34, 302, max(10, int(880 * ratio)), 10), border_radius=5)
        self.text(f"{int(math.ceil(r.time_left))}s", 966, 307, self.f_body, timer_color, "midright")

        # Options
        letters = "ABCD"
        shake_x = int(math.sin(self.time * 60) * 9 * self.shake)
        for i, option in enumerate(q["options"]):
            rect = pygame.Rect(54, 332 + i * 66, 892, 54)
            removed = i in r.removed
            fill, border, text_color = PANEL2, BORDER, WHITE
            hovered = interactive and (not r.locked) and (not removed) and rect.collidepoint(mouse)
            h = self.hover_amount(f"opt{i}", hovered)
            if removed:
                fill, border, text_color = mix(PANEL, BG_TOP, 0.4), mix(BORDER, BG_TOP, 0.6), DIM
            elif r.locked:
                if i == q["answer"]:
                    fill, border = (24, 84, 70), GREEN
                elif i == r.selected:
                    fill, border = (100, 38, 60), RED
                    rect = rect.move(shake_x, 0)
                else:
                    text_color = MUTED
            else:
                fill = mix(PANEL2, WHITE, 0.06 * h)
                border = mix(BORDER, CYAN, h)
            if not removed:
                self.shadow(rect, 13, spread=10, strength=60)
            pygame.draw.rect(self.screen, fill, rect, border_radius=13)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=13)
            badge = pygame.Rect(rect.x + 12, rect.y + 9, 36, 36)
            badge_fill = PANEL if removed else mix(PANEL, border, 0.45)
            pygame.draw.rect(self.screen, badge_fill, badge, border_radius=10)
            self.text(letters[i], badge.centerx, badge.centery, self.f_small, DIM if removed else CYAN, "center")
            opt_font = self.f_body if self.f_body.size(option)[0] < 780 else self.f_small
            self.text(option, rect.x + 64, rect.centery, opt_font, text_color, "midleft")
            if removed:
                width = opt_font.size(option)[0]
                pygame.draw.line(self.screen, DIM, (rect.x + 62, rect.centery), (rect.x + 66 + width, rect.centery), 2)
            if r.locked and i == q["answer"]:
                self.check_icon(rect.right - 32, rect.centery, GREEN)
            elif r.locked and i == r.selected:
                self.cross_icon(rect.right - 32, rect.centery, RED)
            if interactive and not r.locked and not removed:
                self._next_buttons.append((rect, lambda v=i: self.submit(v)))

        # Footer
        if interactive:
            self.button("fifty", "50:50", (34, 622, 118, 40), self.use_fifty, font=self.f_small,
                        enabled=(not r.fifty_used and not r.locked), color=YELLOW)
        else:
            pygame.draw.rect(self.screen, PANEL2, (34, 622, 118, 40), border_radius=14)
        if self.feedback:
            self.text(self.feedback, 500, 642, self.f_body, self.feedback_color, "center")
        else:
            self.text("Pick an answer: click or press A-D / 1-4", 500, 642, self.f_small, DIM, "center")
        sound = "on" if self.sfx.enabled else "off"
        self.text(f"P pause   |   F 50:50   |   M sound {sound}", 966, 642, self.f_small, DIM, "midright")

    def draw_pause(self):
        self.draw_quiz(interactive=False)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 22, 215))
        self.screen.blit(overlay, (0, 0))
        self.card((290, 200, 420, 270), radius=26, border=PURPLE)
        self.text("PAUSED", 500, 258, self.f_big, WHITE, "center")
        self.text("Take a breath. The timer is frozen.", 500, 306, self.f_small, MUTED, "center")
        self.button("resume", "RESUME", (365, 342, 270, 52), self.toggle_pause,
                    gradient=(mix(CYAN, PURPLE, 0.15), PURPLE), font=self.f_body)
        self.button("pause_menu", "MAIN MENU", (365, 406, 270, 46), self.go_menu, font=self.f_body)

    def draw_results(self):
        r = self.round
        self.text("QUIZ COMPLETE", 500, 58, self.f_big, WHITE, "center")
        if self.new_best:
            message, message_color = "NEW PERSONAL BEST!", YELLOW
        elif r.lives <= 0:
            message, message_color = "OUT OF LIVES - TRY AGAIN!", CYAN
        else:
            message, message_color = "GREAT EFFORT - KEEP PRACTISING!", CYAN
        self.text(message, 500, 106, self.f_body, message_color, "center")

        self.card((170, 140, 660, 360), radius=26)
        grade_color = GRADE_COLORS[r.grade]
        pygame.draw.circle(self.screen, mix(PANEL, grade_color, 0.18), (330, 262), 84)
        pygame.draw.circle(self.screen, grade_color, (330, 262), 84, 4)
        self.text(r.grade, 330, 258, self.f_huge, grade_color, "center")
        self.text("GRADE", 330, 366, self.f_small, DIM, "center")

        self.text("YOUR SCORE", 600, 180, self.f_small, DIM, "midtop")
        self.text(int(round(self.display_score)), 600, 202, self.f_big, YELLOW, "midtop")
        rows = [
            ("Correct answers", f"{r.correct_count} / {r.total}"),
            ("Accuracy", f"{r.accuracy}%"),
            ("Best streak", str(r.best_streak)),
            ("Lives left", f"{r.lives} / {ql.STARTING_LIVES}"),
            ("Personal best", str(max(self.current_best(), r.score))),
        ]
        for i, (label, value) in enumerate(rows):
            y = 286 + i * 36
            self.text(label, 470, y, self.f_small, MUTED)
            self.text(value, 770, y, self.f_body, WHITE, "topright")
            pygame.draw.line(self.screen, (44, 58, 98), (470, y + 27), (770, y + 27), 1)

        buttons = [("again", "PLAY AGAIN", self.start_round, True)]
        if r.missed:
            buttons.append(("review", f"REVIEW ({len(r.missed)})", self.open_review, False))
        buttons.append(("menu", "MAIN MENU", self.go_menu, False))
        width, gap = 220, 18
        x = 500 - (len(buttons) * width + (len(buttons) - 1) * gap) // 2
        for key, label, action, primary in buttons:
            self.button(key, label, (x, 530, width, 54), action, font=self.f_body,
                        gradient=(mix(CYAN, PURPLE, 0.15), PURPLE) if primary else None)
            x += width + gap
        if self.save_note:
            tip, tip_color = self.save_note, YELLOW
        elif not self.user:
            tip, tip_color = "Guest mode: log in next time to save your scores", DIM
        else:
            tip, tip_color = "Saved to your profile. Review the questions you missed, then try again!", DIM
        self.text(tip, 500, 622, self.f_small, tip_color, "center")

    def open_review(self):
        self.review_index = 0
        self.set_state("review")

    def step_review(self, delta):
        n = len(self.round.missed)
        self.review_index = max(0, min(n - 1, self.review_index + delta))
        self.sfx.play("click")

    def draw_review(self):
        missed = self.round.missed
        item = missed[self.review_index]
        self.text("REVIEW YOUR MISTAKES", 500, 58, self.f_big, WHITE, "center")
        self.text(f"{self.review_index + 1} of {len(missed)}", 500, 106, self.f_body, MUTED, "center")
        self.card((100, 140, 800, 380), radius=26)
        self.pill(item["category"].upper(), 130, 164, PURPLE)
        font = self.f_q
        lines = wrap_text(item["question"], font, 740)
        if len(lines) > 3:
            font = self.f_q_small
            lines = wrap_text(item["question"], font, 740)
        for i, line in enumerate(lines[:4]):
            self.text(line, 130, 208 + i * (font.get_linesize() + 1), font, WHITE)
        y = 330
        chosen = item["chosen"] if item["chosen"] is not None else "No answer - time ran out"
        self.text("YOUR ANSWER", 130, y, self.f_small, DIM)
        self.cross_icon(140, y + 40, RED)
        self.text(chosen, 164, y + 40, self.f_body, RED, "midleft")
        self.text("CORRECT ANSWER", 130, y + 80, self.f_small, DIM)
        self.check_icon(140, y + 120, GREEN)
        self.text(item["correct"], 164, y + 120, self.f_body, GREEN, "midleft")

        n = len(missed)
        self.button("prev", "PREV", (230, 552, 150, 50), lambda: self.step_review(-1), font=self.f_body,
                    enabled=self.review_index > 0)
        self.button("back", "RESULTS", (410, 552, 180, 50), lambda: self.set_state("results"), font=self.f_body,
                    gradient=(mix(CYAN, PURPLE, 0.15), PURPLE))
        self.button("next", "NEXT", (620, 552, 150, 50), lambda: self.step_review(1), font=self.f_body,
                    enabled=self.review_index < n - 1)
        self.text("Left / Right arrows to browse   |   ESC to go back", 500, 636, self.f_small, DIM, "center")

    def draw_overlays(self):
        for c in self.confetti:
            pygame.draw.rect(self.screen, c["c"], (int(c["x"]), int(c["y"]), c["w"], c["h"]))
        if self.flash > 0:
            self.flash_surface.fill(self.flash_color)
            self.flash_surface.set_alpha(int(60 * self.flash))
            self.screen.blit(self.flash_surface, (0, 0))
        if self.fade > 0:
            self.fade_surface.set_alpha(int(self.fade))
            self.screen.blit(self.fade_surface, (0, 0))

    def draw(self):
        self._next_buttons = []
        self.draw_background()
        if self.state == "auth":
            self.draw_auth()
        elif self.state == "dashboard":
            self.draw_dashboard()
        elif self.state == "menu":
            self.draw_menu()
        elif self.state == "quiz":
            self.draw_quiz()
        elif self.state == "paused":
            self.draw_pause()
        elif self.state == "results":
            self.draw_results()
        elif self.state == "review":
            self.draw_review()
        self.draw_overlays()
        self.buttons = self._next_buttons
        self.update_cursor()

    def update_cursor(self):
        mouse = pygame.mouse.get_pos()
        over = any(rect.collidepoint(mouse) for rect, _ in self.buttons)
        if over != self._hand_cursor:
            self._hand_cursor = over
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if over else pygame.SYSTEM_CURSOR_ARROW)
            except (pygame.error, AttributeError):
                pass

    # ----------------------------- input ----------------------------------- #
    def handle_key(self, key, char=""):
        if key == pygame.K_F11:
            try:
                pygame.display.toggle_fullscreen()
            except pygame.error:
                pass
            return
        if self.state == "auth":
            self.auth_key(key, char)
            return
        if key == pygame.K_m:
            self.sfx.enabled = not self.sfx.enabled
            return
        if key == pygame.K_ESCAPE:
            if self.state in ("quiz", "paused"):
                self.toggle_pause()
            elif self.state == "review":
                self.set_state("results")
            elif self.state == "results":
                self.go_menu()
            elif self.state == "menu":
                self.go_back()
            else:
                self.running = False
            return
        if self.state in ("quiz", "paused") and key == pygame.K_p:
            self.toggle_pause()
            return
        if self.state == "dashboard" and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.go_setup()
        elif self.state in ("menu", "results") and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.start_round()
        elif self.state == "review":
            if key == pygame.K_LEFT:
                self.step_review(-1)
            elif key == pygame.K_RIGHT:
                self.step_review(1)
        elif self.state == "quiz" and self.round:
            r = self.round
            if r.locked:
                if key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.next_question()
                return
            if key == pygame.K_f:
                self.use_fifty()
                return
            key_map = {pygame.K_a: 0, pygame.K_b: 1, pygame.K_c: 2, pygame.K_d: 3,
                       pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}
            choice = key_map.get(key)
            if choice is not None and choice < len(r.current["options"]) and choice not in r.removed:
                self.submit(choice)

    def handle_click(self, pos):
        for rect, action in reversed(self.buttons):
            if rect.collidepoint(pos):
                action()
                return

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.dt = dt
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key, event.unicode)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        if self.db:
            self.db.close()
        pygame.quit()
        sys.exit(0)


def main():
    try:
        QuizGame().run()
    except RuntimeError as error:
        print(error)
        input("Press Enter to close...")


if __name__ == "__main__":
    main()
