#!/usr/bin/env bash
# Kismet WebUI unified installer 
# Usage: sudo ./install.sh

set -Eeuo pipefail

APP_NAME="kismet-webui"
INSTALL_DIR="/opt/${APP_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_NAME="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PUSH_SERVICE_FILE="/etc/systemd/system/kismet-push-services.service"
INSTALL_DIR_METAGPS="/opt/metagps"

die(){ echo "[-] $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }
here(){ cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd; }

[[ $EUID -eq 0 ]] || die "Run as root (use sudo)."

echo "[+] Installing ${APP_NAME} into ${INSTALL_DIR}"

# --- OS deps ---
if have apt-get; then
  echo "[+] Installing OS packages"
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip rsync gpsd gpsd-clients python3-gps rtl-sdr rtl-433 iw wireless-tools net-tools
fi

# --- Copy app files ---
SRC_DIR="$(here)"
mkdir -p "${INSTALL_DIR}"
rsync -a --delete \
  --exclude 'venv' \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "${SRC_DIR}/" "${INSTALL_DIR}/"

mkdir -p "${INSTALL_DIR}/instance"
cd "${INSTALL_DIR}"

# --- Python deps for WebUI ---
echo "[+] Creating virtual environment for WebUI"
python3 -m venv "${VENV_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel

cat > "${INSTALL_DIR}/requirements.txt" <<'EOF'
flask==3.0.0
flask-login==0.6.3
flask-sqlalchemy==3.1.1
gunicorn==21.2.0
psycopg2-binary==2.9.9
werkzeug==3.0.0
email-validator==2.1.0
sqlalchemy==2.0.23
mgrs==1.4.5
EOF

pip install -r "${INSTALL_DIR}/requirements.txt"
deactivate

# --- Permissions ---
chown -R root:root "${INSTALL_DIR}"
chmod -R 755 "${INSTALL_DIR}"

# --- Random session secret ---
SESSION_SECRET="$("${VENV_DIR}/bin/python" - <<'PY'
import secrets,string
print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(64)))
PY
)"

# --- systemd unit for WebUI ---
echo "[+] Writing ${SERVICE_FILE}"
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Kismet WebUI Service
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="SESSION_SECRET=${SESSION_SECRET}"
Environment="DATABASE_URL=sqlite:////${INSTALL_DIR}/instance/kismet_webui.db"
ExecStart=${VENV_DIR}/bin/gunicorn --bind 0.0.0.0:2502 --workers 2 --threads 2 --access-logfile - --error-logfile - main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# --- oneshot service to start push scripts ---
echo "[+] Writing ${PUSH_SERVICE_FILE}"
cat > "${PUSH_SERVICE_FILE}" <<EOF
[Unit]
Description=Kismet Push Services Startup
After=network-online.target kismet-webui.service
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
User=root
Group=root
WorkingDirectory=/opt/kismet-webui
# Use the webui virtualenv and make sure imports resolve from app dir
Environment="PATH=/opt/kismet-webui/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=/opt/kismet-webui"
# Optional but recommended: mirror the DB url the app uses
Environment="DATABASE_URL=sqlite:////opt/kismet-webui/instance/kismet_webui.db"
# Optional: if your app.py expects this
Environment="SESSION_SECRET=${SESSION_SECRET}"

ExecStart=/opt/kismet-webui/venv/bin/python /opt/kismet-webui/push_services_startup.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# --- Install MetaGPS ---
echo "[+] Installing MetaGPS into ${INSTALL_DIR_METAGPS}"
mkdir -p "${INSTALL_DIR_METAGPS}"

# Copy metagpsd.py if it exists in source
if [[ -f "${SRC_DIR}/metagpsd.py" ]]; then
  cp -f "${SRC_DIR}/metagpsd.py" "${INSTALL_DIR_METAGPS}/"
else
  echo "[-] WARNING: metagpsd.py not found in source tree."
fi
chmod +x "${INSTALL_DIR_METAGPS}/metagpsd.py" 2>/dev/null || true

# venv for metagps
python3 -m venv "${INSTALL_DIR_METAGPS}/venv"
# shellcheck disable=SC1091
source "${INSTALL_DIR_METAGPS}/venv/bin/activate"
pip install --upgrade pip
pip install websockets gpsdclient loguru
deactivate

# GPSD default config (safe overwrite)
if [[ -d /etc/default ]]; then
  cat > /etc/default/gpsd <<'EOF2'
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyACM0 /dev/ttyUSB0"
GPSD_OPTIONS="-n -b"
EOF2
  systemctl enable gpsd || true
  systemctl restart gpsd || true
fi

# --- Enable services ---
echo "[+] Enabling services"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl enable kismet-push-services || true

# --- Start services ---
echo "[+] Starting ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}" || true

echo "[+] Starting push services (systemd oneshot)"
systemctl restart kismet-push-services || true

echo
echo "[?] ${APP_NAME} deployed with MetaGPS."
echo "    WebUI: sudo systemctl status ${SERVICE_NAME} --no-pager"
echo "    Push:  sudo systemctl status kismet-push-services --no-pager"
echo "    URL:   http://<host>:2502/"
