import os
import json
import subprocess
import zipfile
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
# Import models inside functions to avoid circular import
from config_manager import ConfigManager
from device_detector import DeviceDetector
from service_manager import KismetServiceManager

config_manager = ConfigManager()
device_detector = DeviceDetector()
service_manager = KismetServiceManager()
ALLOWED_EXTENSIONS = (
    '.wiglecsv',
    '.pcapppi',
    '.pcapng',
    '.kismet',
    '.kismet-journal',
    '.kml'
)

def setup():
    """Initial setup to create the first user"""
    from models import User
    # If a user already exists, redirect to login
    if User.query.first() is not None:
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('User created successfully.', 'success')
            return redirect(url_for('index'))
        flash('Username and password are required.', 'error')
    return render_template('setup.html')

if 'setup' not in app.view_functions:
    app.add_url_rule('/setup', 'setup', setup, methods=['GET', 'POST'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    from models import User
    # Redirect to setup if no users exist yet
    if User.query.first() is None:
        return redirect(url_for('setup'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """Allow the logged-in user to change username and password"""
    from models import User
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username:
            flash('Username is required.', 'error')
            return redirect(url_for('account'))
        existing = User.query.filter(User.username == username, User.id != current_user.id).first()
        if existing:
            flash('Username already taken.', 'error')
            return redirect(url_for('account'))
        current_user.username = username
        if password:
            current_user.set_password(password)
        db.session.commit()
        flash('Account updated successfully.', 'success')
        return redirect(url_for('account'))
    return render_template('account.html')

@app.route('/')
@login_required
def index():
    """Dashboard with service status and recent files"""
    service_status = service_manager.get_status()
    system_info = {'kismet_info': service_status, 'network_info': {}}
    recommendations = []
    recent_files = get_recent_files(limit=5)
    
    return render_template('index.html', 
                         service_status=service_status,
                         system_info=system_info,
                         recommendations=recommendations,
                         recent_files=recent_files)

@app.route('/config')
@login_required
def config():
    """Configuration page with device detection"""
    # Get current configuration
    current_config = config_manager.load_config()
    
    # Debug logging
    app.logger.debug(f"Loaded config: wardrive_mode = {current_config.get('wardrive_mode', 'NOT SET')}")
    
    return render_template('config.html', 
                         current_config=current_config)

@app.route('/config', methods=['POST'])
@login_required
def save_config():
    """Save Kismet configuration"""
    try:
        # Extract form data
        data_sources = []
        
        # Handle WiFi sources
        wifi_interfaces = request.form.getlist('wifi_interface')
        wifi_names = request.form.getlist('wifi_name')
        wifi_channel_hops = request.form.getlist('wifi_channel_hop')
        wifi_channels = request.form.getlist('wifi_channel')
        wifi_channel_lists = request.form.getlist('wifi_channels')
        wifi_hop_speeds = request.form.getlist('wifi_hop_speed')
        wifi_ht_channels = request.form.getlist('wifi_ht_channels')
        wifi_vht_channels = request.form.getlist('wifi_vht_channels')
        wifi_band24ghz = request.form.getlist('wifi_band24ghz')
        wifi_band5ghz = request.form.getlist('wifi_band5ghz')
        wifi_band6ghz = request.form.getlist('wifi_band6ghz')
        
        for i, (interface, name) in enumerate(zip(wifi_interfaces, wifi_names)):
            if interface.strip():
                data_sources.append({
                    'type': 'wifi',
                    'interface': interface.strip(),
                    'name': name.strip() or interface.strip(),
                    'channel_hop': str(i) in wifi_channel_hops,
                    'channel': wifi_channels[i] if i < len(wifi_channels) else '',
                    'channels': wifi_channel_lists[i] if i < len(wifi_channel_lists) else '',
                    'channel_hop_rate': wifi_hop_speeds[i] if i < len(wifi_hop_speeds) else '5/sec',
                    'ht_channels': str(i) in wifi_ht_channels,
                    'vht_channels': str(i) in wifi_vht_channels,
                    'band24ghz': str(i) in wifi_band24ghz,
                    'band5ghz': str(i) in wifi_band5ghz,
                    'band6ghz': str(i) in wifi_band6ghz
                })
        
        # Handle Bluetooth sources
        bt_interfaces = request.form.getlist('bt_interface')
        bt_names = request.form.getlist('bt_name')
        
        for interface, name in zip(bt_interfaces, bt_names):
            if interface.strip():
                data_sources.append({
                    'type': 'bluetooth',
                    'interface': interface.strip(),
                    'name': name.strip() or interface.strip()
                })
        
        # Handle SDR RTL433 sources
        sdr_devices = request.form.getlist('sdr_device')
        sdr_names = request.form.getlist('sdr_name')
        sdr_frequencies = request.form.getlist('sdr_frequency')
        sdr_gains = request.form.getlist('sdr_gain')
        sdr_ppm_errors = request.form.getlist('sdr_ppm_error')
        
        for device, name, freq, gain, ppm in zip(sdr_devices, sdr_names, sdr_frequencies, sdr_gains, sdr_ppm_errors):
            if device.strip():
                sdr_source = {
                    'type': 'rtl433',
                    'device': device.strip(),
                    'name': name.strip() or f"rtl433-{device.strip()}",
                    'frequency': freq.strip() or '433.920MHz'
                }
                if gain.strip():
                    sdr_source['gain'] = gain.strip()
                if ppm.strip():
                    sdr_source['ppm_error'] = ppm.strip()
                data_sources.append(sdr_source)
        
        # GPS Configuration
        gps_config = {
            'gps_type': request.form.get('gps_type', 'disabled'),
            'gps_host': request.form.get('gps_host', 'localhost'),
            'gps_port': request.form.get('gps_port', '2947'),
            'gps_device': request.form.get('gps_device', 'all'),
            'gps_remote_host': request.form.get('gps_remote_host', '0.0.0.0'),
            'gps_remote_port': request.form.get('gps_remote_port', '4545'),
            'coord_format': request.form.get('coord_format', 'latlon'),
            'gps_lat': request.form.get('gps_lat', ''),
            'gps_lon': request.form.get('gps_lon', ''),
            'gps_alt': request.form.get('gps_alt', '0'),
            'gps_alt_mgrs': request.form.get('gps_alt_mgrs', '0'),
            'gps_mgrs': request.form.get('gps_mgrs', '')
        }
        
        # Logging Configuration
        logging_config = {
            'log_types': request.form.getlist('log_types'),
            'log_prefix': request.form.get('log_prefix', '/home/user/kismet'),
            'log_title': request.form.get('log_title', 'Kismet_Wireless_Survey'),
            'pcapng_log_max_mb': int(request.form.get('pcapng_log_max_mb', 0)),
            'pcapng_log_duplicate_packets': request.form.get('pcapng_log_duplicate_packets') == 'on',
            'pcapng_log_data_packets': request.form.get('pcapng_log_data_packets') == 'on'
        }
        
        # Device Alerts Configuration
        device_alerts = {
            'device_found_macs': [mac.strip() for mac in request.form.get('device_found_alerts', '').splitlines() if mac.strip()],
            'device_lost_macs': [mac.strip() for mac in request.form.get('device_lost_alerts', '').splitlines() if mac.strip()],
            'device_found_timeout': request.form.get('device_found_timeout', '30'),
            'device_lost_timeout': request.form.get('device_lost_timeout', '30')
        }
        
        # Wardriving mode
        wardrive_mode = request.form.get('wardrive_mode') == 'on'
        
        # Save configuration - merge all config data
        config_data = {
            'data_sources': data_sources,
            'device_alerts': device_alerts,
            'wardrive_mode': wardrive_mode,
            'logging_config': logging_config,  # Keep as nested dict
            **gps_config  # Flatten GPS config into main config
        }
        
        result = config_manager.save_config(config_data)
        
        if result['success']:
            config_path = result.get('path', 'unknown location')
            flash(f'Configuration saved successfully to {config_path}!', 'success')
            
            # Automatically restart Kismet service after successful configuration save
            try:
                restart_result = service_manager.restart()
                if restart_result['success']:
                    flash('Kismet service restarted successfully to apply new configuration', 'success')
                else:
                    flash(f'Configuration saved but service restart failed: {restart_result["message"]}', 'warning')
            except Exception as restart_error:
                flash(f'Configuration saved but service restart failed: {str(restart_error)}', 'warning')
        else:
            flash('Failed to save configuration. Please check file permissions.', 'error')
            
    except Exception as e:
        app.logger.error(f"Error saving configuration: {e}")
        flash(f'Error saving configuration: {str(e)}', 'error')
    
    return redirect(url_for('config'))

@app.route('/api/detect-devices')
@login_required
def api_detect_devices():
    """AJAX endpoint for device detection"""
    device_type = request.args.get('type', 'all')
    
    try:
        if device_type == 'wifi':
            devices = device_detector.detect_wifi_interfaces()
        elif device_type == 'bluetooth':
            devices = device_detector.detect_bluetooth_interfaces()
        elif device_type == 'sdr':
            devices = device_detector.detect_sdr_devices()
        else:
            devices = {
                'wifi': device_detector.detect_wifi_interfaces(),
                'bluetooth': device_detector.detect_bluetooth_interfaces(),
                'sdr': device_detector.detect_sdr_devices()
            }
        
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        app.logger.error(f"Device detection error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/service/<action>')
@login_required
def service_control(action):
    """Control Kismet service"""
    try:
        if action == 'start':
            result = service_manager.start()
        elif action == 'stop':
            result = service_manager.stop()
        elif action == 'restart':
            result = service_manager.restart()
        elif action == 'enable':
            result = service_manager.enable()
        elif action == 'disable':
            result = service_manager.disable()
        else:
            flash('Invalid action', 'error')
            return redirect(url_for('index'))
        
        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'error')
            
    except Exception as e:
        app.logger.error(f"Service control error: {e}")
        flash(f'Service control error: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/system/<action>')
@login_required
def system_control(action):
    """Control system (device shutdown/restart)"""
    import subprocess
    import time
    
    try:
        # Log the system control attempt
        app.logger.info(f"System control request: {action} by user")
        
        if action == 'shutdown':
            # Check if we have necessary privileges
            try:
                current_user = subprocess.run(['whoami'], capture_output=True, text=True).stdout.strip()
            except:
                current_user = 'unknown'
            
            if os.geteuid() == 0:  # Running as root
                app.logger.warning("Initiating system shutdown as root user")
                flash('System shutdown initiated. The device will power off in 10 seconds.', 'warning')
                # Give time for the response to be sent before shutdown
                subprocess.Popen(['nohup', 'sh', '-c', 'sleep 2 && shutdown -h now'], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            else:
                # Try with sudo (passwordless sudo required)
                try:
                    # Test if sudo is available without password
                    subprocess.run(['sudo', '-n', 'true'], check=True, capture_output=True)
                    app.logger.warning(f"Initiating system shutdown as {current_user} with sudo")
                    flash('System shutdown initiated. The device will power off in 10 seconds.', 'warning')
                    subprocess.Popen(['sudo', 'nohup', 'sh', '-c', 'sleep 2 && shutdown -h now'], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except subprocess.CalledProcessError:
                    app.logger.error(f"Failed to shutdown - insufficient privileges for user {current_user}")
                    flash('Cannot shutdown device: Administrator privileges required. Please run as root or configure passwordless sudo.', 'error')
                    
        elif action == 'restart':
            # Check if we have necessary privileges
            try:
                current_user = subprocess.run(['whoami'], capture_output=True, text=True).stdout.strip()
            except:
                current_user = 'unknown'
            
            if os.geteuid() == 0:  # Running as root
                app.logger.warning("Initiating system restart as root user")
                flash('System restart initiated. The device will reboot in 10 seconds.', 'warning')
                # Give time for the response to be sent before reboot
                subprocess.Popen(['nohup', 'sh', '-c', 'sleep 2 && shutdown -r now'], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            else:
                # Try with sudo (passwordless sudo required)
                try:
                    # Test if sudo is available without password
                    subprocess.run(['sudo', '-n', 'true'], check=True, capture_output=True)
                    app.logger.warning(f"Initiating system restart as {current_user} with sudo")
                    flash('System restart initiated. The device will reboot in 10 seconds.', 'warning')
                    subprocess.Popen(['sudo', 'nohup', 'sh', '-c', 'sleep 2 && shutdown -r now'], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except subprocess.CalledProcessError:
                    app.logger.error(f"Failed to restart - insufficient privileges for user {current_user}")
                    flash('Cannot restart device: Administrator privileges required. Please run as root or configure passwordless sudo.', 'error')
        else:
            flash('Invalid system action', 'error')
            
    except FileNotFoundError as e:
        app.logger.error(f"System control command not found: {e}")
        flash('System control commands not available on this platform.', 'error')
    except Exception as e:
        app.logger.error(f"System control error: {e}")
        flash(f'System control error: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/files')
@login_required
def files():
    """File management page"""
    config = config_manager.load_config()
    default_directory = config.get('logging_config', {}).get('log_prefix', '/home/user/kismet')
    default_directory = os.path.abspath(default_directory)

    requested = request.args.get('directory')
    if requested:
        requested_path = os.path.abspath(requested)
        if os.path.commonpath([requested_path, default_directory]) == default_directory:
            current_directory = requested_path
        else:
            current_directory = default_directory
    else:
        current_directory = default_directory

    files_list = get_files_from_directory(current_directory)

    return render_template('files.html',
                         files=files_list,
                         current_directory=current_directory,
                         default_directory=default_directory)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Download a specific file"""
    try:
        if not filename.endswith(ALLOWED_EXTENSIONS):
            abort(404)

        config = config_manager.load_config()
        root_dir = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))
        file_path = os.path.abspath(os.path.join(root_dir, filename))

        if not file_path.startswith(root_dir) or not os.path.isfile(file_path):
            abort(404)

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        app.logger.error(f"File download error: {e}")
        abort(500)

@app.route('/delete-file', methods=['POST'])
@login_required
def delete_file():
    """Delete a specific file"""
    filename = request.form.get('filename')
    directory = request.form.get('directory')

    if not filename or not directory:
        flash('Missing filename or directory', 'error')
        return redirect(url_for('files'))
    config = config_manager.load_config()
    root_dir = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))
    file_path = os.path.abspath(os.path.join(directory, filename))

    if not file_path.startswith(root_dir) or not filename.endswith(ALLOWED_EXTENSIONS):
        flash('Invalid file path', 'error')
        return redirect(url_for('files'))

    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            flash(f'File {filename} deleted successfully', 'success')
        else:
            flash(f'File {filename} not found', 'error')
    except Exception as e:
        app.logger.error(f"File deletion error: {e}")
        flash(f'Error deleting file: {str(e)}', 'error')
    
    return redirect(url_for('files'))

@app.route('/delete-all-files', methods=['POST'])
@login_required
def delete_all_files():
    """Delete all files in directory"""
    directory = request.form.get('directory')
    confirm_text = request.form.get('confirm_text')

    if confirm_text != 'yes':
        flash('Deletion cancelled - confirmation text did not match', 'error')
        return redirect(url_for('files'))

    config = config_manager.load_config()
    root_dir = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))
    target_dir = os.path.abspath(directory) if directory else root_dir

    if os.path.commonpath([target_dir, root_dir]) != root_dir:
        flash('Invalid directory', 'error')
        return redirect(url_for('files'))

    try:
        if os.path.exists(target_dir):
            deleted_count = 0
            for filename in os.listdir(target_dir):
                if not filename.endswith(ALLOWED_EXTENSIONS):
                    continue
                file_path = os.path.join(target_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1

            flash(f'Successfully deleted {deleted_count} files', 'success')
        else:
            flash('Directory not found', 'error')
    except Exception as e:
        app.logger.error(f"Bulk file deletion error: {e}")
        flash(f'Error deleting files: {str(e)}', 'error')
    
    return redirect(url_for('files'))

@app.route('/vacuum-logs', methods=['POST'])
@login_required
def vacuum_logs():
    """Create archive of log files"""
    try:
        config = config_manager.load_config()
        log_dir = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f'kismet_logs_{timestamp}.zip'
        archive_path = os.path.join(log_dir, archive_name)

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in os.listdir(log_dir):
                if filename == archive_name or not filename.endswith(ALLOWED_EXTENSIONS):
                    continue
                file_path = os.path.join(log_dir, filename)
                if os.path.isfile(file_path):
                    zipf.write(file_path, filename)

        flash(f'Created archive: {archive_name}', 'success')
    except Exception as e:
        app.logger.error(f"Archive creation error: {e}")
        flash(f'Error creating archive: {str(e)}', 'error')
    
    return redirect(url_for('files'))

@app.route('/remote-push')
@login_required
def remote_push():
    """Remote push configuration page"""
    from models import PushService
    from push_service_manager import push_service_manager
    
    # Update service statuses from actual running state
    services = PushService.query.all()
    for service in services:
        actual_status = push_service_manager.get_service_status(service.name)
        if actual_status != service.status:
            service.status = actual_status
            db.session.commit()
    
    return render_template('remote_push.html', services=services)

@app.route('/create-wifi-push', methods=['POST'])
@login_required
def create_wifi_push():
    """Create WiFi push service"""
    try:
        from models import PushService
        from push_service_manager import push_service_manager
        
        name = f"kismet-wifi-push-{request.form.get('wifi_sensor')}"
        
        # Create database entry
        service = PushService()
        service.name = name
        service.service_type = 'WiFi + GPS'
        service.adapter = request.form.get('wifi_adapter')
        service.sensor = request.form.get('wifi_sensor')
        service.kismet_ip = request.form.get('kismet_ip')
        service.api_key = request.form.get('api_key')
        service.gps_api_key = request.form.get('gps_api_key')
        
        db.session.add(service)
        db.session.commit()
        
        # Create the actual service script
        service_data = {
            'name': name,
            'service_type': 'WiFi',
            'adapter': service.adapter,
            'sensor': service.sensor,
            'kismet_ip': service.kismet_ip,
            'api_key': service.api_key,
            'gps_api_key': service.gps_api_key
        }
        push_service_manager.create_push_service_script(service_data)
        
        # Start the service
        result = push_service_manager.start_push_service(name)
        if result['success']:
            service.status = 'running'
            db.session.commit()
            flash(f'WiFi push service {name} created and started successfully', 'success')
        else:
            flash(f'WiFi push service {name} created but failed to start: {result["message"]}', 'warning')
            
    except Exception as e:
        app.logger.error(f"WiFi push service creation error: {e}")
        flash(f'Error creating WiFi push service: {str(e)}', 'error')
    
    return redirect(url_for('remote_push'))

@app.route('/create-bluetooth-push', methods=['POST'])
@login_required
def create_bluetooth_push():
    """Create Bluetooth push service"""
    try:
        from models import PushService
        from push_service_manager import push_service_manager
        
        name = f"kismet-bt-push-{request.form.get('bt_sensor')}"
        
        # Create database entry
        service = PushService()
        service.name = name
        service.service_type = 'Bluetooth'
        service.adapter = request.form.get('bt_device')
        service.sensor = request.form.get('bt_sensor')
        service.kismet_ip = request.form.get('kismet_ip')
        service.api_key = request.form.get('api_key')
        
        db.session.add(service)
        db.session.commit()
        
        # Create the actual service script
        service_data = {
            'name': name,
            'service_type': 'Bluetooth',
            'adapter': service.adapter,
            'sensor': service.sensor,
            'kismet_ip': service.kismet_ip,
            'api_key': service.api_key
        }
        push_service_manager.create_push_service_script(service_data)
        
        # Start the service
        result = push_service_manager.start_push_service(name)
        if result['success']:
            service.status = 'running'
            db.session.commit()
            flash(f'Bluetooth push service {name} created and started successfully', 'success')
        else:
            flash(f'Bluetooth push service {name} created but failed to start: {result["message"]}', 'warning')
            
    except Exception as e:
        app.logger.error(f"Bluetooth push service creation error: {e}")
        flash(f'Error creating Bluetooth push service: {str(e)}', 'error')
    
    return redirect(url_for('remote_push'))

@app.route('/control-push-service', methods=['POST'])
@login_required
def control_push_service():
    """Control push service"""
    service_name = request.form.get('service_name')
    action = request.form.get('action')
    
    try:
        from models import PushService
        from push_service_manager import push_service_manager
        
        # Get service from database
        service = PushService.query.filter_by(name=service_name).first()
        if not service:
            flash(f'Service {service_name} not found', 'error')
            return redirect(url_for('remote_push'))
        
        # Perform the action
        if action == 'start':
            # Recreate the service script in case it was deleted
            service_data = {
                'name': service.name,
                'service_type': 'WiFi' if 'wifi' in service.name else 'Bluetooth',
                'adapter': service.adapter,
                'sensor': service.sensor,
                'kismet_ip': service.kismet_ip,
                'api_key': service.api_key
            }
            if hasattr(service, 'gps_api_key') and service.gps_api_key:
                service_data['gps_api_key'] = service.gps_api_key
            
            push_service_manager.create_push_service_script(service_data)
            result = push_service_manager.start_push_service(service_name)
            
            if result['success']:
                service.status = 'running'
                db.session.commit()
                flash(result['message'], 'success')
            else:
                flash(result['message'], 'error')
                
        elif action == 'stop':
            result = push_service_manager.stop_push_service(service_name)
            if result['success']:
                service.status = 'stopped'
                db.session.commit()
                flash(result['message'], 'success')
            else:
                flash(result['message'], 'error')
                
        elif action == 'restart':
            result = push_service_manager.restart_push_service(service_name)
            if result['success']:
                service.status = 'running'
                db.session.commit()
                flash(f'Service {service_name} restarted successfully', 'success')
            else:
                flash(f'Failed to restart service: {result["message"]}', 'error')
                
    except Exception as e:
        app.logger.error(f"Push service control error: {e}")
        flash(f'Error controlling service: {str(e)}', 'error')
    
    return redirect(url_for('remote_push'))

@app.route('/remove-push-service', methods=['POST'])
@login_required
def remove_push_service():
    """Remove push service"""
    service_name = request.form.get('service_name')
    
    try:
        from models import PushService
        from push_service_manager import push_service_manager
        import os
        
        # Stop the service first
        push_service_manager.stop_push_service(service_name)
        
        # Remove the script file
        script_file = f"push_services/{service_name}.sh"
        if os.path.exists(script_file):
            os.remove(script_file)
            app.logger.info(f"Removed script file: {script_file}")
        
        # Remove the PID file if it exists
        pid_file = f"push_services/{service_name}.pid"
        if os.path.exists(pid_file):
            os.remove(pid_file)
            app.logger.info(f"Removed PID file: {pid_file}")
        
        # Remove from database
        service = PushService.query.filter_by(name=service_name).first()
        if service:
            db.session.delete(service)
            db.session.commit()
            flash(f'Service {service_name} removed successfully', 'success')
        else:
            flash(f'Service {service_name} not found', 'error')
    except Exception as e:
        app.logger.error(f"Push service removal error: {e}")
        flash(f'Error removing service: {str(e)}', 'error')
    
    return redirect(url_for('remote_push'))

@app.route('/system-info')
@login_required
def system_info():
    """System information page"""
    from system_detector import detector
    
    # Get comprehensive system information
    capabilities = detector.get_system_capabilities()
    
    # Restructure network data for template compatibility
    if 'network' in capabilities:
        capabilities['network_info'] = capabilities['network']
        # Keep backward compatibility
        capabilities['network'] = capabilities['network'].get('interfaces', {})
    else:
        # Ensure network_info exists with default values
        capabilities['network_info'] = {
            'capable': False,
            'bluetooth_count': 0,
            'wifi_count': 0,
            'tools': {},
            'interfaces': {'wifi': [], 'bluetooth': [], 'all': []}
        }
    
    # Add kismet service status
    capabilities['kismet_info'] = service_manager.get_status()
    
    # Generate recommendations based on system state
    recommendations = []
    
    if not capabilities['systemd']['available']:
        recommendations.append({
            'type': 'warning',
            'title': 'SystemD Not Available',
            'message': 'SystemD is not available on this system. Service management will be limited.'
        })
    
    if not capabilities['kismet']['installed']:
        recommendations.append({
            'type': 'danger',
            'title': 'Kismet Not Installed',
            'message': 'Kismet is not installed on this system. Please install Kismet to use this interface.'
        })
    
    if not capabilities['privileges']['can_manage_services']:
        recommendations.append({
            'type': 'warning',
            'title': 'Limited Privileges',
            'message': 'Current user cannot manage services. Run with sudo for full functionality.'
        })
    
    return render_template('system_info.html',
                         system_info=capabilities,
                         recommendations=recommendations)

def get_recent_files(limit=10):
    """Get recent files from Kismet directories"""
    files = []
    config = config_manager.load_config()
    directory = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))

    if os.path.exists(directory):
        try:
            for filename in os.listdir(directory):
                if not filename.endswith(ALLOWED_EXTENSIONS):
                    continue
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    stat = os.stat(file_path)
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'directory': directory
                    })
        except PermissionError:
            pass

    files.sort(key=lambda x: x['modified'], reverse=True)
    return files[:limit]

def get_files_from_directory(directory):
    """Get files from a specific directory"""
    files = []

    if not os.path.exists(directory):
        return files

    try:
        for filename in os.listdir(directory):
            if not filename.endswith(ALLOWED_EXTENSIONS):
                continue
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'directory': directory,
                    'source': get_directory_source(directory)
                })
    except PermissionError:
        pass

    return files

def get_directory_source(directory):
    """Get human-readable source for directory"""
    if 'user' in directory:
        return 'User Directory'
    elif 'var/log' in directory:
        return 'System Directory'
    elif 'tmp' in directory:
        return 'Temp Directory'
    else:
        return 'Other'

@app.route('/convert-to-kml', methods=['POST'])
@login_required
def convert_to_kml():
    """Convert a kismet file to KML format"""
    try:
        app.logger.info("KML conversion request received")
        
        # Get JSON data with better error handling
        if not request.is_json:
            app.logger.error("Request is not JSON")
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
            
        data = request.get_json(force=True)
        if not data:
            app.logger.error("No JSON data in request")
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
            
        filename = data.get('filename')
        directory = data.get('directory', '')

        app.logger.info(f"Converting file: {filename} in directory: {directory}")

        if not filename:
            return jsonify({'success': False, 'error': 'Missing filename'}), 400

        if not filename.endswith('.kismet'):
            return jsonify({'success': False, 'error': 'Only .kismet files can be converted to KML'}), 400

        config = config_manager.load_config()
        root_dir = os.path.abspath(config.get('logging_config', {}).get('log_prefix', '/home/user/kismet'))
        dir_path = os.path.abspath(directory) if directory else root_dir
        if os.path.commonpath([dir_path, root_dir]) != root_dir:
            return jsonify({'success': False, 'error': 'Invalid directory'}), 400

        input_path = os.path.join(dir_path, filename)
        output_filename = filename.replace('.kismet', '.kml')
        output_path = os.path.join(dir_path, output_filename)

        if not os.path.exists(input_path):
            app.logger.error(f"Input file not found: {input_path}")
            return jsonify({'success': False, 'error': f'File not found: {filename}'}), 404
        
        # Use the kismetdb_to_kml command
        app.logger.info("Using kismetdb_to_kml command for conversion")
        
        try:
            # Run kismetdb_to_kml command
            cmd = ['kismetdb_to_kml', '--in', input_path, '--out', output_path, '--force']
            app.logger.info(f"Running command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Count devices in the output for the message
                device_count = 0
                if result.stderr:
                    # Count WARNING lines to estimate skipped devices
                    warnings = result.stderr.count('WARNING:')
                    app.logger.info(f"Conversion completed with {warnings} warnings")
                
                return jsonify({
                    'success': True,
                    'output_file': output_filename,
                    'message': 'Successfully converted to KML format'
                }), 200
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                if not error_msg:
                    error_msg = f"Command failed with exit code {result.returncode}"
                app.logger.error(f"kismetdb_to_kml error: {error_msg}")
                return jsonify({'success': False, 'error': error_msg}), 500
                
        except FileNotFoundError:
            app.logger.error("kismetdb_to_kml command not found")
            return jsonify({'success': False, 'error': 'kismetdb_to_kml command not found. Please ensure Kismet is installed.'}), 500
        except Exception as e:
            app.logger.error(f"Error running kismetdb_to_kml: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
            
    except Exception as e:
        app.logger.error(f"KML conversion error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def convert_kismet_to_kml_python(input_path, output_path, output_filename):
    """Fallback Python implementation to convert Kismet DB to KML"""
    try:
        import sqlite3
        import xml.etree.ElementTree as ET
        from xml.dom import minidom
        
        app.logger.info(f"Starting Python KML conversion for {input_path}")
        
        # Connect to the Kismet database
        conn = sqlite3.connect(input_path)
        cursor = conn.cursor()
        
        # First check if the devices table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='devices'")
        if not cursor.fetchone():
            app.logger.error("No 'devices' table found in Kismet database")
            return jsonify({'success': False, 'error': 'Invalid Kismet database: no devices table found'}), 400
        
        # First check available columns in the devices table
        cursor.execute("PRAGMA table_info(devices)")
        columns = [col[1] for col in cursor.fetchall()]
        app.logger.info(f"Available columns in devices table: {columns}")
        
        # Build query based on available columns
        base_columns = ['device', 'avg_lat', 'avg_lon', 'type', 'phyname', 'first_time', 'last_time']
        select_columns = []
        
        for col in base_columns:
            if col in columns:
                select_columns.append(col)
        
        # Add optional columns if they exist
        if 'commonname' in columns:
            select_columns.append('commonname')
        elif 'devname' in columns:
            select_columns.append('devname')
        elif 'name' in columns:
            select_columns.append('name')
            
        # Query for devices with GPS data
        query = f"""
        SELECT {', '.join(select_columns)}
        FROM devices
        WHERE avg_lat != 0 AND avg_lon != 0
        """
        
        app.logger.info(f"Using query: {query}")
        
        cursor.execute(query)
        devices = cursor.fetchall()
        
        app.logger.info(f"Found {len(devices)} devices with GPS data")
        
        if len(devices) == 0:
            conn.close()
            return jsonify({
                'success': False, 
                'error': 'No devices with GPS data found in the Kismet file'
            }), 400
        
        # Create KML structure
        kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
        document = ET.SubElement(kml, 'Document')
        
        # Add document name
        name = ET.SubElement(document, 'name')
        name.text = 'Kismet Wireless Survey'
        
        # Add description
        description = ET.SubElement(document, 'description')
        description.text = f'Converted from {os.path.basename(input_path)}'
        
        # Define styles for different device types
        styles = {
            'wifi': {'color': 'ff0080ff', 'icon': 'http://maps.google.com/mapfiles/kml/shapes/electronics.png'},
            'bluetooth': {'color': 'ff00ff00', 'icon': 'http://maps.google.com/mapfiles/kml/shapes/phone.png'},
            'other': {'color': 'ff808080', 'icon': 'http://maps.google.com/mapfiles/kml/shapes/info.png'}
        }
        
        # Add styles to document
        for style_id, style_data in styles.items():
            style = ET.SubElement(document, 'Style', id=style_id)
            icon_style = ET.SubElement(style, 'IconStyle')
            color = ET.SubElement(icon_style, 'color')
            color.text = style_data['color']
            icon = ET.SubElement(icon_style, 'Icon')
            href = ET.SubElement(icon, 'href')
            href.text = style_data['icon']
        
        # Process devices dynamically based on available columns
        for idx, device_data in enumerate(devices):
            # Create a dictionary for easier access
            device_dict = {}
            for i, col in enumerate(select_columns):
                device_dict[col] = device_data[i]
            
            device_mac = device_dict.get('device', 'Unknown')
            lat = device_dict.get('avg_lat', 0)
            lon = device_dict.get('avg_lon', 0)
            dev_type = device_dict.get('type', '')
            phy = device_dict.get('phyname', '')
            
            # Try different name columns
            common = device_dict.get('commonname') or device_dict.get('devname') or device_dict.get('name') or ''
            
            first = device_dict.get('first_time', '')
            last = device_dict.get('last_time', '')
            
            placemark = ET.SubElement(document, 'Placemark')
            
            # Set name
            pm_name = ET.SubElement(placemark, 'name')
            pm_name.text = common if common else device_mac
            
            # Set description
            pm_desc = ET.SubElement(placemark, 'description')
            desc_text = f"MAC: {device_mac}\nType: {phy if phy else 'Unknown'}"
            if first and last:
                desc_text += f"\nFirst seen: {first}\nLast seen: {last}"
            pm_desc.text = desc_text
            
            # Set style based on type
            style_url = ET.SubElement(placemark, 'styleUrl')
            if phy and 'IEEE802.11' in phy:
                style_url.text = '#wifi'
            elif phy and 'Bluetooth' in phy:
                style_url.text = '#bluetooth'
            else:
                style_url.text = '#other'
            
            # Add point
            point = ET.SubElement(placemark, 'Point')
            coordinates = ET.SubElement(point, 'coordinates')
            coordinates.text = f"{lon},{lat},0"
        
        conn.close()
        
        # Convert to pretty XML
        xml_str = ET.tostring(kml, encoding='utf-8')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8')
        
        # Write to file
        with open(output_path, 'wb') as f:
            f.write(pretty_xml)
        
        app.logger.info(f"KML file written successfully to {output_path}")
        
        return jsonify({
            'success': True,
            'output_file': output_filename,
            'message': f'Successfully converted to KML format ({len(devices)} devices with GPS data)'
        }), 200
        
    except sqlite3.Error as e:
        app.logger.error(f"SQLite error during KML conversion: {e}")
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"Python KML conversion error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Conversion failed: {str(e)}'}), 500
