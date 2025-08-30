#!/bin/bash

# Push Services Cleanup Script
# Removes orphaned push service files and stops any running services

echo "Cleaning up push services..."

# Stop all running push services
for pid_file in push_services/*.pid; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        service_name=$(basename "$pid_file" .pid)
        
        # Try to stop the service
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping service $service_name (PID: $pid)"
            kill -TERM "$pid" 2>/dev/null || true
        fi
        
        # Remove PID file
        rm -f "$pid_file"
    fi
done

# Remove orphaned script files (scripts without corresponding PID files)
for script_file in push_services/*.sh; do
    if [ -f "$script_file" ]; then
        service_name=$(basename "$script_file" .sh)
        pid_file="push_services/${service_name}.pid"
        
        if [ ! -f "$pid_file" ]; then
            echo "Removing orphaned script: $script_file"
            rm -f "$script_file"
        fi
    fi
done

echo "Cleanup complete."
echo "Active services remaining:"
ls -la push_services/*.sh 2>/dev/null || echo "No active services"