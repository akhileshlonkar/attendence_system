#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# One-shot setup script for Ubuntu 22.04 / 24.04 on AWS EC2 (t2.micro OK).
# Run this on the EC2 instance AFTER SSH-ing in as the `ubuntu` user:
#
#   curl -fsSL https://raw.githubusercontent.com/akhileshlonkar/attendence_system/main/deploy/setup_ec2.sh | bash
#
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="https://github.com/akhileshlonkar/attendence_system.git"
APP_DIR="/home/ubuntu/attendance-system"
SERVICE_NAME="attendance"

echo ">> 1/7  Updating apt & installing system packages…"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git nginx

echo ">> 2/7  Cloning repo (or pulling latest)…"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo ">> 3/7  Creating Python virtualenv & installing deps…"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ">> 4/7  Installing systemd service…"
sudo cp deploy/attendance.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}

echo ">> 5/7  Configuring nginx…"
sudo cp deploy/nginx.conf /etc/nginx/sites-available/${SERVICE_NAME}
sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo ">> 6/7  Allowing HTTP through ufw (if enabled)…"
sudo ufw allow 'Nginx Full' 2>/dev/null || true
sudo ufw allow OpenSSH      2>/dev/null || true

echo ">> 7/7  Done! Checking status…"
sudo systemctl --no-pager status ${SERVICE_NAME} | head -20
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "<your-ec2-public-ip>")
echo ""
echo "============================================================"
echo "  Deployed!  Visit:  http://${PUBLIC_IP}/"
echo "  Health:          http://${PUBLIC_IP}/api/health"
echo "============================================================"
