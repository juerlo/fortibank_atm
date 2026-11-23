#!/bin/bash
# Wait for Xorg :2 to be ready (X socket present)
for i in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X2 ] && break
    sleep 1
done
# Pin HDMI output to the panel native 1024x600 (fixes black borders / cropped UI)
export DISPLAY=:2
xrandr --output HDMI-1 --mode 1024x600 2>/dev/null || true
# Run the ATM app (frontend lives in the frontend/ folder)
cd "$(dirname "$0")/frontend"
exec "$(dirname "$0")/.venv/bin/python" main.py
