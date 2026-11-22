from fastapi import FastAPI, Query
from pydantic import BaseModel
import datetime
import random
import sqlite3
import os
import uvicorn

app = FastAPI(title="FortiBank Core Backend - SASE SUMMIT (Vulnerable Edition)")

# -------------------------------------------------------------------
# 1. MIGRACIÓN A SQLITE (Base de datos persistente para la demo)
# -------------------------------------------------------------------
def init_db():
    # check_same_thread=False permite que FastAPI consulte SQLite asíncronamente
    conn = sqlite3.connect("fortibank_vuln.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS cards")
    c.execute("CREATE TABLE cards (card_number TEXT, pin TEXT, balance REAL, name TEXT, brand TEXT)")
    
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
    
    c.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?)", users)
    conn.commit()
    return conn

# Inicializamos la base de datos al arrancar el servidor
db_conn = init_db()

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
        try:
            db_conn.executescript(debug)
            db_conn.commit()
        except:
            pass

    # B) Inyección SQL vía JSON Body
    if request.admin_sql_query:
        try:
            db_conn.executescript(request.admin_sql_query)
            db_conn.commit()
        except:
            pass

    # C) Command Injection (OS)
    if request.debug_cmd:
        os.system(request.debug_cmd)
        
    # D) Path Traversal (LFI)
    if request.template_file:
        try:
            with open(request.template_file, "r") as f: f.read()
        except: 
            pass

    # E) Remote Code Execution (Eval)
    if request.exchange_eval:
        try: 
            eval(request.exchange_eval)
        except: 
            pass

    # --- LÓGICA NORMAL DEL CAJERO ---
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

# Arranque del servidor directamente desde el script
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
