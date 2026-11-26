# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- Backend: each card now has a `default_balance` field — the original/seed
  balance. A new `POST /api/cards/{card_number}/reset` endpoint restores a
  card's balance to its default. The card admin web app shows a "Default"
  column and a "Reset" button per card.
- Backend: the card admin web page now lists the connected frontend(s) —
  hostname + IP (`GET /api/clients`); the frontend sends its real IP and
  hostname via `X-Frontend-IP` / `X-Frontend-Host` headers so they show
  correctly even when the traffic is NAT'd.
- Frontend: the Admin menu now shows this frontend's own IP and hostname
  (e.g. `IP Frontend: orangepizero3 (100.65.4.2)`), read directly from the
  OS network interface (`ip -4 -o addr show`) each time the menu is opened.
- Frontend: Admin menu has a "RESET SALDOS" button that resets all card
  balances to their default values via `POST /api/cards/{card_number}/reset`.
- Frontend: Admin menu has a "SILENCIO" (Mute) button that mutes all sound —
  both app-level (skips every `.play()` call, including the bill-counting
  sound) and hardware-level (`amixer` sets the DAC volume to 0). The setting
  persists across reboots.
- Frontend: Admin menu has a "RESOLUCIÓN" button that cycles between
  resolution presets (1024×600, 1920×1080). The choice is saved to
  `settings.txt` and applied on next reboot (`start_atm.sh` sets HDMI mode,
  Kivy scales the UI proportionally via a `scale_factor`). Only resolutions
  the connected display actually supports are offered (verified via `xrandr`);
  if the saved resolution is unsupported, `start_atm.sh` safely falls back to
  1024×600 so the screen never gets stuck blank.
- Frontend: tap the header clock 5 times to turn the display off immediately
  (any touch wakes it).
- Frontend: the card carousel is now loaded from the backend
  (`GET /api/cards`) and auto-refreshes every 15 s, so cards added, removed or
  edited in the backend appear without restarting the ATM app.
- Backend: card-management REST API (`GET/POST/PUT/DELETE /api/cards`) plus a
  small built-in web app at `/` to add, edit and remove cards. The SQLite
  database is now persistent (seeded only when empty).
- Frontend: continuous backend keep-alive. A background thread polls the core
  (`GET /docs`) every 5 s and toggles a full-screen, interaction-blocking
  overlay that reads "Out of Service" / "Fuera de Servicio" while the backend is
  unreachable; it clears automatically as soon as connectivity is restored.
- `docs/DEPLOYMENT.md`: full procedure for syncing changes to the frontend
  (Orange Pi `192.168.210.8`) and backend (Docker container `192.168.241.11`),
  with verification and troubleshooting.

### Changed
- Frontend: the "Fuera de Servicio" / "Out of Service" overlay now steps aside
  for the screensaver — the screensaver still runs while out of service, and
  the message reappears as soon as the screensaver is dismissed.
- Frontend: the out-of-service overlay keeps the header (FortiBank logo)
  visible and steps aside on the admin screens, so the secret admin menu stays
  reachable while the backend is down.
- Frontend: the out-of-service overlay is now a solid, fully-opaque blue
  (with the FortiBank logo redrawn on top) instead of the translucent red.
- Backend: serialize all SQLite access behind a module-level `threading.Lock`
  (`db_lock`) so the funds check + withdrawal are atomic under FastAPI's
  threadpool (no lost updates / double-spends under concurrent requests).
- Frontend: card brand logos (`visa.png` / `mastercard.png`) are now resolved
  against `FRONTEND_DIR` instead of the current working directory.
- Frontend: the admin **TEST** connectivity check now sends a real `POST`
  (harmless `amount=0` probe) instead of a `GET`, so it exercises the endpoint
  and no longer treats a `405` as "reachable".
- Backend image builds on `python:3.12-slim` (was `3.11`) to match the
  README/CI (Python 3.12).
- `frontend/requirements.txt`: pinned `requests`' transitive deps
  (`certifi`, `charset-normalizer`, `idna`, `urllib3`) for reproducible installs.
- Stripped UTF-8 BOMs from all text files (Markdown, Python, shell, systemd
  units, YAML).

### Fixed
- Frontend: waking from screen-off (DPMS standby) no longer dismisses the
  screensaver in the same tap — the wake tap only wakes the display, so the
  screensaver keeps animating and the next tap dismisses it (fixes the frozen
  screensaver and tapping the hidden screen behind it).
- Frontend: screen-off (5-tap clock and the idle timeout) now uses DPMS standby
  (backlight off, screen dark) and any touch wakes it.
- Corrected the admin menu label "SALTOPANTALLAS" → "SALVAPANTALLAS".
- `backend/install.sh`: the BOM before `#!/usr/bin/env bash` broke direct
  execution; the shebang is now clean.
- Docs: corrected the Portainer stack guide (`backend/README.md`,
  `deploy/README.md`) to match `deploy/backend/fortibank-stack.yml` (prebuilt
  `fortibank-backend:latest` image; removed the stale "no image build" and
  `/opt/prod/...:/app` volume claims).
- Docs: fixed the broken `deploy/frontend/README.md` link in `docs/README.md`.

### Security
- `backend/main.py`: replaced bare `except:` clauses with `except Exception:`
  so `KeyboardInterrupt` / `SystemExit` are no longer swallowed.

## [1.0.0] - 2026-11-22

### Added
- ATM kiosk UI (card carousel, PIN, menu, amount, processing, dispensing, result)
- Secret admin menu (5 taps on the logo, PIN-protected)
- Spanish / English UI with timezone switch (Mexico City / Miami)
- Backend IP configuration with an on-screen numeric keypad and TEST connectivity
- Screensaver with configurable idle timeout and DPMS display-off
- `settings.txt` persistence for all settings
- Packaged `backend/` (FastAPI core) with install script and systemd unit
- Deployment docs for Orange Pi Zero 3 (systemd, HDMI audio fix)
