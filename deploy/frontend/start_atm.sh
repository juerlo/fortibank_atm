#!/bin/bash
# Launcher for the FortiBank ATM frontend (installed on the Orange Pi at the
# repo root). Waits for Xorg, pins HDMI to 1024x600, then runs the app.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Wait for Xorg :2 to be ready (X socket present)
for i in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X2 ] && break
    sleep 1
done

# Pin HDMI output to the panel native 1024x600 (fixes black borders / cropped UI)
export DISPLAY=:2
xrandr --output HDMI-1 --mode 1024x600 2>/dev/null || true

# Run the ATM app using the frontend's own virtualenv
cd "$SCRIPT_DIR/frontend"
exec "$SCRIPT_DIR/frontend/.venv/bin/python" main.py