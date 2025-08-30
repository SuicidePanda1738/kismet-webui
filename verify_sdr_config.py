#!/usr/bin/env python3
"""
Verify SDR configuration is working correctly
"""

import sys
from device_detector import DeviceDetector
from config_manager import ConfigManager

def test_device_detection():
    """Test device detection with your exact rtl_test output"""
    print("=== Testing Device Detection ===")
    
    # Your exact rtl_test output
    rtl_output = """Found 1 device(s):
  0:  Realtek, RTL2838UHIDIR, SN: 00000001

Using device 0: Generic RTL2832U OEM
Detached kernel driver
Found Rafael Micro R820T tuner
Supported gain values (29): 0.0 0.9 1.4 2.7 3.7 7.7 8.7 12.5 14.4 15.7 16.6 19.7 20.7 22.9 25.4 28.0 29.7 32.8 33.8 36.4 37.2 38.6 40.2 42.1 43.4 43.9 44.5 48.0 49.6
[R82XX] PLL not locked!
Sampling at 2048000 S/s.
No E4000 tuner found, aborting."""
    
    detector = DeviceDetector()
    devices = detector._parse_rtl_test(rtl_output)
    
    if devices:
        device = devices[0]
        print(f"✓ Device detected: {device['device']}")
        print(f"  - Device ID: {device['device_id']}")
        print(f"  - Name: {device['name']}")
        print(f"  - Serial: {device['serial']}")
        
        if device['device'] == 'rtl433-0':
            print("✓ CORRECT: Using device ID format (rtl433-0)")
        else:
            print("✗ ERROR: Not using device ID format")
            print(f"  Expected: rtl433-0")
            print(f"  Got: {device['device']}")
    else:
        print("✗ ERROR: No devices detected")
    
    return devices

def test_config_generation(device):
    """Test configuration file generation"""
    print("\n=== Testing Configuration Generation ===")
    
    config_data = {
        'data_sources': [
            {
                'type': 'wifi',
                'interface': 'wlan0',
                'name': 'testing_new'
            },
            {
                'type': 'rtl433',
                'device': device['device'],
                'name': 'test',
                'frequency': '433.920MHz'
            }
        ],
        'gps_config': {'enabled': False},
        'logging_config': {
            'log_types': ['kismet', 'pcapng'],
            'log_prefix': '/home/user/kismet',
            'log_title': 'Kismet_Wireless_Survey',
            'pcapng_log_max_mb': 0,
            'pcapng_log_duplicate_packets': True,
            'pcapng_log_data_packets': True
        }
    }
    
    manager = ConfigManager()
    content = manager._generate_config_content(config_data)
    
    # Check the generated source line
    for line in content.split('\n'):
        if line.startswith('source=rtl433'):
            print(f"Generated line: {line}")
            
            # Check format
            if ':type=rtl433,' in line:
                print("✓ CORRECT: Using comma-separated format")
            else:
                print("✗ ERROR: Not using comma-separated format")
            
            if line.startswith('source=rtl433-0:'):
                print("✓ CORRECT: Using device ID (0)")
            else:
                print("✗ ERROR: Not using device ID")
            
            break
    
    return content

def main():
    print("SDR Configuration Verification")
    print("=" * 50)
    
    # Test device detection
    devices = test_device_detection()
    
    if devices:
        # Test configuration generation
        content = test_config_generation(devices[0])
        
        print("\n=== Expected vs Actual ===")
        print("Expected format: source=rtl433-0:type=rtl433,channel=433.920MHz,name=test")
        print("Your old format: source=rtl433-00000001:type=rtl433:name=test:channel=433.920MHz")
        
        for line in content.split('\n'):
            if line.startswith('source=rtl433'):
                print(f"Current format:  {line}")
                break

if __name__ == "__main__":
    main()