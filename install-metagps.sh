#!/bin/bash

# MetaGPS Installation Script
# Installs the GPS attachment service for Kismet remote capture

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Starting MetaGPS installation...${NC}"

# Variables
INSTALL_DIR="/opt/metagps"

# Check for GPSd
if ! command -v gpsd &> /dev/null; then
    echo -e "${YELLOW}GPSd not found. Installing...${NC}"
    apt-get update
    apt-get install -y gpsd gpsd-clients python3-gps
fi

# Create installation directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"

# Copy metagpsd.py
echo -e "${YELLOW}Installing MetaGPS service...${NC}"
cp metagpsd.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/metagpsd.py"

# Create virtual environment
echo -e "${YELLOW}Creating Python virtual environment...${NC}"
cd "$INSTALL_DIR"
python3 -m venv venv

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install websockets gpsdclient loguru

# Create a systemd service template for GPSd if not exists
if [ ! -f /etc/systemd/system/gpsd.service ]; then
    echo -e "${YELLOW}Configuring GPSd service...${NC}"
    cat > /etc/default/gpsd << 'EOF'
# Default settings for the gpsd init script and the hotplug wrapper.

# Start the gpsd daemon automatically at boot time
START_DAEMON="true"

# Use USB hotplugging to add new USB devices automatically to the daemon
USBAUTO="true"

# Devices gpsd should collect to at boot time.
# They need to be read/writeable, either by user gpsd or the group dialout.
DEVICES="/dev/ttyACM0 /dev/ttyUSB0"

# Other options you want to pass to gpsd
GPSD_OPTIONS="-n"
EOF
fi

# Enable GPSd service
systemctl enable gpsd
systemctl restart gpsd

echo -e "${GREEN}MetaGPS installation complete!${NC}"
echo ""
echo "To use MetaGPS with your WiFi push services:"
echo "1. Ensure GPSd is receiving GPS data: gpsd -N -D 2 /dev/ttyUSB0"
echo "2. Test GPS reception: cgps or gpsmon"
echo "3. The push services will automatically use MetaGPS when GPS API key is provided"
echo ""
echo "MetaGPS installed to: $INSTALL_DIR"
echo "To run manually: $INSTALL_DIR/venv/bin/python $INSTALL_DIR/metagpsd.py --help"