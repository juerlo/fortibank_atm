# FortiBank ATM

A desktop ATM simulator built with **Python** and **Kivy**. It mimics a full ATM workflow: card insertion, PIN entry, menu navigation, amount selection, transaction processing, bill dispensing animation, and result display. The frontend communicates with a backend API over HTTP.

---

## Features

- **Card selection** — Choose from preset VISA and Mastercard cards with animated carousel
- **PIN entry** — 4-digit PIN input screen
- **Main menu** — Withdrawal or balance inquiry
- **Amount selection** — Choose withdrawal amount
- **Processing screen** — Simulated transaction communication with backend
- **Bill dispensing animation** — Animated bills (500, 200, 100, 50) with sound effects
- **Result screen** — Success/decline message with available balance and ISO traffic info
- **Card ejection** — Return to start or eject card

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
├── .venv/                        # Virtual environment (gitignored — do not commit)
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Pinned Python dependencies
├── README.md                     # This file
├── main.py                       # Application entry point and logic
├── fortibank.kv                  # Kivy UI language file (screens and widgets)
├── 50.png                        # Bill image (50 denomination)
├── 100.png                       # Bill image (100 denomination)
├── 200.png                       # Bill image (200 denomination)
├── 500.png                       # Bill image (500 denomination)
├── mastercard.png                # Mastercard brand image
├── visa.png                      # VISA brand image
├── atm_insertion.mp3             # Card insertion sound
├── counting.mp3                  # Bill counting sound
└── __pycache__/                  # Python bytecode cache (gitignored)
```

---

## Prerequisites

- Python 3.12 (recommended) or Python 3.10+
- `pip` and `venv` module
- A backend API running at `http://127.0.0.1:8000/api/withdraw` (configurable via environment variable — see Configuration below)

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

The app opens a fixed-size window (1024×600, non-resizable).

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