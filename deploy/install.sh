#!/bin/bash
set -e

# ============================================================
# Zotero arXiv Daily — Deployment Script
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="zotero-arxiv-daily"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "=== Zotero arXiv Daily — Installer ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Check for required tools
for cmd in uv python3 systemctl; do
  if ! command -v "$cmd" &> /dev/null; then
    echo "ERROR: '$cmd' is not installed. Please install it first."
    exit 1
  fi
done

# Create .env if it doesn't exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Creating .env file..."
  cat > "$PROJECT_DIR/.env" << 'ENVEOF'
# === Required ===
OPENAI_API_KEY=
MODEL_NAME=gpt-4o
OPENAI_API_BASE=https://api.openai.com/v1
LANGUAGE=English

# === arXiv ===
ARXIV_QUERY=cat:cs.AI+cs.CV+cs.LG+cs.CL+cs.RO
MAX_PAPER_NUM=25

# === Zotero (optional, for reranking & export) ===
ZOTERO_ID=
ZOTERO_KEY=
ZOTERO_IGNORE=

# === Email (optional) ===
SMTP_SERVER=
SMTP_PORT=465
SENDER=
SENDER_PASSWORD=
RECEIVER=

# === Server LLM Password (optional) ===
SERVER_LLM_PASSWORD=
ENVEOF
  echo "  Created $PROJECT_DIR/.env — please edit it with your settings."
  echo ""
fi

# Install dependencies
echo "Installing dependencies with uv..."
cd "$PROJECT_DIR"
uv sync
echo "  Dependencies installed."
echo ""

# Install systemd service
echo "Installing systemd service..."
CURRENT_USER="$(whoami)"
sed -e "s|__USER__|$CURRENT_USER|g" \
    -e "s|__WORKDIR__|$PROJECT_DIR|g" \
    "$SCRIPT_DIR/zotero-arxiv-daily.service" | sudo tee "$SERVICE_FILE" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "  Service installed and enabled."
echo ""

# Start the service
echo "Starting $SERVICE_NAME..."
sudo systemctl start "$SERVICE_NAME"
echo ""

# Show status
echo "=== Service Status ==="
sudo systemctl status "$SERVICE_NAME" --no-pager || true
echo ""
echo "=== Done! ==="
echo "  View logs:    journalctl -u $SERVICE_NAME -f"
echo "  Stop:         sudo systemctl stop $SERVICE_NAME"
echo "  Restart:      sudo systemctl restart $SERVICE_NAME"
echo "  Web UI:       http://localhost:8000"
