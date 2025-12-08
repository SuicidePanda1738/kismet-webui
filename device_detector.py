import os
import subprocess
import re
import logging
from typing import List, Dict, Any

class DeviceDetector:
    """Detects available WiFi, Bluetooth, and SDR devices"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def detect_wifi_interfaces(self) -> List[Dict[str, Any]]:
        """Detect available WiFi interfaces"""
        interfaces = []
        
        try:
            # Try iwconfig first
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                interfaces.extend(self._parse_iwconfig(result.stdout))
            else:
                # Fallback to ip link
                result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    interfaces.extend(self._parse_ip_link_wifi(result.stdout))
        
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.logger.error(f"WiFi interface detection error: {e}")
        
        return interfaces
    
    def detect_bluetooth_interfaces(self) -> List[Dict[str, Any]]:
        """Detect available Bluetooth interfaces"""
        interfaces = []
        
        try:
            # Try hcitool dev
            result = subprocess.run(['hcitool', 'dev'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                interfaces.extend(self._parse_hcitool(result.stdout))
            else:
                # Fallback to bluetoothctl
                result = subprocess.run(['bluetoothctl', 'list'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    interfaces.extend(self._parse_bluetoothctl(result.stdout))
        
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.logger.error(f"Bluetooth interface detection error: {e}")
        
        return interfaces
    
    def detect_sdr_devices(self) -> List[Dict[str, Any]]:
        """Detect available RTL-SDR devices"""
        devices = []
        
        try:
            # Use rtl_test to detect RTL-SDR devices
            # Note: rtl_test -t may not exit cleanly, so we use a shorter timeout and catch partial output
            result = subprocess.run(['rtl_test', '-t'], capture_output=True, text=True, timeout=5)
            # rtl_test outputs device info to STDERR, not STDOUT
            output_to_parse = result.stderr if result.stderr.strip() else result.stdout
            devices.extend(self._parse_rtl_test(output_to_parse))
        except subprocess.TimeoutExpired as e:
            # rtl_test often doesn't exit cleanly, but we can still parse the output
            if hasattr(e, 'stdout') and e.stdout:
                stdout_text = e.stdout.decode('utf-8') if isinstance(e.stdout, bytes) else e.stdout
                devices.extend(self._parse_rtl_test(stdout_text))
            elif hasattr(e, 'stderr') and e.stderr:
                stderr_text = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else e.stderr
                devices.extend(self._parse_rtl_test(stderr_text))
            else:
                self.logger.warning("rtl_test timed out without capturing output")
        except FileNotFoundError as e:
            self.logger.error(f"SDR device detection error: {e}")
            # Return empty list if rtl_test is not available
        
        return devices
    
    def _parse_iwconfig(self, output: str) -> List[Dict[str, Any]]:
        """Parse iwconfig output"""
        interfaces = []
        current_interface = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # New interface line
            if not line.startswith(' '):
                parts = line.split()
                if parts and 'IEEE 802.11' in line:
                    current_interface = {
                        'interface': parts[0],
                        'name': parts[0],
                        'type': 'WiFi',
                        'status': 'available',
                        'capabilities': []
                    }
                    interfaces.append(current_interface)
            
            # Interface details
            elif current_interface:
                if 'Mode:' in line:
                    mode_match = re.search(r'Mode:(\w+)', line)
                    if mode_match:
                        current_interface['mode'] = mode_match.group(1)
                
                if 'Frequency:' in line:
                    freq_match = re.search(r'Frequency:([\d.]+)\s*GHz', line)
                    if freq_match:
                        current_interface['frequency'] = f"{freq_match.group(1)} GHz"
        
        return interfaces
    
    def _parse_ip_link_wifi(self, output: str) -> List[Dict[str, Any]]:
        """Parse ip link output for WiFi interfaces"""
        interfaces = []
        
        for line in output.split('\n'):
            if 'wlan' in line or 'wifi' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    interface_name = parts[1].strip().split('@')[0]
                    interfaces.append({
                        'interface': interface_name,
                        'name': interface_name,
                        'type': 'WiFi',
                        'status': 'available',
                        'capabilities': []
                    })
        
        return interfaces
    
    def _parse_hcitool(self, output: str) -> List[Dict[str, Any]]:
        """Parse hcitool dev output"""
        interfaces = []
        
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('hci'):
                parts = line.split()
                if len(parts) >= 2:
                    interfaces.append({
                        'interface': parts[0],
                        'name': parts[0],
                        'type': 'Bluetooth',
                        'address': parts[1],
                        'status': 'available'
                    })
        
        return interfaces
    
    def _parse_bluetoothctl(self, output: str) -> List[Dict[str, Any]]:
        """Parse bluetoothctl list output"""
        interfaces = []
        
        for line in output.split('\n'):
            if 'Controller' in line:
                match = re.search(r'Controller\s+([A-F0-9:]{17})\s+(.*)', line)
                if match:
                    address = match.group(1)
                    name = match.group(2)
                    # Derive hci interface name from address
                    interface = f"hci{len(interfaces)}"
                    interfaces.append({
                        'interface': interface,
                        'name': name,
                        'type': 'Bluetooth',
                        'address': address,
                        'status': 'available'
                    })
        
        return interfaces
    
    def _parse_rtl_test(self, output: str) -> List[Dict[str, Any]]:
        """Parse rtl_test output"""
        devices = []
        
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('Found') and 'device(s):' in line:
                continue
            
            # Parse device lines like: "0:  Nooelec, NESDR SMArt v5, SN: 00000001"
            # Handle different formats: manufacturer, model, SN: serial
            if re.match(r'\d+:\s+', line):
                # Remove device number prefix
                content = re.sub(r'^\d+:\s+', '', line)
                
                # Split by comma and parse components
                parts = [part.strip() for part in content.split(',')]
                
                device_match = re.match(r'(\d+):', line)
                device_id = device_match.group(1) if device_match else "0"
                manufacturer = parts[0] if parts else "Unknown"
                model = ""
                serial = device_id  # default to device_id
                
                # Parse remaining parts for model and serial
                for i, part in enumerate(parts[1:], 1):
                    if part.startswith('SN:'):
                        serial = part.replace('SN:', '').strip()
                    elif i == 1:  # Second part is typically the model
                        model = part.strip()
                
                # Always use device ID for rtl433 naming, not serial
                device_name = f"rtl433-{device_id}"
                
                # Build display name
                display_name = manufacturer
                if model:
                    display_name += f" {model}"
                
                devices.append({
                    'device': device_name,
                    'device_id': device_id,
                    'name': display_name,
                    'type': 'RTL-SDR',
                    'serial': serial,
                    'manufacturer': manufacturer,
                    'model': model,
                    'status': 'available',
                    'default_frequency': '433920000',
                    'supported_frequencies': ['433920000', '915000000', 'Custom']
                })
        
        return devices
    
    def test_device_availability(self, device_type: str, interface: str) -> Dict[str, Any]:
        """Test if a specific device is available and functional"""
        try:
            if device_type == 'wifi':
                result = subprocess.run(['iwconfig', interface], capture_output=True, text=True, timeout=5)
                return {
                    'available': result.returncode == 0,
                    'error': result.stderr if result.returncode != 0 else None
                }
            
            elif device_type == 'bluetooth':
                result = subprocess.run(['hciconfig', interface], capture_output=True, text=True, timeout=5)
                return {
                    'available': result.returncode == 0,
                    'error': result.stderr if result.returncode != 0 else None
                }
            
            elif device_type == 'rtl433':
                # For RTL-SDR, we can test by attempting to open the device briefly
                device_id = interface.split('-')[-1]
                if device_id.isdigit():
                    result = subprocess.run(['rtl_test', '-d', device_id, '-t'], 
                                          capture_output=True, text=True, timeout=10)
                    return {
                        'available': result.returncode == 0,
                        'error': result.stderr if result.returncode != 0 else None
                    }
        
        except Exception as e:
            return {
                'available': False,
                'error': str(e)
            }
        
        return {'available': False, 'error': 'Unknown device type'}
