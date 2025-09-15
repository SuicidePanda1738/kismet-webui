import os
import logging
from typing import Dict, List, Any, Optional
import re

class ConfigManager:
    """Manages Kismet configuration files"""
    
    def __init__(self):
        self.config_paths = [
            '/etc/kismet/kismet_site.conf',
            '/home/user/.kismet/kismet_site.conf',
            './kismet_site.conf'
        ]
        # gpsd default configuration locations
        self.gpsd_paths = [
            '/etc/default/gpsd',
            './gpsd'
        ]
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> Dict[str, Any]:
        """Load current Kismet configuration"""
        config = {
            'data_sources': [],
            'gps_config': {
                'enabled': False,
                'type': 'disabled',
                'host': 'localhost',
                'port': 2947,
                'remote_host': '0.0.0.0',
                'remote_port': 4545,
                'lat': '',
                'lon': '',
                'alt': '',
                'mgrs': '',
                'coord_format': 'latlon'
            },
            'logging_config': {
                'log_types': ['kismet', 'pcapng'],
                'log_prefix': '/home/user/kismet',
                'log_title': 'Kismet_Survey',
                'pcapng_log_max_mb': 0,
                'pcapng_log_duplicate_packets': True,
                'pcapng_log_data_packets': True
            },
            'wardrive_mode': False  # Initialize wardrive_mode
        }
        
        # Try to read existing config
        config_loaded = False
        for config_path in self.config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        parsed_config = self._parse_config_file(f.read())
                    # Merge parsed config with defaults
                    config.update(parsed_config)
                    self.logger.info(f"Loaded config from {config_path}, wardrive_mode = {config.get('wardrive_mode', 'NOT SET')}")
                    config_loaded = True
                    break
                except Exception as e:
                    self.logger.error(f"Error reading config from {config_path}: {e}")

        # Parse gpsd defaults to determine remote/local settings
        for gpsd_path in self.gpsd_paths:
            if os.path.exists(gpsd_path):
                try:
                    with open(gpsd_path, 'r') as f:
                        gpsd_parsed = self._parse_gpsd_defaults(f.read())
                    config['gps_config'].update(gpsd_parsed)
                    break
                except Exception as e:
                    self.logger.error(f"Error reading gpsd config from {gpsd_path}: {e}")
        
        # Log final state
        self.logger.info(f"Final config: wardrive_mode = {config.get('wardrive_mode', 'NOT SET')}")
        
        return config

    def _parse_gpsd_defaults(self, content: str) -> Dict[str, Any]:
        """Parse gpsd default configuration"""
        result: Dict[str, Any] = {}
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('DEVICES='):
                devices = line.split('=', 1)[1].strip().strip('"')
                if devices.startswith('udp://'):
                    result['type'] = 'remote'
                    addr = devices[6:]
                    if ':' in addr:
                        host, port = addr.rsplit(':', 1)
                        result['remote_host'] = host
                        try:
                            result['remote_port'] = int(port)
                        except ValueError:
                            pass
                else:
                    result['type'] = 'gpsd'
        return result
    
    def save_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save Kismet configuration"""
        try:
            config_content = self._generate_config_content(config_data)
            gpsd_content = self._generate_gpsd_defaults(config_data)
            
            # Try to write to the first writable location
            for config_path in self.config_paths:
                try:
                    # For system paths, check if parent directory exists
                    if config_path.startswith('/etc/') or config_path.startswith('/usr/'):
                        if not os.path.exists(os.path.dirname(config_path)):
                            self.logger.info(f"Skipping {config_path} - parent directory doesn't exist")
                            continue
                    else:
                        # Ensure directory exists for user paths
                        os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    
                    with open(config_path, 'w') as f:
                        f.write(config_content)

                    self.logger.info(f"Configuration saved to {config_path}")

                    # Save gpsd defaults
                    for gpsd_path in self.gpsd_paths:
                        try:
                            if gpsd_path.startswith('/etc/') and not os.path.exists(os.path.dirname(gpsd_path)):
                                self.logger.info(f"Skipping {gpsd_path} - parent directory doesn't exist")
                                continue
                            with open(gpsd_path, 'w') as gf:
                                gf.write(gpsd_content)
                            self.logger.info(f"gpsd defaults saved to {gpsd_path}")
                            break
                        except PermissionError:
                            self.logger.warning(f"Permission denied for {gpsd_path}")
                            continue
                        except Exception as e:
                            self.logger.error(f"Error writing gpsd config to {gpsd_path}: {e}")
                            continue
                    
                    # If we wrote to a local file but /etc/kismet exists, copy it there too
                    if not config_path.startswith('/etc/') and os.path.exists('/etc/kismet/'):
                        try:
                            import shutil
                            etc_path = '/etc/kismet/kismet_site.conf'
                            shutil.copy2(config_path, etc_path)
                            self.logger.info(f"Configuration also copied to {etc_path}")
                        except Exception as copy_error:
                            self.logger.warning(f"Could not copy to /etc/kismet/: {copy_error}")
                    
                    return {'success': True, 'path': config_path}
                    
                except PermissionError:
                    self.logger.warning(f"Permission denied for {config_path}")
                    continue
                except Exception as e:
                    self.logger.error(f"Error writing config to {config_path}: {e}")
                    continue
            
            self.logger.error("Could not write configuration to any location")
            return {'success': False, 'error': 'Could not write to any location'}
            
        except Exception as e:
            self.logger.error(f"Configuration generation error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _mgrs_to_latlon(self, mgrs_string):
        """Convert MGRS coordinate to lat/lon"""
        try:
            import mgrs
            m = mgrs.MGRS()
            lat, lon = m.toLatLon(mgrs_string)
            return lat, lon
        except ImportError:
            # If mgrs module not available, try pyproj
            try:
                from pyproj import CRS, Transformer
                # This is a simplified conversion - may need refinement
                raise NotImplementedError("MGRS conversion requires mgrs module")
            except:
                raise ValueError("MGRS conversion not available")
    
    def _parse_config_file(self, content: str) -> Dict[str, Any]:
        """Parse Kismet configuration file content"""
        config = {
            'data_sources': [],
            'gps_config': {
                'enabled': False,
                'type': 'disabled',
                'host': 'localhost',
                'port': 2947,
                'remote_host': '0.0.0.0',
                'remote_port': 4545,
                'lat': '',
                'lon': '',
                'alt': ''
            },
            'logging_config': {
                'log_types': ['kismet', 'pcapng'],
                'log_prefix': '/home/user/kismet',
                'log_title': 'Kismet_Survey',
                'pcapng_log_max_mb': 0,
                'pcapng_log_duplicate_packets': True,
                'pcapng_log_data_packets': True
            },
            'wardrive_mode': False  # Initialize wardrive_mode
        }
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Check for wardrive mode state marker
            if line.startswith('# WARDRIVE_MODE='):
                value = line.split('=', 1)[1].strip()
                config['wardrive_mode'] = value == 'True'
                continue
                
            # Skip other comment lines and empty lines
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Parse data sources
                if key == 'source':
                    source = self._parse_source_line(value)
                    if source:
                        config['data_sources'].append(source)
                
                # Parse GPS configuration
                elif key == 'gps':
                    config['gps_config']['enabled'] = True
                    if value.startswith('gpsd:'):
                        config['gps_config']['type'] = 'gpsd'
                        gps_params = value[5:].split(',')
                        for param in gps_params:
                            if param.startswith('host='):
                                config['gps_config']['host'] = param[5:]
                            elif param.startswith('port='):
                                config['gps_config']['port'] = int(param[5:])
                    elif value.startswith('virtual:'):
                        config['gps_config']['type'] = 'virtual'
                        gps_params = value[8:].split(',')
                        for param in gps_params:
                            if param.startswith('lat='):
                                config['gps_config']['lat'] = param[4:]
                            elif param.startswith('lon='):
                                config['gps_config']['lon'] = param[4:]
                            elif param.startswith('alt='):
                                config['gps_config']['alt'] = param[4:]
                
                # Parse logging configuration
                elif key == 'log_types':
                    config['logging_config']['log_types'] = value.split(',')
                elif key == 'log_prefix':
                    config['logging_config']['log_prefix'] = value
                elif key == 'log_title':
                    config['logging_config']['log_title'] = value
                elif key == 'pcapng_log_max_mb':
                    config['logging_config']['pcapng_log_max_mb'] = int(value)
                elif key == 'pcapng_log_duplicate_packets':
                    config['logging_config']['pcapng_log_duplicate_packets'] = value.lower() == 'true'
                elif key == 'pcapng_log_data_packets':
                    config['logging_config']['pcapng_log_data_packets'] = value.lower() == 'true'
                
                # Parse wardriving mode
                elif key == 'dot11_ap_only_survey' and value.lower() == 'true':
                    config['wardrive_mode'] = True
                elif key == 'load_alert' and 'WARDRIVING:' in value:
                    # Additional check for wardriving mode
                    config['wardrive_mode'] = True
        
        return config
    
    def _parse_source_line(self, source_line: str) -> Optional[Dict[str, Any]]:
        """Parse a Kismet source line"""
        try:
            line = source_line.strip()
            if not line:
                return None
            
            # Remove 'source=' prefix if present
            if line.startswith('source='):
                line = line[7:]
            
            # Split on first colon
            if ':' in line:
                prefix, tail = line.split(':', 1)
            else:
                prefix, tail = line, ''
            
            # Parse options from tail
            def parse_opts(t):
                opts = {}
                for chunk in t.split(','):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    if '=' in chunk:
                        k, v = chunk.split('=', 1)
                        opts[k.strip()] = v.strip().strip('"').strip("'")
                    else:
                        opts[chunk] = True
                return opts
            
            opts = parse_opts(tail) if tail else {}
            
            # Determine source type
            pl = prefix.lower()
            if pl.startswith('hci') or 'bluetooth' in pl or opts.get('type', '').lower() == 'bluetooth':
                source_type = 'bluetooth'
            elif pl.startswith('rtl433') or 'rtl433' in pl or opts.get('type', '').lower() == 'rtl433':
                source_type = 'rtl433'
            else:
                source_type = 'wifi'
            
            # Get name from options or use prefix
            name = opts.get('name', prefix)
            
            src = {
                'type': source_type,
                'name': name
            }
            
            if source_type == 'bluetooth':
                # For Bluetooth, prefer device/interface from options, fall back to prefix if it's hci*
                iface = opts.get('device') or opts.get('interface') or opts.get('if') or opts.get('dev')
                if not iface and prefix.lower().startswith('hci'):
                    iface = prefix
                src['interface'] = iface or ''  # Template uses {{ source.interface }}
                
            elif source_type == 'rtl433':
                # For SDR, template uses {{ source.device }}
                dev = opts.get('device') or prefix  # rtl433-0 etc.
                src['device'] = dev
                src['frequency'] = opts.get('channel', opts.get('frequency', ''))
                if 'gain' in opts:
                    src['gain'] = opts['gain']
                if 'ppm_error' in opts:
                    src['ppm_error'] = opts['ppm_error']
                    
            else:
                # WiFi
                src['interface'] = prefix
                src['channel'] = opts.get('channel', '')
                src['channels'] = opts.get('channels', '').strip('"').strip("'")
                
                # Helper to parse boolean values
                def parse_bool(k, default):
                    v = opts.get(k, default)
                    if isinstance(v, str):
                        return v.lower() in ('1', 'true', 'yes', 'on')
                    return bool(v)
                
                src['channel_hop'] = parse_bool('channel_hop', True)
                src['channel_hop_rate'] = opts.get('channel_hop_rate', opts.get('channel_hoprate', '5/sec'))
                src['ht_channels'] = parse_bool('ht_channels', True)
                src['vht_channels'] = parse_bool('vht_channels', True)
                src['band24ghz'] = parse_bool('band24ghz', True)
                src['band5ghz'] = parse_bool('band5ghz', True)
                src['band6ghz'] = parse_bool('band6ghz', False)
            
            return src
            
        except Exception as e:
            self.logger.error(f"Error parsing source line '{source_line}': {e}")
            return None
    
    def _mgrs_to_latlon(self, mgrs_coord: str) -> tuple:
        """Convert MGRS coordinate to latitude/longitude using a simplified approach"""
        try:
            # Remove spaces and convert to uppercase
            mgrs = mgrs_coord.replace(' ', '').upper()
            
            # Basic validation
            if len(mgrs) < 5:
                raise ValueError("MGRS coordinate too short")
            
            # MGRS Format: Grid Zone + Square ID + Easting/Northing
            # Example: 18TWL8040008400 (18T = zone, WL = square, 80400/08400 = coordinates)
            
            # For a simple implementation, we'll parse the basic structure
            # and provide approximate conversion
            
            # Extract grid zone (first 2-3 characters)
            zone_num = ''
            i = 0
            while i < len(mgrs) and mgrs[i].isdigit():
                zone_num += mgrs[i]
                i += 1
            
            if not zone_num:
                raise ValueError("Invalid MGRS format - no zone number")
                
            zone_num = int(zone_num)
            if zone_num < 1 or zone_num > 60:
                raise ValueError(f"Invalid zone number: {zone_num}")
            
            # Zone letter (next character)
            if i >= len(mgrs):
                raise ValueError("Invalid MGRS format - no zone letter")
            zone_letter = mgrs[i]
            i += 1
            
            # Grid square (next 2 letters)
            if i + 1 >= len(mgrs):
                raise ValueError("Invalid MGRS format - no grid square")
            grid_square = mgrs[i:i+2]
            i += 2
            
            # Remaining are easting/northing coordinates
            coords = mgrs[i:]
            if len(coords) % 2 != 0:
                raise ValueError("Invalid MGRS format - odd number of coordinate digits")
            
            precision = len(coords) // 2
            easting = coords[:precision]
            northing = coords[precision:]
            
            # Simplified conversion (approximate)
            # Central meridian for the zone
            central_meridian = (zone_num - 1) * 6 - 180 + 3
            
            # Base latitude from zone letter (simplified)
            zone_letters = 'CDEFGHJKLMNPQRSTUVWXX'  # X repeats for simplicity
            lat_band_idx = zone_letters.index(zone_letter) if zone_letter in zone_letters else 10
            base_lat = -80 + (lat_band_idx * 8)
            
            # Approximate longitude and latitude
            # This is a simplified calculation and won't be perfectly accurate
            if easting:
                lon_offset = (int(easting) / (10 ** len(easting))) * 6 - 3
            else:
                lon_offset = 0
                
            if northing:
                lat_offset = (int(northing) / (10 ** len(northing))) * 8
            else:
                lat_offset = 0
            
            lon = central_meridian + lon_offset
            lat = base_lat + lat_offset
            
            # Clamp values to valid ranges
            lat = max(-90, min(90, lat))
            lon = max(-180, min(180, lon))
            
            self.logger.info(f"Converted MGRS '{mgrs_coord}' to approximately lat={lat}, lon={lon}")
            return (lat, lon)
            
        except Exception as e:
            self.logger.error(f"Error converting MGRS '{mgrs_coord}': {e}")
            # Return default coordinates as fallback
            self.logger.warning("Using default coordinates (40.7128, -74.0060) as fallback")
            return (40.7128, -74.0060)
    
    def _generate_config_content(self, config_data: Dict[str, Any]) -> str:
        """Generate Kismet configuration file content"""
        lines = [
            "# Kismet site configuration file",
            f"# Generated by Kismet Web UI for kismet_site.conf",
            f"# Updated: {os.popen('date').read().strip()}",
            "",
            "# Copy this file to /etc/kismet/kismet_site.conf to override default settings",
            ""
        ]
        
        # Check if wardriving mode is enabled and add state marker
        wardrive_mode = config_data.get('wardrive_mode', False)
        lines.append(f"# WARDRIVE_MODE={wardrive_mode}")
        lines.append("")
        
        if wardrive_mode:
            lines.extend([
                "# WARDRIVING MODE ENABLED",
                "# This configuration is optimized for basic AP collection",
                "load_alert=WARDRIVING:Kismet is in survey/wardriving mode. This turns off tracking non-AP devices and most packet logging.",
                "",
                "# Wardriving optimizations",
                "dot11_ap_only_survey=true",
                "dot11_fingerprint_devices=false",
                "dot11_keep_ietags=false",
                "dot11_keep_eapol=false",
                "kis_log_channel_history=false",
                "kis_log_datasources=false",
                "",
                "# Enable management frame filter for better performance",
                "dot11_datasource_opt=filter_mgmt,true",
                "",
                "# Force disable HT/VHT channels on all sources",
                "dot11_datasource_opt=ht_channels,false",
                "dot11_datasource_opt=vht_channels,false",
                "dot11_datasource_opt=default_ht20,false",
                "dot11_datasource_opt=expand_ht20,false",
                ""
            ])
        
        # Data Sources Configuration
        if config_data.get('data_sources'):
            lines.append("# Data Sources Configuration")
            for source in config_data['data_sources']:
                source_line = self._generate_source_line(source)
                if source_line:
                    lines.append(f"source={source_line}")
            lines.append("")
        
        # GPS Configuration
        lines.append('# GPS Configuration')
        
        # GPS settings
        gps_type = config_data.get('gps_type', 'disabled')
        if gps_type in ('gpsd', 'remote'):
            gps_host = config_data.get('gps_host', 'localhost')
            gps_port = config_data.get('gps_port', '2947')
            lines.append(f'gps=gpsd:host={gps_host},port={gps_port}')
        elif gps_type == 'virtual':
            # Handle virtual GPS with lat/lon or MGRS
            coord_format = config_data.get('coord_format', 'latlon')
            if coord_format == 'mgrs':
                # Convert MGRS to lat/lon for Kismet
                mgrs_coord = config_data.get('gps_mgrs', '')
                alt = config_data.get('gps_alt_mgrs', '0')
                if mgrs_coord:
                    try:
                        lat, lon = self._mgrs_to_latlon(mgrs_coord)
                        lines.append(f'gps=virtual:lat={lat},lon={lon},alt={alt}')
                    except Exception as e:
                        self.logger.error(f"MGRS conversion error: {e}")
                        lines.append('# Invalid MGRS coordinate provided')
                else:
                    lines.append('# Virtual GPS enabled but no MGRS coordinate provided')
            else:
                # Use lat/lon directly
                lat = config_data.get('gps_lat', '')
                lon = config_data.get('gps_lon', '')
                # Try both gps_alt and gps_alt_mgrs fields
                alt = config_data.get('gps_alt') or config_data.get('gps_alt_mgrs') or '0'
                if lat and lon:
                    lines.append(f'gps=virtual:lat={lat},lon={lon},alt={alt}')
                else:
                    lines.append('# Virtual GPS enabled but coordinates not provided')
        else:
            lines.append('# GPS disabled')
        
        lines.append("")
        
        # Logging Configuration
        logging_config = config_data.get('logging_config', {})
        log_types = logging_config.get('log_types', ['kismet', 'pcapng'])
        
        # If wardriving mode is enabled, ensure wiglecsv is in log types
        if wardrive_mode and 'wiglecsv' not in log_types:
            log_types.append('wiglecsv')
        
        # Ensure log directory exists
        log_prefix = logging_config.get('log_prefix', '/home/user/kismet')
        try:
            os.makedirs(log_prefix, exist_ok=True)
            self.logger.info(f"Ensured log directory exists: {log_prefix}")
        except Exception as e:
            self.logger.warning(f"Could not create log directory {log_prefix}: {e}")
        
        lines.extend([
            "# Logging Configuration",
            f"log_types={','.join(log_types)}",
            f"log_prefix={log_prefix}",
            f"log_title={logging_config.get('log_title', 'Kismet_Wireless_Survey')}",
            f"logname=kismet",
            "",
            "# PCAP-NG Configuration",
            f"pcapng_log_max_mb={logging_config.get('pcapng_log_max_mb', 0)}",
            f"pcapng_log_duplicate_packets={'true' if logging_config.get('pcapng_log_duplicate_packets', True) else 'false'}",
            f"pcapng_log_data_packets={'true' if logging_config.get('pcapng_log_data_packets', True) else 'false'}",
            "channel_hop=true",
            "channel_hop_speed=5/sec",
            "",
            "# Device Detection & Alert Configuration",
            "kis_log_device_filter_default=pass"
        ])
        
        # Add device alerts if configured
        device_alerts = config_data.get('device_alerts', {})
        if device_alerts.get('device_found_macs'):
            lines.append("# Device Found Alerts")
            for mac in device_alerts['device_found_macs']:
                if mac.strip():
                    lines.append(f"devicefound={mac.strip()}")
        
        if device_alerts.get('device_lost_macs'):
            lines.append("# Device Lost Alerts")
            for mac in device_alerts['device_lost_macs']:
                if mac.strip():
                    lines.append(f"devicelost={mac.strip()}")
        
        if device_alerts.get('device_found_timeout'):
            lines.append(f"devicefound_timeout={device_alerts['device_found_timeout']}")
        if device_alerts.get('device_lost_timeout'):
            lines.append(f"devicelost_timeout={device_alerts['device_lost_timeout']}")
        
        lines.extend([
            "",
            "# Device Filtering Configuration",
            ""
        ])
        
        return '\n'.join(lines)

    def _generate_gpsd_defaults(self, config_data: Dict[str, Any]) -> str:
        """Generate /etc/default/gpsd content"""
        gps_type = config_data.get('gps_type', 'disabled')
        if gps_type == 'remote':
            host = config_data.get('gps_remote_host', '0.0.0.0')
            port = config_data.get('gps_remote_port', '4545')
            devices = f'udp://{host}:{port}'
        else:
            devices = '/dev/ttyUSB0 /dev/ttyACM0'

        lines = [
            'START_DAEMON="true"',
            'USBAUTO="true"',
            'GPSD_OPTIONS="-n"',
            f'DEVICES="{devices}"'
        ]
        return '\n'.join(lines) + '\n'

    
    def _generate_source_line(self, source: Dict[str, Any]) -> Optional[str]:
        """Generate a Kismet source line from source configuration"""
        try:
            source_type = source.get('type', 'wifi')
            # For rtl433, use 'device' field; for others use 'interface'
            if source_type == 'rtl433':
                interface = source.get('device', '')
            else:
                interface = source.get('interface', '')
            name = source.get('name', interface)
            
            if not interface:
                return None
            
            if source_type == 'rtl433':
                # RTL433 SDR source - use comma-separated format
                parts = [interface]
                params = []
                
                # Add type first
                params.append("type=rtl433")
                
                # Add other parameters
                if source.get('frequency'):
                    params.append(f"channel={source['frequency']}")
                if name and name != interface:
                    params.append(f"name={name}")
                if source.get('gain'):
                    params.append(f"gain={source['gain']}")
                if source.get('ppm_error'):
                    params.append(f"ppm_error={source['ppm_error']}")
                
                # Join with comma for rtl433 format
                if params:
                    return f"{interface}:{','.join(params)}"
                return interface
            
            elif source_type == 'bluetooth':
                # Bluetooth source - use actual interface
                iface = source.get('interface', interface)
                if iface and iface.startswith('hci'):
                    # If we have hci0, hci1, etc., use it as prefix
                    parts = [iface]
                    if name != iface:
                        parts.append(f"name={name}")
                else:
                    # Otherwise use bluetooth prefix with device option
                    parts = ['bluetooth']
                    options = []
                    if iface:
                        options.append(f"device={iface}")
                    if name != 'bluetooth':
                        options.append(f"name={name}")
                    if options:
                        parts.append(','.join(options))
                
                return ':'.join(parts)
            
            else:
                # WiFi source (default)
                parts = [interface]
                options = []
                
                if name != interface:
                    options.append(f"name={name}")
                
                # Channel hopping options
                if not source.get('channel_hop', True):
                    options.append('channel_hop=false')
                else:
                    hop_rate = source.get('channel_hop_rate', '5/sec')
                    if hop_rate and hop_rate != '5/sec':
                        # Use channel_hoprate (no underscore) for Kismet compatibility
                        options.append(f'channel_hoprate={hop_rate}')
                
                # Fixed channel
                channel = source.get('channel', '')
                if channel:
                    options.append(f'channel={channel}')
                    if source.get('channel_hop', True):
                        options.append('channel_hop=false')
                
                # Channel list
                channels = source.get('channels', '')
                if channels:
                    options.append(f'channels="{channels}"')
                
                # Band restrictions first - only add if enabled (Kismet's format)
                if source.get('band24ghz', True):
                    options.append('band24ghz=true')
                if source.get('band5ghz', True):
                    options.append('band5ghz=true')
                if source.get('band6ghz', False):
                    options.append('band6ghz=true')
                
                # HT/VHT options after bands
                if not source.get('ht_channels', True):
                    options.append('ht_channels=false')
                
                if not source.get('vht_channels', True):
                    options.append('vht_channels=false')
                
                # Combine interface and options
                if options:
                    return f"{interface}:{','.join(options)}"
                return interface
                
        except Exception as e:
            self.logger.error(f"Error generating source line for {source}: {e}")
            return None
