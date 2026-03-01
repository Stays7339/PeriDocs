#!/usr/bin/env bash
# ==========================================================
# PeriDocs Full Setup Script (Cross-Platform)
# Last Updated: 2026-03-01
# Author: PeriDocs Team
# ==========================================================
# This script performs:
# 1) SSH key setup for GitHub
# 2) Non-root folder ownership
# 3) .env creation with Fernet key
# 4) Repository pull into /<variable>/peridocs/app
# 5) Virtual environment creation and dependency installation
# 6) Deterministic RoBERTa model setup
# 7) Optional daemon/service setup
# ==========================================================

set -euo pipefail

# ----------------------------------------------------------
# Utility functions
# ----------------------------------------------------------

function prompt_continue() {
    local message="$1"
    read -rp "$message [y/n]: " response
    case "$response" in
        y|Y|yes|YES) return 0 ;;
        *) echo "Aborted."; exit 1 ;;
    esac
}

function ensure_dir_ownership() {
    local dir="$1"
    local user="$2"
    local group="$3"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
    fi
    chown -R "$user":"$group" "$dir"
}

function generate_fernet_key() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# ----------------------------------------------------------
# Step 0: Detect platform and variables
# ----------------------------------------------------------
OS_TYPE=$(uname | tr '[:upper:]' '[:lower:]')
DEFAULT_ROOT_DIR="$HOME/peridocs"
PERIDOCS_DIR="${PERIDOCS_DIR:-$DEFAULT_ROOT_DIR}"
APP_DIR="$PERIDOCS_DIR/app"
SSH_DIR="$PERIDOCS_DIR/.ssh"
ENV_FILE="$APP_DIR/.env"

RUNTIME_USER="${USER:-$(whoami)}"
RUNTIME_GROUP="${RUNTIME_USER}"

echo "Detected OS: $OS_TYPE"
echo "Using PeriDocs path: $PERIDOCS_DIR"
echo "App path: $APP_DIR"
echo "SSH path: $SSH_DIR"
echo "Runtime user: $RUNTIME_USER"
echo "Runtime group: $RUNTIME_GROUP"

# ----------------------------------------------------------
# Step 1: SSH keys + non-root permissions
# ----------------------------------------------------------
echo -e "\nStep 1 — SSH Key Setup and Non-Root Permissions"

if [[ -f "$SSH_DIR/id_ed25519.pub" ]]; then
    echo "SSH key already exists at $SSH_DIR/id_ed25519.pub"
    prompt_continue "Do you want to generate a new SSH key?"
fi

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

if [[ ! -f "$SSH_DIR/id_ed25519" ]]; then
    ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519" -N "" -C "peridocs-runtime-user@$(hostname)"
fi

chmod 600 "$SSH_DIR/id_ed25519"
chmod 644 "$SSH_DIR/id_ed25519.pub"
chown -R "$RUNTIME_USER":"$RUNTIME_GROUP" "$PERIDOCS_DIR"

echo "Your public SSH key for GitHub is:"
cat "$SSH_DIR/id_ed25519.pub"
echo
read -rp "Paste the public key into GitHub and type 'continue' to proceed: " confirm
if [[ "$confirm" != "continue" ]]; then
    echo "Setup aborted. Paste the SSH public key into GitHub and rerun the script."
    exit 1
fi

# ----------------------------------------------------------
# Step 2: .env creation with Fernet key
# ----------------------------------------------------------
echo -e "\nStep 2 — .env Setup"

mkdir -p "$APP_DIR"
if [[ -f "$ENV_FILE" ]]; then
    echo ".env file already exists."
    prompt_continue "Do you want to overwrite .env with a new Fernet key?"
fi

echo "Do you want to generate a new Fernet key? (y = generate, n = provide your own)"
read -rp "[y/n]: " fernet_choice

if [[ "$fernet_choice" =~ ^[Yy]$ ]]; then
    FERNET_KEY=$(generate_fernet_key)
else
    read -rp "Enter your existing Fernet key: " FERNET_KEY
fi

cat > "$ENV_FILE" <<EOF
PERIDOCS_AES_KEY=$FERNET_KEY
ADMIN_TOKEN=YOUR_ADMIN_TOKEN
EOF

chmod 600 "$ENV_FILE"
chown "$RUNTIME_USER":"$RUNTIME_GROUP" "$ENV_FILE"
echo ".env file created at $ENV_FILE"

# ----------------------------------------------------------
# Step 3: Pull repository
# ----------------------------------------------------------
echo -e "\nStep 3 — Pull repository into $APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
    git clone git@github.com:Stays7339/PeriDocs.git "$APP_DIR"
else
    cd "$APP_DIR"
    git pull origin main
fi

# ----------------------------------------------------------
# Step 4: Virtual environment + dependencies
# ----------------------------------------------------------
echo -e "\nStep 4 — Setup Python virtual environment"

cd "$APP_DIR"
if [[ ! -d "venv" ]]; then
    python3 -m venv venv
fi

# Activate
if [[ "$OS_TYPE" == "windowsnt" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Upgrade pip and install
pip install --upgrade pip
pip install -r requirements.txt

# ----------------------------------------------------------
# Step 5: Run setup_roberta.py
# ----------------------------------------------------------
echo -e "\nStep 5 — Run deterministic RoBERTa setup"
python setup_roberta.py

# ----------------------------------------------------------
# Step 6: Optional daemon/service
# ----------------------------------------------------------
echo -e "\nStep 6 — Optional daemon/service setup"

prompt_continue "Do you want to setup systemd/launchd service for production? (skip if developer)"

if [[ "$OS_TYPE" == "linux" ]]; then
    SYSTEMD_FILE="/etc/systemd/system/peridocs.service"
    echo "Creating systemd service at $SYSTEMD_FILE"
    sudo tee "$SYSTEMD_FILE" > /dev/null <<EOF
[Unit]
Description=PeriDocs FastAPI App
After=network.target

[Service]
Type=simple
User=$RUNTIME_USER
Group=$RUNTIME_GROUP
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable peridocs.service
    sudo systemctl start peridocs.service
    echo "Systemd service started."
elif [[ "$OS_TYPE" == "darwin" ]]; then
    echo "macOS detected — create a launchd plist manually or via launchctl for PeriDocs daemon."
else
    echo "Windows detected — skip daemon setup. Developers can run 'uvicorn app.main:app --host 0.0.0.0 --port 8000' directly."
fi

echo -e "\n✅ Setup completed successfully!"
echo "Run 'source venv/bin/activate' and 'uvicorn app.main:app --host 0.0.0.0 --port 8000' to start manually if not using daemon."
