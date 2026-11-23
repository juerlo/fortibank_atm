# Backend access (FortiBank Core Backend)

Lab backend used by the ATM kiosk. **Lab / SASE SUMMIT exercise only** - these
credentials are intentionally weak; do not use them outside the lab.

## Connection

| Item | Value |
|------|-------|
| Host | `192.168.27.35` |
| SSH user | `fortilab` |
| SSH password | `Fortinet1.` |
| HTTP port | `8000` |
| API docs (Swagger) | http://192.168.27.35:8000/docs |
| OpenAPI spec | http://192.168.27.35:8000/openapi.json |

Interactive login (from the Orange Pi or any host that can reach 192.168.27.35):

```bash
ssh fortilab@192.168.27.35
# password: Fortinet1.
```

Non-interactive (from the Pi, via SSH_ASKPASS so no TTY is required):

```bash
printf '#!/bin/sh\necho Fortinet1.\n' > /tmp/askpass.sh && chmod +x /tmp/askpass.sh
SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force setsid -w \
  ssh -o StrictHostKeyChecking=no fortilab@192.168.27.35 'echo OK'
```

## Layout

| Path | Notes |
|------|-------|
| `/home/fortilab/fortibank-backend/main.py` | FastAPI app (**root-owned** - use `sudo` to edit) |
| `/home/fortilab/fortibank-backend/main2.py` | older/simpler variant (no SQLite) |
| `/home/fortilab/fortibank-backend/fortibank_vuln.db` | SQLite database (cards, balances) |
| `/home/fortilab/fortibank-backend/venv/` | virtualenv |
| `/etc/systemd/system/fortibank-backend.service` | systemd unit |

Service: `fortibank-backend.service` runs `uvicorn main:app --host 0.0.0.0 --port 8000`
as user `fortilab`, group `www-data`, from `/home/fortilab/fortibank-backend`.

```bash
sudo systemctl status fortibank-backend
sudo systemctl restart fortibank-backend
journalctl -u fortibank-backend -n 50 --no-pager
```

## API

`POST /api/withdraw`

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

Response:

```json
{
  "status": "success",
  "remaining_balance": 99500.0,
  "iso_request": "0200...",
  "iso_response": "0210..."
}
```

On errors `status` is `"error"` and a `detail` field is included (HTTP is still 200
so the ISO frames reach the frontend).

> The extra fields (`debug_cmd`, `template_file`, `exchange_eval`,
> `admin_sql_query`) are deliberate backdoors for the SASE SUMMIT exercise; the ATM
> frontend does not send them.
