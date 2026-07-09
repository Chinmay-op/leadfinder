#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Script 2: Create Systemd Service for Auto-Restart
#  This makes your FastAPI backend start on boot and auto-restart
# ═══════════════════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════════════════════"
echo "  LeadScribe AI — Systemd Service Setup"
echo "══════════════════════════════════════════════════════"

APP_DIR="/home/LeadScribe_AI/leadfinder"

# ── 1. Create systemd service file ────────────────────────────────
echo "[1/3] Creating systemd service..."

sudo tee /etc/systemd/system/leadfinder.service > /dev/null << EOF
[Unit]
Description=LeadScribe AI - Lead Finder FastAPI Backend
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=LeadScribe_AI
Group=LeadScribe_AI
WorkingDirectory=${APP_DIR}
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 2

# Auto-restart on failure
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=leadfinder

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "   ✓ Service file created"

# ── 2. Enable and start the service ──────────────────────────────
echo "[2/3] Enabling service for auto-start on boot..."
sudo systemctl daemon-reload
sudo systemctl enable leadfinder.service

echo "[3/3] Starting the service..."
sudo systemctl start leadfinder.service

# ── 3. Show status ───────────────────────────────────────────────
echo ""
sleep 2
sudo systemctl status leadfinder.service --no-pager

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ✓ Systemd service configured!"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status leadfinder    # Check status"
echo "    sudo systemctl restart leadfinder   # Restart"
echo "    sudo systemctl stop leadfinder      # Stop"
echo "    sudo journalctl -u leadfinder -f    # Live logs"
echo ""
echo "  Next: Run script 3_nginx_setup.sh"
echo "══════════════════════════════════════════════════════"
