# Deployment: systemd units

These unit files are installed on the Orange Pi (not part of the app runtime).

## fortibank-app.service

Runs the Kivy ATM app on the Xorg display `:2`.

### Display fix (1024x600)

The physical HDMI panel is natively **1024x600**, but Xorg defaults to 1920x1080.
Because the Kivy UI is a fixed 1024x600 layout with absolute-sized widgets, running
on a 1920x1080 canvas rendered the app as a small window with large black borders.

`ExecStartPre=-/usr/bin/xrandr --output HDMI-1 --mode 1024x600` pins the output to
the panel's native mode before the app starts, so the UI fills the screen correctly
and the touchscreen coordinates (X 0-1024, Y 0-600) line up with the widgets.

### Install

```bash
sudo cp deploy/fortibank-app.service /etc/systemd/system/fortibank-app.service
sudo systemctl daemon-reload
sudo systemctl restart fortibank-app.service
```

The `-` prefix on the `xrandr` ExecStartPre means a failure is non-fatal (the app
still starts).
