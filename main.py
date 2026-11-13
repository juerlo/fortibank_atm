import os
import threading
from datetime import datetime
import requests

from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '600')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle

BACKEND_URL = os.environ.get("ATM_BACKEND_URL", "http://127.0.0.1:8000/api/withdraw")

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


class ScreenBase(Screen):
    pass


class ScreenInsert(ScreenBase):
    def on_kv_post(self, base_widget):
        carousel = self.ids.card_carousel
        for c in CARDS:
            formatted = " ".join(c["num"][i:i+4] for i in range(0, 16, 4))
            card_box = BoxLayout(
                orientation='vertical',
                size_hint=(None, None),
                size=(380, 230),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                padding=22,
                spacing=12
            )
            with card_box.canvas.before:
                Color(0.11, 0.16, 0.22, 1)
                rect = RoundedRectangle(pos=card_box.pos, size=card_box.size, radius=[16])
            card_box.bind(
                pos=lambda inst, val, r=rect: setattr(r, 'pos', val),
                size=lambda inst, val, r=rect: setattr(r, 'size', val)
            )

            top_row = BoxLayout(orientation='horizontal', size_hint_y=0.35)
            chip = Label(
                text="CHIP",
                size_hint=(None, None),
                size=(55, 38),
                color=(0.2, 0.15, 0, 1),
                bold=True
            )
            with chip.canvas.before:
                Color(0.83, 0.69, 0.22, 1)
                c_rect = RoundedRectangle(pos=chip.pos, size=chip.size, radius=[6])
            chip.bind(
                pos=lambda inst, val, r=c_rect: setattr(r, 'pos', val),
                size=lambda inst, val, r=c_rect: setattr(r, 'size', val)
            )
            brand_lbl = Label(
                text=c["brand"],
                font_size='20sp',
                bold=True,
                italic=True,
                color=(0.3, 0.6, 1, 1) if c["brand"] == "VISA" else (1, 0.5, 0.2, 1),
                halign='right',
                text_size=(260, None)
            )
            top_row.add_widget(chip)
            top_row.add_widget(brand_lbl)

            num_lbl = Label(text=formatted, font_size='22sp', bold=True)
            name_lbl = Label(text=c["name"].upper(), font_size='16sp', color=(0.85, 0.85, 0.85, 1))
            select_btn = Button(
                text="INSERTAR TARJETA",
                size_hint_y=None,
                height=42,
                background_normal='',
                background_color=(0.95, 0.61, 0.07, 1),
                bold=True
            )
            select_btn.bind(on_release=lambda inst, card=c: App.get_running_app().insert_card(card))

            card_box.add_widget(top_row)
            card_box.add_widget(num_lbl)
            card_box.add_widget(name_lbl)
            card_box.add_widget(select_btn)
            carousel.add_widget(card_box)


class ScreenPin(ScreenBase):
    nip = ""

    def on_pre_enter(self):
        self.clear_nip()

    def append_nip(self, digit):
        if len(self.nip) < 4:
            self.nip += digit
            self.ids.nip_display.text = "*" * len(self.nip)

    def clear_nip(self):
        self.nip = ""
        self.ids.nip_display.text = ""

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


class Manager(ScreenManager):
    pass


class FortiBankApp(App):
    clock_text = StringProperty("12:00 PM")
    current_card = None
    current_nip = ""
    timer_event = None
    time_left = 30

    def build(self):
        self.kv_file = "fortibank.kv"
        self.snd_insert = SoundLoader.load("atm_insertion.mp3") if os.path.exists("atm_insertion.mp3") else None
        self.snd_count = SoundLoader.load("counting.mp3") if os.path.exists("counting.mp3") else None
        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)
        return Manager()

    def update_clock(self, dt):
        self.clock_text = datetime.now().strftime("%I:%M %p")

    def go_to(self, screen_name):
        self.root.current = screen_name

    def insert_card(self, card):
        self.current_card = card
        if self.snd_insert:
            self.snd_insert.play()
        self.go_to('pin')

    def eject_card(self):
        if self.snd_insert:
            self.snd_insert.play()
        self.current_card = None
        self.current_nip = ""
        self.go_to('insert')

    def start_transaction(self, amount, is_withdrawal):
        self.go_to('processing')
        proc_screen = self.root.get_screen('processing')
        proc_screen.ids.proc_msg.text = (
            "Procesando transacción segura..." if is_withdrawal else "Consultando su saldo..."
        )
        proc_screen.ids.iso_proc_lbl.text = "[SYS] Conectando al Core Bancario (192.168.27.35)..."

        self.time_left = 30
        proc_screen.ids.timer_lbl.text = f"Tiempo restante: {self.time_left}s"
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
        self.root.get_screen('processing').ids.timer_lbl.text = f"Tiempo restante: {self.time_left}s"
        if self.time_left <= 0 and self.timer_event:
            self.timer_event.cancel()

    def _execute_api(self, amount, is_withdrawal):
        payload = {
            "card_number": self.current_card["num"],
            "pin": self.current_nip,
            "amount": amount
        }
        try:
            resp = requests.post(BACKEND_URL, json=payload, timeout=30)
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

    def _dispense_bills(self, amount, data):
        self.go_to('dispensing')
        disp = self.root.get_screen('dispensing')
        disp.ids.disp_title.text = "Contando billetes..."
        disp.ids.disp_sub.text = "Por favor espere"

        if self.snd_count:
            self.snd_count.loop = True
            self.snd_count.play()

        Clock.schedule_once(lambda dt: self._animate_bills(amount, data), 3.0)

    def _animate_bills(self, amount, data):
        if self.snd_count:
            self.snd_count.stop()

        disp = self.root.get_screen('dispensing')
        disp.ids.disp_title.text = "Entregando su dinero"
        disp.ids.disp_sub.text = "Por favor, tome su efectivo"
        area = disp.ids.bill_area

        for child in list(area.children)[:-1]:
            area.remove_widget(child)

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
                    size=(300, 130),
                    pos=(362, 340),
                    opacity=0
                )
                area.add_widget(bill)
                target_y = max(30, 220 - (idx * 14))
                anim = Animation(y=target_y, opacity=1, duration=0.6 + idx * 0.1, t='out_cubic')
                anim.start(bill)

        Clock.schedule_once(
            lambda dt: self._show_result(True, "Dinero entregado", data),
            3.5
        )

    def _show_result(self, success, title, data):
        self.go_to('result')
        res = self.root.get_screen('result')
        if success:
            res.ids.res_title.text = title
            res.ids.res_title.color = (0.18, 0.80, 0.44, 1)
            bal = data.get("remaining_balance", 0)
            res.ids.res_detail.text = f"Saldo Disponible: ${bal:,.2f} MXN"
        else:
            res.ids.res_title.text = "Operación Declinada"
            res.ids.res_title.color = (0.91, 0.30, 0.24, 1)
            res.ids.res_detail.text = title

        req_txt = data.get("iso_request", "N/A")
        res_txt = data.get("iso_response", "N/A")
        res.ids.res_iso.text = f"[SYS] Tráfico SASE Inspeccionado:\nREQ: {req_txt}\nRES: {res_txt}"


if __name__ == '__main__':
    FortiBankApp().run()
