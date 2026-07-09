#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Script 4: Setup Certbot SSL (Let's Encrypt)
#  Adds HTTPS to your domain with auto-renewal
# ═══════════════════════════════════════════════════════════════════

set -e

DOMAIN="leadscribeai.centralindia.cloudapp.azure.com"
EMAIL="chinmaywadettiwar211@gmail.com"

echo "══════════════════════════════════════════════════════"
echo "  LeadScribe AI — SSL Certificate Setup"
echo "══════════════════════════════════════════════════════"

# ── 1. Install Certbot ───────────────────────────────────────────
echo "[1/3] Installing Certbot..."
sudo apt install -y certbot python3-certbot-nginx

# ── 2. Obtain SSL certificate ────────────────────────────────────
echo "[2/3] Obtaining SSL certificate for ${DOMAIN}..."
echo "   This will automatically modify your Nginx config for HTTPS."
echo ""

sudo certbot --nginx \
    -d "${DOMAIN}" \
    --email "${EMAIL}" \
    --agree-tos \
    --non-interactive \
    --redirect

# ── 3. Verify auto-renewal ───────────────────────────────────────
echo "[3/3] Testing auto-renewal..."
sudo certbot renew --dry-run

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ✓ SSL configured!"
echo ""
echo "  Your app is now accessible at:"
echo "    https://${DOMAIN}"
echo ""
echo "  SSL auto-renews via systemd timer."
echo "  Check timer: sudo systemctl status certbot.timer"
echo "══════════════════════════════════════════════════════"
