# Documentation

| Document | Description |
|----------|-------------|
| [Frame adjustment (MARCO)](FRAME_ADJUST.md) | Bezel/safe-area calibration: geometry, per-axis mapping, internals, verification |
| [HDMI audio fix](HDMI_AUDIO_FIX.md) | H618 AHUB I2S1 clock / DTB / ALSA dmix fix for 48 kHz HDMI audio |
| [Lab backend access](BACKEND_ACCESS.md) | SSH/HTTP access, paths and API of the lab backend |
| [Backend install guide](../backend/README.md) | Install/run the FastAPI core on any Linux server |
| [Deployment (Orange Pi)](../deploy/README.md) | systemd units, launcher, ALSA config, audio daemon (kiosk) |
| [Sync / deploy changes](DEPLOYMENT.md) | Push code to the backend (Docker) and frontend (Orange Pi) |
| [Backend service unit](../deploy/backend/fortibank-backend.service) | systemd unit for the FastAPI core |
