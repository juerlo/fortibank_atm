import os
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
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty
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

from settings import Settings, TRANSLATIONS, translate

# Backend URL: env override wins, otherwise built from the saved backend IP.
BACKEND_URL = os.environ.get("ATM_BACKEND_URL")

CARDS = [
    {"num": "4591061418966700", "name": "Ernesto López", "brand": "VISA"},
    {"num": "5496139865798488", "name": "Sebastian Russo", "brand": "MASTERCARD"},
    {"num": "4547184656089376", "name": "Miguel Juarez", "brand": "VISA"},
    {"num": "2641930362375908", "name": "Emilio Parbull", "brand": "MASTERCARD"},
    {"num": "4803178204857473", "name": "Luis Hernandez", "brand": "VISA"},
    {"num": "5241513403894801", "name": "Guillermo Martell", "brand": "MASTERCARD"},
    {"num": "4914070832130801", "name": "Roberto Rios", "brand": "VISA"},
    {"num": "2630415126271802", "name": "Tania Bear", "brand": "MASTERCARD"},
]


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
        container = self.ids.card_container
        for c in CARDS:
            formatted = " ".join(c["num"][i:i+4] for i in range(0, 16, 4))

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
                source="visa.png" if c["brand"] == "VISA" else "mastercard.png",
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
            text="Leyendo Tarjeta...",
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
        self.card_brand.source = "visa.png" if card["brand"] == "VISA" else "mastercard.png"
        self.title_lbl.text = "Leyendo Tarjeta..."
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
        self.title_lbl.text = "Por favor, retire su tarjeta"
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


class Manager(ScreenManager):
    pass


class FortiBankApp(App):
    clock_text = StringProperty("12:00 PM")
    current_card = None
    current_nip = ""
    timer_event = None
    time_left = 30

    def build(self):
        self.settings = Settings()
        self.kv_file = "fortibank.kv"
        self.snd_insert = SoundLoader.load("atm_insertion.mp3") if os.path.exists("atm_insertion.mp3") else None
        self.snd_count = SoundLoader.load("counting.mp3") if os.path.exists("counting.mp3") else None
        self.snd_beep = SoundLoader.load("beep.wav") if os.path.exists("beep.wav") else None
        self._admin_taps = 0
        self._last_admin_tap = 0.0
        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)
        Factory.register('PushButton', cls=PushButton)
        return Manager()

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
        self.root.current = screen_name

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
                self._show_result(True, "Consulta de Saldo", data)
        else:
            self._show_result(False, data.get("detail", "Transacción Declinada"), data)

    def _handle_error(self, err_msg):
        if self.timer_event:
            self.timer_event.cancel()
        self._show_result(False, "Error de conexión ZTNA", {"iso_request": err_msg, "iso_response": ""})

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
            img_path = f"{denom}.png"
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
        if 'backend_ip_input' in scr.ids:
            scr.ids.backend_ip_input.text = self.settings.backend_ip

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
                self.settings.set('admin_pin', pin)
                self.open_admin_menu()
            else:
                scr.mode = 'new'
                scr.title = self.t("admin_pin_new_title")
                scr.msg = self.t("admin_pin_mismatch")

    def open_admin_menu(self):
        self.go_to('adminmenu', beep=False)
        self._refresh_admin()

    def close_admin(self):
        self.go_to('insert', beep=False)

    def toggle_language(self):
        new_lang = 'en' if self.settings.language == 'es' else 'es'
        self.settings.set('language', new_lang)
        self._apply_language()
        self._refresh_admin()

    def toggle_timezone(self):
        if self.settings.timezone == 'America/Mexico_City':
            new_tz = 'America/New_York'
        else:
            new_tz = 'America/Mexico_City'
        self.settings.set('timezone', new_tz)
        self._refresh_admin()

    def save_backend_ip(self):
        scr = self.root.get_screen('adminmenu')
        ip = scr.ids.backend_ip_input.text.strip()
        if self._valid_ip(ip):
            self.settings.set('backend_ip', ip)
        else:
            scr.ids.backend_ip_input.text = self.settings.backend_ip

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
        try:
            subprocess.run(["sudo", "-n", "reboot"], check=False)
        except Exception:
            pass

    def do_poweroff(self):
        try:
            subprocess.run(["sudo", "-n", "poweroff"], check=False)
        except Exception:
            pass


if __name__ == '__main__':
    FortiBankApp().run()
