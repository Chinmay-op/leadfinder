#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Script 1: Clone Repository & Install Dependencies
#  Run this FIRST on your Azure VM
#  SSH: ssh LeadScribe_AI@leadscribeai.centralindia.cloudapp.azure.com
# ═══════════════════════════════════════════════════════════════════

set -e  # Exit on any error

echo "══════════════════════════════════════════════════════"
echo "  LeadScribe AI — Clone & Setup"
echo "══════════════════════════════════════════════════════"

# ── CONFIGURATION — Fill these in before running ─────────────────
GITHUB_USERNAME="YOUR_GITHUB_USERNAME"
GITHUB_TOKEN="YOUR_GITHUB_TOKEN"
GITHUB_REPO="leadfinder"

# ── 1. System packages ───────────────────────────────────────────
echo ""
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "[2/6] Installing Python 3.11 and build tools..."
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    python3-pip git curl wget build-essential \
    libssl-dev libffi-dev

# ── 2. Clone repo ────────────────────────────────────────────────
APP_DIR="/home/LeadScribe_AI/leadfinder"

if [ -d "$APP_DIR" ]; then
    echo "[3/6] Directory exists. Pulling latest changes..."
    cd "$APP_DIR"
    git fetch --all
    git checkout deployment
    git pull origin deployment
else
    echo "[3/6] Cloning repository..."
    git clone "https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com/${GITHUB_USERNAME}/${GITHUB_REPO}.git" "$APP_DIR"
    cd "$APP_DIR"
    git checkout deployment
fi

echo "   ✓ On branch: $(git branch --show-current)"

# ── 3. Python virtual environment ────────────────────────────────
echo "[4/6] Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# ── 4. Install Python dependencies ───────────────────────────────
echo "[5/6] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install groq openai  # AI providers

# ── 5. Install Playwright browsers ───────────────────────────────
echo "[6/6] Installing Playwright Chromium browser..."
playwright install --with-deps chromium

# ── 6. Create .env file ──────────────────────────────────────────
echo ""
echo "Creating .env file..."
echo "   ⚠  IMPORTANT: Edit the .env file with your actual API keys!"

cat > "$APP_DIR/.env" << 'ENVEOF'
# ── Fill in your actual API keys below ──

# Azure OpenAI keys
AZURE_OPENAI_KEY=YOUR_AZURE_OPENAI_KEY
AZURE_OPENAI_ENDPOINT=YOUR_AZURE_OPENAI_ENDPOINT

# Apify LinkedIn Employees Scraper
APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID=harvestapi/linkedin-company-employees
APIFY_EMPLOYEE_SCRAPER_MODE=Full + email search ($12 per 1k)
APIFY_MAX_EMPLOYEES_PER_COMPANY=100
APIFY_API_KEY=YOUR_APIFY_API_KEY
ENVEOF

echo "   ✓ .env template created — edit it with: nano $APP_DIR/.env"

# ── 7. Create required directories ───────────────────────────────
mkdir -p "$APP_DIR/sessions"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo "  App directory: $APP_DIR"
echo "  Python venv:   $APP_DIR/venv"
echo ""
echo "  ⚠  NEXT STEPS:"
echo "    1. Edit .env:  nano $APP_DIR/.env"
echo "    2. Run script: bash 2_systemd_service.sh"
echo "══════════════════════════════════════════════════════"
