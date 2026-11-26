# FortiBank ATM - monorepo task runner
#
# Usage:
#   make install          # create frontend/.venv and backend/venv, install deps
#   make run-frontend     # run the Kivy ATM app
#   make run-backend      # run the FastAPI backend (uvicorn, port 8000)
#   make test             # syntax-check all Python sources
#   make deploy-frontend  # rsync frontend/ to ATM_HOST (see vars below)
#   make deploy-backend   # rsync backend/ to BACKEND_HOST (host-based install)
#   make clean            # remove venvs and caches
#
# For the live lab machines (frontend Orange Pi and the backend Docker
# container on 192.168.241.11) see docs/DEPLOYMENT.md.
# The frontend auto-detects its own IP from the network interface; set
# ATM_HOST to the Orange Pi's current IP.

# ---- Deploy targets (override on the command line) ----
# Frontend (Orange Pi kiosk) - see docs/DEPLOYMENT.md
ATM_HOST      ?= orangepi@192.168.198.2
ATM_DIR       ?= /home/orangepi/fortibank_atm
# Backend (host-based install only; the Docker container on 192.168.241.11 is
# updated with the manual procedure in docs/DEPLOYMENT.md)
BACKEND_HOST  ?= jelopez@192.168.241.6
BACKEND_DIR   ?= /workspace/jelopez/fortibank_atm/backend

PYTHON ?= python3

.PHONY: install run-frontend run-backend test deploy-frontend deploy-backend clean

install:
	$(PYTHON) -m venv frontend/.venv
	frontend/.venv/bin/pip install --upgrade pip
	frontend/.venv/bin/pip install -r frontend/requirements.txt
	cd backend && ./install.sh

run-frontend:
	cd frontend && .venv/bin/python main.py

run-backend:
	cd backend && venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

test:
	$(PYTHON) -m py_compile frontend/main.py frontend/settings.py backend/main.py
	@echo syntax OK

deploy-frontend:
	rsync -av --delete --exclude .venv --exclude __pycache__ --exclude settings.txt frontend/ $(ATM_HOST):$(ATM_DIR)/frontend/
	@echo Frontend deployed to $(ATM_HOST):$(ATM_DIR)/frontend/

deploy-backend:
	rsync -av --delete --exclude venv --exclude __pycache__ --exclude *.db backend/ $(BACKEND_HOST):$(BACKEND_DIR)/
	@echo Backend deployed to $(BACKEND_HOST):$(BACKEND_DIR)/

clean:
	rm -rf frontend/.venv backend/venv
	find . -type d -name __pycache__ -prune -exec rm -rf {} +