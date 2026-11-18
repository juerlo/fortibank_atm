# HDMI Audio Fix — Orange Pi Zero 3 (Allwinner H618) + Ubuntu 24.04

HDMI audio on the Orange Pi Zero 3 (Allwinner H618) running Ubuntu 24.04 with the
vendor kernel `6.1.31-sun50iw9` fails out of the box. There are **three software /
register-level defects** plus a misconfigured default sound card. This document records
the fix that makes HDMI audio (48 kHz stereo) work on the FortiBank ATM kiosk.

> Target hardware: Orange Pi Zero 3 (H618), HDMI panel `QDtech MPI7003` (1024x600),
> kernel `6.1.31-sun50iw9`, ALSA (no PulseAudio), HDMI audio on **card 2 (`ahubhdmi`)**.

---

## Root causes

1. **Half-speed I2S1 bit clock (AHUB_I2S1_CLKD).**
   When card 2 (`ahubhdmi`, `hw:2,0`) opens a playback stream, `snd_sunxi_ahub` writes
   `0x9` (÷32) into bits [7:4] (BCLKDIV) of register `0x0509730c`. Against the
   49.152 MHz audio-hub clock and 64-BCLK stereo framing, LRCK runs at **24 kHz instead
   of 48 kHz**, doubling the DesignWare HDMI CTS counter (98,000 instead of 49,000) and
   causing HDMI displays to **mute audio**. Setting bits [7:4] to `0x7` (÷16) restores the
   48 kHz frame rate and locks CTS to 49,000 (`68 bf 00`).

2. **Missing `mclk-fs` in the Device Tree.**
   `ahub1_mach` in `sun50i-h618-orangepi-zero3.dtb` sets
   `soundcard-mach,mclk-fs = <0x00>` instead of `<0x100>` (256 × fs).

3. **Wrong default sound card & exclusive hardware lock.**
   Linux defaults to **Card 0** (`audiocodec`, the 13-pin analog header). PulseAudio
   ignores Card 2 (`ahubhdmi`) because it has no mixer controls, and `hw:2,0` only
   accepts a single 48000 Hz stream unless wrapped in ALSA `dmix`.

---

## Component reference

| Component | Identifier / Address | Working value |
|-----------|----------------------|---------------|
| HDMI ALSA device | card 2, device 0 (`ahubhdmi`) | `hw:2,0` (48000 Hz, S16_LE, 2 ch) |
| AHUB base address | `0x05097000` (`5097000.ahub_dam_plat`) | mapped via `/dev/mem` |
| I2S1 clock divider | `0x0509730c` (`AHUB_I2S1_CLKD`) | bits [7:4] = `0x7` (`0x00000173` / `0x00000175`) |
| HDMI N / CTS registers | `6000000.hdmi` (`0x3200–0x3205`) | N = 6144 (`00 18 00`), CTS = 49000 (`68 bf 00` at 49 MHz) |

---

## The four steps

### 1. Patch the Device Tree (`ahub1_mach`)

Install `device-tree-compiler`, back up the stock `.dtb`, set
`soundcard-mach,mclk-fs = <0x100>` (256), and recompile:

```bash
sudo apt-get update && sudo apt-get install -y device-tree-compiler

DTB=$(find /boot/dtb* -name "*zero3*.dtb" | head -n 1)
echo "Patching DTB: $DTB"
sudo cp -n "$DTB" "${DTB}.bak"

dtc -I dtb -O dts -o /tmp/zero3.dts "$DTB"
sed -i '/ahub1_mach {/,/};/ s/soundcard-mach,mclk-fs = <0x00>;/soundcard-mach,mclk-fs = <0x100>;/' /tmp/zero3.dts
sudo dtc -I dts -O dtb -o "$DTB" /tmp/zero3.dts
```

Verify the updated property is present (the `dtc` unit-address warnings during
recompilation are expected):

```bash
dtc -I dtb -O dts "$DTB" 2>/dev/null | grep -A 20 "ahub1_mach {"
```

Expected: `soundcard-mach,mclk-fs = <0x100>;`

### 2. Configure system-wide ALSA dmix routing (`/etc/asound.conf`)

Route all default ALSA playback through `dmix` on `hw:2,0`, locked to 48000 Hz and
S16_LE, so multiple processes can share HDMI audio with automatic resampling:

```bash
sudo tee /etc/asound.conf > /dev/null << 'EOF'
pcm.hdmi_dmix {
    type dmix
    ipc_key 1024
    slave {
        pcm "hw:2,0"
        rate 48000
        channels 2
        format S16_LE
    }
}

pcm.!default {
    type plug
    slave.pcm "hdmi_dmix"
}

ctl.!default {
    type hw
    card 2
}
EOF
```

Verify `/etc/asound.conf` exists and `ctl.!default` points to card 2.

### 3. Install the AHUB_I2S1_CLKD register watcher daemon

`snd_sunxi_ahub` resets `0x0509730c` back to BCLKDIV = `0x9` whenever an audio
stream initializes. A small background Python daemon + systemd service enforces
BCLKDIV = `0x7`:

`/usr/local/bin/fix_h618_hdmi_audio.py`:

```bash
sudo tee /usr/local/bin/fix_h618_hdmi_audio.py > /dev/null << 'EOF'
#!/usr/bin/env python3
import mmap, os, struct, time

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
mm = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05097000)

while True:
    val = struct.unpack("<I", mm[0x30c:0x310])[0]
    if (val & 0xF0) == 0x90:
        mm[0x30c:0x310] = struct.pack("<I", (val & ~0xF0) | 0x70)
    time.sleep(0.05)
EOF
sudo chmod +x /usr/local/bin/fix_h618_hdmi_audio.py
```

`/etc/systemd/system/h618-hdmi-audio-fix.service`:

```bash
sudo tee /etc/systemd/system/h618-hdmi-audio-fix.service > /dev/null << 'EOF'
[Unit]
Description=Fix Allwinner H618 AHUB I2S1 BCLKDIV for 48kHz HDMI Audio
Before=fortibank-app.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/fix_h618_hdmi_audio.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now h618-hdmi-audio-fix.service
```

Verify: `systemctl status h618-hdmi-audio-fix.service` is **active (running)**.

### 4. Force Kivy / SDL2 to use the ALSA default device

By default SDL2/Kivy talks to PulseAudio (which only sees Card 0). Force the app
service to use the ALSA `default` device from Step 2 via a systemd drop-in:

```bash
sudo mkdir -p /etc/systemd/system/fortibank-app.service.d
sudo tee /etc/systemd/system/fortibank-app.service.d/audio.conf > /dev/null << 'EOF'
[Service]
Environment="SDL_AUDIODRIVER=alsa"
Environment="AUDIODEV=default"
EOF

sudo systemctl daemon-reload
```

Optional — for interactive/desktop SDL2 apps launched outside systemd:

```bash
echo 'SDL_AUDIODRIVER=alsa' | sudo tee -a /etc/environment
echo 'AUDIODEV=default'   | sudo tee -a /etc/environment
```

---

## 5. Reboot & end-to-end verification

Power on the HDMI screen **first** (so `sun8i-dw-hdmi` reads the display audio EDID
at boot), then reboot:

```bash
sudo reboot
```

While audio is playing (app, or `speaker-test -c 2 -t wav`), verify the clocks and
register state over SSH:

```bash
sudo python3 -c '
import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
mm = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05097000)
print(f"AHUB_I2S1_CLKD: 0x{struct.unpack(\"<I\", mm[0x30c:0x310])[0]:08x}")
'
sudo grep -E "^(3200|3201|3202|3203|3204|3205):" /sys/kernel/debug/regmap/6000000.hdmi/registers
```

Expected during active playback:

- `AHUB_I2S1_CLKD` ends in `73` or `75` (bits [7:4] = 7).
- `3203: 68`, `3204: bf`, `3205: 00` (CTS = 49,000 on the 1024x600 / 49 MHz panel).

---

## Rollback

Restore the Device Tree backup and disable the daemon:

```bash
DTB=$(find /boot/dtb* -name "*zero3*.dtb" | head -n 1)
sudo cp "${DTB}.bak" "$DTB"
sudo systemctl disable --now h618-hdmi-audio-fix.service
sudo reboot
```
