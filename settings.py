"""Persistent settings and UI translations for the FortiBank ATM.

Settings are stored in a plain-text settings.txt file next to this module so
the secret admin menu can persist language, timezone, backend IP and admin PIN
across reboots.
"""
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.txt")

DEFAULTS = {
    "language": "es",
    "timezone": "America/Mexico_City",
    "backend_ip": "192.168.27.35",
    "admin_pin": "0000",
}

# key -> (Spanish, English)
TRANSLATIONS = {
    "ins_title": ("Deslice para seleccionar su tarjeta", "Swipe to select your card"),
    "ins_sub": ("(Deslice izquierda/derecha y presione una tarjeta)",
                "(Swipe left/right and press a card)"),
    "pin_title": ("Ingrese su NIP de 4 dígitos", "Enter your 4-digit PIN"),
    "menu_title": ("Seleccione una operación", "Select an operation"),
    "menu_withdraw": ("RETIRO DE EFECTIVO", "CASH WITHDRAWAL"),
    "menu_balance": ("CONSULTA DE SALDO", "BALANCE INQUIRY"),
    "menu_cancel": ("CANCELAR Y RETIRAR TARJETA", "CANCEL AND EJECT CARD"),
    "amt_title": ("Seleccione la cantidad a retirar", "Select withdrawal amount"),
    "amt_back": ("REGRESAR", "GO BACK"),
    "res_again": ("OTRO MOVIMIENTO", "ANOTHER TRANSACTION"),
    "res_eject": ("RETIRAR TARJETA", "EJECT CARD"),

    # Runtime (code-driven) strings
    "proc_withdraw": ("Procesando transacción segura...", "Processing secure transaction..."),
    "proc_balance": ("Consultando su saldo...", "Checking your balance..."),
    "timer": ("Tiempo restante: %ss", "Time remaining: %ss"),
    "iso_proc": ("[SYS] Conectando al Core Bancario (%s)...", "[SYS] Connecting to Banking Core (%s)..."),
    "disp_count": ("Contando billetes...", "Counting bills..."),
    "disp_count_sub": ("Por favor espere", "Please wait"),
    "disp_deliver": ("Entregando su dinero", "Dispensing your money"),
    "disp_take": ("Por favor, tome su efectivo", "Please take your cash"),
    "res_success": ("Operación Exitosa", "Operation Successful"),
    "res_declined": ("Operación Declinada", "Operation Declined"),
    "res_balance": ("Saldo Disponible: $%s MXN", "Available Balance: $%s MXN"),
    "iso_traffic": ("Tráfico SASE Inspeccionado", "SASE Traffic Inspected"),

    # Admin menu
    "admin_menu_title": ("Menú de Administración", "Administration Menu"),
    "admin_backend_lbl": ("Backend IP:", "Backend IP:"),
    "admin_save_btn": ("GUARDAR", "SAVE"),
    "admin_change_pin": ("CAMBIAR NIP", "CHANGE PIN"),
    "admin_poweroff": ("APAGAR", "POWER OFF"),
    "admin_reboot": ("REINICIAR", "REBOOT"),
    "admin_close": ("CERRAR", "CLOSE"),
    "admin_pin_clear": ("BORRAR", "CLEAR"),
    "admin_pin_enter": ("ENTRAR", "ENTER"),
    "admin_pin_cancel": ("CANCELAR", "CANCEL"),
    "admin_pin_verify_title": ("PIN de Administrador", "Administrator PIN"),
    "admin_pin_new_title": ("Nuevo PIN de 4 dígitos", "New 4-digit PIN"),
    "admin_pin_confirm_title": ("Confirme el nuevo PIN", "Confirm new PIN"),
    "admin_pin_mismatch": ("Los PIN no coinciden", "PINs do not match"),
    "admin_pin_incorrect": ("PIN incorrecto", "Incorrect PIN"),
    "admin_pin_incomplete": ("NIP incompleto", "Incomplete PIN"),
}


def translate(lang, key):
    """Return the translated string for key (defaults to Spanish)."""
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry[0] if lang == "es" else entry[1]


class Settings:
    """Load/save a simple key=value text file with app settings."""

    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key in self.data:
                    self.data[key] = value.strip()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("# FortiBank ATM settings (auto-generated)\n")
            for key in DEFAULTS:
                fh.write("{0}={1}\n".format(key, self.data[key]))

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    @property
    def language(self):
        return self.data["language"]

    @property
    def timezone(self):
        return self.data["timezone"]

    @property
    def backend_ip(self):
        return self.data["backend_ip"]

    @property
    def admin_pin(self):
        return self.data["admin_pin"]

    def backend_url(self):
        return "http://{0}:8000/api/withdraw".format(self.data["backend_ip"])
