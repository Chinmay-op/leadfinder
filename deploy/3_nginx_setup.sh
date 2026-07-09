#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Script 3: Setup Nginx Reverse Proxy
#  Nginx sits in front of Uvicorn on port 80, proxies to :8000
# ═══════════════════════════════════════════════════════════════════

set -e

DOMAIN="leadscribeai.centralindia.cloudapp.azure.com"

echo "══════════════════════════════════════════════════════"
echo "  LeadScribe AI — Nginx Setup"
echo "══════════════════════════════════════════════════════"

# ── 1. Install Nginx ─────────────────────────────────────────────
echo "[1/4] Installing Nginx..."
sudo apt install -y nginx

# ── 2. Create Nginx config ───────────────────────────────────────
echo "[2/4] Creating Nginx site configuration..."

sudo tee /etc/nginx/sites-available/leadfinder > /dev/null << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    # Max upload size (for file uploads if any)
    client_max_body_size 50M;

    # ── API Backend (proxy to Uvicorn) ────────────────────────────
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Required headers for WebSocket / SSE
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE: disable buffering so events stream in real-time
        proxy_buffering off;
        proxy_cache off;

        # Long timeout for SSE connections (10 minutes)
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF

echo "   ✓ Nginx config created"

# ── 3. Enable the site ───────────────────────────────────────────
echo "[3/4] Enabling site and removing default..."

# Remove default site if exists
sudo rm -f /etc/nginx/sites-enabled/default

# Enable our site
sudo ln -sf /etc/nginx/sites-available/leadfinder /etc/nginx/sites-enabled/leadfinder

# ── 4. Test and restart Nginx ─────────────────────────────────────
echo "[4/4] Testing Nginx configuration..."
sudo nginx -t

echo "Restarting Nginx..."
sudo systemctl restart nginx
sudo systemctl enable nginx

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ✓ Nginx configured!"
echo ""
echo "  Your app is now accessible at:"
echo "    http://${DOMAIN}"
echo ""
echo "  Next: Run script 4_ssl_certbot.sh"
echo "══════════════════════════════════════════════════════"
