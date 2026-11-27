# FortiBank ATM

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Kivy](https://img.shields.io/badge/Kivy-2.3.2-5b8db8)](https://kivy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Orange%20Pi%20Zero%203-orange)](https://www.orangepi.org/)

A desktop ATM simulator built with **Python** and **Kivy**. It mimics a full ATM
workflow: card insertion, PIN entry, menu navigation, amount selection, transaction
processing, bill dispensing animation and result display. The frontend talks to a
separate backend API over HTTP and includes a PIN-protected admin menu for
on-device configuration.

---

## Features

- **Card selection** - animated carousel of preset VISA / Mastercard cards
- **PIN entry** - 4-digit PIN screen
- **Main menu** - cash withdrawal or balance inquiry
- **Amount selection** - choose the withdrawal amount
- **Processing screen** - simulated transaction over the Fortinet ZTNA/SASE network
- **Bill dispensing animation** - animated 500/200/100/50 bills with sound
- **Result screen** - success/decline, available balance and ISO 8583 traffic
- **Card ejection** - return to start or eject the card
- **Secret admin menu** - language, timezone, backend IP, PIN, frame (bezel)
  calibration, resolution, mute, balance reset, reboot / power-off
- **Frame calibration (MARCO)** - nudge each bezel edge independently; the UI
  (canvas *and* text) is mapped onto the visible area per axis, so a margin
  only cuts its own edge (no phantom bands) - see
  [docs/FRAME_ADJUST.md](docs/FRAME_ADJUST.md)
- **Bilingual UI** - Spanish / English
- **Screensaver & display-off** - configurable burn-in protection
- **Touch-first** - on-screen numeric keypads (PIN and backend IP)
- **Backend keep-alive** - full-screen "Out of Service" / "Fuera de
  Servicio" overlay (blocks the ATM) while the core is unreachable, auto-cleared
  on reconnect
- **Backend-driven cards** - the card carousel is loaded from the backend
  (`GET /api/cards`) and auto-refreshes when cards are added/removed/edited
- **Card admin web app** - `http://<backend>:8000/` to add, edit and delete
  cards

---

## Tech Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12.3 | Programming language |
| Kivy | 2.3.2 | GUI framework |
| Kivy-Garden | 0.1.5 | Kivy extensions |
| requests | 2.34.2 | HTTP client for the backend API |

---

## Project Structure

The repository is a **monorepo** that keeps the frontend and backend code in the
same top-level folder:

```
fortibank_atm/
|-- frontend/                # ATM kiosk app (Kivy) - its own .venv
|   |-- main.py              #   App entry point, screens and business logic
|   |-- fortibank.kv         #   Kivy UI (screens, widgets, styles)
|   |-- settings.py          #   Settings persistence + ES/EN translations
|   |-- settings.txt         #   Runtime settings (gitignored - holds the admin PIN)
|   |-- requirements.txt     #   Pinned Python dependencies
|   |-- 50.png 100.png 200.png 500.png   # Bill images
|   |-- visa.png mastercard.png          # Card brand images
|   `-- atm_insertion.mp3 counting.mp3 beep.wav   # Sounds
|-- backend/                 # FortiBank Core Backend (FastAPI) - its own venv
|   |-- main.py
|   |-- requirements.txt
|   |-- install.sh
|   `-- README.md
|-- deploy/                  # Per-app deployment (systemd, ALSA/audio fix)
|   |-- frontend/            #   Orange Pi kiosk units + launcher + audio fix
|   `-- backend/             #   FastAPI systemd unit
|-- docs/                    # HDMI audio fix + lab backend access notes
|-- start_atm.sh             # Launcher (waits for X, sets 1024x600, runs frontend)
|-- Makefile                 # Task runner: install / run / test / deploy / clean
|-- README.md                # This file
`-- .venv/                   # (legacy root venv, gitignored)
```

The frontend lives in `frontend/`; the backend lives in `backend/`; deployment
artifacts live in `deploy/frontend/` and `deploy/backend/`. Everything is
version-controlled from the repository root, so a single clone contains all the
code.

## Common tasks (Makefile)

| Command | Description |
|---------|-------------|
| `make install` | Create `frontend/.venv` + `backend/venv` and install deps |
| `make run-frontend` | Run the Kivy ATM app |
| `make run-backend` | Run the FastAPI backend (uvicorn, port 8000) |
| `make test` | Syntax-check all Python sources |
| `make deploy-frontend` | rsync `frontend/` to `ATM_HOST` (default `orangepi@100.65.4.2`) |
| `make deploy-backend` | rsync `backend/` to `BACKEND_HOST` (default `jelopez@192.168.241.6`) |
| `make clean` | Remove venvs and `__pycache__` |

Override the deploy targets on the command line, e.g.
`make deploy-frontend ATM_HOST=user@host ATM_DIR=/opt/fortibank_atm`.

---

## Prerequisites

- Python 3.12 (recommended) or 3.10+
- `pip` and `venv`
- A backend API (see [backend/](backend/)) reachable at
  `http://<backend_ip>:8000/api/withdraw`

---

## Installation & Setup

There are **two apps** in this monorepo, each with its own virtual environment:
`frontend/` (the Kivy ATM) and `backend/` (the FastAPI core).

```bash
cd /home/orangepi/fortibank_atm

# Create both virtualenvs and install dependencies
make install
# (or manually:)
#   python3 -m venv frontend/.venv && frontend/.venv/bin/pip install -r frontend/requirements.txt
#   cd backend && ./install.sh
```

Run the frontend (ATM app):

```bash
make run-frontend
# or: ./start_atm.sh          # waits for X, sets 1024x600, runs the app
# or: cd frontend && .venv/bin/python main.py
```

Run the backend (FastAPI):

```bash
make run-backend
# or: cd backend && venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend lives in [`backend/`](backend/) - see its README for install/run steps.
Both the frontend and backend code live in this single repository.

The app opens a fixed-size 1024x600 window.

---

## Configuration

Settings live in **`frontend/settings.txt`** next to `main.py` (created
automatically):

```ini
language=es
timezone=America/Mexico_City
backend_ip=192.168.241.11
admin_pin=0000
saver_timeout=120
screenoff_timeout=0
muted=0
resolution=1024x600
safe_left=0
safe_top=0
safe_right=0
safe_bottom=0
```

- `language` - `es` or `en`
- `timezone` - `America/Mexico_City` or `America/New_York`
- `backend_ip` - host used to build `http://<ip>:8000/api/withdraw`
- `admin_pin` - 4-digit PIN for the secret menu
- `saver_timeout` - seconds before the screensaver (0 = off)
- `screenoff_timeout` - seconds before the display blanks (0 = off)
- `muted` - `1` mutes all sound (app-level + hardware DAC), `0` = sound on
- `resolution` - preset applied on next boot (`1024x600` or `1920x1080`)
- `safe_left` / `safe_top` / `safe_right` / `safe_bottom` - frame (bezel)
  margins in pixels; they define the visible area. Each margin only cuts its own
  edge. See [docs/FRAME_ADJUST.md](docs/FRAME_ADJUST.md).

All of them are normally edited from the admin menu; the file is written on
every change and read on start.

The backend URL can also be overridden with the `ATM_BACKEND_URL` environment
variable, which takes precedence over `backend_ip`.

---

## Secret Admin Menu

Tap the **"FortiBank ATM"** logo in the top-left of the header **5 times** to open
the secret admin menu. You will be asked for the admin PIN (default **0000**).

The menu lets you configure:

- **Language** - Espanol / English (translates the whole UI)
- **Timezone** - Mexico City (`America/Mexico_City`) / Miami (`America/New_York`)
- **Backend IP** - on-screen numeric keypad (0-9 and dot); used to build
  `http://<ip>:8000/api/withdraw`. **TEST** checks connectivity to the backend.
  The line under it shows this frontend's own IP/hostname.
- **Change PIN** - set a new 4-digit admin PIN (entered twice to confirm)
- **Screensaver** - idle timeout and display-off delay (see below)
- **Mute** - `SILENCIO` toggles all sound (app + hardware)
- **Reset balances** - `RESET SALDOS` restores every card to its
  `default_balance` (via `POST /api/cards/{card_number}/reset`)
- **Resolution** - `RESOLUCIÓN` cycles through the presets the connected display
  supports; applied on next boot
- **Frame** - `MARCO` opens the bezel calibration screen (see below)
- **Reboot** / **Power Off** - restart or shut down the device

Changes are saved automatically when you close the menu (**CERRAR**) - there is no
separate save button. All settings are persisted to **`settings.txt`** and reloaded
on startup. `settings.txt` is gitignored because it stores the admin PIN.

---

## Frame adjustment (MARCO)

The physical frame of the panel can cover part of the screen. **MARCO** lets you
calibrate the visible area in 10 px steps per edge (`Izq`/`Der`/`Arr`/`Ab`,
`−` adds a margin, `+` removes it; **RESETEAR** goes back to full screen).

The UI is **mapped onto the visible rectangle per axis**: adding a left margin
only removes width (the UI keeps the full height), so there are no extra bands
on the other edges. The blue canvas and the text always move together, and text
stays proportional (`scale = min(sx, sy)`). A nudge that would leave less than
480x280 of visible area is ignored.

Full details (geometry, internals, how to verify a calibration, troubleshooting):
**[docs/FRAME_ADJUST.md](docs/FRAME_ADJUST.md)**.

---

## Screensaver & Display Timeouts

Both are configurable in the admin menu under **SALVAPANTALLAS / SCREENSAVER**
(defaults: screensaver after **120 s**, screen-off **disabled**):

- **Screensaver** - after the configured idle time a screensaver is shown to
  protect the panel from burn-in:
  - A bouncing "FortiBank ATM" logo (DVD-style) drifting around the screen
  - Floating banknotes (50/100/200/500) drifting upward
  - A pulsing "Touch the screen to continue" hint
  (the clock was removed because a fixed element would itself burn in)
- **Screen off** - after the configured idle time the display is put into DPMS
  standby (backlight off, so the screen goes dark); any touch wakes it.
- **Manual screen off** - tap the **clock** (top-right of the header) **5 times**
  to blank the display immediately; any touch wakes it.

Any tap dismisses the screensaver and returns to the previous screen (the tap is
consumed so it does not activate anything underneath). Both are skipped on the
processing/dispensing/card-animation screens so they never interrupt a transaction.
Screen-off behaves exactly like tapping the clock 5 times: the display is put
into DPMS standby (backlight off) and any touch wakes it. It can also trigger
while the screensaver is running (the idle timer is measured from the last touch).
Values are stored in `settings.txt` (`saver_timeout`, `screenoff_timeout`, seconds).

---

## Backend

The ATM talks to the FortiBank Core Backend at `http://<backend_ip>:8000/api/withdraw`.
The backend IP is configurable from the admin menu.

A card-management web app is served at `http://<backend_ip>:8000/` — use it to
add, edit or delete cards (the ATM picks up changes automatically within ~15 s).
See [backend/README.md](backend/README.md#card-management-api--web-app).

- Backend source & install guide: [backend/](backend/) (`backend/README.md`)
- Lab backend access (SSH, paths, API): [docs/BACKEND_ACCESS.md](docs/BACKEND_ACCESS.md)

---

## Deployment (Orange Pi Zero 3)

The systemd units, launcher, ALSA config and the audio-fix daemon used on the
kiosk live in **[deploy/](deploy/)** (see `deploy/README.md` for install steps).

To push code changes to the live lab machines (frontend Orange Pi and backend
Docker container), see **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## HDMI Audio Fix (Orange Pi Zero 3 / Allwinner H618)

HDMI audio on the Orange Pi Zero 3 running Ubuntu 24.04 (vendor kernel
`6.1.31-sun50iw9`) does not work out of the box: the AHUB I2S1 bit clock runs at
half speed (24 kHz instead of 48 kHz), the Device Tree is missing
`soundcard-mach,mclk-fs = <0x100>`, and the default ALSA card is the analog codec
(card 0) rather than HDMI (card 2). The full fix - DTB patch, ALSA `dmix`
routing, the `AHUB_I2S1_CLKD` register-watcher daemon and the SDL2 env drop-in -
is documented in **[docs/HDMI_AUDIO_FIX.md](docs/HDMI_AUDIO_FIX.md)**.

---

## Contributing / License / Security

- [CONTRIBUTING.md](CONTRIBUTING.md) - development setup and guidelines
- [SECURITY.md](SECURITY.md) - how to report vulnerabilities
- [CHANGELOG.md](CHANGELOG.md) - release notes
- [LICENSE](LICENSE) - MIT license

---

## Notes

- Bill images (`50.png`, `100.png`, `200.png`, `500.png`) must be present in the
  project root for the dispensing animation.
- Sounds (`atm_insertion.mp3`, `counting.mp3`, `beep.wav`) are loaded via Kivy's
  `SoundLoader`.
- The backend returns JSON with `status`, `detail`, `remaining_balance`,
  `iso_request` and `iso_response`; HTTP is always 200 so the ISO frames reach the
  frontend.
