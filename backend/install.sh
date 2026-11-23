#!/usr/bin/env bash
# Install the FortiBank Core Backend into ./venv
set -e
cd "$(dirname "$0")"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
echo
echo "Done. Start the backend with:"
echo "  ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000"
