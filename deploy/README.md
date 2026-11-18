# Deployment: systemd units & config

These files are installed on the Orange Pi Zero 3 (Ubuntu Server 24.04) to run the
FortiBank ATM kiosk. They are **not** part of the Python runtime; they configure
how the app, Xorg, and audio are launched on the device.

## Files

| File | Installed at | Purpose |
|------|-------------|---------|
| `fortibank-x.service` | `/etc/systemd/system/` | Xorg on HDMI `:2` (modesetting + glamor) |
| `fortibank-app.service` | `/etc/systemd/system/` | The Kivy ATM app |
| `fortibank-vnc.service` | `/etc/systemd/system/` | x11vnc mirror of `:2` (port 5900) |
| `start_atm.sh` | `/home/orangepi/fortibank_atm/` | Launcher: waits for X, sets 1024x600, runs app |
| `asound.conf` | `/etc/asound.conf` | Default audio -> HDMI (card 2), 48 kHz |

## Fixes applied

### 1. Display (1024x600, no black borders)
The HDMI panel is natively **1024x600**, but Xorg defaulted to 1920x1080. Because the
Kivy UI is a fixed 1024x600 layout with absolute-sized widgets, it rendered as a
small window with large black borders. `start_atm.sh` runs
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

### 4. Audio (48 kHz)
The app WAV/MP3 assets are 44.1 kHz; HDMI audio paths often only lock to 48 kHz.
`/etc/asound.conf` routes the default PCM to HDMI (card 2) through a `plug` at 48 kHz.
Note: HDMI audio on the current QDtech panel still does not produce sound on Ubuntu
(the panel EDID audio block is malformed and the dw-hdmi path differs from Windows);
this config is correct and ready for a compliant sink / the analog or USB output.

## Install

```bash
# On the Orange Pi
sudo cp deploy/fortibank-x.service   /etc/systemd/system/
sudo cp deploy/fortibank-app.service /etc/systemd/system/
sudo cp deploy/fortibank-vnc.service /etc/systemd/system/
sudo cp deploy/start_atm.sh          /home/orangepi/fortibank_atm/
sudo chmod +x                        /home/orangepi/fortibank_atm/start_atm.sh
sudo cp deploy/asound.conf           /etc/asound.conf
sudo usermod -aG render orangepi
sudo systemctl daemon-reload
sudo systemctl enable --now fortibank-x fortibank-app fortibank-vnc
```
