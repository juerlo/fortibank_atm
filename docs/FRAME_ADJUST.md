# Frame adjustment (safe area / MARCO)

The kiosk panel sits inside a physical frame (bezel) that can hide part of the
screen. **MARCO** (FRAME) calibrates the area that is really visible, without
touching the X/HDMI resolution or the app layout:

- the blue "canvas" and the text/buttons/cards always stay together, and
- a margin only cuts **its own** edge - adding a left margin does not create
  extra bands at the top or bottom.

---

## Using it

1. Tap the **FortiBank ATM** logo 5 times, enter the admin PIN (default `0000`).
2. Tap **MARCO**. The frame-adjustment screen opens with 8 nudge buttons:

   | Button | Effect (`frame_nudge`) |
   |--------|------------------------|
   | `Izq −` | adds 10 px to the **left** margin (the visible area's left edge moves right) |
   | `Izq +` | removes 10 px from the left margin |
   | `Der −` / `Der +` | same for the **right** edge |
   | `Arr −` / `Arr +` | same for the **top** edge |
   | `Ab −` / `Ab +` | same for the **bottom** edge |

   `−` always **shrinks** the visible area (adds a margin), `+` always **grows**
   it. Every press is applied live and saved immediately to `settings.txt`.
3. **RESETEAR** sets all four margins back to `0` (full screen).
4. **VOLVER** returns to the admin menu (margins are already saved).

The margins are re-applied on every start, so the UI always boots inside the
calibrated area.

---

## How the geometry works

With window `W x H` and margins `(left, top, right, bottom)`:

```
safe_w   = W - left - right                      visible width
safe_h   = H - top  - bottom                     visible height
sx       = safe_w / 1024                         horizontal design->screen factor
sy       = safe_h / 600                          vertical   design->screen factor
scale    = min(sx, sy)                           text/radii/spacing factor
manager  = (left, bottom) + (safe_w, safe_h)     the ScreenManager
```

The app is authored for a fixed **1024x600** design. The `ScreenManager` is
placed on the visible rectangle and every screen fills it, so:

- **widths** in the KV use `app.sx * N`,
- **heights** use `app.sy * N`,
- **text, radii and spacing** use `app.scale * N` (= the smaller factor, so
  glyphs never stretch unevenly).

Because the mapping is **per axis**, a left margin of 40 px only removes 40 px
of width (`sx = 0.961`, `sy = 1.0`): the UI keeps the full height, it is just
~4 % narrower. There is no letterboxing/centering, hence no phantom top/bottom
band.

| `settings.txt` | visible rectangle | `sx` / `sy` |
|---|---|---|
| all `0` | `1024x600` at `(0,0)` | `1.000` / `1.000` |
| `safe_left=40` | `984x600` at `(40,0)` | `0.961` / `1.000` |
| `safe_top=20` | `1024x580` at `(0,0)` | `1.000` / `0.967` |
| `40/20/10/30` | `974x550` at `(40,30)` | `0.951` / `0.917` |

### Safety clamp

A nudge that would leave less than **480x280** of visible area is ignored (the
previous value stays, nothing is saved), so the UI can never be collapsed into
an unusable strip. See `FortiBankApp.MIN_SAFE_W` / `MIN_SAFE_H`.

---

## Implementation notes (important when touching the UI)

These are the traps behind the frame bugs fixed in this release:

1. **Backgrounds inside a `Screen` must use relative coordinates.**
   A `Screen` is a Kivy `RelativeLayout`: it lays children out at `pos=(0,0)`
   and translates its canvas by `+self.pos`. A background rectangle must
   therefore be `pos=(0, 0)`, `size=self.size` - using `pos=self.pos` renders it
   at *twice* the offset (the blue canvas drifts away from the text as soon as a
   margin is set). See `ScreenBase.on_kv_post`, the `<ScreenBase>` rule and
   `ScreenSaver._build`.

2. **KV expressions must be reactive.**
   Use `app.sx * 40`, `app.sy * 64`, `app.scale * 22`. Do **not** call a helper
   such as `app.s(40)`: Kivy evaluates a kv expression once and only rebinds
   properties, so a method call would freeze the design value forever (text and
   buttons would keep their 1024x600 size after a nudge).

3. **Layouts outside the KV follow the same factors.** The card carousel
   (`ScreenInsert.build_cards`), the card animation transform
   (`ScreenCardAnim.set_scale`), the screensaver decorations
   (`ScreenSaver.apply_scale`), the dispensed bill images and the
   out-of-service overlay (`OOSOverlay.set_safe_rect`) are all re-applied from
   `FortiBankApp._apply_scale_to_screens()`.

4. **Force a relayout after changing the geometry.**
   `_apply_safe_area()` resizes the `ScreenManager`, updates the factors and
   schedules `_force_relayout()`, which re-lays-out the current screen and its
   children. Kivy only re-lays-out screens that are in the widget tree when the
   manager resizes; without this the visible screen can keep a stale (larger)
   layout and spill over the bezel for a frame.

5. **Margins are persisted immediately** (`frame_nudge()` calls
   `Settings.set(..., persist=True)`) and re-applied on start via
   `_apply_safe_area()`, which is also bound to `Window.size`.

---

## Verifying a calibration

The X screen must be the panel's native mode (1024x600 on the lab Orange Pi;
`start_atm.sh` pins it). Then:

```bash
# on the Pi, with the app running
DISPLAY=:2 scrot -o /tmp/frame.png
```

Check on the image that:

- the blue area starts exactly at `safe_left` and ends at the window's right
  edge (same for the top/bottom margins),
- the orange header line and the buttons start/end with the blue area,
- everything outside the margins is pure black (that part is under the bezel).

Numeric check (any machine with Pillow):

```python
from PIL import Image
im = Image.open('frame.png').convert('RGB'); px = im.load()
W, H = im.size
left, top, right, bottom = 40, 0, 0, 0          # your settings.txt values
x0, x1 = left, W - right
y0, y1 = top, H - bottom
outside = [1 for y in range(H) for x in range(W)
           if not (x0 <= x < x1 and y0 <= y < y1) and sum(px[x, y]) > 40]
assert not outside, "content painted outside the safe area"
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Blue canvas shifted relative to the text | A background uses `pos=self.pos` inside a `Screen` (RelativeLayout). Use `(0, 0)`. |
| Text/buttons keep their old size after a nudge | A KV value uses a helper call (`app.s(...)`) instead of a reactive `app.sx` / `app.sy` / `app.scale` expression. |
| Extra band on the opposite axis | The geometry was uniformly scaled and centered; the mapping must be per axis (see the formulas above). |
| Layout spills over the bezel for a moment | `_force_relayout()` was removed/disabled. |
| Nudging does nothing | The clamp (480x280 minimum visible area) refused the change. |
| Margins are lost after a restart | `settings.txt` is not writable or was replaced (it is gitignored and excluded from `make deploy-frontend`). |
