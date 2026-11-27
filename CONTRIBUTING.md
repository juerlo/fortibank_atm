# Contributing

Thanks for your interest in FortiBank ATM!

## Development setup

```bash
python3 -m venv frontend/.venv
frontend/.venv/bin/pip install -r frontend/requirements.txt
frontend/.venv/bin/python frontend/main.py
```

See the [README](README.md) for the full setup, configuration and the admin menu.

## Guidelines

- Keep the app dependency-light (Kivy + requests only).
- UI strings must go through `frontend/settings.py` `TRANSLATIONS` (Spanish + English) - never hardcode text in `main.py`/`fortibank.kv`.
- Settings must go through the `Settings` class and persist to `frontend/settings.txt`.
- **UI scaling (frame/safe area)** - the app is authored for a fixed 1024x600
  design and mapped onto the visible area per axis. In `fortibank.kv`:
  - widths: `app.sx * N`, heights: `app.sy * N`,
  - text, radii, spacing: `app.scale * N` (= `min(sx, sy)`),
  - always use these **property expressions**; never a helper call such as
    `app.s(N)` - a kv expression is evaluated once and only rebinds properties,
    so a method call freezes the design size forever.
- **Screen backgrounds** must be drawn with relative coordinates
  (`pos: 0, 0`, `size: self.size`): a `Screen` is a Kivy `RelativeLayout`, so
  `pos: self.pos` renders the background at twice the offset. Layouts created in
  Python must use `app.sx` / `app.sy` too (cards, card animation, screensaver,
  bills, out-of-service overlay).
- Run `python -m py_compile frontend/main.py frontend/settings.py backend/main.py` before opening a PR.
- Check the UI at a non-zero frame margin (admin menu -> MARCO, e.g. `Izq -` x4):
  nothing may be drawn outside the visible rectangle and the blue canvas must
  stay aligned with the text. See [docs/FRAME_ADJUST.md](docs/FRAME_ADJUST.md).
- Keep commits focused and descriptive.

## Pull requests

1. Fork the repo and create a branch.
2. Make your change, with tests/screenshots when UI-related.
3. Verify the app still starts and the admin menu still works (5 taps on the logo).
4. Open a PR describing the change and how to test it.