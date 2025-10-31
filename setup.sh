#!/bin/bash

# --- Pi Kiosk One-Command Installer ---
# This script installs and configures the entire kiosk application.
# Run it with:
# curl -sSL https://raw.githubusercontent.com/kaperose/pi-kiosk/master/setup.sh | sudo bash
#
# Or, if your main branch is "main":
# curl -sSL https://raw.githubusercontent.com/kaperose/pi-kiosk/main/setup.sh | sudo bash

# Check if running as root (required)
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo:"
  echo "curl -sSL ... | sudo bash"
  exit 1
fi

# --- Find the correct non-root user ---
# This is usually "pi", but we check to be sure.
if [ -n "$SUDO_USER" ]; then
    PI_USER=$SUDO_USER
else
    PI_USER=$(logname 2>/dev/null || who am i | awk '{print $1}')
fi

# Default to 'pi' if all else fails
if [ -z "$PI_USER" ] || [ "$PI_USER" == "root" ]; then
    PI_USER="pi"
fi

PI_HOME="/home/$PI_USER"
REPO_DIR="$PI_HOME/pi-kiosk"
# IMPORTANT: Use your actual repository URL here
REPO_URL="https://github.com/kaperose/pi-kiosk.git"

echo "--- Starting Pi Kiosk Setup ---"
echo "Target User: $PI_USER"
echo "Target Home: $PI_HOME"
echo "Repo Dir: $REPO_DIR"

# --- PHASE 1: Install Dependencies ---
echo "[1/5] Updating and installing dependencies..."
apt-get update
apt-get upgrade -y
# Install all dependencies at once
apt-get install -y git python3 python3-pip python3-flask python3-psutil xdotool chromium
if [ $? -ne 0 ]; then echo "Error: Failed to install dependencies." >&2; exit 1; fi

# --- PHASE 2: Clone The Project ---
echo "[2/5] Cloning repository to $REPO_DIR..."
# Run the clone command as the non-root user
sudo -u "$PI_USER" git clone "$REPO_URL" "$REPO_DIR"

if [ $? -ne 0 ]; then
    echo "Warning: Repository may already exist. Attempting to update..."
    cd "$REPO_DIR" || exit 1
    sudo -u "$PI_USER" git pull origin master
    if [ $? -ne 0 ]; then
        echo "Error: Failed to clone or update repository. Please check $REPO_DIR manually." >&2
        exit 1
    fi
fi

# --- PHASE 3: Create Systemd Services ---
echo "[3/5] Creating systemd service files..."

# 1. Kiosk Display Service
cat > /etc/systemd/system/kiosk-display.service << EOL
[Unit]
Description=Kiosk Display Service
After=graphical.target
Wants=graphical.target

[Service]
Environment=DISPLAY=:0
Environment=XAUTHORITY=$PI_HOME/.Xauthority
User=$PI_USER
Group=$PI_USER
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/python3 $REPO_DIR/kiosk_control.py
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
EOL

# 2. Kiosk Web Server Service
cat > /etc/systemd/system/kiosk-web.service << EOL
[Unit]
Description=Kiosk Web Interface Server
After=network.target

[Service]
User=$PI_USER
Group=$PI_USER
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/python3 $REPO_DIR/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# --- PHASE 4: Set Permissions ---
echo "[4/5] Setting up sudo permissions for web UI..."
# This allows the web server to restart the kiosk service
cat > /etc/sudoers.d/010-pi-kiosk << EOL
# Allow the $PI_USER user to restart the kiosk-display service
$PI_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart kiosk-display.service
EOL
# Set correct permissions for the sudoers file
chmod 0440 /etc/sudoers.d/010-pi-kiosk

# --- PHASE 5: Launch ---
echo "[5/5] Reloading daemon and starting services..."
systemctl daemon-reload
systemctl enable kiosk-display.service
systemctl enable kiosk-web.service
systemctl start kiosk-display.service
systemctl start kiosk-web.service

# --- DONE! ---
echo "---"
echo "Installation Complete!"
echo "Your Pi's monitor should now launch the kiosk."
echo "You can access the web config panel at:"
echo ""
echo "http://$(hostname -I | awk '{print $1}'):8080"
echo ""
