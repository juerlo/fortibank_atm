#!/bin/sh
set -e

# Runtime config (no secrets baked into the image)
: "${ROOT_PASSWORD:=Fortinet1}"
: "${PORT:=8000}"
: "${WORKERS:=2}"

# Configure + start sshd
echo "root:${ROOT_PASSWORD}" | chpasswd
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
mkdir -p /run/sshd
/usr/sbin/sshd

# Start the API
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}"
