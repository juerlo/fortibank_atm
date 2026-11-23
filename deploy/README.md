# Deployment: systemd units & config

These files are installed on the Orange Pi Zero 3 (Ubuntu Server 24.04) to run the
FortiBank ATM kiosk. They are **not** part of the Python runtime; they configure how
the app, Xorg, HDMI audio, and the GPU are set up on the device.

## Files

| File | Installed at | Purpose |
|------|-------------|---------|
| `fortibank-x.service` | `/etc/systemd/system/` | Xorg on HDMI `:2` (modesetting + glamor) |
| `fortibank-app.service` | `/etc/systemd/system/` | The Kivy ATM app |
| `fortibank-vnc.service` | `/etc/systemd/system/` | x11vnc mirror of `:2` (port 5900) |
| `start_atm.sh` | `/home/orangepi/fortibank_atm/` | Launcher: waits for X, sets 1024x600, runs app |
| `asound.conf` | `/etc/asound.conf` | Default ALSA -> HDMI card 2 via dmix @ 48 kHz |
| `h618-hdmi-audio-fix.service` | `/etc/systemd/system/` | Daemon enforcing AHUB I2S1 BCLKDIV = 0x7 |
| `fix_h618_hdmi_audio.py` | `/usr/local/bin/` | The BCLKDIV watcher daemon |
| `patch-dtb-audio.sh` | (run once) | Sets `mclk-fs = 0x100` in the DTB |

See [`docs/HDMI_AUDIO_FIX.md`](../docs/HDMI_AUDIO_FIX.md) for the full HDMI audio
walkthrough (root causes, register addresses, verification, rollback).

## Fixes applied

### 1. Display (1024x600, no black borders)
The HDMI panel is natively **1024x600**, but Xorg defaulted to 1920x1080. Because the
Kivy UI is a fixed 1024x600 layout with absolute-sized widgets, it rendered as a small
window with large black borders. `start_atm.sh` runs
`xrandr --output HDMI-1 --mode 1024x600` before launching the app.

### 2. Boot auto-start (blank screen)
`fortibank-x.service` used `After=multi-user.target`, while `fortibank-app.service`
and `fortibank-vnc.service` are `WantedBy=multi-user.target` **and** `After=fortibank-x.service`.
That created an ordering cycle (`multi-user.target -> fortibank-app -> fortibank-x ->
multi-user.target`), so systemd deleted the app/vnc start jobs and the screen stayed blank.
Fixed by changing `fortibank-x.service` to `Before=multi-user.target` (X starts first,
then the app), and by making `start_atm.sh` wait for the X socket before launching.

### 3. Hardware acceleration (Mali GPU, not llvmpipe)
The `orangepi` user was not in the `render` group, so the app could not open
`/dev/dri/renderD128` and Mesa fell back to **llvmpipe** (software rendering).
Fixed by `sudo usermod -aG render orangepi` and adding
`SupplementaryGroups=video render` to `fortibank-app.service`.
Verified: `OpenGL renderer: Mali-G31 (Panfrost)`.

### 4. HDMI audio (48 kHz)
HDMI audio on the H618 fails out of the box due to a half-speed I2S1 bit clock, a
missing `mclk-fs` in the DTB, and the wrong default sound card. Fixed by:
- Patching the DTB (`soundcard-mach,mclk-fs = <0x100>`) via `patch-dtb-audio.sh`.
- Routing default ALSA through `dmix` on `hw:2,0` @ 48 kHz (`asound.conf`).
- Running `h618-hdmi-audio-fix.service` to keep BCLKDIV = 0x7 (`fix_h618_hdmi_audio.py`).
- Forcing SDL2/Kivy to the ALSA default via a drop-in
  (`fortibank-app.service.d/audio.conf`: `SDL_AUDIODRIVER=alsa`, `AUDIODEV=default`).
See `docs/HDMI_AUDIO_FIX.md` for the full procedure.

## Install

```bash
# On the Orange Pi
sudo cp deploy/frontend/fortibank-x.service           /etc/systemd/system/
sudo cp deploy/frontend/fortibank-app.service         /etc/systemd/system/
sudo cp deploy/frontend/fortibank-vnc.service         /etc/systemd/system/
sudo cp deploy/frontend/h618-hdmi-audio-fix.service   /etc/systemd/system/
sudo cp deploy/frontend/start_atm.sh                  /home/orangepi/fortibank_atm/
sudo chmod +x                                /home/orangepi/fortibank_atm/start_atm.sh
sudo cp deploy/frontend/asound.conf                   /etc/asound.conf
sudo cp deploy/frontend/fix_h618_hdmi_audio.py        /usr/local/bin/
sudo chmod +x                                /usr/local/bin/fix_h618_hdmi_audio.py

# DTB audio patch (one-time)
sudo apt-get install -y device-tree-compiler
sudo bash deploy/frontend/patch-dtb-audio.sh

# SDL2 audio env for the app service
sudo mkdir -p /etc/systemd/system/fortibank-app.service.d
sudo tee /etc/systemd/system/fortibank-app.service.d/audio.conf > /dev/null << 'EOF'
[Service]
Environment="SDL_AUDIODRIVER=alsa"
Environment="AUDIODEV=default"
EOF

# Groups + units
sudo usermod -aG render orangepi
sudo systemctl daemon-reload
sudo systemctl enable --now fortibank-x fortibank-app fortibank-vnc h618-hdmi-audio-fix
```
