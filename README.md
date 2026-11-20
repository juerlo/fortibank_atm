# FortiBank ATM

A desktop ATM simulator built with **Python** and **Kivy**. It mimics a full ATM workflow: card insertion, PIN entry, menu navigation, amount selection, transaction processing, bill dispensing animation, and result display. The frontend communicates with a backend API over HTTP.

---

## Features

- **Card selection** â€” Choose from preset VISA and Mastercard cards with animated carousel
- **PIN entry** â€” 4-digit PIN input screen
- **Main menu** â€” Withdrawal or balance inquiry
- **Amount selection** â€” Choose withdrawal amount
- **Processing screen** â€” Simulated transaction communication with backend
- **Bill dispensing animation** â€” Animated bills (500, 200, 100, 50) with sound effects
- **Result screen** â€” Success/decline message with available balance and ISO traffic info
- **Card ejection** â€” Return to start or eject card

---

## Tech Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12.3 | Programming language |
| Kivy | 2.3.2 | GUI framework (desktop app) |
| Kivy-Garden | 0.1.5 | Kivy extensions |
| requests | 2.34.2 | HTTP client for backend API |

---

## Project Structure

```
fortibank_atm/                    # Project root (Pattern A: everything in one folder)
â”œâ”€â”€ .venv/                        # Virtual environment (gitignored â€” do not commit)
â”œâ”€â”€ .gitignore                    # Git ignore rules
â”œâ”€â”€ requirements.txt              # Pinned Python dependencies
â”œâ”€â”€ README.md                     # This file
â”œâ”€â”€ main.py                       # Application entry point and logic
â”œâ”€â”€ fortibank.kv                  # Kivy UI language file (screens and widgets)
â”œâ”€â”€ 50.png                        # Bill image (50 denomination)
â”œâ”€â”€ 100.png                       # Bill image (100 denomination)
â”œâ”€â”€ 200.png                       # Bill image (200 denomination)
â”œâ”€â”€ 500.png                       # Bill image (500 denomination)
â”œâ”€â”€ mastercard.png                # Mastercard brand image
â”œâ”€â”€ visa.png                      # VISA brand image
â”œâ”€â”€ atm_insertion.mp3             # Card insertion sound
â”œâ”€â”€ counting.mp3                  # Bill counting sound
â””â”€â”€ __pycache__/                  # Python bytecode cache (gitignored)
```

---

## Prerequisites

- Python 3.12 (recommended) or Python 3.10+
- `pip` and `venv` module
- A backend API running at `http://127.0.0.1:8000/api/withdraw` (configurable via environment variable â€” see Configuration below)

---

## Installation & Setup

### 1. Clone or open the project folder

```bash
cd /home/orangepi/fortibank_atm
```

### 2. Create and activate the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the application

```bash
python main.py
```

The app opens a fixed-size window (1024Ã—600, non-resizable).

---

## Configuration

The backend API URL is read from the environment variable `ATM_BACKEND_URL`. If not set, it defaults to:

```
http://127.0.0.1:8000/api/withdraw
```

To override it:

```bash
export ATM_BACKEND_URL="http://your-backend-host:8000/api/withdraw"
python main.py
```

---

## Secret Admin Menu

Tap the **"FortiBank ATM"** logo in the top-left of the header **5 times** to open
the secret admin menu. You'll be asked for the admin PIN (default **0000**).

The menu lets you configure:

- **Language** — Español / English (translates the whole UI)
- **Timezone** — Mexico City (`America/Mexico_City`) / Miami (`America/New_York`)
- **Backend IP** — enter the host on an on-screen numeric keypad (0–9 and dot); used to build `http://<ip>:8000/api/withdraw`. **TEST** checks the connection to the backend.
- **Change PIN** — set a new 4-digit admin PIN (entered twice to confirm)
- **Reboot** / **Power Off** — restart or shut down the device

Changes are saved automatically when you close the menu (**CERRAR**) — there is no
separate save button. All settings are persisted to **`settings.txt`** next to
`main.py` and reloaded on startup. `settings.txt` is gitignored because it stores the
admin PIN.

---

## Best Practices Followed

- **Pattern A layout**: Virtual environment (`.venv/`) lives inside the project root so the entire project is self-contained.
- **`.gitignore`**: Excludes `.venv/`, `__pycache__/`, `*.pyc`, `.env`, IDE folders (`.vscode/`, `.idea/`), OS junk, and build artifacts.
- **Pinned dependencies**: `requirements.txt` uses exact versions (`==`) for reproducible installs.
- **Never commit the virtual environment**: `.venv/` is gitignored. Only `requirements.txt` is tracked so others can recreate the environment.

---

## How to Work with This Project

```bash
# Enter the project folder
cd /home/orangepi/fortibank_atm

# Activate the virtual environment
source .venv/bin/activate

# Install new packages (then update requirements.txt)
pip install <package>
pip freeze > requirements.txt

# Run the app
python main.py

# Exit the virtual environment when done
deactivate
```

---

## Notes

- This is the **frontend client** only. It expects a separate backend service to handle withdrawal/balance logic and return JSON responses with fields like `status`, `detail`, `remaining_balance`, `iso_request`, and `iso_response`.
- Bill images (`50.png`, `100.png`, `200.png`, `500.png`) must be present in the project root for the dispensing animation to display correctly.
- Sound files (`atm_insertion.mp3`, `counting.mp3`) are loaded via Kivy's `SoundLoader`.
---

## HDMI Audio Fix (Orange Pi Zero 3 / Allwinner H618)

HDMI audio on the Orange Pi Zero 3 running Ubuntu 24.04 (vendor kernel
`6.1.31-sun50iw9`) does not work out of the box: the AHUB I2S1 bit clock runs at
half speed (24 kHz instead of 48 kHz), the Device Tree is missing
`soundcard-mach,mclk-fs = <0x100>`, and the default ALSA card is the analog codec
(card 0) rather than HDMI (card 2). The full fix — DTB patch, ALSA `dmix`
routing, the `AHUB_I2S1_CLKD` register-watcher daemon, and the SDL2 env drop-in —
is documented in **[docs/HDMI_AUDIO_FIX.md](docs/HDMI_AUDIO_FIX.md)**.

---

## Deployment (Orange Pi Zero 3)

The systemd units, launcher, ALSA config, and the audio-fix daemon used on the
kiosk live in **[deploy/](deploy/)** (see `deploy/README.md` for install steps).
