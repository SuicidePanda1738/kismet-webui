import subprocess
import time
import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

class KismetServiceManager:
    """Manages Kismet service operations using systemctl with proper privilege handling."""
    
    def __init__(self):
        self.service_name = 'kismet'
        self.logger = logging.getLogger(__name__)
        self.systemctl_path = self._find_systemctl()
        self.use_sudo = self._needs_sudo()
        self.service_available = self._check_service_exists()
        
    def _find_systemctl(self):
        """Find systemctl binary path."""
        systemctl_paths = [
            '/usr/bin/systemctl',
            '/bin/systemctl',
            '/usr/local/bin/systemctl'
        ]
        
        for path in systemctl_paths:
            if os.path.exists(path):
                return path
        
        # Try to find via which
        systemctl = shutil.which('systemctl')
        if systemctl:
            return systemctl
            
        return None
    
    def _needs_sudo(self):
        """Check if we need sudo for systemctl operations."""
        if os.geteuid() == 0:  # Already root
            return False
            
        if not self.systemctl_path:
            return True
            
        # Check if user has passwordless sudo for systemctl
        try:
            result = subprocess.run(['sudo', '-n', self.systemctl_path, '--version'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True
    
    def _check_service_exists(self):
        """Check if the Kismet service exists."""
        if not self.systemctl_path:
            return False
            
        try:
            cmd = ['systemctl', 'list-unit-files', f'{self.service_name}.service']
            if self.use_sudo:
                cmd = ['sudo'] + cmd
                
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return self.service_name in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_systemctl_command(self, action, check_output=False):
        """Run a systemctl command with proper error handling and privilege escalation."""
        if not self.systemctl_path:
            raise Exception("systemctl not found - systemd is not available on this system")
            
        if not self.service_available and action != 'status':
            raise Exception(f"Service '{self.service_name}' is not installed on this system")
        
        try:
            cmd = [self.systemctl_path, action, self.service_name]
            if self.use_sudo:
                cmd = ['sudo'] + cmd
                
            self.logger.info(f"Running command: {' '.join(cmd)}")
            
            if check_output:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                # 'is-enabled' returns non-zero for disabled/static/etc. That's not an error.
                if result.returncode != 0 and action not in ('status', 'is-enabled'):
                    self.logger.error(f"Command failed: {result.stderr or result.stdout or 'no stderr'}")
                return result
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
                return None
                
        except subprocess.TimeoutExpired:
            raise Exception(f"Command timed out: systemctl {action}")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise Exception(f"Failed to {action} service: {error_msg}")
        except FileNotFoundError as e:
            if 'sudo' in str(e):
                raise Exception("sudo not found - cannot escalate privileges for systemctl")
            raise Exception(f"Command not found: {e}")
    
    def get_status(self):
        """Get current service status from systemctl with comprehensive error handling."""
        # Check system availability first
        if not self.systemctl_path:
            return {
                'status': 'unavailable',
                'uptime': 0,
                'enabled': False,
                'error': 'systemctl not available - systemd not found on this system',
                'pid': None,
                'last_started': None,
                'system_info': {
                    'systemctl_path': None,
                    'use_sudo': self.use_sudo,
                    'service_available': False
                }
            }
        
        try:
            result = self._run_systemctl_command('status', check_output=True)
            
            if result.returncode == 0:
                status = 'running'
            elif result.returncode == 3:
                status = 'stopped'
            elif result.returncode == 4:
                status = 'not-found'
            else:
                status = 'failed'
            
            # Parse output for additional information
            output = result.stdout
            enabled = False
            pid = None
            last_started = None
            uptime = 0
            
            # Extract PID if running
            pid_match = re.search(r'Main PID: (\d+)', output)
            if pid_match and status == 'running':
                pid = int(pid_match.group(1))
            
            # Extract uptime if service is active
            if status == 'running':
                # Look for "Active: active (running) since" line
                for line in output.split('\n'):
                    if 'Active: active' in line and 'since' in line:
                        try:
                            # Extract the timestamp
                            since_part = line.split('since')[1].strip()
                            # Remove any trailing info like "; 1h 23min ago"
                            if ';' in since_part:
                                last_started = since_part.split(';')[0].strip()
                                # Parse uptime from "ago" part
                                if 'ago' in line:
                                    uptime_part = line.split(';')[1].replace('ago', '').strip()
                                    uptime = self._parse_uptime(uptime_part)
                            else:
                                last_started = since_part
                        except (ValueError, IndexError):
                            pass
                        break
            
            # Check if service is enabled
            try:
                enable_result = self._run_systemctl_command('is-enabled', check_output=True)
                enabled = enable_result.returncode == 0 and 'enabled' in enable_result.stdout
            except Exception as e:
                self.logger.warning(f"Could not check service enabled status: {e}")
            
            return {
                'status': status,
                'uptime': uptime,
                'enabled': enabled,
                'pid': pid,
                'last_started': last_started,
                'system_info': {
                    'systemctl_path': self.systemctl_path,
                    'use_sudo': self.use_sudo,
                    'service_available': self.service_available
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            if 'not installed' in error_msg or 'not found' in error_msg:
                status = 'not-installed'
            else:
                status = 'error'
                
            return {
                'status': status,
                'uptime': 0,
                'enabled': False,
                'error': error_msg,
                'pid': None,
                'last_started': None,
                'system_info': {
                    'systemctl_path': self.systemctl_path,
                    'use_sudo': self.use_sudo,
                    'service_available': self.service_available
                }
            }
    
    def _parse_uptime(self, uptime_str):
        """Parse uptime string into seconds."""
        try:
            total_seconds = 0
            
            # Parse different time formats
            if 'day' in uptime_str:
                days = re.search(r'(\d+)\s*day', uptime_str)
                if days:
                    total_seconds += int(days.group(1)) * 86400
            
            if 'h' in uptime_str or 'hour' in uptime_str:
                hours = re.search(r'(\d+)\s*h', uptime_str)
                if not hours:
                    hours = re.search(r'(\d+)\s*hour', uptime_str)
                if hours:
                    total_seconds += int(hours.group(1)) * 3600
            
            if 'min' in uptime_str:
                mins = re.search(r'(\d+)\s*min', uptime_str)
                if mins:
                    total_seconds += int(mins.group(1)) * 60
            
            if 's' in uptime_str and 'min' not in uptime_str:
                secs = re.search(r'(\d+)\s*s', uptime_str)
                if secs:
                    total_seconds += int(secs.group(1))
            
            return total_seconds
        except:
            return 0
    
    def _kill_rtl433(self):
        """Best-effort cleanup of orphaned rtl_433 processes which can block restarts."""
        try:
            cmd = ['pkill', '-f', 'rtl_433']
            if self.use_sudo:
                cmd = ['sudo'] + cmd
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode not in (0, 1):  # 1 = nothing matched
                self.logger.warning(f"pkill rtl_433 returned {result.returncode}: {result.stderr or result.stdout}")
        except Exception as e:
            self.logger.warning(f"Could not clean up rtl_433: {e}")
    
    def start(self):
        """Start Kismet service."""
        try:
            self._run_systemctl_command('start')
            return {'success': True, 'message': 'Kismet service started successfully'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def stop(self):
        """Stop Kismet service."""
        try:
            self._run_systemctl_command('stop')
            return {'success': True, 'message': 'Kismet service stopped successfully'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def restart(self):
        """Restart Kismet service."""
        try:
            # Use explicit stop/start with a cleanup hook to prevent stuck rtl_433 processes
            try:
                self._run_systemctl_command('stop')
            except Exception as stop_err:
                self.logger.warning(f"Ignoring stop error during restart: {stop_err}")
            
            # Clean up any orphaned rtl_433 processes which can hold the SDR open
            self._kill_rtl433()
            
            # Small pause to let sockets/devices release
            time.sleep(0.5)
            
            self._run_systemctl_command('start')
            return {'success': True, 'message': 'Kismet service restarted successfully'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def enable(self):
        """Enable Kismet service for auto-start."""
        try:
            self._run_systemctl_command('enable')
            return {'success': True, 'message': 'Kismet service enabled for auto-start'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def disable(self):
        """Disable Kismet service from auto-start."""
        try:
            self._run_systemctl_command('disable')
            return {'success': True, 'message': 'Kismet service disabled from auto-start'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
