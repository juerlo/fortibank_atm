# FortiBank Core Backend (SASE SUMMIT - Vulnerable Edition)

FastAPI service that simulates the bank core for the FortiBank ATM kiosk. It
exposes one endpoint, `POST /api/withdraw`, which validates a card + PIN, checks
the balance, applies the withdrawal and returns ISO 8583 request/response frames.

> **WARNING - lab only.** This service contains deliberate backdoors (SQL
> injection, command injection, path traversal, `eval` RCE, auth bypass). Do not
> expose it outside an isolated lab network.

## Requirements

- Linux (tested on Ubuntu 24.04, x86_64)
- Python 3.10+ (tested on 3.12.3)
- `python3-venv`

## Install

```bash
# Copy this folder to the server (e.g. /opt/fortibank-backend)
sudo mkdir -p /opt/fortibank-backend
sudo cp -r backend/* /opt/fortibank-backend/
cd /opt/fortibank-backend

# Create the virtual environment and install dependencies
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

Or simply run `./install.sh`.

The SQLite database `fortibank_vuln.db` is created automatically on first start
with the demo cards (PIN `1234`).

## Run

```bash
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Interactive docs: `http://<host>:8000/docs` (Swagger UI).

## Run as a systemd service

`deploy/backend/fortibank-backend.service` is a template. Adjust `User`, `Group`,
`WorkingDirectory` and the venv path, then install it:

```bash
sudo cp deploy/backend/fortibank-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fortibank-backend
systemctl status fortibank-backend
journalctl -u fortibank-backend -n 50 --no-pager
```

Example unit (user `fortilab`, backend in `/home/fortilab/fortibank-backend`):

```ini
[Unit]
Description=FortiBank Core Backend (FastAPI/Uvicorn)
After=network.target

[Service]
User=fortilab
Group=www-data
WorkingDirectory=/home/fortilab/fortibank-backend
Environment="PATH=/home/fortilab/fortibank-backend/venv/bin"
ExecStart=/home/fortilab/fortibank-backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

[Install]
WantedBy=multi-user.target
```

## API

### `POST /api/withdraw`

Optional query param: `debug` (string).

Request body:

```json
{
  "card_number": "4591061418966700",
  "pin": "1234",
  "amount": 500,
  "debug_cmd": null,
  "template_file": null,
  "exchange_eval": null,
  "admin_sql_query": null
}
```

- `amount > 0` -> withdrawal
- `amount == 0` -> balance inquiry

Success response (always HTTP 200):

```json
{
  "status": "success",
  "remaining_balance": 99500.0,
  "iso_request": "0200...",
  "iso_response": "0210..."
}
```

Error response:

```json
{
  "status": "error",
  "detail": "Fondos Insuficientes (DE39: 51)",
  "iso_request": "0200...",
  "iso_response": "0210...",
  "remaining_balance": 1000.0
}
```

DE39 response codes: `00` success, `51` insufficient funds, `55` incorrect PIN.

## Demo cards

All demo cards use PIN `1234`. Initial balances are defined in `init_db()`:

| Card | Name | Brand | Balance |
|------|------|-------|---------|
| 4591061418966700 | Ernesto Lopez | VISA | 100.00 |
| 5496139865798488 | Sebastian Russo | MASTERCARD | 300012.00 |
| 4547184656089376 | Miguel Juarez | VISA | 500200.00 |
| 2641930362375908 | Emilio Parbull | MASTERCARD | 50004.00 |
| 4803178204857473 | Luis Hernandez | VISA | 75000.00 |
| 5241513403894801 | Guillermo Martell | MASTERCARD | 20009.00 |
| 4914070832130801 | Roberto Rios | VISA | 200000.00 |
| 2630415126271802 | Tania Bear | MASTERCARD | 11000.00 |

Balances are stored in `fortibank_vuln.db` and persist across restarts until
`init_db()` re-runs (which drops and recreates the table on every start - so
balances reset when the service restarts).

## Concurrency & data

- All SQLite access is serialized with a module-level `threading.Lock`
  (`db_lock` in `main.py`), so the funds check and the withdrawal are atomic
  even though FastAPI runs the endpoint in a threadpool. This prevents lost
  updates / double-spends under concurrent requests.
- `init_db()` drops and recreates the `cards` table on every start, so demo
  balances reset whenever the service (or container) restarts.

## Deliberate backdoors (lab exercises)

The request model accepts extra fields used by the SASE SUMMIT exercises:

| Field | Vulnerability |
|-------|---------------|
| `?debug=UPDATE ...` | SQL injection (`executescript`) |
| `admin_sql_query` | SQL injection (`executescript`) |
| `debug_cmd` | OS command injection (`os.system`) |
| `template_file` | Path traversal / LFI (file read) |
| `exchange_eval` | Python `eval()` RCE |
| `card_number` / `pin` | SQL injection in the auth query (string concat) |

## Run as a container (Portainer stack)

The backend ships with a Portainer stack file at
[`deploy/backend/fortibank-stack.yml`](../deploy/backend/fortibank-stack.yml) that
runs the prebuilt image `fortibank-backend:latest` (the SSH server and Python
dependencies are baked into the image via the `Dockerfile`).

1. Build the image on the Docker host from this folder (so `main.py` and
   `requirements.txt` are copied in):
   ```bash
   docker build -t fortibank-backend:latest backend/
   ```
2. In Portainer: **Stacks -> Add stack -> Upload** the `fortibank-stack.yml`
   (adjust `ROOT_PASSWORD` and the static `lan_bridge` IP first).
3. Deploy. The container `prod-fortibank_atm` gets IP **192.168.241.11** on the
   external `lan_bridge` network and serves on port **8000**.
4. The ATM reaches it at `http://192.168.241.11:8000/api/withdraw`.

The image entrypoint starts `sshd` and then runs
`uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS}`.

> Note: `init_db()` drops and recreates the `cards` table on every start, so demo
> balances reset when the container restarts.
