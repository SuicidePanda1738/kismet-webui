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
 - kismet-webui.service (Gunicorn on port 2502)
 - kismet-push-services.service (push-service supervisor - Pushes kismet data [WiFi & BT] to a remote server)
 - Installs a fork of MetaGPS [enhanced reconnects when service drops in&out] for use with the kismet_cap_linux_wifi
-----------------------------------------------------------------------------
Access the UI:
 - http://host-or-ip:2502/
 - upon first time visiting the webui you will be prompted to set username and password
-----------------------------------------------------------------------------
Dashboard
<img width="2006" height="1169" alt="dashboard" src="https://github.com/user-attachments/assets/658db454-aad1-40ba-ab80-5c3f2d819fcd" />

Configure
<img width="1585" height="1215" alt="Config-WIFI" src="https://github.com/user-attachments/assets/45b425b7-0d27-4d46-b960-0690eacf0d38" />
<img width="1441" height="1144" alt="Config-settings" src="https://github.com/user-attachments/assets/0215e507-1908-4877-b501-e53c615298c1" />
<img width="1459" height="821" alt="Config-setting-1" src="https://github.com/user-attachments/assets/5cdd3881-3724-43e7-b5d2-4cd502d05eff" />

Files
<img width="1457" height="740" alt="files" src="https://github.com/user-attachments/assets/11e093c6-bf6a-4fb8-92a1-f7bb1339af8c" />

Remote-Push
<img width="1199" height="1205" alt="remote-push" src="https://github.com/user-attachments/assets/352a0b00-043a-4d7e-90ea-1f80a5839628" />

Admin
<img width="1204" height="477" alt="admin" src="https://github.com/user-attachments/assets/ef2725da-fcc3-4387-a41d-180c3590172c" />





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
