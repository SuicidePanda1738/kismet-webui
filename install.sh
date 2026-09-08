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
# instance/ (database) and push_services/ are runtime data: never copied or deleted.
rsync -a --delete \
  --exclude 'venv' \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'instance' \
  --exclude 'push_services' \
  "${SRC_DIR}/" "${INSTALL_DIR}/"

mkdir -p "${INSTALL_DIR}/instance"
cd "${INSTALL_DIR}"

# --- Python deps for WebUI ---
echo "[+] Creating virtual environment for WebUI"
python3 -m venv "${VENV_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel

# Install from requirements-deploy.txt — the single source of truth for the
# app's Python dependencies. (Previously this list was duplicated inline here,
# which silently drifted and shipped without flask-wtf / cryptography.)
if [[ ! -f "${INSTALL_DIR}/requirements-deploy.txt" ]]; then
  die "requirements-deploy.txt not found in ${INSTALL_DIR}"
fi
pip install -r "${INSTALL_DIR}/requirements-deploy.txt"
deactivate

# --- Permissions ---
chown -R root:root "${INSTALL_DIR}"
chmod -R 755 "${INSTALL_DIR}"

# --- Secrets: root-only env file, written once and kept on re-runs ---
# Both systemd units and the kismet-webui-admin command load this file.
# SESSION_SECRET also derives the database encryption key (crypto_utils.py),
# so regenerating it would make every stored API key unreadable.
ENV_DIR="/etc/kismet-webui"
ENV_FILE="${ENV_DIR}/env"
mkdir -p "${ENV_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[+] Writing ${ENV_FILE}"
  # Carry over the secret from a unit written by an older installer, so API
  # keys encrypted under it stay readable; otherwise generate a new one.
  SESSION_SECRET="$(sed -n 's/^Environment="SESSION_SECRET=//p' "${SERVICE_FILE}" 2>/dev/null | tr -d '"' || true)"
  if [[ -z "${SESSION_SECRET}" || "${SESSION_SECRET}" == "change-this-to-a-random-secret-key" ]]; then
    SESSION_SECRET="$("${VENV_DIR}/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
  fi
  (umask 077 && cat > "${ENV_FILE}" <<EOF
SESSION_SECRET=${SESSION_SECRET}
DATABASE_URL=sqlite:///${INSTALL_DIR}/instance/kismet_webui.db
EOF
  )
else
  echo "[+] Keeping existing ${ENV_FILE}"
fi
chmod 600 "${ENV_FILE}"

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
EnvironmentFile=${ENV_FILE}
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
EnvironmentFile=${ENV_FILE}

ExecStart=/opt/kismet-webui/venv/bin/python /opt/kismet-webui/push_services_startup.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# --- kismet-webui-admin command (account/password reset) ---
ADMIN_CMD="/usr/local/sbin/kismet-webui-admin"
echo "[+] Writing ${ADMIN_CMD}"
cat > "${ADMIN_CMD}" <<EOF
#!/usr/bin/env bash
# Runs manage.py with the same environment as the kismet-webui service.
set -euo pipefail
[[ \$EUID -eq 0 ]] || { echo "Run as root (use sudo)." >&2; exit 1; }
set -a
# shellcheck disable=SC1091
. "${ENV_FILE}"
set +a
exec "${VENV_DIR}/bin/python" "${INSTALL_DIR}/manage.py" "\$@"
EOF
chmod 755 "${ADMIN_CMD}"

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
DEVICES="/dev/ttyACM0"
GPSD_OPTIONS="-n -b"
EOF2
  systemctl enable gpsd || true
  systemctl restart gpsd || true
fi

# --- Kismet service hardening ---
# Kismet's packaged unit uses KillMode=process, so kismet_cap_* helpers and
# rtl_433 keep running after Kismet stops. The orphaned rtl_433 holds the
# RTL-SDR dongle and an inherited copy of Kismet's port-3501 listener, so the
# next Kismet dies at startup ("bind: Address already in use"), five fast
# relaunches trip systemd's start-rate limit, and the rtl433 source can never
# get the dongle back. Stop the whole control group, force-kill stragglers
# after 30s, and pace relaunches.
KISMET_DROPIN_DIR="/etc/systemd/system/kismet.service.d"
echo "[+] Writing ${KISMET_DROPIN_DIR}/kismet-webui.conf"
mkdir -p "${KISMET_DROPIN_DIR}"
cat > "${KISMET_DROPIN_DIR}/kismet-webui.conf" <<'EOF'
[Service]
KillMode=control-group
TimeoutStopSec=30
RestartSec=5
EOF

# The DVB-T kernel driver claims RTL-SDR dongles and re-initialises them each
# time an SDR program closes the device; librtlsdr and rtl_433 require it to
# be blacklisted.
echo "[+] Blacklisting dvb_usb_rtl28xxu"
cat > /etc/modprobe.d/blacklist-rtlsdr.conf <<'EOF'
blacklist dvb_usb_rtl28xxu
EOF
modprobe -r dvb_usb_rtl28xxu 2>/dev/null || true

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
echo "    Admin: sudo kismet-webui-admin reset-users | reset-password <username>"
