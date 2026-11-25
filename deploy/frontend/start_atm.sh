#!/bin/bash
# Launcher for the FortiBank ATM frontend (installed on the Orange Pi at the
# repo root). Waits for Xorg, pins HDMI to the configured resolution, then
# runs the app.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Wait for Xorg :2 to be ready (X socket present)
for i in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X2 ] && break
    sleep 1
done

# Pin HDMI output to the configured resolution (default 1024x600).
# The resolution is stored in frontend/settings.txt and changed from the
# hidden Admin menu; a reboot is required to apply.
# SAFETY: verify the mode is actually supported by the connected display
# before applying it — otherwise fall back to 1024x600 and reset the setting
# so the screen never gets stuck blank.
export DISPLAY=:2
RESOLUTION=$(grep '^resolution=' "$SCRIPT_DIR/frontend/settings.txt" 2>/dev/null | cut -d= -f2)
RESOLUTION="${RESOLUTION:-1024x600}"
AVAILABLE=$(xrandr 2>/dev/null | grep -oE '[0-9]+x[0-9]+' || true)
if echo "$AVAILABLE" | grep -qw "$RESOLUTION"; then
    xrandr --output HDMI-1 --mode "$RESOLUTION" 2>/dev/null || true
else
    # Requested resolution not supported — fall back safely.
    RESOLUTION="1024x600"
    xrandr --output HDMI-1 --mode "$RESOLUTION" 2>/dev/null || true
    sed -i 's/^resolution=.*/resolution=1024x600/' "$SCRIPT_DIR/frontend/settings.txt" 2>/dev/null || true
fi

# Run the ATM app using the frontend's own virtualenv
cd "$SCRIPT_DIR/frontend"
exec "$SCRIPT_DIR/frontend/.venv/bin/python" main.py