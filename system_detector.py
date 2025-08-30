#!/usr/bin/env python3
"""
System Environment Detection for Kismet Web Interface
Detects production vs development environment and system capabilities.
"""

import os
import shutil
import subprocess
import logging

class SystemEnvironmentDetector:
    """Detects system environment and capabilities for service integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._environment = None
        self._capabilities = None
    
    def get_environment(self):
        """Detect if running in development or production environment."""
        if self._environment is not None:
            return self._environment
            
        # Development indicators (besides absence of systemd)
        dev_indicators = [
            os.environ.get('FLASK_ENV') == 'development',  # Flask dev mode
            os.environ.get('ENVIRONMENT') == 'development',  # Explicit dev setting
            not os.path.exists('/etc/systemd'),  # No systemd presence
        ]
        
        # Production indicators (need multiple to be confident)
        prod_indicators = [
            os.path.exists('/etc/systemd/system'),  # Systemd services directory
            os.path.exists('/etc/nginx'),  # Nginx installation
            shutil.which('kismet') is not None or shutil.which('kismet_server') is not None,  # Kismet installed
            os.geteuid() == 0,  # Running as root
            os.path.exists('/lib/systemd/system'),  # System services path
        ]
        
        if any(dev_indicators):
            self._environment = 'development'
        elif sum(bool(p) for p in prod_indicators) >= 2:
            self._environment = 'production'
        else:
            self._environment = 'hybrid'
            
        return self._environment
    
    def get_system_capabilities(self):
        """Get detailed system capabilities for service integration."""
        if self._capabilities is not None:
            return self._capabilities
            
        capabilities = {
            'environment': self.get_environment(),
            'systemd': self._check_systemd(),
            'kismet': self._check_kismet(),
            'privileges': self._check_privileges(),
            'network': self._check_network(),
            'filesystem': self._check_filesystem_access(),
        }
        
        self._capabilities = capabilities
        return capabilities
    
    def _check_systemd(self):
        """Check systemd availability and capabilities."""
        systemctl_path = shutil.which('systemctl')
        
        if not systemctl_path:
            return {
                'available': False,
                'path': None,
                'version': None,
                'user_services': False,
                'system_services': False,
                'reason': 'systemctl not found'
            }
        
        try:
            version_result = subprocess.run([systemctl_path, '--version'], 
                                          capture_output=True, text=True, timeout=5)
            version = version_result.stdout.split('\n')[0] if version_result.returncode == 0 else 'unknown'
            
            user_services = False
            try:
                subprocess.run([systemctl_path, '--user', 'list-units'], 
                               capture_output=True, timeout=5, check=True)
                user_services = True
            except:
                pass
            
            system_services = False
            try:
                subprocess.run([systemctl_path, 'list-units'], 
                               capture_output=True, timeout=5, check=True)
                system_services = True
            except:
                try:
                    subprocess.run(['sudo', '-n', systemctl_path, 'list-units'], 
                                   capture_output=True, timeout=5, check=True)
                    system_services = True
                except:
                    pass
            
            return {
                'available': True,
                'path': systemctl_path,
                'version': version,
                'user_services': user_services,
                'system_services': system_services,
                'reason': 'systemd detected and functional'
            }
            
        except Exception as e:
            return {
                'available': False,
                'path': systemctl_path,
                'version': None,
                'user_services': False,
                'system_services': False,
                'reason': f'systemd error: {str(e)}'
            }
    
    def _check_kismet(self):
        """Check Kismet installation and configuration."""
        kismet_paths = {
            'kismet': shutil.which('kismet'),
            'kismet_server': shutil.which('kismet_server'),
            'kismet_cap_linux_wifi': shutil.which('kismet_cap_linux_wifi'),
            'kismet_cap_linux_bluetooth': shutil.which('kismet_cap_linux_bluetooth'),
        }
        
        available = any(path is not None for path in kismet_paths.values())
        
        # Get Kismet service status
        service_exists = False
        service_status = 'unknown'
        service_enabled = False
        
        if shutil.which('systemctl'):
            try:
                # Check if service exists
                result = subprocess.run(['systemctl', 'list-unit-files', 'kismet.service'],
                                      capture_output=True, text=True, timeout=5)
                service_exists = 'kismet.service' in result.stdout
                
                if service_exists:
                    # Get service status
                    result = subprocess.run(['systemctl', 'is-active', 'kismet'],
                                          capture_output=True, text=True, timeout=5)
                    service_status = result.stdout.strip()
                    
                    # Check if enabled
                    result = subprocess.run(['systemctl', 'is-enabled', 'kismet'],
                                          capture_output=True, text=True, timeout=5)
                    service_enabled = result.stdout.strip() == 'enabled'
            except:
                pass
        
        # Find config files
        config_files = []
        config_locations = [
            '/etc/kismet/',
            '/usr/local/etc/kismet/',
            os.path.expanduser('~/.kismet/'),
        ]
        
        for loc in config_locations:
            if os.path.exists(loc):
                try:
                    for f in os.listdir(loc):
                        if f.endswith('.conf'):
                            config_files.append(os.path.join(loc, f))
                except:
                    pass
        
        return {
            'installed': available,
            'binary_available': kismet_paths.get('kismet') is not None,
            'binary_path': kismet_paths.get('kismet', ''),
            'server_available': kismet_paths.get('kismet_server') is not None,
            'server_path': kismet_paths.get('kismet_server', ''),
            'paths': {k: v for k, v in kismet_paths.items() if v},
            'config_files': config_files[:5],  # Limit to first 5 config files
            'config_locations': [loc for loc in config_locations if os.path.exists(loc)],
            'version': self._get_kismet_version(kismet_paths),
            'service_exists': service_exists,
            'service_status': service_status,
            'service_enabled': service_enabled,
        }
    
    def _get_kismet_version(self, paths):
        """Get Kismet version if possible."""
        for cmd in ['kismet', 'kismet_server']:
            if paths.get(cmd):
                try:
                    result = subprocess.run([paths[cmd], '--version'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        return result.stdout.strip()
                except:
                    pass
        return 'unknown'
    
    def _check_privileges(self):
        """Check process privileges and capabilities."""
        sudo_available = self._check_sudo_access()
        return {
            'uid': os.getuid(),
            'euid': os.geteuid(),
            'gid': os.getgid(),
            'egid': os.getegid(),
            'user_id': os.getuid(),
            'is_root': os.geteuid() == 0,
            'can_use_sudo': sudo_available,
            'sudo_available': sudo_available,
            'can_manage_services': os.geteuid() == 0 or sudo_available,
        }
    
    def _check_sudo_access(self):
        """Check if process can use sudo without password."""
        try:
            result = subprocess.run(['sudo', '-n', 'true'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def _check_network(self):
        """Check network interfaces and capabilities."""
        interfaces = {
            'wifi': [],
            'bluetooth': [],
            'all': []
        }
        
        # Check WiFi interfaces
        try:
            result = subprocess.run(['ip', 'link', 'show'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'wlan' in line or 'wlp' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            interfaces['wifi'].append(parts[1].strip())
                            interfaces['all'].append(parts[1].strip())
        except:
            pass
        
        # Check Bluetooth interfaces
        try:
            result = subprocess.run(['hciconfig', '-a'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'hci' in line and ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 1:
                            interfaces['bluetooth'].append(parts[0].strip())
                            interfaces['all'].append(parts[0].strip())
        except:
            pass
        
        # Check for network tools
        network_tools = {
            'ip': shutil.which('ip') is not None,
            'ifconfig': shutil.which('ifconfig') is not None, 
            'iwconfig': shutil.which('iwconfig') is not None,
            'hciconfig': shutil.which('hciconfig') is not None,
        }
        
        return {
            'interfaces': interfaces,
            'tools': network_tools,
            'capable': any(interfaces['all']),
            'bluetooth_count': len(interfaces['bluetooth']),
            'wifi_count': len(interfaces['wifi']),
        }
    
    def _check_filesystem_access(self):
        """Check filesystem access permissions."""
        important_paths = {
            '/etc/kismet/': 'config',
            '/var/log/kismet/': 'logs',
            '/home/user/kismet/': 'user_data',
            '/tmp/': 'temp',
        }
        
        access = {}
        for path, name in important_paths.items():
            access[name] = {
                'path': path,
                'exists': os.path.exists(path),
                'readable': os.access(path, os.R_OK) if os.path.exists(path) else False,
                'writable': os.access(path, os.W_OK) if os.path.exists(path) else False,
            }
        
        return access

# Create singleton instance
detector = SystemEnvironmentDetector()