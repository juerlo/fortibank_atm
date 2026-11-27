import os
import socket
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

# Resolution is read directly from settings.txt (before the Settings class and
# Kivy App are imported) because Config.set must run before the window is
# created. The value is a preset like "1024x600" or "1920x1080".
def _load_resolution():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.txt")
    value = "1024x600"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("resolution="):
                    value = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except Exception:
        return 1024, 600

_RES_W, _RES_H = _load_resolution()
Config.set('graphics', 'width', str(_RES_W))
Config.set('graphics', 'height', str(_RES_H))
Config.set('graphics', 'resizable', '0')
Config.set('graphics', 'maxfps', '60')

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.factory import Factory
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line, PushMatrix, PopMatrix, Rotate, Translate, Scale
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
    """Base screen.

    The background is drawn in the screen's *own* canvas. ``Screen`` is a
    ``RelativeLayout``: Kivy lays children out at ``pos=(0, 0)`` and translates
    the canvas by ``+self.pos``. A background rectangle must therefore use
    *relative* coordinates ``(0, 0)`` -- using ``self.pos`` would render it at
    twice the screen offset (the safe-area/frame bug: with margins the blue
    canvas drifted away from the text).
    """

    def on_kv_post(self, base_widget):
        self._bg_rect = None
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(
                pos=(0, 0), size=self.size, texture=_screen_bg_tex()
            )
        self.bind(size=lambda *a: setattr(self._bg_rect, 'size', self.size))


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
        app = App.get_running_app()
        sx, sy = app.sx, app.sy
        s = app.scale            # fonts / radii stay uniform
        container = self.ids.card_container
        container.clear_widgets()
        for c in cards:
            num = c.get("num", "")
            formatted = " ".join(num[i:i+4] for i in range(0, len(num), 4))

            W, H = int(320 * sx), int(200 * sy)
            card = RelativeLayout(size_hint=(None, None), size=(W, H))

            # Background drawn by a child widget (relative coords — reliable for all cards)
            bg = Widget(size_hint=(None, None), pos=(0, 0), size=(W, H))
            with bg.canvas:
                Color(0, 0, 0, 0.6)
                RoundedRectangle(pos=(int(2 * sx), int(-6 * sy)),
                                 size=(int(316 * sx), H), radius=[int(15 * s)])
                Color(0.043, 0.059, 0.079, 1)
                RoundedRectangle(pos=(0, 0), size=(W, H), radius=[int(15 * s)])
                Color(0.090, 0.125, 0.168, 1)
                RoundedRectangle(pos=(0, int(78 * sy)), size=(W, int(122 * sy)),
                                 radius=[int(15 * s), int(15 * s), 0, 0])
                Color(0.333, 0.333, 0.333, 1)
                Line(rounded_rectangle=(0, 0, W, H, int(15 * s)), width=1)

            # .chip — 45x35, #d4af37, radius 6
            chip = Widget(size_hint=(None, None), pos=(int(20 * sx), int(145 * sy)),
                          size=(int(45 * sx), int(35 * sy)))
            with chip.canvas:
                Color(0.831, 0.686, 0.216, 1)
                RoundedRectangle(pos=chip.pos, size=chip.size, radius=[int(6 * s)])
                Color(1, 1, 1, 0.30)
                RoundedRectangle(pos=(chip.x + int(12 * sx), chip.y + int(8 * sy)),
                                 size=(chip.width - int(16 * sx), chip.height - int(16 * sy)),
                                 radius=[int(4 * s)])

            num_lbl = Label(
                text=formatted, font_size=max(1, int(17 * s)), bold=True,
                color=(1, 1, 1, 1), halign='left', valign='middle',
                size_hint=(None, None), pos=(int(20 * sx), int(100 * sy)),
                size=(int(280 * sx), int(24 * sy)),
                text_size=(int(280 * sx), int(24 * sy)),
            )
            name_lbl = Label(
                text=c["name"].upper(), font_size=max(1, int(14 * s)),
                color=(0.867, 0.867, 0.867, 1), halign='left', valign='middle',
                size_hint=(None, None), pos=(int(20 * sx), int(66 * sy)),
                size=(int(230 * sx), int(22 * sy)),
                text_size=(int(230 * sx), int(22 * sy)),
            )
            brand_img = Image(
                source=os.path.join(
                    FRONTEND_DIR,
                    "visa.png" if c["brand"] == "VISA" else "mastercard.png",
                ),
                size_hint=(None, None), pos=(int(240 * sx), int(20 * sy)),
                size=(int(60 * sx), int(40 * sy)), fit_mode="contain",
            )
            select_btn = Button(
                size_hint=(None, None), pos=(0, 0), size=(W, H),
                background_normal='', background_color=(0, 0, 0, 0), opacity=0,
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
    """Full-screen card insertion / ejection animation (matches the HTML overlay).

    The animation is authored in the fixed 1024x600 design space and drawn
    through a ``Scale`` canvas transform, so it always fills the visible area
    (the Manager is mapped per axis onto the safe rectangle).
    """
    BG = (0.035, 0.231, 0.439, 1)  # #093b70

    def __init__(self, **kw):
        super().__init__(**kw)
        self._flash_event = None
        self._slot_on = True
        self._scale_instr = None
        self._design_root = None
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
        app = App.get_running_app()
        sx, sy = app.sx, app.sy
        # Design-space container: children keep their 1024x600 coordinates and
        # the canvas transform maps them into the safe area (per axis).
        root = FloatLayout(size_hint=(None, None), size=(1024 * sx, 600 * sy), pos=(0, 0))
        with root.canvas.before:
            PushMatrix()
            self._scale_instr = Scale(sx, sy, 1)
        with root.canvas.after:
            PopMatrix()
        self._design_root = root

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

    def set_scale(self, sx, sy):
        """Re-apply the safe-area scale after a frame adjustment."""
        if self._design_root is None or self._scale_instr is None:
            return
        self._design_root.size = (1024 * sx, 600 * sy)
        self._scale_instr.x = sx
        self._scale_instr.y = sy

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
        Clock.schedule_once(lambda dt: app.snd_insert and not app.muted and app.snd_insert.play(), 0.3)

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
        Clock.schedule_once(lambda dt: app.snd_insert and not app.muted and app.snd_insert.play(), 0.3)

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
        app = App.get_running_app()
        sx, sy = app.sx, app.sy
        s = app.scale
        # Dark radial gradient backdrop. Relative coordinates (0, 0): the screen
        # is a RelativeLayout, so self.pos would be applied twice.
        self._bg = Rectangle(
            pos=(0, 0), size=self.size,
            texture=_radial_texture((0.02, 0.10, 0.22), (0.0, 0.01, 0.03)))
        self.canvas.add(self._bg)
        self.bind(size=self._sync_bg)

        # Floating banknotes
        bill_imgs = [os.path.join(FRONTEND_DIR, f"{d}.png") for d in (50, 100, 200, 500)]
        for i in range(10):
            src = bill_imgs[i % len(bill_imgs)]
            if not os.path.exists(src):
                continue
            img = Image(source=src, size_hint=(None, None),
                        size=(int(120 * sx), int(51 * sy)),
                        opacity=random.uniform(0.12, 0.28), allow_stretch=True)
            img.pos = (random.uniform(0, max(1.0, self.width - img.width)),
                       random.uniform(0, max(1.0, self.height - img.height)))
            self.add_widget(img)
            self._bills.append([img, random.uniform(10, 26), random.uniform(-8, 8)])

        # Bouncing FortiBank logo
        self._logo = Factory.AtmButton(
            text=self._logo_markup(s),
            markup=True, size_hint=(None, None),
            size=(int(self.LOGO_W * sx), int(self.LOGO_H * sy)),
            background_color=(0.05, 0.10, 0.18, 0.96))
        self._logo.pos = (self._logo_x, self._logo_y)
        self.add_widget(self._logo)

        # Pulsing hint
        self._hint = Label(
            text=App.get_running_app().t("saver_hint"),
            font_size=max(1, int(18 * s)), color=(1, 1, 1, 0.55),
            size_hint=(None, None), size=(int(700 * sx), int(40 * sy)),
            halign='center', valign='middle',
            text_size=(int(700 * sx), int(40 * sy)))
        self._hint.pos = (int((1024 - 700) / 2.0 * sx), int(100 * sy))
        self.add_widget(self._hint)

        # Full-screen invisible touch catcher: any tap dismisses the screensaver
        self._dismiss = Button(
            text="", size_hint=(1, 1), background_normal='',
            background_down='', background_color=(0, 0, 0, 0))
        self._dismiss.on_release = self._dismiss_now
        self.add_widget(self._dismiss)

    @staticmethod
    def _logo_markup(s):
        size = max(1, int(38 * s))
        return ("[b][color=f39c12][size={0}]FortiBank[/size][/color] "
                "[b][color=ffffff][size={0}]ATM[/size][/color][/b]").format(size)

    def apply_scale(self, sx, sy):
        """Resize the decorative elements to the current safe-area scale."""
        s = min(sx, sy)
        try:
            self._logo.text = self._logo_markup(s)
            self._logo.size = (int(self.LOGO_W * sx), int(self.LOGO_H * sy))
            self._hint.font_size = max(1, int(18 * s))
            self._hint.size = (int(700 * sx), int(40 * sy))
            self._hint.text_size = self._hint.size
            self._hint.pos = (int((1024 - 700) / 2.0 * sx), int(100 * sy))
            for img, _vy, _vx in self._bills:
                img.size = (int(120 * sx), int(51 * sy))
        except Exception:
            pass

    def _dismiss_now(self, *a):
        App.get_running_app().dismiss_screensaver()

    def _sync_bg(self, *a):
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
        maxx = max(0.0, self.width - self._logo.width)
        maxy = max(0.0, self.height - self._logo.height)
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

        # Drift the banknotes upward, wrapping inside the visible area (the
        # screen no longer clips them, so they must never leave it).
        for bill in self._bills:
            img, vy, vx = bill
            ix, iy = img.pos
            span_y = max(1.0, self.height - img.height)
            span_x = max(1.0, self.width - img.width)
            iy = (iy + vy * dt) % span_y
            ix += vx * dt
            if ix < 0:
                ix = 0.0
                bill[2] = abs(vx)
            elif ix > span_x:
                ix = span_x
                bill[2] = -abs(vx)
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


class FrameCfgScreen(ScreenBase):
    """Admin screen to adjust the safe-area (frame) margins."""

    def nudge(self, side, delta):
        App.get_running_app().frame_nudge(side, delta)

    def reset(self):
        App.get_running_app().frame_reset()

    def back(self):
        App.get_running_app().open_admin_menu()


class Manager(ScreenManager):
    def on_touch_down(self, touch):
        app = App.get_running_app()
        if app is not None:
            # Any activity resets the idle timer and wakes the display
            app._last_activity = time.time()
            if app._screen_off:
                # Wake the display and consume this touch. Do NOT dismiss the
                # screensaver here, otherwise its animation is cancelled and a
                # frozen frame stays on screen while the next tap hits the
                # (not-yet-visible) screen behind it.
                app._wake_screen()
                return True
            # While the screensaver is up, consume the touch and dismiss it
            if self.current == 'screensaver':
                app.dismiss_screensaver()
                return True
        return super().on_touch_down(touch)


class RootLayout(FloatLayout):
    """Full-window root that holds the Manager and exposes its API.

    The Manager is positioned/sized to the safe area (frame margins) inside
    this wrapper, so the whole UI fits the visible region while the root
    itself stays full-window (Kivy forces the root's size to the window).
    """

    def __init__(self, manager, **kw):
        super().__init__(**kw)
        self.manager = manager
        self.add_widget(manager)

    def get_screen(self, name):
        return self.manager.get_screen(name)

    @property
    def screens(self):
        return self.manager.screens

    @property
    def current(self):
        return self.manager.current

    @current.setter
    def current(self, value):
        self.manager.current = value


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
        # Big message (positioned inside the visible area, not the bezel).
        self.label = Label(
            text="", font_size='80sp', bold=True, color=(1, 1, 1, 1),
            halign='center', valign='middle', size_hint=(None, None),
            size=self.size, pos=(0, 0), text_size=self.size,
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
        self._safe_rect = None
        Window.bind(size=self._sync_window)
        self._sync_window()

    def set_safe_rect(self, x, y, w, h, scale):
        """Keep the overlay's text/logo inside the visible (safe) area.

        The overlay itself stays full-window so it blocks every touch, but its
        content must not be drawn under the physical frame (bezel).
        """
        self._safe_rect = (x, y, w, h)
        logo_h = max(1, int(self.LOGO_H * scale))
        self.label.font_size = max(1, int(80 * scale))
        self.label.size = (w, max(1, h - logo_h))
        self.label.pos = (x, y)
        self.label.text_size = self.label.size
        self._logo.font_size = max(1, int(28 * scale))
        self._logo.size = (min(w, max(1, int(340 * scale))), max(1, int(48 * scale)))
        self._logo.pos = (x + max(1, int(30 * scale)), y + h - logo_h + max(1, int(8 * scale)))

    def _sync_window(self, *a):
        self.size = Window.size
        self.pos = (0, 0)
        self._bg.size = self.size
        if self._safe_rect is None:
            self.label.size = self.size
            self.label.text_size = self.size
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
    ADMIN_SCREENS = {'adminpin', 'adminmenu', 'adminip', 'savercfg', 'framecfg'}
    # The visible area may never shrink below this (the UI would collapse).
    MIN_SAFE_W = 480
    MIN_SAFE_H = 280
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
        self._saved_volume = ""
        if self.muted:
            Clock.schedule_once(lambda dt: self._set_hardware_mute(True), 1)
        self._admin_taps = 0
        self._last_admin_tap = 0.0
        self._clock_taps = 0
        self._last_clock_tap = 0.0
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
        # Safe-area state: the visible rectangle (frame margins) and the
        # pending relayout scheduled after each change.
        self._safe_rect = (0, 0, Window.width, Window.height)
        self._relayout_event = None
        self.manager = Manager()
        # Apply the safe-area (frame margins) once the window is up, and
        # re-apply on resize so the UI stays inside the visible region.
        Clock.schedule_once(lambda dt: self._apply_safe_area(), 0)
        Window.bind(size=lambda *a: self._apply_safe_area())
        return self.manager

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
        if self.snd_beep and not self.muted:
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

        if self.snd_count and not self.muted:
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

        sx, sy = self.sx, self.sy
        for idx, denom in enumerate(bills):
            img_path = os.path.join(FRONTEND_DIR, f"{denom}.png")
            if os.path.exists(img_path):
                bill = Image(
                    source=img_path,
                    size_hint=(None, None),
                    size=(int(364 * sx), int(155 * sy)),
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
            lambda dt: self._show_result(True, self.t("res_delivered"), data),
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
        if 'admin_frontend_ip' in scr.ids:
            label = self.t("admin_frontend_ip")
            scr.ids.admin_frontend_ip.text = "{} ...".format(label)
            threading.Thread(target=self._do_lookup_frontend_ip, daemon=True).start()
        if 'admin_mute_btn' in scr.ids:
            scr.ids.admin_mute_btn.text = self.t("admin_unmuted") if self.muted else self.t("admin_mute_btn")
        if 'admin_resolution_btn' in scr.ids:
            cur = self.settings.get("resolution", "1024x600")
            scr.ids.admin_resolution_btn.text = "{} {}".format(self.t("resolution_lbl"), cur.replace("x", "×"))

    def register_admin_tap(self):
        now = time.time()
        if now - self._last_admin_tap > 3.5:
            self._admin_taps = 0
        self._admin_taps += 1
        self._last_admin_tap = now
        if self._admin_taps >= 5:
            self._admin_taps = 0
            self.open_admin_pin()

    def register_clock_tap(self):
        # 5 taps on the header clock within 3.5 s turns the display off.
        now = time.time()
        if now - self._last_clock_tap > 3.5:
            self._clock_taps = 0
        self._clock_taps += 1
        self._last_clock_tap = now
        if self._clock_taps >= 5:
            self._clock_taps = 0
            self._turn_screen_off()

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

    def reset_cards_balance(self):
        self._set_admin_status(self.t("admin_resetting"), None)
        threading.Thread(target=self._do_reset_cards, daemon=True).start()

    @property
    def muted(self):
        return self.settings.get("muted", "0") == "1"

    def toggle_mute(self):
        new_val = not self.muted
        self.settings.set("muted", "1" if new_val else "0", persist=True)
        self._set_hardware_mute(new_val)
        self._set_admin_status(
            self.t("admin_muted") if new_val else self.t("admin_unmuted"), True)
        # Update button label to reflect current state
        scr = self.root.get_screen('adminmenu')
        if 'admin_mute_btn' in scr.ids:
            scr.ids.admin_mute_btn.text = self.t("admin_unmuted") if new_val else self.t("admin_mute_btn")

    def _set_hardware_mute(self, mute):
        # Mute/unmute the hardware DAC so no sound escapes at the system level.
        try:
            if mute:
                # Save current volume (parse "Mono: 63 [100%]" -> "63")
                r = subprocess.run(["amixer", "-c", "0", "sget", "digital volume"],
                                   capture_output=True, text=True, timeout=3)
                for line in r.stdout.splitlines():
                    if "Mono:" in line:
                        self._saved_volume = line.split("Mono:")[1].strip().split()[0]
                        break
            vol = "0" if mute else (self._saved_volume or "63")
            subprocess.run(["amixer", "-c", "0", "sset", "digital volume", vol],
                           capture_output=True, timeout=3)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Resolution / safe-area scaling.
    #
    # The UI is authored for a fixed 1024x600 design and the Manager is resized
    # to fill the visible area (window minus the frame margins). The mapping is
    # *per axis* (``sx``/``sy``): a margin must only cut its own edge,
    # so a left margin does not shrink the height (no extra top/bottom bands).
    # Fixed widths in the KV use ``app.sx * N``, heights ``app.sy * N``; text,
    # radii and spacing use ``app.scale`` (the smaller factor) so they stay
    # proportional. These are reactive bindings -- do NOT use a helper call like
    # ``app.s(N)`` in KV: a method call is evaluated once and never rebound.
    # ------------------------------------------------------------------
    _RESOLUTION_PRESETS = [(1024, 600), (1920, 1080)]

    scale = NumericProperty(1.0)
    # Independent design->safe-area factors. Each frame margin must only affect
    # its own axis (a left margin must not create a top/bottom band), so the UI
    # is mapped onto the safe rectangle per axis instead of being uniformly
    # scaled. ``scale`` (the smaller of the two) is used for text, radii and
    # spacing so they stay uniform.
    sx = NumericProperty(1.0)
    sy = NumericProperty(1.0)

    # ------------------------------------------------------------------
    # Safe area / frame margins: the physical frame covers the outer edges
    # of the screen. These margins define the visible region; the UI is
    # sized/positioned to fit inside it and scales proportionally.
    # ------------------------------------------------------------------
    def _safe_margins(self):
        def g(k):
            try:
                return max(0, int(self.settings.get(k, "0")))
            except Exception:
                return 0
        return g("safe_left"), g("safe_top"), g("safe_right"), g("safe_bottom")

    def _apply_safe_area(self, *args):
        m = getattr(self, "manager", None)
        if m is None:
            return
        l, t, r, b = self._safe_margins()
        safe_w = max(1, Window.width - l - r)
        safe_h = max(1, Window.height - t - b)
        # Map the 1024x600 design onto the visible rectangle per axis: a margin
        # only cuts its own edge (a left margin does not shrink the height), so
        # there are no extra top/bottom (or left/right) bands.
        sx = safe_w / 1024.0
        sy = safe_h / 600.0
        m.size_hint = (None, None)
        m.size = (safe_w, safe_h)
        m.pos = (l, b)
        self.sx, self.sy = sx, sy
        self.scale = min(sx, sy)      # text/radii/spacing stay proportional
        self._safe_rect = (l, b, safe_w, safe_h)
        # Everything that is authored outside the KV (card carousel, card
        # animation, screensaver, out-of-service overlay) must follow the new
        # safe area too, otherwise it keeps drawing over the black bezel.
        self._rebuild_cards()
        self._apply_scale_to_screens()
        self._schedule_relayout()

    def _apply_scale_to_screens(self):
        try:
            self.root.get_screen('cardanim').set_scale(self.sx, self.sy)
        except Exception:
            pass
        try:
            self.root.get_screen('screensaver').apply_scale(self.sx, self.sy)
        except Exception:
            pass
        try:
            ox, oy, sw, sh = self._safe_rect
            self.oos_overlay.set_safe_rect(ox, oy, sw, sh, self.scale)
        except Exception:
            pass

    def _schedule_relayout(self):
        # Coalesce the synchronous + queued layouts triggered by a nudge.
        if self._relayout_event is not None:
            self._relayout_event.cancel()
        self._relayout_event = Clock.schedule_once(self._force_relayout, -1)

    def _force_relayout(self, *args):
        """Lay the visible screen out again for the current safe area.

        Kivy re-lays-out the ScreenManager on resize, but a screen can keep a
        stale child layout (fixed sizes fit the old, larger rectangle) which
        made text/buttons spill over the frame. Doing it explicitly here makes
        the frame adjustment deterministic instead of depending on which screen
        happened to be visible when the margins changed.
        """
        self._relayout_event = None
        m = getattr(self, "manager", None)
        if m is None:
            return
        try:
            m.do_layout()
        except Exception:
            pass
        try:
            scr = m.current_screen
        except Exception:
            scr = None
        if scr is None:
            return
        stack = [scr]
        while stack:
            w = stack.pop()
            if hasattr(w, 'do_layout'):
                try:
                    w.do_layout()
                except Exception:
                    pass
            stack.extend(w.children)

    def _rebuild_cards(self):
        try:
            scr = self.root.get_screen('insert')
            if hasattr(scr, 'build_cards'):
                scr.build_cards(self.cards)
        except Exception:
            pass

    def open_frame_cfg(self):
        self.go_to('framecfg', beep=False)

    def frame_nudge(self, side, delta):
        key = "safe_" + side
        try:
            cur = int(self.settings.get(key, "0"))
        except Exception:
            cur = 0
        cur = max(0, cur + delta)
        # Refuse margins that would swallow the visible area: the ATM must stay
        # usable, and a (nearly) empty safe area made the whole UI collapse.
        vals = dict(zip(("left", "top", "right", "bottom"), self._safe_margins()))
        vals[side] = cur
        if Window.width - vals["left"] - vals["right"] < self.MIN_SAFE_W:
            return
        if Window.height - vals["top"] - vals["bottom"] < self.MIN_SAFE_H:
            return
        self.settings.set(key, str(cur), persist=True)
        self._apply_safe_area()

    def frame_reset(self):
        for k in ("safe_left", "safe_top", "safe_right", "safe_bottom"):
            self.settings.set(k, "0", persist=False)
        self.settings.save()
        self._apply_safe_area()

    def _supported_presets(self):
        # Query xrandr for modes the connected display actually supports and
        # return only the presets that are available. Falls back to the full
        # preset list if xrandr fails (e.g. not running under X).
        try:
            r = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=3)
            available = set()
            for token in r.stdout.replace(",", " ").split():
                if "x" in token and token.replace("x", "").isdigit():
                    available.add(token)
            supported = [(w, h) for w, h in self._RESOLUTION_PRESETS
                         if "{}x{}".format(w, h) in available]
            return supported or self._RESOLUTION_PRESETS
        except Exception:
            return self._RESOLUTION_PRESETS

    def cycle_resolution(self):
        presets = self._supported_presets()
        if len(presets) <= 1:
            self._set_admin_status(
                self.t("resolution_lbl") + " " +
                "{}x{}".format(*presets[0]) if presets else "—", None)
            return
        cur = self.settings.get("resolution", "1024x600")
        idx = 0
        for i, (w, h) in enumerate(presets):
            if cur == "{}x{}".format(w, h):
                idx = i
                break
        w, h = presets[(idx + 1) % len(presets)]
        self.settings.set("resolution", "{}x{}".format(w, h), persist=True)
        label = self.t("resolution_lbl")
        self._set_admin_status(
            "{} {}×{} — {}".format(label, w, h, self.t("resolution_restart")), None)
        scr = self.root.get_screen('adminmenu')
        if 'admin_resolution_btn' in scr.ids:
            scr.ids.admin_resolution_btn.text = "{} {}×{}".format(label, w, h)

    def _do_reset_cards(self):
        try:
            base = self._api_url("/api/cards")
            r = requests.get(base, timeout=4)
            cards = r.json() if r.ok else []
            if not isinstance(cards, list):
                cards = []
            count = 0
            for c in cards:
                cn = c.get("card_number")
                if not cn:
                    continue
                rr = requests.post(self._api_url("/api/cards/{0}/reset".format(cn)), timeout=4)
                if rr.ok:
                    count += 1
            self._set_admin_status(self.t("admin_reset_ok") % count, True)
        except Exception as e:
            self._set_admin_status(self.t("admin_reset_fail") % type(e).__name__, False)

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

    def _frontend_ip(self):
        # Return (ip, hostname) of this frontend, read directly from the Linux
        # network interface. Picks the first non-loopback IPv4 address. Falls
        # back to the UDP-socket-to-backend trick if `ip` is unavailable.
        ip = ""
        try:
            r = subprocess.run(["ip", "-4", "-o", "addr", "show"],
                               capture_output=True, text=True, timeout=3)
            for line in r.stdout.splitlines():
                # Format: "2: eth0    inet 100.65.4.2/24 scope global eth0"
                parts = line.split()
                if len(parts) >= 4 and parts[2] == "inet":
                    addr = parts[3].split("/")[0]
                    if addr and not addr.startswith("127."):
                        ip = addr
                        break
        except Exception:
            ip = ""
        if not ip:
            # Fallback: UDP socket connect to backend to discover the
            # interface IP that routes toward it.
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect((self.settings.backend_ip, 8000))
                    ip = s.getsockname()[0]
                finally:
                    s.close()
            except Exception:
                ip = ""
        return ip, (socket.gethostname() if ip else "")

    def _client_headers(self):
        # Send our own IP/hostname so the backend can show the real frontend
        # even when the request is NAT'd through a gateway.
        ip, host = self._frontend_ip()
        if ip:
            return {"X-Frontend-IP": ip, "X-Frontend-Host": host}
        return {}

    def _do_lookup_frontend_ip(self):
        # Read this frontend's own IP/hostname directly from the OS network
        # interface (no backend round-trip needed).
        ip, host = self._frontend_ip()
        self._set_frontend_ip_label(ip, host)

    @mainthread
    def _set_frontend_ip_label(self, ip, host):
        scr = self.root.get_screen('adminmenu')
        if 'admin_frontend_ip' not in scr.ids:
            return
        label = self.t("admin_frontend_ip")
        if ip:
            scr.ids.admin_frontend_ip.text = "{} {} ({})".format(label, host or "?", ip)
        else:
            scr.ids.admin_frontend_ip.text = "{} —".format(label)

    def _health_url(self):
        """Lightweight URL used to check whether the backend is reachable."""
        return self._api_url("/docs")

    def _backend_reachable(self):
        try:
            r = requests.get(self._health_url(), timeout=4, headers=self._client_headers())
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
            r = requests.get(self._api_url("/api/cards"), timeout=5, headers=self._client_headers())
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
        current = self.root.current
        # Never blank the display during a transaction or card animation.
        if current in ('processing', 'dispensing', 'cardanim'):
            return
        elapsed = time.time() - self._last_activity
        screenoff = self.settings.screenoff_timeout
        saver = self.settings.saver_timeout
        if screenoff > 0 and elapsed >= screenoff:
            self._turn_screen_off()
            return
        # Show the screensaver only if it isn't already up.
        if saver > 0 and current not in self.SCREENSAVER_SKIP and elapsed >= saver:
            self._show_screensaver()

    def _show_screensaver(self):
        if self.root is None or self.root.current == 'screensaver':
            return
        self._prev_screen = self.root.current
        # Switch without resetting the idle timer, so the screen-off timeout is
        # measured from the last real activity (not from when the screensaver
        # appeared).
        self.root.current = 'screensaver'
        self._refresh_oos_overlay()

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
        # Put the monitor into DPMS standby: the backlight goes off (screen is
        # dark) while the monitor stays in standby rather than fully dropping.
        self._screen_off = True
        try:
            subprocess.run(["xset", "dpms", "force", "standby"], check=False,
                           env=dict(os.environ, DISPLAY=":2"))
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
