#!/usr/bin/env bash
# Re-deploy after pushing new code to GitHub.
# Run on EC2:  bash deploy/update.sh
set -euo pipefail

APP_DIR="/home/ubuntu/attendance-system"
cd "$APP_DIR"

git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt

sudo systemctl restart attendance
sudo systemctl --no-pager status attendance | head -15
