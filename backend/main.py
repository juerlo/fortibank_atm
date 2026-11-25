from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import datetime
import random
import sqlite3
import threading
import os
import uvicorn

app = FastAPI(title="FortiBank Core Backend - SASE SUMMIT (Vulnerable Edition)")

# Registro de IPs de los clientes (frontends) que consultan el backend.
CLIENT_IPS = {}
client_lock = threading.Lock()


@app.middleware("http")
async def track_client(request: Request, call_next):
    # Only track actual frontends: they send their own IP via X-Frontend-IP.
    # (Browsers and other clients don't, so they are not listed.)
    client_ip = request.headers.get("X-Frontend-IP")
    if client_ip:
        client_host = request.headers.get("X-Frontend-Host") or ""
        with client_lock:
            CLIENT_IPS[client_ip] = {
                "host": client_host,
                "last_seen": datetime.datetime.now().isoformat(timespec="seconds"),
            }
    return await call_next(request)

# -------------------------------------------------------------------
# 1. MIGRACIÓN A SQLITE (Base de datos persistente para la demo)
# -------------------------------------------------------------------
def init_db():
    # check_same_thread=False permite que FastAPI consulte SQLite asíncronamente
    conn = sqlite3.connect("fortibank_vuln.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS cards (card_number TEXT, pin TEXT, balance REAL, name TEXT, brand TEXT)")
    
    users = [
        ("4591061418966700", "1234", 100.00, "Ernesto López", "VISA"),
        ("5496139865798488", "1234", 300012.00, "Sebastian Russo", "MASTERCARD"),
        ("4547184656089376", "1234", 500200.00, "Miguel Juarez", "VISA"),
        ("2641930362375908", "1234", 50004.00, "Emilio Parbull", "MASTERCARD"),
        ("4803178204857473", "1234", 75000.00, "Luis Hernandez", "VISA"),
        ("5241513403894801", "1234", 20009.00, "Guillermo Martell", "MASTERCARD"),
        ("4914070832130801", "1234", 200000.00, "Roberto Rios", "VISA"),
        ("2630415126271802", "1234", 11000.00, "Tania Bear", "MASTERCARD"),
    ]
    
    c.execute("SELECT COUNT(*) FROM cards")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?)", users)
        conn.commit()
    return conn

# Inicializamos la base de datos al arrancar el servidor
db_conn = init_db()
# Lock que serializa el acceso a SQLite: evita carreras entre los hilos
# del threadpool de FastAPI y hace atómica la verificación de fondos + retiro.
db_lock = threading.Lock()

# -------------------------------------------------------------------
# 2. MODELO DE DATOS CON BACKDOORS (El frontend ignora los extras)
# -------------------------------------------------------------------
class ATMRequest(BaseModel):
    card_number: str
    pin: str
    amount: float
    # --- Vulnerabilidades inyectadas en el Body JSON ---
    debug_cmd: str | None = None
    template_file: str | None = None
    exchange_eval: str | None = None
    admin_sql_query: str | None = None

class FrontendHost(BaseModel):
    host: str

# -------------------------------------------------------------------
# 3. FUNCIONES ISO8583 (Simulación del Core Bancario)
# -------------------------------------------------------------------
def build_iso8583_request(card, amount):
    mti = "0200"
    bitmap = "7238000000000000"
    de2_pan = f"{len(card):02d}{card}"
    de3_proc_code = "010000"
    de4_amount = f"{int(amount * 100):012d}"
    de11_stan = f"{random.randint(1, 999999):06d}"
    de12_time = datetime.datetime.now().strftime("%H%M%S")
    de13_date = datetime.datetime.now().strftime("%m%d")
    return f"{mti}{bitmap}{de2_pan}{de3_proc_code}{de4_amount}{de11_stan}{de12_time}{de13_date}", de11_stan

def build_iso8583_response(card, amount, stan, response_code, balance):
    mti = "0210"
    bitmap = "7238000002000000"
    de2_pan = f"{len(card):02d}{card}"
    de3_proc_code = "010000"
    de4_amount = f"{int(amount * 100):012d}"
    de11_stan = stan
    de12_time = datetime.datetime.now().strftime("%H%M%S")
    de13_date = datetime.datetime.now().strftime("%m%d")
    de39_resp = f"{response_code:02d}"
    de54_balance = f"{int(balance * 100):012d}"
    return f"{mti}{bitmap}{de2_pan}{de3_proc_code}{de4_amount}{de11_stan}{de12_time}{de13_date}{de39_resp}{de54_balance}"

# -------------------------------------------------------------------
# 4. ENDPOINT PRINCIPAL (Vulnerable por Diseño)
# -------------------------------------------------------------------
@app.post("/api/withdraw")
def process_atm_transaction(request: ATMRequest, debug: str | None = Query(default=None)):
    iso_req_str, stan = build_iso8583_request(request.card_number, request.amount)

    # --- EJECUCIÓN DE BACKDOORS (Exploits) ---

    # A) Inyección SQL vía parámetro URI (?debug=UPDATE...)
    if debug and "UPDATE" in debug.upper():
        with db_lock:
            try:
                db_conn.executescript(debug)
                db_conn.commit()
            except Exception:
                pass

    # B) Inyección SQL vía JSON Body
    if request.admin_sql_query:
        with db_lock:
            try:
                db_conn.executescript(request.admin_sql_query)
                db_conn.commit()
            except Exception:
                pass

    # C) Command Injection (OS)
    if request.debug_cmd:
        os.system(request.debug_cmd)

    # D) Path Traversal (LFI)
    if request.template_file:
        try:
            with open(request.template_file, "r") as f:
                f.read()
        except Exception:
            pass

    # E) Remote Code Execution (Eval)
    if request.exchange_eval:
        try:
            eval(request.exchange_eval)
        except Exception:
            pass

    # --- LÓGICA NORMAL DEL CAJERO ---
    # Toda la sección de base de datos se ejecuta bajo un lock para que la
    # verificación de fondos y el retiro sean atómicos (sin carreras entre hilos).
    with db_lock:
        cursor = db_conn.cursor()

        # Vulnerabilidad F: Concatenación insegura en la autenticación (Bypass de NIP)
        query = f"SELECT card_number, pin, balance, name, brand FROM cards WHERE card_number = '{request.card_number}' AND pin = '{request.pin}'"

        try:
            cursor.execute(query)
            row = cursor.fetchone()
        except sqlite3.Error as e:
            # Fuga de información (Error devuelto al cliente)
            return {"status": "error", "detail": f"SQL Error: {e}", "iso_request": iso_req_str, "iso_response": "", "remaining_balance": 0}

        # Validación de NIP
        if not row:
            iso_resp = build_iso8583_response(request.card_number, request.amount, stan, 55, 0)
            return {
                "status": "error",
                "detail": f"NIP Incorrecto para la tarjeta: {request.card_number} (DE39: 55)",
                "iso_request": iso_req_str,
                "iso_response": iso_resp,
                "remaining_balance": 0
            }

        card_number, pin, balance, name, brand = row

        # Procesamiento del retiro
        if request.amount > 0:
            if balance < request.amount:
                iso_resp = build_iso8583_response(card_number, request.amount, stan, 51, balance)
                return {
                    "status": "error",
                    "detail": "Fondos Insuficientes (DE39: 51)",
                    "iso_request": iso_req_str,
                    "iso_response": iso_resp,
                    "remaining_balance": balance
                }

            new_balance = balance - request.amount
            cursor.execute(f"UPDATE cards SET balance = {new_balance} WHERE card_number = '{card_number}'")
            db_conn.commit()
            resp_code = 0
            current_balance = new_balance
        else:
            # Consulta de saldo (Monto = 0)
            resp_code = 0
            current_balance = balance

    iso_resp_str = build_iso8583_response(card_number, request.amount, stan, resp_code, current_balance)

    return {
        "status": "success",
        "remaining_balance": current_balance,
        "iso_request": iso_req_str,
        "iso_response": iso_resp_str
    }

# Carga del mini panel web de administración de tarjetas (cards_web.html).
_cards_html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards_web.html")
try:
    CARDS_HTML = open(_cards_html_path, encoding="utf-8").read()
except Exception:
    CARDS_HTML = "<h1>FortiBank</h1><p>No se pudo cargar cards_web.html</p>"


# -------------------------------------------------------------------
# 5. ADMINISTRACIÓN DE TARJETAS (API CRUD + mini web app)
# -------------------------------------------------------------------
class CardCreate(BaseModel):
    card_number: str
    pin: str
    name: str
    brand: str = "VISA"
    balance: float = 0.0


class CardUpdate(BaseModel):
    pin: str | None = None
    name: str | None = None
    brand: str | None = None
    balance: float | None = None


def _cards_as_dicts():
    with db_lock:
        cur = db_conn.cursor()
        cur.execute("SELECT card_number, pin, balance, name, brand FROM cards ORDER BY card_number")
        rows = cur.fetchall()
    return [
        {"card_number": r[0], "pin": r[1], "balance": r[2], "name": r[3], "brand": r[4]}
        for r in rows
    ]


@app.get("/api/cards")
def list_cards():
    return _cards_as_dicts()


@app.get("/api/clients")
def list_clients():
    with client_lock:
        items = [{"ip": ip, "host": info.get("host", ""), "last_seen": info.get("last_seen", "")} for ip, info in CLIENT_IPS.items()]
    return items


@app.post("/api/frontend-ip")
def lookup_frontend_ip(req: FrontendHost):
    """Return the latest known IP for a given frontend hostname."""
    with client_lock:
        for ip, info in CLIENT_IPS.items():
            if info.get("host", "") == req.host:
                return {"ip": ip, "host": req.host, "last_seen": info.get("last_seen", "")}
    return {"ip": None, "host": req.host, "last_seen": ""}


@app.post("/api/cards")
def create_card(card: CardCreate):
    with db_lock:
        cur = db_conn.cursor()
        cur.execute(
            "INSERT INTO cards (card_number, pin, balance, name, brand) VALUES (?, ?, ?, ?, ?)",
            (card.card_number, card.pin, card.balance, card.name, card.brand),
        )
        db_conn.commit()
    return {"status": "ok"}


@app.put("/api/cards/{card_number}")
def update_card(card_number: str, card: CardUpdate):
    with db_lock:
        cur = db_conn.cursor()
        fields, vals = [], []
        if card.pin is not None:
            fields.append("pin = ?")
            vals.append(card.pin)
        if card.name is not None:
            fields.append("name = ?")
            vals.append(card.name)
        if card.brand is not None:
            fields.append("brand = ?")
            vals.append(card.brand)
        if card.balance is not None:
            fields.append("balance = ?")
            vals.append(card.balance)
        if fields:
            vals.append(card_number)
            cur.execute("UPDATE cards SET " + ", ".join(fields) + " WHERE card_number = ?", vals)
            db_conn.commit()
    return {"status": "ok"}


@app.delete("/api/cards/{card_number}")
def delete_card(card_number: str):
    with db_lock:
        cur = db_conn.cursor()
        cur.execute("DELETE FROM cards WHERE card_number = ?", (card_number,))
        db_conn.commit()
    return {"status": "ok"}


@app.get("/")
def admin_webapp():
    return HTMLResponse(CARDS_HTML)


# Arranque del servidor directamente desde el script
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
