# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- Frontend: continuous backend keep-alive. A background thread polls the core
  (`GET /docs`) every 5 s and toggles a header banner that reads
  "Out of Service" / "Fuera de Servicio" while the backend is unreachable; the
  banner clears automatically as soon as connectivity is restored.

### Changed
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
