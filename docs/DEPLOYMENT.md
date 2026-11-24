# Deploying / syncing changes

This guide describes how to push code changes from this repository to the two
live lab machines used by the demo:

| Role | Host | SSH access | Code path |
|------|------|------------|-----------|
| **Frontend** (Kivy kiosk) | `192.168.210.8` (`orangepizero3`) | `orangepi` / `orangepi` | `/home/orangepi/fortibank_atm/frontend` |
| **Backend** (FastAPI core) | `192.168.241.11` (container `prod-fortibank_atm`) | `root` / `Fortinet1.` | `/app` |

> These are **lab** credentials and must never be used outside the isolated lab.

## Prerequisites (local machine)

- `sshpass`, `rsync` and `ssh` (used to authenticate non-interactively).
- Network reachability to both hosts.
- The repo checked out locally.

If `sshpass` is unavailable, use an `SSH_ASKPASS` helper instead (see
`docs/BACKEND_ACCESS.md` for an example).

---

## Frontend — Orange Pi (`192.168.210.8`)

The frontend is a Kivy app run by systemd (`fortibank-app.service`) via
`start_atm.sh`, which executes `frontend/.venv/bin/python main.py`.

### 1. Sync the code

```bash
cd /path/to/fortibank_atm

rsync -av --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='settings.txt' \
  -e "sshpass -p orangepi ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  frontend/ orangepi@192.168.210.8:/home/orangepi/fortibank_atm/frontend/
```

`settings.txt` is intentionally **excluded** — it holds the admin PIN and the
device-specific `backend_ip`, and is gitignored.

### 2. Make sure the app can start

The device historically kept a single root virtualenv at
`/home/orangepi/fortibank_atm/.venv` (Python 3.12 + Kivy 2.3.2), while
`start_atm.sh` launches `frontend/.venv/bin/python`. If `frontend/.venv` is
missing, the service crash-loops with:

```
frontend/.venv/bin/python: No such file or directory
```

Fix it by pointing `frontend/.venv` at the root venv:

```bash
ssh orangepi@192.168.210.8 'ln -sfn ../.venv ~/fortibank_atm/frontend/.venv'
```

(If you prefer a real per-app venv, run `make install` on the device instead.)

### 3. Make sure `backend_ip` is correct

`frontend/settings.txt` must point at the backend, e.g.:

```ini
backend_ip=192.168.241.11
```

If it is missing or wrong, the keep-alive will show **"Fuera de Servicio" /
"Out of Service"**. Check it with:

```bash
ssh orangepi@192.168.210.8 'cat ~/fortibank_atm/frontend/settings.txt'
```

### 4. Restart the app

```bash
ssh orangepi@192.168.210.8 \
  'echo orangepi | sudo -S -p "" systemctl restart fortibank-app'
```

### 5. Verify

```bash
ssh orangepi@192.168.210.8 '
  systemctl is-active fortibank-app
  systemctl is-enabled fortibank-app
  ps -ef | grep "[m]ain.py"
  echo orangepi | sudo -S -p "" journalctl -u fortibank-app -n 30 --no-pager
'
```

The log should end with Kivy's `Start application main loop` and no traceback.

---

## Backend — Docker container (`192.168.241.11`)

The backend runs as the container `prod-fortibank_atm` (from
`deploy/backend/fortibank-stack.yml`). Uvicorn is **PID 1** inside the container
(`--workers 2`, no `--reload`) and the code lives at `/app`.

### Option A — update the running container (fastest)

**1. Upload `main.py` and validate it inside the container:**

```bash
cd /path/to/fortibank_atm

cat backend/main.py | \
  sshpass -p 'Fortinet1.' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.241.11 '
    cp /app/main.py /app/main.py.bak.$(date +%s) 2>/dev/null
    cat > /app/main.py.new &&
    python3 -m py_compile /app/main.py.new &&
    mv /app/main.py.new /app/main.py &&
    echo REPLACED_OK
  '
```

Also upload the card-management web asset if it changed (it is served at `/`):

```bash
cat backend/cards_web.html | \
  sshpass -p 'Fortinet1.' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.241.11 'cat > /app/cards_web.html && echo HTML_OK'
```

If `requirements.txt` changed, upload it too and reinstall:

```bash
cat backend/requirements.txt | \
  sshpass -p 'Fortinet1.' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.241.11 'cat > /app/requirements.txt && pip install --no-cache-dir -r /app/requirements.txt'
```

**2. Restart uvicorn.** Because uvicorn is PID 1, ask it to terminate and let
Docker's `restart: unless-stopped` policy bring the container back:

```bash
sshpass -p 'Fortinet1.' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.241.11 \
  'nohup sh -c "sleep 1; kill -TERM 1" >/dev/null 2>&1 & echo RESTART_SCHEDULED'

sleep 15   # give Docker time to restart the container
```

**3. Verify:**

```bash
sshpass -p 'Fortinet1.' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.241.11 '
    echo -n "db_lock: "; grep -c "db_lock = threading.Lock" /app/main.py
    ps -ef | grep "[u]vicorn main:app"
    python3 -c "import urllib.request;print(\"GET /docs ->\", urllib.request.urlopen(\"http://127.0.0.1:8000/docs\", timeout=5).status)"
  '
```

> If the container does not come back (e.g. its restart policy was changed),
> start it from the Docker host: `docker start prod-fortibank_atm`.

### Option B — rebuild the image (from the Docker host)

Use this when the change must be baked into the image (e.g. new OS packages):

```bash
# on the Docker host, from the repo's backend/ directory
docker build -t fortibank-backend:latest backend/
# then recreate the container from the Portainer stack
# (Stacks -> prod-fortibank_atm -> Redeploy)
```

### Verify the backend API

```bash
python3 - <<'PY'
import requests
B = "http://192.168.241.11:8000"
print("GET /docs ->", requests.get(B + "/docs", timeout=6).status_code)
r = requests.post(B + "/api/withdraw",
                  json={"card_number": "5496139865798488", "pin": "1234", "amount": 0},
                  timeout=6)
print("balance inquiry ->", r.status_code, r.json().get("status"), r.json().get("remaining_balance"))
PY
```

---

## End-to-end check (frontend → backend)

Run this **on the frontend** to confirm the kiosk can actually reach the core:

```bash
ssh orangepi@192.168.210.8 '~/fortibank_atm/frontend/.venv/bin/python - <<PY
import requests
print("frontend->backend /docs ->", requests.get("http://192.168.241.11:8000/docs", timeout=5).status_code)
PY'
```

Both `GET /docs` returning `200` and a successful balance inquiry confirm the
link is healthy; the keep-alive overlay stays hidden while this succeeds.

---

## Makefile shortcuts

```bash
make deploy-frontend   # rsync frontend/ to ATM_HOST (default orangepi@192.168.210.8)
make deploy-backend    # rsync backend/ to BACKEND_HOST (host-based install only)
```

- `deploy-frontend` maps directly to step 1 above (override with
  `ATM_HOST=... ATM_DIR=...`).
- `deploy-backend` targets a **host-based** (non-container) install. The
  container on `192.168.241.11` uses the manual **Option A** procedure above,
  because uvicorn runs as PID 1 and must be restarted.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `frontend/.venv/bin/python: No such file or directory` (service crash-loop) | `frontend/.venv` missing → `ln -sfn ../.venv ~/fortibank_atm/frontend/.venv` |
| App shows **"Fuera de Servicio" / "Out of Service"** | `frontend/settings.txt` `backend_ip` wrong/unset, or backend unreachable → set `backend_ip=192.168.241.11` and confirm `GET :8000/docs` returns 200 |
| rsync/deployment removed `settings.txt` | It is gitignored and excluded from rsync; recreate it if needed |
| Container didn't restart after `kill -TERM 1` | Start it on the Docker host: `docker start prod-fortibank_atm` |
| `Permission denied` on SSH | Wrong user/password. Backend container uses `root` / `Fortinet1.`; frontend uses `orangepi` / `orangepi` |

## Credentials (lab only)

| Host | User | Password |
|------|------|----------|
| `192.168.210.8` (frontend) | `orangepi` | `orangepi` |
| `192.168.241.11` (backend container) | `root` | `Fortinet1.` |
