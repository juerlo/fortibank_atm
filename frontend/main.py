import os
import math
import random
import threading
import logging
import subprocess
import time
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None
import requests

# Suppress urllib3/requests DEBUG logging to prevent Kivy logger recursion
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '600')
Config.set('graphics', 'resizable', '0')
Config.set('graphics', 'maxfps', '60')

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty, BooleanProperty
from kivy.factory import Factory
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line, PushMatrix, PopMatrix, Rotate
from kivy.graphics.texture import Texture
from kivy.core.window import Window

from settings import Settings, TRANSLATIONS, translate

# Directory that holds the frontend code/assets (this file). The ATM app is
# deployed in ``frontend/`` but may be launched from another working directory,
# so all local resources (kv, sounds, images) are resolved against it.
FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))

# Backend URL: env override wins, otherwise built from the saved backend IP.
BACKEND_URL = os.environ.get("ATM_BACKEND_URL")

# The card catalogue is fetched from the backend (GET /api/cards) into
# ``FortiBankApp.cards`` and kept in sync by ``_refresh_cards``.


def _gradient_texture(c1, c2, diagonal=True, size=128):
    """Create a gradient texture.

    CSS `linear-gradient(135deg, c1, c2)` colours go from top-left (c1) to
    bottom-right (c2). Kivy textures are bottom-up, so we invert the y axis.
    """
    tex = Texture.create(size=(size, size))
    buf = []
    for row in range(size):  # row 0 = bottom of texture
        for col in range(size):
            if diagonal:
                # top-left -> bottom-right
                t = (col + row) / (2.0 * (size - 1))
            else:
                t = row / (size - 1)
            r = c1[0] + (c2[0] - c1[0]) * t
            g = c1[1] + (c2[1] - c1[1]) * t
            b = c1[2] + (c2[2] - c1[2]) * t
            buf.extend([int(r * 255), int(g * 255), int(b * 255), 255])
    tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
    return tex


def _radial_texture(center, edge, size=256):
    """Radial gradient: `center` at middle, `edge` at the corners."""
    tex = Texture.create(size=(size, size))
    buf = []
    cx = cy = (size - 1) / 2.0
    max_d = (cx * cx + cy * cy) ** 0.5
    for row in range(size):
        for col in range(size):
            d = (((col - cx) ** 2 + (row - cy) ** 2) ** 0.5) / max_d
            d = min(d, 1.0)
            r = center[0] + (edge[0] - center[0]) * d
            g = center[1] + (edge[1] - center[1]) * d
            b = center[2] + (edge[2] - center[2]) * d
            buf.extend([int(r * 255), int(g * 255), int(b * 255), 255])
    tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
    return tex


# Textures are created lazily (after the OpenGL context exists) to avoid
# segfaults from touching GL resources at import time.
_SCREEN_BG_TEX = None
_CARD_BG_TEX = None


def _screen_bg_tex():
    global _SCREEN_BG_TEX
    if _SCREEN_BG_TEX is None:
        # radial-gradient(circle at center, #0b4a8f 0%, #062a50 100%)
        _SCREEN_BG_TEX = _radial_texture((0.043, 0.290, 0.561), (0.024, 0.165, 0.314))
    return _SCREEN_BG_TEX


def _card_bg_tex():
    global _CARD_BG_TEX
    if _CARD_BG_TEX is None:
        # linear-gradient(135deg, #1e2a38, #000000)
        _CARD_BG_TEX = _gradient_texture((0.118, 0.165, 0.220), (0.0, 0.0, 0.0))
    return _CARD_BG_TEX


class ScreenBase(Screen):
    def on_kv_post(self, base_widget):
        self._bg_rect = None
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(
                pos=self.pos, size=self.size, texture=_screen_bg_tex()
            )
        self.bind(
            pos=lambda *a: setattr(self._bg_rect, 'pos', self.pos),
            size=lambda *a: setattr(self._bg_rect, 'size', self.size),
        )


class PushButton(Button):
    """Button with a 3D drop shadow and a press/push effect."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self._shadow = None
        self._normal_bg = None
        with self.canvas.before:
            Color(0, 0, 0, 0.35)
            self._shadow = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self._sync_shadow, size=self._sync_shadow, state=self._on_state)

    def _sync_shadow(self, *a):
        off = 1 if self.state == 'down' else 5
        self._shadow.pos = (self.x, self.y - off)
        self._shadow.size = self.size

    def _on_state(self, *a):
        if self._normal_bg is None:
            self._normal_bg = tuple(self.background_color)
        if self.state == 'down':
            r, g, b, a = self._normal_bg
            self.background_color = (r * 0.7, g * 0.7, b * 0.7, a)
        else:
            self.background_color = self._normal_bg
        self._sync_shadow()


class ScreenInsert(ScreenBase):
    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.build_cards(App.get_running_app().cards)

    def build_cards(self, cards):
        container = self.ids.card_container
        container.clear_widgets()
        for c in cards:
            num = c.get("num", "")
            formatted = " ".join(num[i:i+4] for i in range(0, len(num), 4))

            card = RelativeLayout(size_hint=(None, None), size=(320, 200))

            # Background drawn by a child widget (relative coords — reliable for all cards)
            bg = Widget(size_hint=(None, None), pos=(0, 0), size=(320, 200))
            with bg.canvas:
                # box-shadow: 0 10px 20px rgba(0,0,0,0.6)
                Color(0, 0, 0, 0.6)
                RoundedRectangle(pos=(2, -6), size=(316, 200), radius=[15])
                # base dark (end of 135° gradient -> #000)
                Color(0.043, 0.059, 0.079, 1)
                RoundedRectangle(pos=(0, 0), size=(320, 200), radius=[15])
                # lighter top (start of 135° gradient -> #1e2a38), softened contrast
                Color(0.090, 0.125, 0.168, 1)
                RoundedRectangle(pos=(0, 78), size=(320, 122), radius=[15, 15, 0, 0])
                # border: 1px solid #555
                Color(0.333, 0.333, 0.333, 1)
                Line(rounded_rectangle=(0, 0, 320, 200, 15), width=1)

            # .chip — 45x35, #d4af37, radius 6, positioned 20px from top/left
            chip = Widget(size_hint=(None, None), pos=(20, 145), size=(45, 35))
            with chip.canvas:
                Color(0.831, 0.686, 0.216, 1)  # #d4af37
                RoundedRectangle(pos=chip.pos, size=chip.size, radius=[6])
                # diagonal highlight (approximation of the CSS gradient overlay)
                Color(1, 1, 1, 0.30)
                RoundedRectangle(pos=(chip.x + 12, chip.y + 8), size=(chip.width - 16, chip.height - 16), radius=[4])

            # .card-number — monospace, white, 1.2rem, letter-spacing 2px
            num_lbl = Label(
                text=formatted,
                font_size='17sp',
                bold=True,
                color=(1, 1, 1, 1),
                halign='left',
                valign='middle',
                size_hint=(None, None),
                pos=(20, 100),
                size=(280, 24),
                text_size=(280, 24),
            )

            # .card-name — 1rem, uppercase, #ddd
            name_lbl = Label(
                text=c["name"].upper(),
                font_size='14sp',
                color=(0.867, 0.867, 0.867, 1),  # #ddd
                halign='left',
                valign='middle',
                size_hint=(None, None),
                pos=(20, 66),
                size=(230, 22),
                text_size=(230, 22),
            )

            # .card-brand — right:20, bottom:20, width:60
            brand_img = Image(
                source=os.path.join(
                    FRONTEND_DIR,
                    "visa.png" if c["brand"] == "VISA" else "mastercard.png",
                ),
                size_hint=(None, None),
                pos=(240, 20),
                size=(60, 40),
                fit_mode="contain",
            )

            # Transparent button overlay for tap-to-select
            select_btn = Button(
                size_hint=(None, None),
                pos=(0, 0),
                size=(320, 200),
                background_normal='',
                background_color=(0, 0, 0, 0),
                opacity=0,
            )
            select_btn.bind(on_release=lambda inst, card=c: App.get_running_app().insert_card(card))

            card.add_widget(bg)
            card.add_widget(chip)
            card.add_widget(num_lbl)
            card.add_widget(name_lbl)
            card.add_widget(brand_img)
            card.add_widget(select_btn)
            container.add_widget(card)


class ScreenPin(ScreenBase):
    nip = ""

    def on_pre_enter(self):
        self.clear_nip()

    def append_nip(self, digit):
        if len(self.nip) < 4:
            App.get_running_app()._beep()
            self.nip += digit
            self._refresh_nip()

    def clear_nip(self):
        App.get_running_app()._beep()
        self.nip = ""
        self._refresh_nip()

    def _refresh_nip(self):
        # spaced asterisks approximate the HTML letter-spacing: 20px
        self.ids.nip_display.text = "  ".join("*" for _ in self.nip)

    def submit_nip(self):
        if len(self.nip) == 4:
            app = App.get_running_app()
            app.current_nip = self.nip
            app.go_to('menu')


class ScreenMenu(ScreenBase):
    pass


class ScreenAmount(ScreenBase):
    pass


class ScreenProcessing(ScreenBase):
    pass


class ScreenDispensing(ScreenBase):
    pass


class ScreenResult(ScreenBase):
    pass


class ScreenCardAnim(Screen):
    """Full-screen card insertion / ejection animation (matches the HTML overlay)."""
    BG = (0.035, 0.231, 0.439, 1)  # #093b70

    def __init__(self, **kw):
        super().__init__(**kw)
        self._flash_event = None
        self._slot_on = True
        self._build_anim()

    def _toggle_slot(self, dt):
        self._slot_on = not self._slot_on
        if hasattr(self, 'slot_color'):
            self.slot_color.a = 1.0 if self._slot_on else 0.15

    def _start_flash(self):
        self._stop_flash()
        self._slot_on = True
        if hasattr(self, 'slot_color'):
            self.slot_color.a = 1.0
        self._flash_event = Clock.schedule_interval(self._toggle_slot, 0.25)

    def _stop_flash(self):
        if self._flash_event:
            self._flash_event.cancel()
            self._flash_event = None
        if hasattr(self, 'slot_color'):
            self.slot_color.a = 1.0

    def _build_anim(self):
        root = FloatLayout()

        # background #093b70
        bg = Widget(size_hint=(None, None), size=(1024, 600))
        with bg.canvas:
            Color(*self.BG)
            Rectangle(pos=(0, 0), size=(1024, 600))

        # the big vertical card
        self.card = self._make_card()

        # top-half cover (background colour) so the card appears to go into the slot
        cover = Widget(size_hint=(None, None), pos=(0, 300), size=(1024, 300))
        with cover.canvas:
            Color(*self.BG)
            Rectangle(pos=(0, 300), size=(1024, 300))

        # slot: 400x30, #050505 with a 4px #333 border and a green inner line
        slot = Widget(size_hint=(None, None), pos=(312, 285), size=(400, 30))
        with slot.canvas:
            Color(0.02, 0.02, 0.02, 1)
            RoundedRectangle(pos=(312, 285), size=(400, 30), radius=[10])
            self.slot_color = Color(0.18, 0.80, 0.44, 1)
            Rectangle(pos=(320, 298), size=(384, 4))
            Color(0.20, 0.20, 0.20, 1)
            Line(rounded_rectangle=(312, 285, 400, 30, 10), width=4)

        # title text (top ~20%)
        self.title_lbl = Label(
            text=App.get_running_app().t("card_reading"),
            font_size='44sp',
            bold=True,
            size_hint=(None, None),
            pos=(0, 455),
            size=(1024, 70),
            halign='center',
            valign='middle',
            text_size=(1024, 70),
        )

        # z-order: bg, card, cover, slot, title
        root.add_widget(bg)
        root.add_widget(self.card)
        root.add_widget(cover)
        root.add_widget(slot)
        root.add_widget(self.title_lbl)
        self.add_widget(root)

    def _make_card(self):
        card = RelativeLayout(size_hint=(None, None), size=(300, 480), pos=(362, -480))
        bg = Widget(size_hint=(None, None), pos=(0, 0), size=(300, 480))
        with bg.canvas:
            Color(0.043, 0.059, 0.079, 1)
            RoundedRectangle(pos=(0, 0), size=(300, 480), radius=[20])
            Color(0.090, 0.125, 0.168, 1)
            RoundedRectangle(pos=(0, 200), size=(300, 280), radius=[20, 20, 0, 0])
            Color(0.333, 0.333, 0.333, 1)
            Line(rounded_rectangle=(0, 0, 300, 480, 20), width=2)
        card.add_widget(bg)

        # chip 60x40 at (30, 400)
        chip = Widget(size_hint=(None, None), pos=(30, 400), size=(60, 40))
        with chip.canvas:
            Color(0.831, 0.686, 0.216, 1)
            RoundedRectangle(pos=(30, 400), size=(60, 40), radius=[8])
            Color(1, 1, 1, 0.30)
            RoundedRectangle(pos=(38, 408), size=(44, 24), radius=[5])
        card.add_widget(chip)

        # number + name, rotated 90°
        self.card_num = self._vlabel("**** **** **** ****", '20sp', (1, 1, 1, 1), 120, 250)
        self.card_name = self._vlabel("NOMBRE APELLIDO", '15sp', (0.87, 0.87, 0.87, 1), 195, 250)
        card.add_widget(self.card_num)
        card.add_widget(self.card_name)

        # brand logo, rotated 90°
        self.card_brand = Image(size_hint=(None, None), size=(80, 30), pos=(205, 40),
                                fit_mode="contain")
        with self.card_brand.canvas.before:
            PushMatrix()
            Rotate(angle=90, origin=(245, 55))
        with self.card_brand.canvas.after:
            PopMatrix()
        card.add_widget(self.card_brand)
        return card

    def _vlabel(self, text, fs, color, cx, cy, w=320, h=40):
        lbl = Label(
            text=text, font_size=fs, color=color, bold=True,
            size_hint=(None, None), size=(w, h),
            pos=(cx - w / 2.0, cy - h / 2.0),
            halign='center', valign='middle', text_size=(w, h),
        )
        with lbl.canvas.before:
            PushMatrix()
            Rotate(angle=90, origin=(cx, cy))
        with lbl.canvas.after:
            PopMatrix()
        return lbl

    # ---- animation entry points ----
    def play_insert(self, card):
        self.card_num.text = " ".join(card["num"][i:i + 4] for i in range(0, 16, 4))
        self.card_name.text = card["name"].upper()
        self.card_brand.source = os.path.join(
            FRONTEND_DIR,
            "visa.png" if card["brand"] == "VISA" else "mastercard.png",
        )
        self.title_lbl.text = App.get_running_app().t("card_reading")
        self.card.y = -480

        app = App.get_running_app()
        app.go_to('cardanim')
        self._start_flash()
        Clock.schedule_once(lambda dt: app.snd_insert and app.snd_insert.play(), 0.3)

        a = Animation(y=-150, duration=1.05, t='in_out_cubic')  # 0-30%
        h = Animation(y=-150, duration=1.05, t='linear')        # 30-60% (hold)
        b = Animation(y=720, duration=1.4, t='in_out_cubic')    # 60-100%
        seq = a + h + b
        seq.bind(on_complete=lambda *args: (self._stop_flash(), app.go_to('pin', beep=False)))
        seq.start(self.card)

    def play_eject(self):
        self.title_lbl.text = App.get_running_app().t("card_eject")
        self.card.y = 720

        app = App.get_running_app()
        app.go_to('cardanim')
        self._start_flash()
        Clock.schedule_once(lambda dt: app.snd_insert and app.snd_insert.play(), 0.3)

        a = Animation(y=-150, duration=1.2, t='in_out_cubic')   # 0-30%
        h = Animation(y=-150, duration=1.2, t='linear')         # 30-60%
        b = Animation(y=-480, duration=1.6, t='in_out_cubic')   # 60-100%

        def _done(*args):
            self._stop_flash()
            app.current_card = None
            app.current_nip = ""
            app.go_to('insert', beep=False)

        seq = a + h + b
        seq.bind(on_complete=_done)
        seq.start(self.card)


class AdminPinScreen(ScreenBase):
    mode = StringProperty("verify")
    title = StringProperty("PIN de Administrador")
    msg = StringProperty("")
    pin = StringProperty("")
    pin_display = StringProperty("")
    temp_pin = StringProperty("")

    def append_digit(self, digit):
        if len(self.pin) < 4:
            self.pin = self.pin + digit
            self.pin_display = "*" * len(self.pin)
            self.msg = ""

    def clear(self):
        self.pin = ""
        self.pin_display = ""
        self.msg = ""

    def submit(self):
        if len(self.pin) != 4:
            self.msg = App.get_running_app().t("admin_pin_incomplete")
            return
        App.get_running_app().handle_admin_pin(self.mode, self.pin)
        self.pin = ""
        self.pin_display = ""

    def cancel(self):
        App.get_running_app().close_admin()


class AdminMenuScreen(ScreenBase):
    pass


class AdminIpScreen(ScreenBase):
    value = StringProperty("")
    msg = StringProperty("")

    def append_digit(self, digit):
        if len(self.value) < 15:
            self.value = self.value + digit
            self.msg = ""

    def append_dot(self):
        if len(self.value) < 15 and not self.value.endswith("."):
            self.value = self.value + "."
            self.msg = ""

    def backspace(self):
        self.value = self.value[:-1]
        self.msg = ""

    def clear(self):
        self.value = ""
        self.msg = ""

    def submit(self):
        App.get_running_app().handle_admin_ip(self.value)

    def cancel(self):
        App.get_running_app().open_admin_menu()


class ScreenSaver(ScreenBase):
    """Idle burn-in protection: bouncing FortiBank logo, floating bills, clock."""

    LOGO_W = 430
    LOGO_H = 110

    def __init__(self, **kw):
        super().__init__(**kw)
        self._t = 0.0
        self._logo_x = 300.0
        self._logo_y = 250.0
        self._vx = 95.0
        self._vy = 65.0
        self._bills = []
        self._anim = None
        self._build()

    def _build(self):
        # Dark radial gradient backdrop
        self._bg = Rectangle(
            pos=self.pos, size=self.size,
            texture=_radial_texture((0.02, 0.10, 0.22), (0.0, 0.01, 0.03)))
        self.canvas.add(self._bg)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        # Floating banknotes
        bill_imgs = [os.path.join(FRONTEND_DIR, f"{d}.png") for d in (50, 100, 200, 500)]
        for i in range(10):
            src = bill_imgs[i % len(bill_imgs)]
            if not os.path.exists(src):
                continue
            img = Image(source=src, size_hint=(None, None), size=(120, 51),
                        opacity=random.uniform(0.12, 0.28), allow_stretch=True)
            img.pos = (random.uniform(0, 900), random.uniform(0, 560))
            self.add_widget(img)
            self._bills.append([img, random.uniform(10, 26), random.uniform(-8, 8)])

        # Bouncing FortiBank logo
        self._logo = Factory.AtmButton(
            text=("[b][color=f39c12][size=38]FortiBank[/size][/color] "
                  "[b][color=ffffff][size=38]ATM[/size][/color][/b]"),
            markup=True, size_hint=(None, None), size=(self.LOGO_W, self.LOGO_H),
            background_color=(0.05, 0.10, 0.18, 0.96))
        self._logo.pos = (self._logo_x, self._logo_y)
        self.add_widget(self._logo)

        # Pulsing hint
        self._hint = Label(
            text=App.get_running_app().t("saver_hint"), font_size='18sp',
            color=(1, 1, 1, 0.55), size_hint=(None, None), size=(700, 40),
            halign='center', valign='middle', text_size=(700, 40))
        self._hint.pos = (162, 100)
        self.add_widget(self._hint)

        # Full-screen invisible touch catcher: any tap dismisses the screensaver
        self._dismiss = Button(
            text="", size_hint=(1, 1), background_normal='',
            background_down='', background_color=(0, 0, 0, 0))
        self._dismiss.on_release = self._dismiss_now
        self.add_widget(self._dismiss)

    def _dismiss_now(self, *a):
        App.get_running_app().dismiss_screensaver()

    def _sync_bg(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def on_enter(self):
        self._t = 0.0
        if self._anim:
            self._anim.cancel()
        self._anim = Clock.schedule_interval(self._animate, 0)

    def on_leave(self):
        if self._anim:
            self._anim.cancel()
            self._anim = None

    def _animate(self, dt):
        self._t += dt

        # Bounce the logo off the screen edges
        x = self._logo_x + self._vx * dt
        y = self._logo_y + self._vy * dt
        maxx = max(0.0, self.width - self.LOGO_W)
        maxy = max(0.0, self.height - self.LOGO_H)
        if x <= 0:
            x, self._vx = 0.0, abs(self._vx)
        elif x >= maxx:
            x, self._vx = maxx, -abs(self._vx)
        if y <= 0:
            y, self._vy = 0.0, abs(self._vy)
        elif y >= maxy:
            y, self._vy = maxy, -abs(self._vy)
        self._logo_x, self._logo_y = x, y
        self._logo.pos = (x, y)

        # Drift the banknotes upward, wrapping around
        for img, vy, vx in self._bills:
            ix, iy = img.pos
            iy += vy * dt
            ix += vx * dt
            if iy > self.height + 60:
                iy = -60.0
                ix = random.uniform(0, max(1.0, self.width - 120))
            if ix < -130:
                ix = self.width + 10.0
            elif ix > self.width + 10:
                ix = -130.0
            img.pos = (ix, iy)

        # Pulse the hint
        self._hint.opacity = 0.40 + 0.25 * (0.5 + 0.5 * math.sin(self._t * 2.0))

    def on_touch_down(self, touch):
        # Consume the touch so the screen behind is not activated
        return True

    def on_touch_up(self, touch):
        return True


class ScreenSaverCfg(ScreenBase):
    """Admin screen to configure the screensaver and display-off timeouts."""

    def set_saver(self, seconds):
        App.get_running_app().set_saver_timeout(seconds)

    def set_screenoff(self, seconds):
        App.get_running_app().set_screenoff_timeout(seconds)

    def back(self):
        App.get_running_app().open_admin_menu()


class Manager(ScreenManager):
    def on_touch_down(self, touch):
        app = App.get_running_app()
        if app is not None:
            # Any activity resets the idle timer and wakes the display
            app._last_activity = time.time()
            if app._screen_off:
                app._wake_screen()
            # While the screensaver is up, consume the touch and dismiss it
            if self.current == 'screensaver':
                app.dismiss_screensaver()
                return True
        return super().on_touch_down(touch)


class OOSOverlay(FloatLayout):
    """Solid-blue, interaction-blocking overlay shown while the backend is down.

    It is added directly to the Window (above the ScreenManager) and covers the
    whole screen with an opaque blue background. A copy of the FortiBank logo is
    drawn top-left so the secret admin menu stays reachable; while ``active`` it
    swallows touches everywhere else so the ATM cannot be used.
    """

    LOGO_H = 64  # top strip reserved for the logo

    def __init__(self, **kw):
        super().__init__(**kw)
        self.active = False
        self.size = Window.size
        self.pos = (0, 0)
        with self.canvas.before:
            Color(0.043, 0.290, 0.561, 1.0)  # solid blue, fully opaque
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)
        # Big message
        self.label = Label(
            text="", font_size='80sp', bold=True, color=(1, 1, 1, 1),
            halign='center', valign='middle',
        )
        self.add_widget(self.label)
        # Logo copy (top-left) so the secret admin menu (5 taps) still works.
        self._logo = Button(
            text="[b][color=f39c12][size=28]FortiBank ATM[/size][/color][/b]",
            markup=True, background_normal='', background_color=(0, 0, 0, 0),
            color=(1, 1, 1, 1), halign='left', valign='middle',
            size_hint=(None, None), size=(340, 48),
        )
        self._logo.bind(on_release=lambda *a: App.get_running_app().register_admin_tap())
        self.add_widget(self._logo)
        Window.bind(size=self._sync_window)
        self._sync_window()

    def _sync_window(self, *a):
        self.size = Window.size
        self.pos = (0, 0)
        self._bg.size = self.size
        self._logo.pos = (30, self.height - self.LOGO_H + 8)

    def _sync_bg(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def on_touch_down(self, touch):
        # Block the ATM everywhere except the logo, which opens the admin menu.
        if self.active:
            if self._logo.collide_point(*touch.pos):
                return super().on_touch_down(touch)
            return True
        return False


class FortiBankApp(App):
    clock_text = StringProperty("12:00 PM")
    oos_active = BooleanProperty(False)
    oos_text = StringProperty("")
    current_card = None
    current_nip = ""
    timer_event = None
    time_left = 30
    SCREENSAVER_SKIP = {'processing', 'dispensing', 'cardanim', 'screensaver'}
    # Screens where the out-of-service overlay steps aside so the secret admin
    # menu stays reachable while the backend is down.
    ADMIN_SCREENS = {'adminpin', 'adminmenu', 'adminip', 'savercfg'}
    # Backend keep-alive: how often (seconds) to re-check backend reachability.
    KEEPALIVE_INTERVAL = 5
    # How often (seconds) to refresh the card catalogue from the backend.
    CARDS_INTERVAL = 15

    def build(self):
        self.settings = Settings()
        self.kv_file = os.path.join(FRONTEND_DIR, "fortibank.kv")
        self.snd_insert = self._load_sound("atm_insertion.mp3")
        self.snd_count = self._load_sound("counting.mp3")
        self.snd_beep = self._load_sound("beep.wav")
        self._admin_taps = 0
        self._last_admin_tap = 0.0
        self._last_activity = time.time()
        self._prev_screen = 'insert'
        self._screen_off = False
        self._oos_state = None
        self.cards = []
        self._cards_sig = None
        Clock.schedule_interval(self.update_clock, 1)
        Clock.schedule_interval(self._check_idle, 5)
        self.update_clock(0)
        Factory.register('PushButton', cls=PushButton)
        # Full-screen, interaction-blocking "out of service" overlay. It is
        # added to the Window (above every screen) in on_start.
        self.oos_overlay = OOSOverlay()
        self.oos_label = self.oos_overlay.label
        self.oos_overlay.opacity = 0
        return Manager()

    def _load_sound(self, filename):
        path = os.path.join(FRONTEND_DIR, filename)
        return SoundLoader.load(path) if os.path.exists(path) else None

    def update_clock(self, dt):
        tz = None
        if ZoneInfo is not None:
            try:
                tz = ZoneInfo(self.settings.timezone)
            except Exception:
                tz = None
        if tz is None:
            tz = timezone(timedelta(hours=-6))
        now = datetime.now(tz)
        self.clock_text = now.strftime("%I:%M %p")

    def _beep(self):
        if self.snd_beep:
            now = Clock.get_boottime()
            if now - getattr(self, "_last_beep", 0) < 0.12:
                return
            self._last_beep = now
            try:
                self.snd_beep.stop()
                self.snd_beep.play()
            except Exception:
                pass

    def _eject_beeps(self):
        # three beeps, starting 2 seconds after the card is being withdrawn
        for i in range(3):
            Clock.schedule_once(lambda dt: self._beep(), 2.0 + 0.4 * i)

    def go_to(self, screen_name, beep=True):
        if beep:
            self._beep()
        self._last_activity = time.time()
        self.root.current = screen_name
        self._refresh_oos_overlay()

    def insert_card(self, card):
        self._beep()
        self.current_card = card
        anim = self.root.get_screen('cardanim')
        anim.play_insert(card)

    def eject_card(self):
        self._clear_bills()
        anim = self.root.get_screen('cardanim')
        anim.play_eject()
        self._eject_beeps()

    def start_transaction(self, amount, is_withdrawal):
        self._beep()
        self.go_to('processing', beep=False)
        proc_screen = self.root.get_screen('processing')
        proc_screen.ids.proc_msg.text = (
            self.t("proc_withdraw") if is_withdrawal else self.t("proc_balance")
        )
        proc_screen.ids.iso_proc_lbl.text = self.t("iso_proc") % (self.settings.backend_ip,)

        self.time_left = 30
        proc_screen.ids.timer_lbl.text = self.t("timer", self.time_left)
        if self.timer_event:
            self.timer_event.cancel()
        self.timer_event = Clock.schedule_interval(self._tick_timer, 1)

        threading.Thread(
            target=self._execute_api,
            args=(amount, is_withdrawal),
            daemon=True
        ).start()

    def _tick_timer(self, dt):
        self.time_left -= 1
        self.root.get_screen('processing').ids.timer_lbl.text = self.t("timer", self.time_left)
        if self.time_left <= 0 and self.timer_event:
            self.timer_event.cancel()

    def _execute_api(self, amount, is_withdrawal):
        payload = {
            "card_number": self.current_card["num"],
            "pin": self.current_nip,
            "amount": amount
        }
        try:
            resp = requests.post(BACKEND_URL or self.settings.backend_url(), json=payload, timeout=30)
            data = resp.json()
            Clock.schedule_once(lambda dt: self._handle_response(data, amount, is_withdrawal), 0)
        except Exception as exc:
            Clock.schedule_once(lambda dt, msg=str(exc): self._handle_error(msg), 0)

    def _handle_response(self, data, amount, is_withdrawal):
        if self.timer_event:
            self.timer_event.cancel()
        if data.get("status") == "success":
            if is_withdrawal:
                self._dispense_bills(amount, data)
            else:
                self._show_result(True, self.t("res_success"), data)
        else:
            self._show_result(False, data.get("detail") or self.t("declined"), data)

    def _handle_error(self, err_msg):
        if self.timer_event:
            self.timer_event.cancel()
        self._show_result(False, self.t("conn_error"), {"iso_request": err_msg, "iso_response": ""})

    def _clear_bills(self):
        """Remove any bill images left in the dispensing area."""
        try:
            disp = self.root.get_screen('dispensing')
            area = disp.ids.bill_area
            for child in list(area.children):
                if isinstance(child, Image):
                    area.remove_widget(child)
        except Exception:
            pass

    def _dispense_bills(self, amount, data):
        self._clear_bills()
        self.go_to('dispensing', beep=False)
        disp = self.root.get_screen('dispensing')
        disp.ids.disp_title.text = self.t("disp_count")
        disp.ids.disp_sub.text = self.t("disp_count_sub")

        if self.snd_count:
            self.snd_count.loop = True
            self.snd_count.play()

        Clock.schedule_once(lambda dt: self._animate_bills(amount, data), 3.0)

    def _animate_bills(self, amount, data):
        if self.snd_count:
            self.snd_count.stop()

        disp = self.root.get_screen('dispensing')
        disp.ids.disp_title.text = self.t("disp_deliver")
        disp.ids.disp_sub.text = self.t("disp_take")
        area = disp.ids.bill_area

        # Clear any previous bills from the bill area
        self._clear_bills()

        remaining = amount
        bills = []
        if remaining >= 500:
            num_500 = (remaining // 500) - 1
            bills.extend([500] * num_500)
            bills.extend([200, 100, 100, 50, 50])
            remaining %= 500
        for denom in (200, 100, 50):
            count = remaining // denom
            bills.extend([denom] * count)
            remaining %= denom

        for idx, denom in enumerate(bills):
            img_path = os.path.join(FRONTEND_DIR, f"{denom}.png")
            if os.path.exists(img_path):
                bill = Image(
                    source=img_path,
                    size_hint=(None, None),
                    size=(364, 155),
                    opacity=0
                )
                area.add_widget(bill)
                # Position relative to bill_area using pos_hint
                start_y = 0.9  # Start near the top
                target_y = min(0.92, max(0.12, (0.5 - (idx * 0.08)) * 1.2))  # 20% higher resting spot
                bill.pos_hint = {'center_x': 0.5, 'top': start_y}
                anim = Animation(
                    opacity=1,
                    duration=0.6 + idx * 0.1,
                    t='out_cubic'
                )
                anim.start(bill)
                # Animate position
                pos_anim = Animation(
                    pos_hint={'center_x': 0.5, 'top': target_y},
                    duration=0.6 + idx * 0.1,
                    t='out_cubic'
                )
                pos_anim.start(bill)

        Clock.schedule_once(
            lambda dt: self._show_result(True, "Dinero entregado", data),
            3.5
        )

    def _show_result(self, success, title, data):
        self._clear_bills()
        self.go_to('result', beep=False)
        res = self.root.get_screen('result')
        if success:
            res.ids.res_title.text = self.t("res_success")
            res.ids.res_title.color = (0.18, 0.80, 0.44, 1)
            bal = data.get("remaining_balance", 0)
            res.ids.res_detail.text = self.t("res_balance", f"{bal:,.2f}")
        else:
            res.ids.res_title.text = self.t("res_declined")
            res.ids.res_title.color = (0.91, 0.30, 0.24, 1)
            res.ids.res_detail.text = title

        req_txt = data.get("iso_request", "N/A")
        res_txt = data.get("iso_response", "N/A")
        res.ids.res_iso.text = "[SYS] {0}:\nREQ: {1}\nRES: {2}".format(
            self.t("iso_traffic"), req_txt, res_txt)


    def on_start(self):
        self._apply_language()
        self._refresh_admin()
        # Put the full-screen "out of service" overlay above every screen.
        Window.add_widget(self.oos_overlay)
        # Start the background keep-alive that watches the backend and toggles
        # the "Out of Service" / "Fuera de Servicio" overlay.
        threading.Thread(target=self._keepalive_loop, daemon=True).start()
        threading.Thread(target=self._cards_loop, daemon=True).start()

    def t(self, key, *args):
        text = translate(self.settings.language, key)
        if args:
            try:
                return text % args
            except Exception:
                return text
        return text

    def _apply_language(self):
        lang = self.settings.language
        for screen in self.root.screens:
            for key, widget in screen.ids.items():
                if key in TRANSLATIONS:
                    widget.text = TRANSLATIONS[key][0 if lang == 'es' else 1]
        # Keep the out-of-service overlay text in sync with the UI language.
        self.oos_text = self.t("out_of_service") if self.oos_active else ""
        if self.oos_active:
            self.oos_label.text = self.oos_text

    def _refresh_admin(self):
        lang = self.settings.language
        scr = self.root.get_screen('adminmenu')
        if 'admin_lang_btn' in scr.ids:
            scr.ids.admin_lang_btn.text = (
                "Idioma: Español" if lang == 'es' else "Language: English")
        if 'admin_tz_btn' in scr.ids:
            tz_label = ("CDMX" if self.settings.timezone == 'America/Mexico_City'
                        else "Miami")
            prefix = "Zona Horaria: " if lang == 'es' else "Timezone: "
            scr.ids.admin_tz_btn.text = prefix + tz_label
        if 'backend_ip_value' in scr.ids:
            scr.ids.backend_ip_value.text = self.settings.backend_ip

    def register_admin_tap(self):
        now = time.time()
        if now - self._last_admin_tap > 3.5:
            self._admin_taps = 0
        self._admin_taps += 1
        self._last_admin_tap = now
        if self._admin_taps >= 5:
            self._admin_taps = 0
            self.open_admin_pin()

    def open_admin_pin(self, mode='verify'):
        scr = self.root.get_screen('adminpin')
        scr.mode = mode
        scr.pin = ""
        scr.pin_display = ""
        scr.msg = ""
        if mode == 'verify':
            scr.title = self.t("admin_pin_verify_title")
        else:
            scr.title = self.t("admin_pin_new_title")
        self.go_to('adminpin', beep=False)

    def open_change_pin(self):
        self.open_admin_pin('new')

    def handle_admin_pin(self, mode, pin):
        scr = self.root.get_screen('adminpin')
        if mode == 'verify':
            if pin == self.settings.admin_pin:
                self.open_admin_menu()
            else:
                scr.msg = self.t("admin_pin_incorrect")
        elif mode == 'new':
            scr.temp_pin = pin
            scr.mode = 'confirm'
            scr.title = self.t("admin_pin_confirm_title")
            scr.msg = ""
        elif mode == 'confirm':
            if pin == scr.temp_pin:
                self.settings.set('admin_pin', pin, persist=False)
                self.open_admin_menu()
            else:
                scr.mode = 'new'
                scr.title = self.t("admin_pin_new_title")
                scr.msg = self.t("admin_pin_mismatch")

    def open_admin_menu(self):
        self.go_to('adminmenu', beep=False)
        self._refresh_admin()

    def close_admin(self):
        self.settings.save()
        self.go_to('insert', beep=False)

    def open_admin_ip(self):
        scr = self.root.get_screen('adminip')
        scr.value = self.settings.backend_ip
        scr.msg = ""
        self.go_to('adminip', beep=False)

    def handle_admin_ip(self, ip):
        ip = ip.strip()
        if self._valid_ip(ip):
            self.settings.set('backend_ip', ip, persist=False)
            self._refresh_admin()
            self.open_admin_menu()
        else:
            scr = self.root.get_screen('adminip')
            scr.value = ""
            scr.msg = self.t("admin_ip_invalid")

    def toggle_language(self):
        new_lang = 'en' if self.settings.language == 'es' else 'es'
        self.settings.set('language', new_lang, persist=False)
        self._apply_language()
        self._refresh_admin()

    def toggle_timezone(self):
        if self.settings.timezone == 'America/Mexico_City':
            new_tz = 'America/New_York'
        else:
            new_tz = 'America/Mexico_City'
        self.settings.set('timezone', new_tz, persist=False)
        self._refresh_admin()

    def test_backend(self):
        self._set_admin_status(self.t("admin_testing"), None)
        threading.Thread(target=self._do_test_backend, daemon=True).start()

    def _do_test_backend(self):
        url = "http://{0}:8000/api/withdraw".format(self.settings.backend_ip)
        # /api/withdraw is POST-only, so probe with a minimal, harmless body
        # (empty card + amount 0 is a no-op balance inquiry that still exercises
        # the full request path and returns HTTP 200 when the core is reachable).
        probe = {"card_number": "", "pin": "", "amount": 0}
        try:
            r = requests.post(url, json=probe, timeout=4)
            if r.status_code < 500:
                self._set_admin_status(self.t("admin_test_ok"), True)
            else:
                self._set_admin_status(self.t("admin_test_http") % r.status_code, False)
        except Exception as e:
            self._set_admin_status(self.t("admin_test_fail") % (type(e).__name__,), False)

    @mainthread
    def _set_admin_status(self, msg, ok=True):
        scr = self.root.get_screen('adminmenu')
        if 'admin_status' in scr.ids:
            scr.ids.admin_status.text = msg
            if ok is True:
                col = (0.18, 0.80, 0.44, 1)
            elif ok is False:
                col = (0.91, 0.30, 0.24, 1)
            else:
                col = (0.95, 0.61, 0.07, 1)
            scr.ids.admin_status.color = col

    # ------------------------------------------------------------------
    # Backend keep-alive (drives the "Out of Service" banner)
    # ------------------------------------------------------------------
    def _api_url(self, path):
        """Build an absolute backend URL for the given API path."""
        if BACKEND_URL:
            base = BACKEND_URL.split("/api/")[0].rstrip("/")
        else:
            base = "http://{0}:8000".format(self.settings.backend_ip)
        return base + path

    def _health_url(self):
        """Lightweight URL used to check whether the backend is reachable."""
        return self._api_url("/docs")

    def _backend_reachable(self):
        try:
            r = requests.get(self._health_url(), timeout=4)
            return r.status_code < 500
        except Exception:
            return False

    def _keepalive_loop(self):
        """Continuously poll the backend and reflect reachability in the UI."""
        while True:
            self._update_oos(not self._backend_reachable())
            time.sleep(self.KEEPALIVE_INTERVAL)

    def _update_oos(self, active):
        # Only touch the UI when the state actually changes.
        if active == self._oos_state:
            return
        self._oos_state = active
        self._apply_oos(active)

    @mainthread
    def _apply_oos(self, active):
        self.oos_active = active
        self.oos_text = self.t("out_of_service") if active else ""
        self.oos_label.text = self.oos_text
        self._refresh_oos_overlay()

    def _refresh_oos_overlay(self):
        # The "Fuera de Servicio" overlay steps aside for the screensaver and
        # for the admin screens, so the secret menu stays reachable while the
        # backend is down. It reappears when the user leaves those screens.
        overlay = getattr(self, "oos_overlay", None)
        if overlay is None or self.root is None:
            return
        hide = self.root.current == 'screensaver' or self.root.current in self.ADMIN_SCREENS
        show = self.oos_active and not hide
        overlay.active = show
        overlay.opacity = 1 if show else 0

    # ------------------------------------------------------------------
    # Card catalogue (fetched from the backend, kept in sync)
    # ------------------------------------------------------------------
    def _cards_loop(self):
        """Continuously refresh the card list from the backend."""
        while True:
            self._refresh_cards()
            time.sleep(self.CARDS_INTERVAL)

    def _refresh_cards(self):
        try:
            r = requests.get(self._api_url("/api/cards"), timeout=5)
            if r.status_code != 200:
                return
            data = r.json()
            if not isinstance(data, list):
                return
            cards = [
                {"num": c.get("card_number", ""), "name": c.get("name", ""), "brand": c.get("brand", "")}
                for c in data if c.get("card_number")
            ]
        except Exception:
            return
        sig = tuple(sorted((c["num"], c["name"], c["brand"]) for c in cards))
        if sig == self._cards_sig:
            return
        self._cards_sig = sig
        Clock.schedule_once(lambda dt: self._apply_cards(cards), 0)

    def _apply_cards(self, cards):
        self.cards = cards
        if self.root is None:
            return
        try:
            self.root.get_screen('insert').build_cards(cards)
        except Exception:
            pass

    @staticmethod
    def _valid_ip(ip):
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            if not (0 <= int(part) <= 255):
                return False
        return True

    def do_reboot(self):
        self.settings.save()
        try:
            subprocess.run(["sudo", "-n", "reboot"], check=False)
        except Exception:
            pass

    def do_poweroff(self):
        self.settings.save()
        try:
            subprocess.run(["sudo", "-n", "poweroff"], check=False)
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Screensaver (idle burn-in protection)
    # ------------------------------------------------------------------
    def _check_idle(self, dt):
        if self.root is None:
            return
        if self._screen_off:
            return
        if self.root.current in self.SCREENSAVER_SKIP:
            return
        elapsed = time.time() - self._last_activity
        screenoff = self.settings.screenoff_timeout
        saver = self.settings.saver_timeout
        if screenoff > 0 and elapsed >= screenoff:
            self._turn_screen_off()
            return
        if saver > 0 and elapsed >= saver:
            self._show_screensaver()

    def _show_screensaver(self):
        if self.root is None or self.root.current == 'screensaver':
            return
        self._prev_screen = self.root.current
        self.go_to('screensaver', beep=False)

    def dismiss_screensaver(self):
        if self.root is None or self.root.current != 'screensaver':
            return
        self._last_activity = time.time()
        self.go_to(self._prev_screen or 'insert', beep=False)


    # ------------------------------------------------------------------
    # Screensaver / display configuration
    # ------------------------------------------------------------------
    def open_saver_cfg(self):
        self._refresh_saver_cfg()
        self.go_to('savercfg', beep=False)

    def _fmt_timeout(self, seconds):
        if seconds <= 0:
            return self.t("saver_off")
        if seconds < 60:
            return "{0}s".format(seconds)
        if seconds % 60 == 0:
            return "{0}m".format(seconds // 60)
        return "{0}m{1}s".format(seconds // 60, seconds % 60)

    def _refresh_saver_cfg(self):
        scr = self.root.get_screen('savercfg')
        if 'saver_value_lbl' in scr.ids:
            scr.ids.saver_value_lbl.text = self._fmt_timeout(self.settings.saver_timeout)
        if 'screenoff_value_lbl' in scr.ids:
            scr.ids.screenoff_value_lbl.text = self._fmt_timeout(self.settings.screenoff_timeout)

    def set_saver_timeout(self, seconds):
        self.settings.set('saver_timeout', str(int(seconds)), persist=False)
        self._refresh_saver_cfg()

    def set_screenoff_timeout(self, seconds):
        self.settings.set('screenoff_timeout', str(int(seconds)), persist=False)
        self._refresh_saver_cfg()

    def _turn_screen_off(self):
        try:
            subprocess.run(["xset", "dpms", "force", "off"], check=False,
                           env=dict(os.environ, DISPLAY=":2"))
            self._screen_off = True
        except Exception:
            pass

    def _wake_screen(self):
        self._screen_off = False
        try:
            subprocess.run(["xset", "dpms", "force", "on"], check=False,
                           env=dict(os.environ, DISPLAY=":2"))
        except Exception:
            pass


if __name__ == '__main__':
    FortiBankApp().run()
