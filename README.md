Kismet WebUI
 - A Flask-based web interface for configuring the Kismet wireless detector (Wi-Fi, Bluetooth, SDR). It provides a focused dashboard to manage Kismet settings, data sources, service status, log files, and remote sources.
-----------------------------------------------------------------------------
Requirements:
 - Kismet installed
 - Note* All testing and development has been done on a PI4 running Raspbian bookworm 
-----------------------------------------------------------------------------
Architecture:
 - Frontend: Flask + Jinja2, Bootstrap 5 (dark mode), Feather Icons, vanilla JS
 - Backend: Flask + SQLAlchemy (SQLite by default, configurable), optional ProxyFix, Python logging
 - System Integration: systemd service control; device discovery for Wi-Fi, Bluetooth, SDR
 - Files/Data: reads/writes Kismet configs and logs
-----------------------------------------------------------------------------
Installation:
 - Clone the repo (install git first if needed)
 - sudo apt update -y && sudo apt install -y git
 - git clone https://github.com/SuicidePanda1738/kismet-webui.git
 - cd kismet-webui
 - sudo chmod +x install.sh
 - sudo ./install.sh
-----------------------------------------------------------------------------
What install.sh does:
 - Installs OS prerequisites on Bookworm/Debian/Ubuntu (python3, python3-venv, python3-pip, rsync, gpsd, gpsd-clients, python3-gps)
 - Creates a Python virtual environment and installs Python dependencies
 - Deploys the app to /opt/kismet-webui
 - Creates systemd services:
 - kismet-webui.service (Gunicorn on port 5000)
 - kismet-push-services.service (push-service supervisor - Pushes kismet data [WiFi & BT] to a remote server)
 - Installs a fork of MetaGPS [enhanced reconnects when service drops in&out] for use with the kismet_cap_linux_wifi
-----------------------------------------------------------------------------
Access the UI:
 - http://host-or-ip:5000/
-----------------------------------------------------------------------------
Uninstall:
 - sudo systemctl disable --now kismet-webui kismet-push-services
 - sudo rm -f /etc/systemd/system/kismet-webui.service /etc/systemd/system/kismet-push-services.service
 - sudo systemctl daemon-reload
 - sudo rm -rf /opt/kismet-webui
-----------------------------------------------------------------------------
Acknowledgments:
 - Kismet Wireless — core wireless detection platform
 - hobobandy — metagpsd.py
