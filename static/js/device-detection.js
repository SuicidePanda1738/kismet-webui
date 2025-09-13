/**
 * Device Detection Module
 * Handles real-time detection of WiFi, Bluetooth, and SDR devices
 */
window.DeviceDetection = (function() {
    'use strict';
    
    const API_BASE = '/api/detect-devices';
    
    /**
     * Make an AJAX request to the device detection API
     * @param {string} type - Device type ('wifi', 'bluetooth', 'sdr', or 'all')
     * @returns {Promise} - Promise that resolves with device data
     */
    function makeDetectionRequest(type) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const url = `${API_BASE}?type=${encodeURIComponent(type)}`;
            
            xhr.open('GET', url, true);
            xhr.timeout = 30000; // 30 second timeout
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            resolve(response.devices);
                        } else {
                            reject(new Error(response.error || 'Device detection failed'));
                        }
                    } catch (e) {
                        reject(new Error('Invalid response format'));
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            };
            
            xhr.onerror = function() {
                reject(new Error('Network error during device detection'));
            };
            
            xhr.ontimeout = function() {
                reject(new Error('Device detection request timed out'));
            };
            
            xhr.send();
        });
    }
    
    /**
     * Detect all device types
     * @returns {Promise} - Promise that resolves with all device data
     */
    function detectAllDevices() {
        return makeDetectionRequest('all');
    }
    
    /**
     * Detect specific device type
     * @param {string} type - Device type ('wifi', 'bluetooth', or 'sdr')
     * @returns {Promise} - Promise that resolves with device data for that type
     */
    function detectDevices(type) {
        if (!['wifi', 'bluetooth', 'sdr'].includes(type)) {
            return Promise.reject(new Error('Invalid device type'));
        }
        return makeDetectionRequest(type);
    }
    
    /**
     * Test if a specific device is available
     * @param {string} deviceType - Type of device ('wifi', 'bluetooth', 'sdr')
     * @param {string} interfaceName - Interface name or device identifier
     * @returns {Promise} - Promise that resolves with availability status
     */
    function testDeviceAvailability(deviceType, interfaceName) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const url = `/api/test-device?type=${encodeURIComponent(deviceType)}&interface=${encodeURIComponent(interfaceName)}`;
            
            xhr.open('GET', url, true);
            xhr.timeout = 15000; // 15 second timeout
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (e) {
                        reject(new Error('Invalid response format'));
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            };
            
            xhr.onerror = function() {
                reject(new Error('Network error during device test'));
            };
            
            xhr.ontimeout = function() {
                reject(new Error('Device test request timed out'));
            };
            
            xhr.send();
        });
    }
    
    /**
     * Format device information for display
     * @param {Object} device - Device object
     * @param {string} type - Device type
     * @returns {string} - Formatted device description
     */
    function formatDeviceInfo(device, type) {
        switch (type) {
            case 'wifi':
                let info = device['interface'];
                if (device.mode) info += ` (${device.mode})`;
                if (device.frequency) info += ` @ ${device.frequency}`;
                return info;
                
            case 'bluetooth':
                info = device['interface'];
                if (device.address) info += ` (${device.address})`;
                if (device.name && device.name !== device['interface']) info += ` - ${device.name}`;
                return info;
                
            case 'sdr':
                info = device.device;
                if (device.manufacturer && device.model) {
                    info += ` (${device.manufacturer} ${device.model})`;
                }
                if (device.serial && device.serial !== '00000000' && device.serial !== '0') {
                    info += ` SN:${device.serial}`;
                }
                return info;
                
            default:
                return device['interface'] || device.device || 'Unknown';
        }
    }
    
    /**
     * Create a device option element for select dropdowns
     * @param {Object} device - Device object
     * @param {string} type - Device type
     * @returns {HTMLOptionElement} - Option element
     */
    function createDeviceOption(device, type) {
        const option = document.createElement('option');
        const field = type === 'sdr' ? 'device' : 'interface';
        
        option.value = device[field];
        option.textContent = formatDeviceInfo(device, type);
        option.setAttribute('data-device-type', type);
        option.setAttribute('data-device-info', JSON.stringify(device));
        
        return option;
    }
    
    /**
     * Populate a select element with detected devices
     * @param {HTMLSelectElement} selectElement - Select element to populate
     * @param {Array} devices - Array of device objects
     * @param {string} type - Device type
     * @param {boolean} keepExisting - Whether to keep existing options
     */
    function populateSelect(selectElement, devices, type, keepExisting = false) {
        if (!selectElement) return;
        
        // Store current selection
        const currentValue = selectElement.value;
        
        // Clear existing options (except first placeholder if keepExisting is true)
        const startIndex = keepExisting ? 1 : 0;
        while (selectElement.options.length > startIndex) {
            selectElement.removeChild(selectElement.lastChild);
        }
        
        // Add new options
        devices.forEach(device => {
            const option = createDeviceOption(device, type);
            selectElement.appendChild(option);
        });
        
        // Restore selection if possible
        if (currentValue) {
            const matchingOption = Array.from(selectElement.options).find(opt => opt.value === currentValue);
            if (matchingOption) {
                matchingOption.selected = true;
            }
        }
        
        // Trigger change event if value changed
        if (selectElement.value !== currentValue) {
            selectElement.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
    
    /**
     * Auto-refresh device lists in select elements
     * @param {string} selector - CSS selector for select elements to update
     * @param {string} type - Device type to detect
     * @param {number} interval - Refresh interval in milliseconds (default: 30000)
     */
    function autoRefreshSelects(selector, type, interval = 30000) {
        function refresh() {
            const selects = document.querySelectorAll(selector);
            if (selects.length > 0) {
                detectDevices(type)
                    .then(devices => {
                        selects.forEach(select => {
                            populateSelect(select, devices, type, true);
                        });
                    })
                    .catch(error => {
                        console.warn(`Auto-refresh failed for ${type} devices:`, error);
                    });
            }
        }
        
        // Initial refresh
        refresh();
        
        // Set up interval
        return setInterval(refresh, interval);
    }
    
    /**
     * Display detection results in a container element
     * @param {Object} devices - Device detection results
     * @param {HTMLElement} container - Container element to display results
     * @param {Object} options - Display options
     */
    function displayResults(devices, container, options = {}) {
        if (!container) return;
        
        const showIcons = options.showIcons !== false;
        const showCounts = options.showCounts !== false;
        
        let html = '';
        
        if (showCounts) {
            const totalDevices = (devices.wifi?.length || 0) + 
                               (devices.bluetooth?.length || 0) + 
                               (devices.sdr?.length || 0);
            html += `<div class="mb-3"><strong>Total devices detected: ${totalDevices}</strong></div>`;
        }
        
        // WiFi devices
        if (devices.wifi && devices.wifi.length > 0) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="wifi" class="me-1"></i>' : ''}WiFi Interfaces (${devices.wifi.length}):</strong>
                <ul class="mb-0 mt-1">`;
            devices.wifi.forEach(device => {
                html += `<li><code>${device['interface']}</code> - ${device.name || device.type}`;
                if (device.mode) html += ` (${device.mode})`;
                if (device.frequency) html += ` @ ${device.frequency}`;
                html += '</li>';
            });
            html += '</ul></div>';
        } else if (options.showEmpty !== false) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="wifi" class="me-1"></i>' : ''}WiFi Interfaces:</strong>
                <span class="text-muted">None detected</span>
            </div>`;
        }
        
        // Bluetooth devices
        if (devices.bluetooth && devices.bluetooth.length > 0) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="bluetooth" class="me-1"></i>' : ''}Bluetooth Interfaces (${devices.bluetooth.length}):</strong>
                <ul class="mb-0 mt-1">`;
            devices.bluetooth.forEach(device => {
                html += `<li><code>${device['interface']}</code>`;
                if (device.name && device.name !== device['interface']) html += ` - ${device.name}`;
                if (device.address) html += ` (${device.address})`;
                html += '</li>';
            });
            html += '</ul></div>';
        } else if (options.showEmpty !== false) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="bluetooth" class="me-1"></i>' : ''}Bluetooth Interfaces:</strong>
                <span class="text-muted">None detected</span>
            </div>`;
        }
        
        // SDR devices
        if (devices.sdr && devices.sdr.length > 0) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="radio" class="me-1"></i>' : ''}SDR Devices (${devices.sdr.length}):</strong>
                <ul class="mb-0 mt-1">`;
            devices.sdr.forEach(device => {
                html += `<li><code>${device.device}</code> - ${device.name}`;
                if (device.serial && device.serial !== '00000000') html += ` (SN: ${device.serial})`;
                if (device.manufacturer) html += ` (${device.manufacturer})`;
                html += '</li>';
            });
            html += '</ul></div>';
        } else if (options.showEmpty !== false) {
            html += `<div class="mb-3">
                <strong>${showIcons ? '<i data-feather="radio" class="me-1"></i>' : ''}SDR Devices:</strong>
                <span class="text-muted">None detected</span>
            </div>`;
        }
        
        if (html === '' && options.showEmpty !== false) {
            html = '<div class="text-muted">No devices detected</div>';
        }
        
        container.innerHTML = html;
        
        // Replace feather icons if they're being used
        if (showIcons && window.feather) {
            window.feather.replace();
        }
    }
    
    // Public API
    return {
        detectAllDevices: detectAllDevices,
        detectDevices: detectDevices,
        testDeviceAvailability: testDeviceAvailability,
        formatDeviceInfo: formatDeviceInfo,
        createDeviceOption: createDeviceOption,
        populateSelect: populateSelect,
        autoRefreshSelects: autoRefreshSelects,
        displayResults: displayResults
    };
})();

// Initialize device detection when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Auto-populate any existing device selects
    const wifiSelects = document.querySelectorAll('select[name*="wifi"]');
    const btSelects = document.querySelectorAll('select[name*="bt"], select[name*="bluetooth"]');
    const sdrSelects = document.querySelectorAll('select[name*="sdr"]');
    
    if (wifiSelects.length > 0) {
        DeviceDetection.detectDevices('wifi')
            .then(devices => {
                wifiSelects.forEach(select => {
                    DeviceDetection.populateSelect(select, devices, 'wifi', true);
                });
            })
            .catch(error => console.warn('Failed to detect WiFi devices:', error));
    }
    
    if (btSelects.length > 0) {
        DeviceDetection.detectDevices('bluetooth')
            .then(devices => {
                btSelects.forEach(select => {
                    DeviceDetection.populateSelect(select, devices, 'bluetooth', true);
                });
            })
            .catch(error => console.warn('Failed to detect Bluetooth devices:', error));
    }
    
    if (sdrSelects.length > 0) {
        DeviceDetection.detectDevices('sdr')
            .then(devices => {
                sdrSelects.forEach(select => {
                    DeviceDetection.populateSelect(select, devices, 'sdr', true);
                });
            })
            .catch(error => console.warn('Failed to detect SDR devices:', error));
    }
});
