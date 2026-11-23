# Contributing

Thanks for your interest in FortiBank ATM!

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r frontend/requirements.txt
python frontend/main.py
```

See the [README](README.md) for the full setup, configuration and the admin menu.

## Guidelines

- Keep the app dependency-light (Kivy + requests only).
- UI strings must go through `frontend/settings.py` `TRANSLATIONS` (Spanish + English) - never hardcode text in `main.py`/`fortibank.kv`.
- Settings must go through the `Settings` class and persist to `frontend/settings.txt`.
- Run `python -m py_compile frontend/main.py frontend/settings.py backend/main.py` before opening a PR.
- Keep commits focused and descriptive.

## Pull requests

1. Fork the repo and create a branch.
2. Make your change, with tests/screenshots when UI-related.
3. Verify the app still starts and the admin menu still works (5 taps on the logo).
4. Open a PR describing the change and how to test it.